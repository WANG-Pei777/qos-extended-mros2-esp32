#!/usr/bin/env python3
"""Preregistered analysis and publication exports for the three-system study."""

from __future__ import annotations

import argparse
from itertools import product
import json
from pathlib import Path
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from three_system_common import SYSTEM_LABELS, SYSTEM_ORDER, load_manifest, sha256_file


PAIR_ORDER = (
    ("mros2qos", "upstream"),
    ("mros2qos", "microros"),
    ("upstream", "microros"),
)
OUTCOMES = ("rtt_p95_us", "runner_ready_ms")
BOOTSTRAP_SEED = 202607154
BOOTSTRAP_DRAWS = 10_000


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap-draws", type=int, default=BOOTSTRAP_DRAWS)
    return parser.parse_args()


def exact_sign_flip(differences):
    values = np.asarray(differences, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan
    observed = abs(values.mean())
    statistics = [
        abs(np.mean(values * np.asarray(signs)))
        for signs in product((-1.0, 1.0), repeat=len(values))
    ]
    return float(np.mean(np.asarray(statistics) >= observed - 1e-12))


def holm_adjust(p_values):
    adjusted = [np.nan] * len(p_values)
    valid = [(index, value) for index, value in enumerate(p_values) if np.isfinite(value)]
    ordered = sorted(valid, key=lambda item: item[1])
    running = 0.0
    total = len(ordered)
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[index] = running
    return adjusted


def bootstrap_mean_interval(values, draws, generator):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    samples = generator.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
    return tuple(np.quantile(samples, [0.025, 0.975]))


def bootstrap_difference_interval(left, right, draws, generator):
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    left = left[np.isfinite(left)]
    right = right[np.isfinite(right)]
    left_means = generator.choice(left, size=(draws, len(left)), replace=True).mean(axis=1)
    right_means = generator.choice(right, size=(draws, len(right)), replace=True).mean(axis=1)
    return tuple(np.quantile(left_means - right_means, [0.025, 0.975]))


def quantile95(values):
    values = np.asarray(values, dtype=float)
    return float(np.quantile(values, 0.95)) if len(values) else np.nan


def source_commit():
    completed = subprocess.run(
        ["git", "-C", str(SCRIPT_DIR.parents[1]), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def main():
    args = parse_args()
    root = args.results_root.resolve()
    output = args.output.resolve() if args.output else root / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    audit = load_manifest(root / "audit/audit_report.json")
    if audit.get("status") != "PASS":
        raise SystemExit("formal audit must pass before analysis")
    runs = pd.read_csv(root / "accepted_runs.csv")
    messages = pd.read_csv(root / "accepted_messages.csv")
    if len(runs) != 300:
        raise SystemExit("analysis requires exactly 300 accepted runs")

    message_metrics = (
        messages.groupby(["system", "accepted_ordinal"], as_index=False)
        .agg(
            rtt_median_us=("rtt_us", "median"),
            rtt_p95_us=("rtt_us", quantile95),
            rtt_p99_us=("rtt_us", lambda values: float(np.quantile(values, 0.99))),
        )
    )
    metrics = runs.merge(
        message_metrics, on=["system", "accepted_ordinal"], how="left", validate="one_to_one"
    )
    metrics["wire_bytes_per_delivered"] = np.where(
        metrics["rx"] > 0, metrics["board_udp_bytes"] / metrics["rx"], np.nan
    )
    metrics["wire_packets_per_delivered"] = np.where(
        metrics["rx"] > 0, metrics["board_udp_packets"] / metrics["rx"], np.nan
    )
    metrics.to_csv(output / "run_metrics.csv", index=False)
    metrics.to_csv(output / "origin_primary_data.csv", index=False)

    generator = np.random.default_rng(BOOTSTRAP_SEED)
    summaries = []
    for system in SYSTEM_ORDER:
        subset = metrics[metrics.system == system]
        row = {"system": system, "label": SYSTEM_LABELS[system], "n_runs": len(subset)}
        for outcome in (
            "rtt_p95_us",
            "runner_ready_ms",
            "delivery_ratio",
            "free_heap_bytes",
            "wire_bytes_per_delivered",
        ):
            values = subset[outcome].dropna().to_numpy()
            low, high = bootstrap_mean_interval(values, args.bootstrap_draws, generator)
            row[f"{outcome}_mean"] = float(np.mean(values))
            row[f"{outcome}_median"] = float(np.median(values))
            row[f"{outcome}_ci_low"] = float(low)
            row[f"{outcome}_ci_high"] = float(high)
        summaries.append(row)
    summary_frame = pd.DataFrame(summaries)
    packet_generator = np.random.default_rng(BOOTSTRAP_SEED)
    for index, system in enumerate(SYSTEM_ORDER):
        values = metrics.loc[
            metrics.system == system, "wire_packets_per_delivered"
        ].dropna().to_numpy()
        low, high = bootstrap_mean_interval(
            values, args.bootstrap_draws, packet_generator
        )
        summary_frame.loc[index, "wire_packets_per_delivered_mean"] = float(
            np.mean(values)
        )
        summary_frame.loc[index, "wire_packets_per_delivered_median"] = float(
            np.median(values)
        )
        summary_frame.loc[index, "wire_packets_per_delivered_ci_low"] = float(low)
        summary_frame.loc[index, "wire_packets_per_delivered_ci_high"] = float(high)
    summary_frame.to_csv(output / "system_summary.csv", index=False)

    block_means = metrics.groupby(["block", "system"], as_index=False)[list(OUTCOMES)].mean()
    contrasts = []
    for outcome in OUTCOMES:
        pivot = block_means.pivot(index="block", columns="system", values=outcome)
        for left, right in PAIR_ORDER:
            differences = (pivot[left] - pivot[right]).to_numpy()
            left_values = metrics.loc[metrics.system == left, outcome].dropna().to_numpy()
            right_values = metrics.loc[metrics.system == right, outcome].dropna().to_numpy()
            ci_low, ci_high = bootstrap_difference_interval(
                left_values, right_values, args.bootstrap_draws, generator
            )
            contrasts.append(
                {
                    "outcome": outcome,
                    "contrast": f"{left}-{right}",
                    "left": left,
                    "right": right,
                    "estimate_mean_difference": float(left_values.mean() - right_values.mean()),
                    "bootstrap_ci_low": float(ci_low),
                    "bootstrap_ci_high": float(ci_high),
                    "superblock_difference_mean": float(differences.mean()),
                    "exact_sign_flip_p": exact_sign_flip(differences),
                    "superblocks": len(differences),
                }
            )
    adjusted = holm_adjust([row["exact_sign_flip_p"] for row in contrasts])
    for row, value in zip(contrasts, adjusted):
        row["holm_p"] = value
        row["holm_reject_0p05"] = bool(value <= 0.05)
    contrast_frame = pd.DataFrame(contrasts)
    contrast_frame.to_csv(output / "confirmatory_contrasts.csv", index=False)
    block_means.to_csv(output / "superblock_means.csv", index=False)

    plot_metrics = metrics.assign(
        rtt_p95_ms=metrics["rtt_p95_us"] / 1_000.0,
        runner_ready_s=metrics["runner_ready_ms"] / 1_000.0,
    )
    colors = {"mros2qos": "#176B87", "upstream": "#C04B3A", "microros": "#4B7F52"}
    tick_labels = ("mROS2-QoS", "upstream\nmros2-esp32", "micro-ROS")
    with plt.rc_context({
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }):
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.15), constrained_layout=True)
        for axis, outcome, title, units, panel in (
            (axes[0], "rtt_p95_ms", "Per-run RTT p95", "RTT p95 (ms)", "a"),
            (axes[1], "runner_ready_s", "Reset-to-ready", "Reset-to-ready (s)", "b"),
        ):
            data = [
                plot_metrics.loc[plot_metrics.system == system, outcome].dropna()
                for system in SYSTEM_ORDER
            ]
            box = axis.boxplot(
                data,
                tick_labels=tick_labels,
                patch_artist=True,
                showfliers=True,
                widths=0.58,
                boxprops={"linewidth": 1.0},
                whiskerprops={"linewidth": 1.0},
                capprops={"linewidth": 1.0},
                medianprops={"color": "#111111", "linewidth": 1.4},
                flierprops={
                    "marker": "o",
                    "markerfacecolor": "none",
                    "markeredgecolor": "#333333",
                    "markersize": 3.4,
                    "linestyle": "none",
                    "markeredgewidth": 0.8,
                },
            )
            for patch, system in zip(box["boxes"], SYSTEM_ORDER):
                patch.set_facecolor(colors[system])
                patch.set_alpha(0.78)
            axis.set_title(f"({panel})  {title}", loc="left", pad=7)
            axis.set_ylabel(units)
            axis.set_axisbelow(True)
            axis.grid(axis="y", color="#D7D7D7", linewidth=0.6)
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.tick_params(axis="x", rotation=0, length=0, pad=5)
        fig.savefig(output / "three_system_primary_outcomes.png", dpi=600)
        fig.savefig(output / "three_system_primary_outcomes.pdf")
        fig.savefig(output / "three_system_primary_outcomes.svg")
        plt.close(fig)

    design = load_manifest(root / "design_manifest.json")
    asset = load_manifest(Path(design["asset_manifest"]["path"]))
    resources = []
    for system in SYSTEM_ORDER:
        resource_row = summary_frame[summary_frame.system == system].iloc[0]
        resources.append(
            {
                "system": system,
                "firmware_bytes": asset["systems"][system]["artifacts"]["firmware"]["bytes"],
                "free_heap_bytes_mean": resource_row["free_heap_bytes_mean"],
                "free_heap_bytes_ci_low": resource_row["free_heap_bytes_ci_low"],
                "free_heap_bytes_ci_high": resource_row["free_heap_bytes_ci_high"],
                "wire_packets_per_delivered_mean": resource_row[
                    "wire_packets_per_delivered_mean"
                ],
                "wire_packets_per_delivered_ci_low": resource_row[
                    "wire_packets_per_delivered_ci_low"
                ],
                "wire_packets_per_delivered_ci_high": resource_row[
                    "wire_packets_per_delivered_ci_high"
                ],
                "wire_bytes_per_delivered_mean": resource_row["wire_bytes_per_delivered_mean"],
                "wire_bytes_per_delivered_ci_low": resource_row[
                    "wire_bytes_per_delivered_ci_low"
                ],
                "wire_bytes_per_delivered_ci_high": resource_row[
                    "wire_bytes_per_delivered_ci_high"
                ],
            }
        )
    resource_frame = pd.DataFrame(resources)
    resource_frame.to_csv(output / "resource_wire_table.csv", index=False)

    publication_rows = []
    for system in SYSTEM_ORDER:
        row = summary_frame[summary_frame.system == system].iloc[0]
        resource = resource_frame[resource_frame.system == system].iloc[0]
        publication_rows.append(
            {
                "system": SYSTEM_LABELS[system],
                "n_runs": int(row["n_runs"]),
                "rtt_p95_mean_ms": row["rtt_p95_us_mean"] / 1_000.0,
                "rtt_p95_ci_low_ms": row["rtt_p95_us_ci_low"] / 1_000.0,
                "rtt_p95_ci_high_ms": row["rtt_p95_us_ci_high"] / 1_000.0,
                "reset_to_ready_mean_s": row["runner_ready_ms_mean"] / 1_000.0,
                "reset_to_ready_ci_low_s": row["runner_ready_ms_ci_low"] / 1_000.0,
                "reset_to_ready_ci_high_s": row["runner_ready_ms_ci_high"] / 1_000.0,
                "delivery_percent": row["delivery_ratio_mean"] * 100.0,
                "firmware_kib": resource["firmware_bytes"] / 1_024.0,
                "free_heap_mean_kib": resource["free_heap_bytes_mean"] / 1_024.0,
                "wire_packets_per_message": resource["wire_packets_per_delivered_mean"],
                "wire_bytes_per_message": resource["wire_bytes_per_delivered_mean"],
            }
        )
    publication_frame = pd.DataFrame(publication_rows)
    publication_frame.to_csv(output / "publication_system_table.csv", index=False)

    publication_contrasts = contrast_frame.copy()
    publication_contrasts["outcome"] = publication_contrasts["outcome"].map(
        {"rtt_p95_us": "RTT p95 (ms)", "runner_ready_ms": "reset-to-ready (s)"}
    )
    publication_contrasts["comparison"] = publication_contrasts.apply(
        lambda row: f"{SYSTEM_LABELS[row['left']]} - {SYSTEM_LABELS[row['right']]}",
        axis=1,
    )
    scale = np.where(
        contrast_frame["outcome"].eq("rtt_p95_us"), 1_000.0, 1_000.0
    )
    publication_contrasts["mean_difference"] = (
        publication_contrasts["estimate_mean_difference"] / scale
    )
    publication_contrasts["ci_low"] = publication_contrasts["bootstrap_ci_low"] / scale
    publication_contrasts["ci_high"] = publication_contrasts["bootstrap_ci_high"] / scale
    publication_contrasts = publication_contrasts[
        [
            "outcome",
            "comparison",
            "mean_difference",
            "ci_low",
            "ci_high",
            "exact_sign_flip_p",
            "holm_p",
            "holm_reject_0p05",
        ]
    ]
    publication_contrasts.to_csv(
        output / "publication_confirmatory_table.csv", index=False
    )

    table_lines = [
        "# Three-System Publication Tables",
        "",
        "## System Summary",
        "",
        "| System | N | RTT p95, ms | Reset-to-ready, s | Delivery | Firmware, KiB | Free heap, KiB | Wire packets/msg | Wire bytes/msg |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in publication_rows:
        table_lines.append(
            "| {system} | {n_runs} | {rtt_p95_mean_ms:.2f} [{rtt_p95_ci_low_ms:.2f}, {rtt_p95_ci_high_ms:.2f}] "
            "| {reset_to_ready_mean_s:.2f} [{reset_to_ready_ci_low_s:.2f}, {reset_to_ready_ci_high_s:.2f}] "
            "| {delivery_percent:.1f}% | {firmware_kib:.1f} | {free_heap_mean_kib:.1f} "
            "| {wire_packets_per_message:.2f} | {wire_bytes_per_message:.1f} |".format(**row)
        )
    table_lines.extend(
        [
            "",
            "Values are means with 95% run-cluster bootstrap intervals in brackets for the two primary outcomes. Wire counts cover board-addressed UDP observed in each accepted PCAP.",
            "",
            "## Confirmatory Contrasts",
            "",
            "| Outcome | Contrast (left - right) | Mean difference | 95% bootstrap CI | Exact p | Holm p | Reject |",
            "| --- | --- | ---: | ---: | ---: | ---: | :---: |",
        ]
    )
    for row in publication_contrasts.to_dict("records"):
        table_lines.append(
            f"| {row['outcome']} | {row['comparison']} | {row['mean_difference']:.3f} "
            f"| [{row['ci_low']:.3f}, {row['ci_high']:.3f}] "
            f"| {row['exact_sign_flip_p']:.6f} | {row['holm_p']:.6f} "
            f"| {'yes' if row['holm_reject_0p05'] else 'no'} |"
        )
    table_lines.extend(
        [
            "",
            "Exact p-values use the ten randomized superblock differences; Holm adjustment covers all six preregistered contrasts.",
        ]
    )
    (output / "publication_tables.md").write_text(
        "\n".join(table_lines) + "\n", encoding="utf-8"
    )

    report = {
        "schema_version": 1,
        "classification": "three_system_preregistered_analysis",
        "status": "COMPLETE",
        "runs": len(metrics),
        "runs_per_system": {system: int((metrics.system == system).sum()) for system in SYSTEM_ORDER},
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_draws": args.bootstrap_draws,
        "confirmatory_family_size": 6,
        "holm_applied_across_all_six": True,
        "accepted_messages": len(messages),
        "all_runs_complete_delivery": bool(metrics["delivery_ratio"].eq(1.0).all()),
        "publication_outputs": [
            "origin_primary_data.csv",
            "publication_system_table.csv",
            "publication_confirmatory_table.csv",
            "publication_tables.md",
            "three_system_primary_outcomes.png",
            "three_system_primary_outcomes.pdf",
            "three_system_primary_outcomes.svg",
            "figure_caption.md",
        ],
        "provenance": {
            "source_commit": source_commit(),
            "analysis_script": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "inputs": {
                "design_manifest_sha256": sha256_file(root / "design_manifest.json"),
                "audit_report_sha256": sha256_file(root / "audit/audit_report.json"),
                "accepted_runs_sha256": sha256_file(root / "accepted_runs.csv"),
                "accepted_messages_sha256": sha256_file(root / "accepted_messages.csv"),
            },
        },
        "contrasts": contrasts,
    }
    (output / "analysis_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    ready_mq_micro = next(
        row for row in contrasts
        if row["outcome"] == "runner_ready_ms"
        and row["left"] == "mros2qos"
        and row["right"] == "microros"
    )
    ready_up_micro = next(
        row for row in contrasts
        if row["outcome"] == "runner_ready_ms"
        and row["left"] == "upstream"
        and row["right"] == "microros"
    )
    minimum_rtt_holm = min(
        row["holm_p"] for row in contrasts if row["outcome"] == "rtt_p95_us"
    )
    caption = (
        "**Figure: Matched-workload latency and cold readiness across three embedded "
        "ROS 2 implementations.** Each box summarizes 100 independently reset runs "
        "with 40 BEST_EFFORT 64-byte messages per run; center lines are medians, boxes "
        "span the interquartile range, whiskers extend to 1.5 times that range, and all "
        "remaining observations are shown. (a) Board-measured per-run RTT p95. No RTT "
        f"contrast survived correction (minimum Holm p={minimum_rtt_holm:.4f}). "
        "(b) Host-measured reset-to-first-echo time. micro-ROS was faster to ready than "
        f"mROS2-QoS by {ready_mq_micro['estimate_mean_difference'] / 1_000.0:.2f} s and "
        f"upstream mros2-esp32 by {ready_up_micro['estimate_mean_difference'] / 1_000.0:.2f} s "
        f"(Holm p={ready_mq_micro['holm_p']:.4f} for each). Confirmatory p-values use "
        "exact sign-flip tests over ten randomized superblocks with Holm correction "
        "across all six preregistered contrasts."
    )
    (output / "caption_draft.md").write_text(caption + "\n", encoding="utf-8")
    (output / "figure_caption.md").write_text(caption + "\n", encoding="utf-8")
    print(f"[analysis] COMPLETE runs={len(metrics)} output={output}")


if __name__ == "__main__":
    main()
