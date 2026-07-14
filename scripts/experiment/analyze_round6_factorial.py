#!/usr/bin/env python3
"""Analyze accepted Round 6 delivery and run-level RTT p95 outcomes."""

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


CELL_RE = re.compile(r"round6_d(\d+)_h(\d+)_b2h_")
DEPTHS = (5, 10, 20, 40)
HEARTBEATS = (250, 1000, 4000)
COLORS = ("#007C83", "#D1495B", "#2F5D8C", "#D99B2B")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (
        position - lower
    )


def holm_adjust(p_values):
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted = [0.0] * len(p_values)
    running = 0.0
    total = len(p_values)
    for rank, index in enumerate(order):
        running = max(running, (total - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def cell_from_condition(condition):
    match = CELL_RE.match(condition)
    if not match:
        raise ValueError(f"unrecognized Round 6 condition: {condition}")
    return int(match.group(1)), int(match.group(2))


def load_runs(results_root):
    results_root = Path(results_root)
    accepted = [
        row for row in read_csv(results_root / "acceptance_ledger.csv")
        if row["accepted"] == "1"
    ]
    raw = {}
    samples = defaultdict(list)
    conditions = sorted({row["condition"] for row in accepted})
    for condition in conditions:
        for row in read_csv(results_root / f"mros2qos_{condition}.csv"):
            raw[(condition, row["run_id"])] = row
        sample_path = results_root / f"mros2qos_{condition}_rtt_samples.csv"
        for row in read_csv(sample_path):
            samples[(condition, row["run_id"])].append(float(row["rtt_us"]))

    output = []
    for ledger_row in accepted:
        key = (ledger_row["condition"], ledger_row["run_id"])
        row = raw[key]
        values = samples[key]
        if len(values) != int(row["rtt_count"]):
            raise ValueError(f"RTT sidecar mismatch for {key}")
        depth, heartbeat = cell_from_condition(ledger_row["condition"])
        tx = int(row["tx_count"])
        rx = int(row["rx_count"])
        if tx <= 0 or not values:
            raise ValueError(f"invalid accepted outcome for {key}")
        output.append({
            "block": int(ledger_row["block"]),
            "visit": int(ledger_row["visit"]),
            "cell": ledger_row["cell"],
            "condition": ledger_row["condition"],
            "run_id": int(ledger_row["run_id"]),
            "accepted_ordinal": int(ledger_row["accepted_ordinal"]),
            "depth": depth,
            "heartbeat_ms": heartbeat,
            "tx_count": tx,
            "rx_count": rx,
            "delivery_ratio": rx / tx,
            "rtt_p95_ms": percentile(values, 0.95) / 1000.0,
            "rtt_sample_count": len(values),
            "link_ping_avg_ms": float(row["link_ping_avg_ms"]),
        })
    if len(output) != 360:
        raise ValueError(f"expected 360 accepted runs, got {len(output)}")
    return output


def contrast_specs():
    specs = []
    for high in (10, 20, 40):
        weights = {
            (depth, heartbeat): (
                1 / 3 if depth == high else -1 / 3 if depth == 5 else 0
            )
            for depth in DEPTHS for heartbeat in HEARTBEATS
        }
        specs.append((f"depth_{high}_minus_5", weights))
    for fast in (250, 1000):
        weights = {
            (depth, heartbeat): (
                1 / 4 if heartbeat == fast
                else -1 / 4 if heartbeat == 4000 else 0
            )
            for depth in DEPTHS for heartbeat in HEARTBEATS
        }
        specs.append((f"heartbeat_{fast}_minus_4000", weights))
    interaction = {(depth, heartbeat): 0 for depth in DEPTHS for heartbeat in HEARTBEATS}
    interaction[(40, 250)] = 1
    interaction[(5, 250)] = -1
    interaction[(40, 4000)] = -1
    interaction[(5, 4000)] = 1
    specs.append(("interaction_depth40_vs5_hb250_vs4000", interaction))
    return specs


def weighted_contrast(cell_values, weights):
    return sum(weights[cell] * cell_values[cell] for cell in weights)


def bootstrap_cells(runs, outcome, samples, rng):
    grouped = defaultdict(list)
    for row in runs:
        grouped[(row["depth"], row["heartbeat_ms"])].append(row[outcome])
    draws = {}
    for cell, values in grouped.items():
        array = np.asarray(values, dtype=float)
        indices = rng.integers(0, len(array), size=(samples, len(array)))
        draws[cell] = array[indices].mean(axis=1)
    return grouped, draws


def blocked_signflip_contrasts(runs, outcome, specs):
    visits = defaultdict(lambda: defaultdict(list))
    for row in runs:
        visits[row["block"]][(row["depth"], row["heartbeat_ms"])].append(
            row[outcome]
        )
    blocks = sorted(visits)
    estimates = []
    p_values = []
    for _name, weights in specs:
        block_effects = []
        for block in blocks:
            means = {
                cell: float(np.mean(values))
                for cell, values in visits[block].items()
            }
            block_effects.append(weighted_contrast(means, weights))
        observed = float(np.mean(block_effects))
        null = []
        for mask in range(1 << len(blocks)):
            signed = [
                value if mask & (1 << index) else -value
                for index, value in enumerate(block_effects)
            ]
            null.append(float(np.mean(signed)))
        p_value = sum(
            abs(value) >= abs(observed) - 1e-15 for value in null
        ) / len(null)
        estimates.append(observed)
        p_values.append(p_value)
    return estimates, p_values


def summarize(runs, bootstrap_samples, seed):
    specs = contrast_specs()
    summary_rows = []
    contrast_rows = []
    rng = np.random.default_rng(seed)
    outcomes = (
        ("delivery_ratio", "ratio"),
        ("rtt_p95_ms", "ms"),
    )
    for outcome, unit in outcomes:
        grouped, draws = bootstrap_cells(runs, outcome, bootstrap_samples, rng)
        for cell in sorted(grouped):
            values = np.asarray(grouped[cell], dtype=float)
            low, high = np.quantile(draws[cell], [0.025, 0.975])
            summary_rows.append({
                "depth": cell[0],
                "heartbeat_ms": cell[1],
                "outcome": outcome,
                "unit": unit,
                "n_runs": len(values),
                "mean": float(values.mean()),
                "ci_low": float(low),
                "ci_high": float(high),
                "median": float(np.median(values)),
                "min": float(values.min()),
                "max": float(values.max()),
            })
        estimates, p_values = blocked_signflip_contrasts(
            runs, outcome, specs
        )
        for index, (name, weights) in enumerate(specs):
            bootstrap_effect = sum(
                weights[cell] * draws[cell] for cell in weights
            )
            low, high = np.quantile(bootstrap_effect, [0.025, 0.975])
            contrast_rows.append({
                "outcome": outcome,
                "unit": unit,
                "contrast": name,
                "estimate": estimates[index],
                "ci_low": float(low),
                "ci_high": float(high),
                "randomization_p": p_values[index],
                "bootstrap_samples": bootstrap_samples,
                "randomization_assignments": 1 << 10,
                "seed": seed,
            })
    adjusted = holm_adjust([row["randomization_p"] for row in contrast_rows])
    for row, value in zip(contrast_rows, adjusted):
        row["holm_p"] = value
    return summary_rows, contrast_rows


def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_interactions(summary_rows, output_dir):
    by_key = {
        (row["outcome"], row["depth"], row["heartbeat_ms"]): row
        for row in summary_rows
    }
    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#FAFAF8",
    })
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.4), constrained_layout=True)
    panels = (
        ("rtt_p95_ms", "Run-level RTT p95 (ms)", "RTT tail"),
        ("delivery_ratio", "Delivery ratio", "Delivery"),
    )
    x = np.arange(len(HEARTBEATS))
    for axis, (outcome, ylabel, title) in zip(axes, panels):
        for depth, color in zip(DEPTHS, COLORS):
            rows = [by_key[(outcome, depth, heartbeat)] for heartbeat in HEARTBEATS]
            means = np.asarray([row["mean"] for row in rows])
            lower = means - np.asarray([row["ci_low"] for row in rows])
            upper = np.asarray([row["ci_high"] for row in rows]) - means
            axis.errorbar(
                x,
                means,
                yerr=np.vstack([lower, upper]),
                marker="o",
                linewidth=1.8,
                markersize=4.5,
                capsize=2.5,
                color=color,
                label=f"Depth {depth}",
            )
        axis.set_xticks(x, ["250", "1000", "4000"])
        axis.set_xlabel("Heartbeat period (ms)")
        axis.set_ylabel(ylabel)
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    axes[1].set_ylim(0, 1.03)
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    fig.suptitle(
        "Round 6 mechanism factorial: mean and run-bootstrap 95% CI",
        fontsize=12,
        fontweight="bold",
    )
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"round6_factorial_interactions.{suffix}", dpi=300)
    plt.close(fig)


def write_markdown(path, summary_rows, contrast_rows):
    lines = [
        "# Round 6 Factorial Summary",
        "",
        "Only rows marked accepted in `acceptance_ledger.csv` are analyzed.",
        "Cell uncertainty uses run-stratified bootstrap confidence intervals;",
        "confirmatory p-values use the exact 2^10 block sign-flip distribution",
        "and one Holm correction across all listed contrasts/outcomes.",
        "",
        "## Cell Means",
        "",
        "| Depth | Heartbeat ms | Delivery [95% CI] | RTT p95 ms [95% CI] |",
        "| ---: | ---: | ---: | ---: |",
    ]
    indexed = {
        (row["outcome"], row["depth"], row["heartbeat_ms"]): row
        for row in summary_rows
    }
    for depth in DEPTHS:
        for heartbeat in HEARTBEATS:
            delivery = indexed[("delivery_ratio", depth, heartbeat)]
            rtt = indexed[("rtt_p95_ms", depth, heartbeat)]
            lines.append(
                f"| {depth} | {heartbeat} | {delivery['mean']:.3f} "
                f"[{delivery['ci_low']:.3f}, {delivery['ci_high']:.3f}] | "
                f"{rtt['mean']:.1f} [{rtt['ci_low']:.1f}, {rtt['ci_high']:.1f}] |"
            )
    lines.extend([
        "",
        "## Confirmatory Contrasts",
        "",
        "| Outcome | Contrast | Estimate | 95% CI | Randomization p | Holm p |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for row in contrast_rows:
        lines.append(
            f"| {row['outcome']} | {row['contrast']} | {row['estimate']:.6g} | "
            f"[{row['ci_low']:.6g}, {row['ci_high']:.6g}] | "
            f"{row['randomization_p']:.6g} | {row['holm_p']:.6g} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260714)
    args = parser.parse_args()
    if args.bootstrap_samples < 1000:
        parser.error("bootstrap samples must be at least 1000")
    runs = load_runs(args.results_root)
    summary_rows, contrast_rows = summarize(
        runs,
        args.bootstrap_samples,
        args.seed,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "round6_run_outcomes.csv", runs)
    write_csv(args.output_dir / "round6_cell_summary.csv", summary_rows)
    write_csv(args.output_dir / "round6_confirmatory_contrasts.csv", contrast_rows)
    write_markdown(
        args.output_dir / "round6_factorial_summary.md",
        summary_rows,
        contrast_rows,
    )
    plot_interactions(summary_rows, args.output_dir)
    manifest = {
        "schema_version": 1,
        "classification": "round6_preregistered_factorial_analysis",
        "results_root": str(args.results_root.resolve()),
        "acceptance_ledger_sha256": sha256_file(
            args.results_root / "acceptance_ledger.csv"
        ),
        "bootstrap_samples": args.bootstrap_samples,
        "randomization_method": "exact_2^10_block_sign_flip",
        "seed": args.seed,
        "accepted_runs": len(runs),
        "holm_family_size": len(contrast_rows),
        "analysis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
    }
    (args.output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
