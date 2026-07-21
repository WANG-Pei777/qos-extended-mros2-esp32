#!/usr/bin/env python3
"""Run the frozen H2B confirmatory and per-message cluster analysis."""

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

from analyze_round6_factorial import holm_adjust, percentile, write_csv
from h2b_formal_common import (
    EXPECTED_ACCEPTED_RUNS,
    LOSS_TARGETS,
    QOS_MODES,
    read_rows,
    sha256_file,
)


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
MESSAGE_STATISTICS = ("mean", "median", "p95", "p99")


def load_runs(results_root):
    accepted = [
        row
        for row in read_rows(results_root / "acceptance_ledger.csv")
        if row["accepted"] == "1"
    ]
    raw = {}
    samples = defaultdict(list)
    for condition in sorted({row["condition"] for row in accepted}):
        for row in read_rows(results_root / f"mros2qos_{condition}.csv"):
            raw[(condition, row["run_id"])] = row
        for row in read_rows(
            results_root / f"mros2qos_{condition}_rtt_samples.csv"
        ):
            samples[(condition, row["run_id"])].append(float(row["rtt_us"]))
    runs = []
    clusters = {}
    for ledger_row in accepted:
        key = (ledger_row["condition"], ledger_row["run_id"])
        if key not in raw:
            raise ValueError(f"missing H2B raw outcome for {key}")
        row = raw[key]
        rtt = samples[key]
        if len(rtt) != int(row["rtt_count"]):
            raise ValueError(f"H2B RTT sidecar mismatch for {key}")
        tx = int(row["tx_count"])
        rx = int(row["rx_count"])
        if tx <= 0:
            raise ValueError(f"H2B nonpositive TX count for {key}")
        target = int(ledger_row["target_loss_percent"])
        run_key = (
            ledger_row["qos"],
            target,
            int(ledger_row["block"]),
            int(ledger_row["run_id"]),
        )
        clusters[run_key] = [value / 1000.0 for value in rtt]
        runs.append({
            "block": int(ledger_row["block"]),
            "visit": int(ledger_row["visit"]),
            "cell": ledger_row["cell"],
            "condition": ledger_row["condition"],
            "run_id": int(ledger_row["run_id"]),
            "accepted_ordinal": int(ledger_row["accepted_ordinal"]),
            "qos": ledger_row["qos"],
            "target_loss_percent": target,
            "effective_loss_percent": float(
                ledger_row["effective_loss_percent"]
            ),
            "tx_count": tx,
            "rx_count": rx,
            "delivery_ratio": rx / tx,
            "rtt_estimable": int(bool(rtt)),
            "rtt_median_ms": percentile(rtt, 0.50) / 1000.0 if rtt else None,
            "rtt_p95_ms": percentile(rtt, 0.95) / 1000.0 if rtt else None,
            "rtt_p99_ms": percentile(rtt, 0.99) / 1000.0 if rtt else None,
            "rtt_sample_count": len(rtt),
            "match_wait_ms": float(row["match_wait_ms"]),
            "link_ping_avg_ms": float(row["link_ping_avg_ms"]),
        })
    if len(runs) != EXPECTED_ACCEPTED_RUNS:
        raise ValueError(
            f"expected {EXPECTED_ACCEPTED_RUNS} H2B runs, got {len(runs)}"
        )
    counts = defaultdict(int)
    for row in runs:
        counts[(row["qos"], row["target_loss_percent"])] += 1
    expected = {(qos, loss) for qos in QOS_MODES for loss in LOSS_TARGETS}
    if set(counts) != expected or any(value != 30 for value in counts.values()):
        raise ValueError(f"H2B analysis cells are incomplete: {dict(counts)}")
    return runs, clusters


def bootstrap_cells(runs, outcome, samples, rng):
    grouped = defaultdict(list)
    for row in runs:
        value = row[outcome]
        if value is not None:
            grouped[(row["qos"], row["target_loss_percent"])].append(value)
    draws = {}
    for cell, values in grouped.items():
        if len(values) != 30:
            raise ValueError(
                f"confirmatory H2B outcome {outcome} is not estimable for all "
                f"30 runs in {cell}; missing values remain accepted and must be reported"
            )
        array = np.asarray(values, dtype=float)
        indices = rng.integers(0, len(array), size=(samples, len(array)))
        draws[cell] = array[indices].mean(axis=1)
    return grouped, draws


def exact_block_signflip(runs, outcome, loss):
    by_block = defaultdict(lambda: defaultdict(list))
    for row in runs:
        if row["target_loss_percent"] == loss and row[outcome] is not None:
            by_block[row["block"]][row["qos"]].append(row[outcome])
    if set(by_block) != set(range(1, 11)):
        raise ValueError(f"H2B {outcome} target {loss}: incomplete blocks")
    effects = []
    for block in sorted(by_block):
        cells = by_block[block]
        if any(len(cells[qos]) != 3 for qos in QOS_MODES):
            raise ValueError(
                f"H2B {outcome} target {loss}: unbalanced block {block}"
            )
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


def infer_run_level(runs, bootstrap_samples, seed):
    cell_rows = []
    contrast_rows = []
    outcomes = PRIMARY_OUTCOMES + SECONDARY_OUTCOMES
    for index, (outcome, unit) in enumerate(outcomes):
        grouped, draws = bootstrap_cells(
            runs,
            outcome,
            bootstrap_samples,
            np.random.default_rng(seed + index),
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
            is_primary = (outcome, unit) in PRIMARY_OUTCOMES
            contrast_rows.append({
                "outcome": outcome,
                "unit": unit,
                "contrast": f"reliable_minus_best_effort_at_target_{loss:02d}",
                "target_loss_percent": loss,
                "estimate": estimate,
                "ci_low": float(low),
                "ci_high": float(high),
                "randomization_p": p_value,
                "holm_family": "confirmatory_10" if is_primary else "secondary",
                "holm_p": "",
                "block_effect_min": min(block_effects),
                "block_effect_max": max(block_effects),
                "bootstrap_samples": bootstrap_samples,
                "randomization_assignments": 1 << 10,
                "seed": seed,
            })
    primary = [
        row for row in contrast_rows if row["holm_family"] == "confirmatory_10"
    ]
    adjusted = holm_adjust([row["randomization_p"] for row in primary])
    for row, value in zip(primary, adjusted):
        row["holm_p"] = value
    return cell_rows, contrast_rows


def message_statistics(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        raise ValueError("per-message RTT statistics require at least one sample")
    return {
        "mean": float(values.mean()),
        "median": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
        "p99": float(np.quantile(values, 0.99)),
    }


def infer_message_level(clusters, bootstrap_samples, seed):
    by_cell = defaultdict(dict)
    for (qos, loss, block, run_id), values in clusters.items():
        by_cell[(qos, loss)][(block, run_id)] = values
    rows = []
    draws_by_cell = {}
    for cell_index, cell in enumerate(
        (qos, loss) for qos in QOS_MODES for loss in LOSS_TARGETS
    ):
        cell_clusters = by_cell[cell]
        run_keys = sorted(cell_clusters)
        if len(run_keys) != 30:
            raise ValueError(f"H2B message cluster count mismatch for {cell}")
        point_values = [
            value for run_key in run_keys for value in cell_clusters[run_key]
        ]
        point = message_statistics(point_values)
        rng = np.random.default_rng(seed + 100 + cell_index)
        draws = {name: [] for name in MESSAGE_STATISTICS}
        for _ in range(bootstrap_samples):
            selected = rng.integers(0, len(run_keys), size=len(run_keys))
            values = [
                value
                for selected_index in selected
                for value in cell_clusters[run_keys[int(selected_index)]]
            ]
            stats = message_statistics(values)
            for name in MESSAGE_STATISTICS:
                draws[name].append(stats[name])
        row = {
            "qos": cell[0],
            "target_loss_percent": cell[1],
            "n_runs": len(run_keys),
            "n_messages": len(point_values),
            "bootstrap_samples": bootstrap_samples,
            "seed": seed,
        }
        for name in MESSAGE_STATISTICS:
            low, high = np.quantile(draws[name], [0.025, 0.975])
            row[f"rtt_{name}_ms"] = point[name]
            row[f"rtt_{name}_ci_low_ms"] = float(low)
            row[f"rtt_{name}_ci_high_ms"] = float(high)
        rows.append(row)
        draws_by_cell[cell] = draws
    effects = []
    by_key = {(row["qos"], row["target_loss_percent"]): row for row in rows}
    for loss in LOSS_TARGETS:
        reliable = by_key[("reliable", loss)]
        best_effort = by_key[("best_effort", loss)]
        row = {
            "target_loss_percent": loss,
            "reliable_runs": reliable["n_runs"],
            "best_effort_runs": best_effort["n_runs"],
            "bootstrap_samples": bootstrap_samples,
            "seed": seed,
        }
        for name in MESSAGE_STATISTICS:
            differences = np.asarray(
                draws_by_cell[("reliable", loss)][name]
            ) - np.asarray(draws_by_cell[("best_effort", loss)][name])
            low, high = np.quantile(differences, [0.025, 0.975])
            row[f"rtt_{name}_difference_ms"] = (
                reliable[f"rtt_{name}_ms"] - best_effort[f"rtt_{name}_ms"]
            )
            row[f"rtt_{name}_difference_ci_low_ms"] = float(low)
            row[f"rtt_{name}_difference_ci_high_ms"] = float(high)
        effects.append(row)
    return rows, effects


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
        axis.set_xticks(x, [str(value) for value in LOSS_TARGETS])
        axis.set_xlabel("Nominal host-to-board loss target (%)")
        axis.set_ylabel(ylabel)
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(axis="y", color="#D8D8D5", linewidth=0.6)
    axes[1].set_ylim(0, 1.03)
    axes[0].legend(frameon=False, loc="upper left")
    fig.suptitle(
        "H2B formal outcomes: mean and run-bootstrap 95% CI",
        fontsize=11.5,
        fontweight="bold",
    )
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"h2b_primary_outcomes.{suffix}", dpi=300)
    plt.close(fig)


def write_summary(path, cell_rows, contrast_rows, message_rows, message_effects):
    indexed = {
        (row["outcome"], row["qos"], row["target_loss_percent"]): row
        for row in cell_rows
    }
    lines = [
        "# H2B Formal Analysis",
        "",
        "Population: 300 accepted independent runs (30 per cell). The ten",
        "confirmatory contrasts use exact 2^10 block sign-flip tests and Holm",
        "correction. Per-message intervals use run-cluster bootstrap and are",
        "prespecified secondary outcomes.",
        "",
        "## Run-Level Cell Outcomes",
        "",
        "| Loss | QoS | N | Delivery mean [95% CI] | RTT p95 ms mean [95% CI] |",
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
        if row["holm_family"] != "confirmatory_10":
            continue
        lines.append(
            f"| {row['outcome']} | {row['target_loss_percent']}% | "
            f"{row['estimate']:.6g} | [{row['ci_low']:.6g}, "
            f"{row['ci_high']:.6g}] | {row['randomization_p']:.6g} | "
            f"{float(row['holm_p']):.6g} |"
        )
    message_index = {
        (row["qos"], row["target_loss_percent"]): row for row in message_rows
    }
    lines.extend([
        "",
        "## Per-Message RTT Secondary Outcomes",
        "",
        "| Loss | QoS | Runs | Messages | Median ms [95% CI] | P95 ms [95% CI] | P99 ms [95% CI] |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for loss in LOSS_TARGETS:
        for qos in QOS_MODES:
            row = message_index[(qos, loss)]
            lines.append(
                f"| {loss}% | {qos} | {row['n_runs']} | {row['n_messages']} | "
                f"{row['rtt_median_ms']:.3f} [{row['rtt_median_ci_low_ms']:.3f}, "
                f"{row['rtt_median_ci_high_ms']:.3f}] | {row['rtt_p95_ms']:.3f} "
                f"[{row['rtt_p95_ci_low_ms']:.3f}, {row['rtt_p95_ci_high_ms']:.3f}] | "
                f"{row['rtt_p99_ms']:.3f} [{row['rtt_p99_ci_low_ms']:.3f}, "
                f"{row['rtt_p99_ci_high_ms']:.3f}] |"
            )
    lines.extend([
        "",
        "Per-message RELIABLE-minus-BEST_EFFORT effects are in",
        "`h2b_message_qos_effects.csv`. They are secondary cluster-bootstrap",
        "intervals, not additional confirmatory tests. Nominal 15% is configured",
        "as 1/7 = 14.285714%. Cross-direction comparison with P4 is descriptive",
        "because direction was not randomized within one campaign.",
        "",
        f"Secondary message-effect rows: {len(message_effects)}.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=202607154)
    args = parser.parse_args()
    if args.bootstrap_samples < 1000:
        parser.error("bootstrap samples must be at least 1000")
    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS":
        raise SystemExit("H2B analysis requires a PASS formal audit")
    results_root = args.results_root.resolve()
    runs, clusters = load_runs(results_root)
    cell_rows, contrast_rows = infer_run_level(
        runs, args.bootstrap_samples, args.seed
    )
    message_rows, message_effects = infer_message_level(
        clusters, args.bootstrap_samples, args.seed
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "runs": output_dir / "h2b_run_outcomes.csv",
        "cells": output_dir / "h2b_cell_summary.csv",
        "contrasts": output_dir / "h2b_contrasts.csv",
        "messages": output_dir / "h2b_message_summary.csv",
        "message_effects": output_dir / "h2b_message_qos_effects.csv",
        "summary": output_dir / "h2b_complete_summary.md",
    }
    write_csv(output_paths["runs"], runs)
    write_csv(output_paths["cells"], cell_rows)
    write_csv(output_paths["contrasts"], contrast_rows)
    write_csv(output_paths["messages"], message_rows)
    write_csv(output_paths["message_effects"], message_effects)
    plot_primary(cell_rows, output_dir)
    write_summary(
        output_paths["summary"],
        cell_rows,
        contrast_rows,
        message_rows,
        message_effects,
    )
    manifest = {
        "schema_version": 1,
        "classification": "h2b_per_message_formal_analysis",
        "analysis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "analysis_script_sha256": sha256_file(__file__),
        "audit_report_sha256": sha256_file(args.audit_report),
        "acceptance_ledger_sha256": sha256_file(
            results_root / "acceptance_ledger.csv"
        ),
        "bootstrap_samples": args.bootstrap_samples,
        "seed": args.seed,
        "confirmatory_family": "10 H2B run-level QoS contrasts",
        "secondary_message_family": "run-cluster intervals without added tests",
        "outputs": {},
    }
    for path in list(output_paths.values()) + [
        output_dir / "h2b_primary_outcomes.png",
        output_dir / "h2b_primary_outcomes.pdf",
    ]:
        manifest["outputs"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    manifest_path = output_dir / "h2b_analysis_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[complete] H2B analysis: {manifest_path}")


if __name__ == "__main__":
    main()
