#!/usr/bin/env python3
"""Run the frozen P4 six-contrast confirmatory analysis."""

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_round6_factorial import holm_adjust, percentile, sha256_file, write_csv


QOS_MODES = ("reliable", "best_effort")
LOSS_TARGETS = (0, 5, 15)
PRIMARY_OUTCOMES = (
    ("rtt_p95_ms", "ms"),
    ("delivery_ratio", "ratio"),
)
SECONDARY_OUTCOMES = (
    ("rtt_median_ms", "ms"),
    ("rtt_p99_ms", "ms"),
    ("match_wait_ms", "ms"),
    ("link_ping_avg_ms", "ms"),
)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_runs(results_root):
    results_root = Path(results_root)
    accepted = [
        row for row in read_csv(results_root / "acceptance_ledger.csv")
        if row["accepted"] == "1"
    ]
    raw = {}
    samples = defaultdict(list)
    for condition in sorted({row["condition"] for row in accepted}):
        for row in read_csv(results_root / f"mros2qos_{condition}.csv"):
            raw[(condition, row["run_id"])] = row
        for row in read_csv(
            results_root / f"mros2qos_{condition}_rtt_samples.csv"
        ):
            samples[(condition, row["run_id"])].append(float(row["rtt_us"]))
    output = []
    for ledger_row in accepted:
        key = (ledger_row["condition"], ledger_row["run_id"])
        if key not in raw:
            raise ValueError(f"missing raw outcome for {key}")
        row = raw[key]
        rtt = samples[key]
        if len(rtt) != int(row["rtt_count"]):
            raise ValueError(f"RTT sidecar mismatch for {key}")
        tx = int(row["tx_count"])
        rx = int(row["rx_count"])
        if tx <= 0:
            raise ValueError(f"nonpositive TX count for {key}")
        if not rtt:
            raise ValueError(
                f"primary RTT p95 is not estimable for accepted run {key}"
            )
        output.append({
            "block": int(ledger_row["block"]),
            "visit": int(ledger_row["visit"]),
            "cell": ledger_row["cell"],
            "condition": ledger_row["condition"],
            "run_id": int(ledger_row["run_id"]),
            "accepted_ordinal": int(ledger_row["accepted_ordinal"]),
            "qos": ledger_row["qos"],
            "target_loss_percent": int(ledger_row["target_loss_percent"]),
            "effective_loss_percent": float(
                ledger_row["effective_loss_percent"]
            ),
            "tx_count": tx,
            "rx_count": rx,
            "delivery_ratio": rx / tx,
            "rtt_median_ms": percentile(rtt, 0.50) / 1000.0,
            "rtt_p95_ms": percentile(rtt, 0.95) / 1000.0,
            "rtt_p99_ms": percentile(rtt, 0.99) / 1000.0,
            "rtt_sample_count": len(rtt),
            "match_wait_ms": float(row["match_wait_ms"]),
            "link_ping_avg_ms": float(row["link_ping_avg_ms"]),
        })
    if len(output) != 180:
        raise ValueError(f"expected 180 accepted runs, got {len(output)}")
    counts = defaultdict(int)
    for row in output:
        counts[(row["qos"], row["target_loss_percent"])] += 1
    if set(counts) != {
        (qos, loss) for qos in QOS_MODES for loss in LOSS_TARGETS
    } or any(value != 30 for value in counts.values()):
        raise ValueError(f"P4 analysis cells are incomplete: {dict(counts)}")
    return output


def bootstrap_cells(runs, outcome, samples, rng):
    grouped = defaultdict(list)
    for row in runs:
        grouped[(row["qos"], row["target_loss_percent"])].append(
            row[outcome]
        )
    draws = {}
    for cell, values in grouped.items():
        array = np.asarray(values, dtype=float)
        indices = rng.integers(0, len(array), size=(samples, len(array)))
        draws[cell] = array[indices].mean(axis=1)
    return grouped, draws


def exact_block_signflip(runs, outcome, loss):
    by_block = defaultdict(lambda: defaultdict(list))
    for row in runs:
        if row["target_loss_percent"] == loss:
            by_block[row["block"]][row["qos"]].append(row[outcome])
    if set(by_block) != set(range(1, 11)):
        raise ValueError(f"outcome {outcome} loss {loss}: incomplete blocks")
    effects = []
    for block in sorted(by_block):
        cells = by_block[block]
        if any(len(cells[qos]) != 3 for qos in QOS_MODES):
            raise ValueError(f"outcome {outcome} loss {loss}: unbalanced block {block}")
        effects.append(
            float(np.mean(cells["reliable"]))
            - float(np.mean(cells["best_effort"]))
        )
    observed = float(np.mean(effects))
    null = []
    for mask in range(1 << len(effects)):
        signed = [
            value if mask & (1 << index) else -value
            for index, value in enumerate(effects)
        ]
        null.append(float(np.mean(signed)))
    p_value = sum(
        abs(value) >= abs(observed) - 1e-15 for value in null
    ) / len(null)
    return observed, p_value, effects


def infer(runs, bootstrap_samples, seed):
    cell_rows = []
    contrast_rows = []
    outcomes = PRIMARY_OUTCOMES + SECONDARY_OUTCOMES
    for outcome_index, (outcome, unit) in enumerate(outcomes):
        grouped, draws = bootstrap_cells(
            runs,
            outcome,
            bootstrap_samples,
            np.random.default_rng(seed + outcome_index),
        )
        for qos in QOS_MODES:
            for loss in LOSS_TARGETS:
                values = np.asarray(grouped[(qos, loss)], dtype=float)
                low, high = np.quantile(draws[(qos, loss)], [0.025, 0.975])
                cell_rows.append({
                    "qos": qos,
                    "target_loss_percent": loss,
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
        for loss in LOSS_TARGETS:
            estimate, p_value, block_effects = exact_block_signflip(
                runs, outcome, loss
            )
            effect_draws = (
                draws[("reliable", loss)]
                - draws[("best_effort", loss)]
            )
            low, high = np.quantile(effect_draws, [0.025, 0.975])
            contrast_rows.append({
                "outcome": outcome,
                "unit": unit,
                "contrast": (
                    f"reliable_minus_best_effort_at_target_{loss:02d}"
                ),
                "target_loss_percent": loss,
                "estimate": estimate,
                "ci_low": float(low),
                "ci_high": float(high),
                "randomization_p": p_value,
                "holm_family": (
                    "confirmatory_6"
                    if (outcome, unit) in PRIMARY_OUTCOMES
                    else "secondary_not_adjusted"
                ),
                "holm_p": "",
                "block_effect_min": min(block_effects),
                "block_effect_max": max(block_effects),
                "bootstrap_samples": bootstrap_samples,
                "randomization_assignments": 1 << 10,
                "seed": seed,
            })
    primary = [
        row for row in contrast_rows
        if row["holm_family"] == "confirmatory_6"
    ]
    adjusted = holm_adjust([row["randomization_p"] for row in primary])
    for row, value in zip(primary, adjusted):
        row["holm_p"] = value
    return cell_rows, contrast_rows


def primary_conclusions(contrast_rows):
    indexed = {
        (row["outcome"], row["target_loss_percent"]): row
        for row in contrast_rows
        if row["holm_family"] == "confirmatory_6"
    }
    rtt5 = indexed[("rtt_p95_ms", 5)]
    rtt15 = indexed[("rtt_p95_ms", 15)]
    delivery15 = indexed[("delivery_ratio", 15)]
    rtt0 = indexed[("rtt_p95_ms", 0)]
    r1 = (
        rtt5["estimate"] > 0
        and rtt15["estimate"] > 0
        and rtt15["ci_low"] > 0
    )
    return {
        "replication_success": r1,
        "r1_same_positive_direction_at_5_and_15": (
            rtt5["estimate"] > 0 and rtt15["estimate"] > 0
        ),
        "r1_15pct_ci_excludes_zero_positive": rtt15["ci_low"] > 0,
        "r2_15pct_delivery_reliable_minus_best_effort_le_zero": (
            delivery15["estimate"] <= 0
        ),
        "r3_absolute_rtt_effect_at_0_smaller_than_15": (
            abs(rtt0["estimate"]) < abs(rtt15["estimate"])
        ),
        "r3_absolute_rtt_effect_ratio_0_over_15": (
            abs(rtt0["estimate"]) / abs(rtt15["estimate"])
            if rtt15["estimate"] else None
        ),
    }


def plot_primary(cell_rows, output_dir):
    indexed = {
        (row["outcome"], row["qos"], row["target_loss_percent"]): row
        for row in cell_rows
    }
    colors = {"reliable": "#176B75", "best_effort": "#C64B32"}
    labels = {"reliable": "RELIABLE", "best_effort": "BEST_EFFORT"}
    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 10.5,
        "axes.labelsize": 9.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#FAFAF8",
    })
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.35), constrained_layout=True)
    panels = (
        ("rtt_p95_ms", "Run-level RTT p95 (ms)", "A  RTT tail"),
        ("delivery_ratio", "Delivery ratio", "B  Delivery"),
    )
    x = np.arange(len(LOSS_TARGETS))
    for axis, (outcome, ylabel, title) in zip(axes, panels):
        for qos in QOS_MODES:
            rows = [indexed[(outcome, qos, loss)] for loss in LOSS_TARGETS]
            means = np.asarray([row["mean"] for row in rows])
            low = means - np.asarray([row["ci_low"] for row in rows])
            high = np.asarray([row["ci_high"] for row in rows]) - means
            axis.errorbar(
                x,
                means,
                yerr=np.vstack([low, high]),
                color=colors[qos],
                marker="o",
                markersize=5,
                linewidth=1.7,
                capsize=2.5,
                label=labels[qos],
            )
        axis.set_xticks(x, ["0", "5", "15"])
        axis.set_xlabel("Nominal board-to-host loss target (%)")
        axis.set_ylabel(ylabel)
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(axis="y", color="#D8D8D5", linewidth=0.6)
    axes[1].set_ylim(0, 1.03)
    axes[0].legend(frameon=False, loc="upper left")
    fig.suptitle(
        "P4 independent-window replication: mean and run-bootstrap 95% CI",
        fontsize=11.5,
        fontweight="bold",
    )
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"p4_primary_outcomes.{suffix}", dpi=300)
    plt.close(fig)


def write_markdown(path, cell_rows, contrast_rows, conclusions):
    indexed = {
        (row["outcome"], row["qos"], row["target_loss_percent"]): row
        for row in cell_rows
    }
    lines = [
        "# P4 Independent-Window Confirmatory Analysis",
        "",
        "Population: 180 accepted independent runs (30 per cell). Cell",
        "intervals use run-stratified bootstrap with 10,000 draws. Exact",
        "randomization p-values use all 2^10 block sign assignments. Holm",
        "correction covers the six pre-registered primary contrasts.",
        "",
        "## Cell Outcomes",
        "",
        "| Loss target | QoS | N | Delivery mean [95% CI] | RTT p95 ms mean [95% CI] |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for loss in LOSS_TARGETS:
        for qos in QOS_MODES:
            delivery = indexed[("delivery_ratio", qos, loss)]
            rtt = indexed[("rtt_p95_ms", qos, loss)]
            lines.append(
                f"| {loss}% | {qos} | {delivery['n_runs']} | "
                f"{delivery['mean']:.4f} [{delivery['ci_low']:.4f}, "
                f"{delivery['ci_high']:.4f}] | {rtt['mean']:.2f} "
                f"[{rtt['ci_low']:.2f}, {rtt['ci_high']:.2f}] |"
            )
    lines.extend([
        "",
        "## Confirmatory Contrasts",
        "",
        "All effects are RELIABLE minus BEST_EFFORT.",
        "",
        "| Outcome | Loss | Estimate | 95% CI | Exact p | Holm p |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in contrast_rows:
        if row["holm_family"] != "confirmatory_6":
            continue
        lines.append(
            f"| {row['outcome']} | {row['target_loss_percent']}% | "
            f"{row['estimate']:.6g} | [{row['ci_low']:.6g}, "
            f"{row['ci_high']:.6g}] | {row['randomization_p']:.6g} | "
            f"{float(row['holm_p']):.6g} |"
        )
    lines.extend([
        "",
        "## Pre-Registered Conclusions",
        "",
        f"- Replication success (R1 rule): **{conclusions['replication_success']}**.",
        "- R2 directional check, RELIABLE delivery minus BEST_EFFORT at 15% "
        f"is <= 0: **{conclusions['r2_15pct_delivery_reliable_minus_best_effort_le_zero']}**.",
        "- R3 descriptive check, absolute 0% RTT effect is smaller than 15%: "
        f"**{conclusions['r3_absolute_rtt_effect_at_0_smaller_than_15']}**.",
        "",
        "The 15% label is nominal; the configured gact probability is 1/7",
        "(14.285714%). P4 supports same-hardware temporal/network-window",
        "replication only, not cross-device or cross-site generalization.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()
    if args.bootstrap_samples < 1000:
        parser.error("bootstrap samples must be at least 1000")
    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS":
        raise SystemExit("P4 analysis requires a PASS formal audit")
    runs = load_runs(args.results_root)
    cell_rows, contrast_rows = infer(
        runs, args.bootstrap_samples, args.seed
    )
    conclusions = primary_conclusions(contrast_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_path = args.output_dir / "p4_run_outcomes.csv"
    cell_path = args.output_dir / "p4_cell_summary.csv"
    contrast_path = args.output_dir / "p4_contrasts.csv"
    conclusion_path = args.output_dir / "p4_conclusions.json"
    write_csv(run_path, runs)
    write_csv(cell_path, cell_rows)
    write_csv(contrast_path, contrast_rows)
    conclusion_path.write_text(
        json.dumps(conclusions, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    plot_primary(cell_rows, args.output_dir)
    write_markdown(
        args.output_dir / "p4_complete_summary.md",
        cell_rows,
        contrast_rows,
        conclusions,
    )
    manifest = {
        "schema_version": 1,
        "classification": "p4_confirmatory_analysis",
        "analysis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "audit_report_sha256": sha256_file(args.audit_report),
        "acceptance_ledger_sha256": sha256_file(
            args.results_root / "acceptance_ledger.csv"
        ),
        "run_outcomes_sha256": sha256_file(run_path),
        "cell_summary_sha256": sha256_file(cell_path),
        "contrasts_sha256": sha256_file(contrast_path),
        "conclusions_sha256": sha256_file(conclusion_path),
        "accepted_runs": len(runs),
        "bootstrap_samples": args.bootstrap_samples,
        "randomization_method": "exact_2^10_block_sign_flip_two_sided",
        "confirmatory_holm_family_size": 6,
        "seed": args.seed,
    }
    (args.output_dir / "p4_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
