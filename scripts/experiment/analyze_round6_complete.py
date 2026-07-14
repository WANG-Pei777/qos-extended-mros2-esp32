#!/usr/bin/env python3
"""Combine Round 6 application and wire outcomes into final inference."""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_round6_factorial import (
    COLORS,
    DEPTHS,
    HEARTBEATS,
    blocked_signflip_contrasts,
    bootstrap_cells,
    contrast_specs,
    holm_adjust,
    sha256_file,
    write_csv,
)


OUTCOMES = (
    ("delivery_ratio", "ratio"),
    ("rtt_p95_ms", "ms"),
    ("wire_prior_and_post_nack_data", "indicator"),
    ("wire_unresolved_unique_sequences_all", "count"),
)
SENSITIVITY_OUTCOME = (
    "wire_unresolved_unique_sequences_uncensored",
    "count",
)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def merge_runs(factorial_path, wire_path):
    factorial = read_csv(factorial_path)
    wire = read_csv(wire_path)
    wire_by_key = {
        (row["condition"], row["run_id"]): row for row in wire
    }
    if len(wire_by_key) != len(wire):
        raise ValueError("wire outcomes contain duplicate run keys")
    merged = []
    for row in factorial:
        key = (row["condition"], row["run_id"])
        if key not in wire_by_key:
            raise ValueError(f"missing wire outcome for {key}")
        wire_row = wire_by_key[key]
        if row["cell"] != wire_row["cell"]:
            raise ValueError(f"cell mismatch for {key}")
        combined = {
            field: int(row[field])
            for field in (
                "block",
                "visit",
                "run_id",
                "accepted_ordinal",
                "depth",
                "heartbeat_ms",
                "tx_count",
                "rx_count",
                "rtt_sample_count",
            )
        }
        combined.update({
            "cell": row["cell"],
            "condition": row["condition"],
            "delivery_ratio": float(row["delivery_ratio"]),
            "rtt_p95_ms": float(row["rtt_p95_ms"]),
            "link_ping_avg_ms": float(row["link_ping_avg_ms"]),
        })
        for field in (
            "wire_prior_and_post_nack_data",
            "wire_requested_unique_sequences",
            "wire_unresolved_unique_sequences_all",
            "wire_requested_unique_sequences_uncensored",
            "wire_unresolved_unique_sequences_uncensored",
            "wire_right_censored_request_observations",
            "wire_acknack_observations",
            "wire_data_duplicate_observations",
            "wire_heartbeat_observations",
        ):
            combined[field] = int(wire_row[field])
        for field in (
            "wire_nack_to_data_median_ms",
            "wire_heartbeat_interval_median_ms",
        ):
            combined[field] = (
                float(wire_row[field]) if wire_row[field] else ""
            )
        merged.append(combined)
    if len(merged) != 360 or len(wire) != 360:
        raise ValueError(
            f"expected 360 factorial and wire runs, got {len(merged)} and {len(wire)}"
        )
    return merged


def infer(runs, bootstrap_samples, seed):
    specs = contrast_specs()
    cell_rows = []
    contrast_rows = []
    all_outcomes = OUTCOMES + (SENSITIVITY_OUTCOME,)
    for outcome_index, (outcome, unit) in enumerate(all_outcomes):
        grouped, draws = bootstrap_cells(
            runs,
            outcome,
            bootstrap_samples,
            np.random.default_rng(seed + outcome_index),
        )
        for cell in sorted(grouped):
            values = np.asarray(grouped[cell], dtype=float)
            low, high = np.quantile(draws[cell], [0.025, 0.975])
            cell_rows.append({
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
            effect_draws = sum(
                weights[cell] * draws[cell] for cell in weights
            )
            low, high = np.quantile(effect_draws, [0.025, 0.975])
            contrast_rows.append({
                "outcome": outcome,
                "unit": unit,
                "contrast": name,
                "estimate": estimates[index],
                "ci_low": float(low),
                "ci_high": float(high),
                "randomization_p": p_values[index],
                "holm_family": (
                    "primary_24" if (outcome, unit) in OUTCOMES
                    else "sensitivity_not_in_primary_family"
                ),
                "holm_p": "",
                "bootstrap_samples": bootstrap_samples,
                "randomization_assignments": 1 << 10,
                "seed": seed,
            })
    primary = [row for row in contrast_rows if row["holm_family"] == "primary_24"]
    adjusted = holm_adjust([row["randomization_p"] for row in primary])
    for row, value in zip(primary, adjusted):
        row["holm_p"] = value
    return cell_rows, contrast_rows


def plot_complete(cell_rows, runs, output_dir):
    indexed = {
        (row["outcome"], row["depth"], row["heartbeat_ms"]): row
        for row in cell_rows
    }
    plt.rcParams.update({
        "font.size": 8.5,
        "axes.titlesize": 10.5,
        "axes.labelsize": 9.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#FAFAF8",
    })
    fig, axes = plt.subplots(2, 2, figsize=(8.2, 6.2), constrained_layout=True)
    panels = (
        ("rtt_p95_ms", "Run-level RTT p95 (ms)", "A  RTT tail"),
        ("delivery_ratio", "Delivery ratio", "B  Delivery"),
        (
            "wire_unresolved_unique_sequences_all",
            "Unresolved requested sequences",
            "C  Unresolved repair requests",
        ),
        (
            "wire_prior_and_post_nack_data",
            "Run proportion",
            "D  DATA before and after NACK",
        ),
    )
    x = np.arange(len(HEARTBEATS))
    for axis, (outcome, ylabel, title) in zip(axes.flat, panels):
        for depth, color in zip(DEPTHS, COLORS):
            selected = [indexed[(outcome, depth, hb)] for hb in HEARTBEATS]
            means = np.asarray([row["mean"] for row in selected])
            low = means - np.asarray([row["ci_low"] for row in selected])
            high = np.asarray([row["ci_high"] for row in selected]) - means
            axis.errorbar(
                x,
                means,
                yerr=np.vstack([low, high]),
                color=color,
                marker="o",
                markersize=4,
                linewidth=1.6,
                capsize=2.3,
                label=f"Depth {depth}",
            )
        axis.set_xticks(x, ["250", "1000", "4000"])
        axis.set_xlabel("Heartbeat period (ms)")
        axis.set_ylabel(ylabel)
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    axes[0, 1].set_ylim(0, 1.03)
    axes[1, 1].set_ylim(0.90, 1.01)
    axes[0, 0].legend(frameon=False, ncol=2, loc="upper left")
    fig.suptitle(
        "Round 6 repair mechanism outcomes: mean and run-bootstrap 95% CI",
        fontsize=12,
        fontweight="bold",
    )
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"round6_complete_outcomes.{suffix}", dpi=300)
    plt.close(fig)

    heartbeat_rows = []
    for depth in DEPTHS:
        for heartbeat in HEARTBEATS:
            values = [
                row["wire_heartbeat_interval_median_ms"]
                for row in runs
                if row["depth"] == depth
                and row["heartbeat_ms"] == heartbeat
                and row["wire_heartbeat_interval_median_ms"] != ""
            ]
            heartbeat_rows.append({
                "depth": depth,
                "heartbeat_ms": heartbeat,
                "n_runs": len(values),
                "observed_median_ms": float(np.median(values)),
                "observed_min_ms": float(np.min(values)),
                "observed_max_ms": float(np.max(values)),
            })
    return heartbeat_rows


def write_markdown(path, cell_rows, contrasts, heartbeat_rows):
    indexed = {
        (row["outcome"], row["depth"], row["heartbeat_ms"]): row
        for row in cell_rows
    }
    lines = [
        "# Round 6 Complete Confirmatory Analysis",
        "",
        "Population: 360 accepted independent runs (30 per cell). One",
        "instrumentation-interrupted run is retained but excluded by the acceptance",
        "ledger. Cell intervals use run-stratified bootstrap (10,000 draws).",
        "Randomization p-values use the exact 2^10 block sign-flip distribution.",
        "Holm correction covers 24 contrasts: six prespecified contrasts across",
        "four primary outcomes. The right-censoring variant is sensitivity-only.",
        "",
        "## Cell Outcomes",
        "",
        "| Depth | HB ms | Delivery | RTT p95 ms | Strong wire evidence | "
        "Unresolved requests |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for depth in DEPTHS:
        for heartbeat in HEARTBEATS:
            values = [
                indexed[(outcome, depth, heartbeat)]["mean"]
                for outcome, _unit in OUTCOMES
            ]
            lines.append(
                f"| {depth} | {heartbeat} | {values[0]:.3f} | "
                f"{values[1]:.1f} | {values[2]:.3f} | {values[3]:.3f} |"
            )
    lines.extend([
        "",
        "## Primary Contrasts",
        "",
        "| Outcome | Contrast | Estimate | 95% CI | Randomization p | Holm p |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for row in contrasts:
        if row["holm_family"] != "primary_24":
            continue
        lines.append(
            f"| {row['outcome']} | {row['contrast']} | {row['estimate']:.6g} | "
            f"[{row['ci_low']:.6g}, {row['ci_high']:.6g}] | "
            f"{row['randomization_p']:.6g} | {float(row['holm_p']):.6g} |"
        )
    lines.extend([
        "",
        "## Manipulation Check",
        "",
        "Observed board-writer heartbeat intervals track the three configured",
        "levels. Full min/median/max values are in `round6_heartbeat_check.csv`.",
        "",
        "Ingress PCAPs may observe DATA before `tc` drops it. Wire-level",
        "before/after-NACK evidence is not application-delivery proof.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorial-runs", type=Path, required=True)
    parser.add_argument("--wire-runs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260714)
    args = parser.parse_args()
    if args.bootstrap_samples < 1000:
        parser.error("bootstrap samples must be at least 1000")
    runs = merge_runs(args.factorial_runs, args.wire_runs)
    cell_rows, contrasts = infer(runs, args.bootstrap_samples, args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    merged_path = args.output_dir / "round6_complete_run_outcomes.csv"
    cell_path = args.output_dir / "round6_complete_cell_summary.csv"
    contrast_path = args.output_dir / "round6_complete_contrasts.csv"
    write_csv(merged_path, runs)
    write_csv(cell_path, cell_rows)
    write_csv(contrast_path, contrasts)
    heartbeat_rows = plot_complete(cell_rows, runs, args.output_dir)
    heartbeat_path = args.output_dir / "round6_heartbeat_check.csv"
    write_csv(heartbeat_path, heartbeat_rows)
    write_markdown(
        args.output_dir / "round6_complete_summary.md",
        cell_rows,
        contrasts,
        heartbeat_rows,
    )
    manifest = {
        "schema_version": 1,
        "classification": "round6_complete_confirmatory_analysis",
        "analysis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "factorial_runs_sha256": sha256_file(args.factorial_runs),
        "wire_runs_sha256": sha256_file(args.wire_runs),
        "merged_runs_sha256": sha256_file(merged_path),
        "cell_summary_sha256": sha256_file(cell_path),
        "contrasts_sha256": sha256_file(contrast_path),
        "heartbeat_check_sha256": sha256_file(heartbeat_path),
        "accepted_runs": len(runs),
        "bootstrap_samples": args.bootstrap_samples,
        "randomization_method": "exact_2^10_block_sign_flip",
        "primary_holm_family_size": 24,
        "seed": args.seed,
    }
    (args.output_dir / "complete_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
