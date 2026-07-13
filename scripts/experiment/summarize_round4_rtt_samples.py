#!/usr/bin/env python3
"""Summarize per-message ROUND4 RTT sidecars with run-cluster bootstrap CIs."""

import argparse
import csv
import math
from pathlib import Path
import random
import re
import statistics


CONDITION_RE = re.compile(
    r"^round4_transport_(reliable|best_effort)_(\d+)pct"
    r"(?:_(host_to_board|board_to_host))?$"
)
REQUIRED_COLUMNS = {"run_id", "condition", "qos_mode", "rtt_us"}
BOOTSTRAP_STATISTICS = ("mean", "median", "p95", "p99")


def percentile(values, fraction):
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] if lower == upper else (
        values[lower] + (values[upper] - values[lower]) * (position - lower)
    )


def rtt_statistics(values):
    ordered = sorted(values)
    return {
        "mean": statistics.mean(ordered),
        "median": statistics.median(ordered),
        "p95": percentile(ordered, 0.95),
        "p99": percentile(ordered, 0.99),
        "max": ordered[-1],
    }


def bootstrap_interval(estimates):
    ordered = sorted(estimates)
    return percentile(ordered, 0.025), percentile(ordered, 0.975)


def cluster_bootstrap(clusters, samples, rng):
    """Resample runs, preserving all messages within each selected run."""
    run_ids = sorted(clusters)
    draws = {name: [] for name in BOOTSTRAP_STATISTICS}
    for _ in range(samples):
        resampled = []
        for _ in run_ids:
            run_id = run_ids[rng.randrange(len(run_ids))]
            resampled.extend(clusters[run_id])
        estimates = rtt_statistics(resampled)
        for name in BOOTSTRAP_STATISTICS:
            draws[name].append(estimates[name])
    return draws


def read_samples(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("contains no per-message RTT samples")
    missing = REQUIRED_COLUMNS.difference(rows[0])
    if missing:
        raise ValueError(f"missing required columns: {', '.join(sorted(missing))}")
    condition = rows[0]["condition"]
    match = CONDITION_RE.fullmatch(condition)
    if match is None:
        raise ValueError(f"unexpected condition {condition!r}")
    if any(row["condition"] != condition for row in rows):
        raise ValueError("contains multiple conditions")
    if any(not row["run_id"] for row in rows):
        raise ValueError("contains an empty run_id")
    qos = match.group(1)
    if any(row["qos_mode"] != qos for row in rows):
        raise ValueError("qos_mode does not match condition")
    rtt_values = [float(row["rtt_us"]) for row in rows]
    if any(not math.isfinite(value) or value <= 0 for value in rtt_values):
        raise ValueError("rtt_us must contain finite positive values")
    return qos, int(match.group(2)), match.group(3) or "host_to_board", rows


def summarize(path, qos, loss_pct, direction, rows, samples, seed):
    clusters = {}
    for row in rows:
        clusters.setdefault(row["run_id"], []).append(float(row["rtt_us"]) / 1000.0)
    values = [value for run_values in clusters.values() for value in run_values]
    point = rtt_statistics(values)
    rng = random.Random(f"{seed}:{direction}:{loss_pct}:{qos}")
    draws = cluster_bootstrap(clusters, samples, rng)
    intervals = {name: bootstrap_interval(draws[name]) for name in BOOTSTRAP_STATISTICS}
    summary = {
        "source_csv": str(path),
        "direction": direction,
        "qos": qos,
        "loss_pct": loss_pct,
        "run_count_with_samples": len(clusters),
        "sample_count": len(values),
        "bootstrap_resamples": samples,
        "bootstrap_seed": seed,
        "rtt_message_mean_ms": point["mean"],
        "rtt_message_mean_ci_low_ms": intervals["mean"][0],
        "rtt_message_mean_ci_high_ms": intervals["mean"][1],
        "rtt_message_median_ms": point["median"],
        "rtt_message_median_ci_low_ms": intervals["median"][0],
        "rtt_message_median_ci_high_ms": intervals["median"][1],
        "rtt_message_p95_ms": point["p95"],
        "rtt_message_p95_ci_low_ms": intervals["p95"][0],
        "rtt_message_p95_ci_high_ms": intervals["p95"][1],
        "rtt_message_p99_ms": point["p99"],
        "rtt_message_p99_ci_low_ms": intervals["p99"][0],
        "rtt_message_p99_ci_high_ms": intervals["p99"][1],
        "rtt_message_max_ms": point["max"],
    }
    return summary, draws


def effect_rows(summaries, bootstrap_draws):
    by_key = {
        (row["direction"], row["qos"], row["loss_pct"]): row
        for row in summaries
    }
    effects = []
    for direction in sorted({key[0] for key in by_key}):
        losses = sorted({key[2] for key in by_key if key[0] == direction})
        for loss_pct in losses:
            reliable_key = (direction, "reliable", loss_pct)
            best_effort_key = (direction, "best_effort", loss_pct)
            if reliable_key not in by_key or best_effort_key not in by_key:
                continue
            reliable = by_key[reliable_key]
            best_effort = by_key[best_effort_key]
            row = {
                "direction": direction,
                "loss_pct": loss_pct,
                "reliable_run_count": reliable["run_count_with_samples"],
                "best_effort_run_count": best_effort["run_count_with_samples"],
                "bootstrap_resamples": reliable["bootstrap_resamples"],
                "bootstrap_seed": reliable["bootstrap_seed"],
            }
            for name in BOOTSTRAP_STATISTICS:
                reliable_draws = bootstrap_draws[reliable_key][name]
                best_effort_draws = bootstrap_draws[best_effort_key][name]
                differences = [
                    left - right
                    for left, right in zip(reliable_draws, best_effort_draws)
                ]
                low, high = bootstrap_interval(differences)
                prefix = f"rtt_message_{name}_difference"
                row[f"{prefix}_ms"] = (
                    reliable[f"rtt_message_{name}_ms"]
                    - best_effort[f"rtt_message_{name}_ms"]
                )
                row[f"{prefix}_ci_low_ms"] = low
                row[f"{prefix}_ci_high_ms"] = high
            effects.append(row)
    return effects


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def formatted_ci(row, name):
    return (
        f"{row[f'rtt_message_{name}_ms']:.3f} "
        f"[{row[f'rtt_message_{name}_ci_low_ms']:.3f}, "
        f"{row[f'rtt_message_{name}_ci_high_ms']:.3f}]"
    )


def formatted_effect_ci(row, name):
    prefix = f"rtt_message_{name}_difference"
    return (
        f"{row[f'{prefix}_ms']:.3f} "
        f"[{row[f'{prefix}_ci_low_ms']:.3f}, "
        f"{row[f'{prefix}_ci_high_ms']:.3f}]"
    )


def write_markdown(path, rows, effects, samples, seed):
    lines = [
        "# ROUND4 Per-Message RTT Summary",
        "",
        "This summary is computed from `_rtt_samples.csv` sidecars emitted by",
        "`run_matrix.sh` when firmware prints `RTT_SAMPLE` lines.",
        "",
        f"Uncertainty: run-cluster percentile bootstrap; {samples} resamples; "
        f"seed {seed}. Runs are resampled and messages remain inside their run.",
        "",
        "| Direction | QoS | Loss (%) | Runs | Samples | Mean ms [95% CI] | "
        "Median ms [95% CI] | P95 ms [95% CI] | P99 ms [95% CI] | Max ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['direction']} | {row['qos']} | {row['loss_pct']} | "
            f"{row['run_count_with_samples']} | {row['sample_count']} | "
            f"{formatted_ci(row, 'mean')} | {formatted_ci(row, 'median')} | "
            f"{formatted_ci(row, 'p95')} | {formatted_ci(row, 'p99')} | "
            f"{row['rtt_message_max_ms']:.3f} |"
        )
    lines.extend([
        "",
        "## QoS Effects (RELIABLE minus BEST_EFFORT)",
        "",
        "| Direction | Loss (%) | Reliable runs | Best Effort runs | "
        "Mean difference ms [95% CI] | Median difference ms [95% CI] | "
        "P95 difference ms [95% CI] | P99 difference ms [95% CI] |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in effects:
        lines.append(
            f"| {row['direction']} | {row['loss_pct']} | "
            f"{row['reliable_run_count']} | {row['best_effort_run_count']} | "
            f"{formatted_effect_ci(row, 'mean')} | "
            f"{formatted_effect_ci(row, 'median')} | "
            f"{formatted_effect_ci(row, 'p95')} | "
            f"{formatted_effect_ci(row, 'p99')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_csv_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260711)
    args = parser.parse_args()
    if args.bootstrap_samples < 1000:
        parser.error("--bootstrap-samples must be at least 1000")

    summaries = []
    bootstrap_draws = {}
    seen = set()
    for path in args.sample_csv_paths:
        try:
            qos, loss_pct, direction, rows = read_samples(path)
            key = (direction, qos, loss_pct)
            if key in seen:
                raise ValueError(f"duplicate condition input {key}")
            seen.add(key)
            summary, draws = summarize(
                path,
                qos,
                loss_pct,
                direction,
                rows,
                args.bootstrap_samples,
                args.seed,
            )
        except (OSError, ValueError, csv.Error) as exc:
            raise SystemExit(f"FAIL: {path}: {exc}") from exc
        summaries.append(summary)
        bootstrap_draws[key] = draws
    summaries.sort(key=lambda row: (row["direction"], row["loss_pct"], row["qos"]))
    effects = effect_rows(summaries, bootstrap_draws)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "round4_rtt_message_summary.csv"
    effect_path = args.output_dir / "round4_rtt_message_qos_effects.csv"
    markdown_path = args.output_dir / "round4_rtt_message_summary.md"
    write_csv(summary_path, summaries)
    write_csv(effect_path, effects)
    write_markdown(
        markdown_path,
        summaries,
        effects,
        args.bootstrap_samples,
        args.seed,
    )
    print(f"Wrote {summary_path}")
    print(f"Wrote {effect_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
