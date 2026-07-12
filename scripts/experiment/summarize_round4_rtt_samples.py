#!/usr/bin/env python3
"""Summarize per-message ROUND4 RTT sidecar CSVs."""

import argparse
import csv
import math
import re
import statistics
from pathlib import Path


CONDITION_RE = re.compile(r"^round4_transport_(reliable|best_effort)_(\d+)pct(?:_(host_to_board|board_to_host))?$")
REQUIRED_COLUMNS = {"run_id", "condition", "qos_mode", "rtt_us"}


def percentile(values, fraction):
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] if lower == upper else values[lower] + (values[upper] - values[lower]) * (position - lower)


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
    return match.group(1), int(match.group(2)), match.group(3) or "host_to_board", rows


def summarize(path, qos, loss_pct, direction, rows):
    rtt_ms = sorted(float(row["rtt_us"]) / 1000.0 for row in rows)
    run_ids = {row["run_id"] for row in rows}
    return {
        "source_csv": str(path),
        "direction": direction,
        "qos": qos,
        "loss_pct": loss_pct,
        "run_count_with_samples": len(run_ids),
        "sample_count": len(rtt_ms),
        "rtt_message_mean_ms": statistics.mean(rtt_ms),
        "rtt_message_median_ms": statistics.median(rtt_ms),
        "rtt_message_p95_ms": percentile(rtt_ms, 0.95),
        "rtt_message_p99_ms": percentile(rtt_ms, 0.99),
        "rtt_message_max_ms": max(rtt_ms),
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path, rows):
    lines = [
        "# ROUND4 Per-Message RTT Summary",
        "",
        "This summary is computed from `_rtt_samples.csv` sidecars emitted by",
        "`run_matrix.sh` when firmware prints `RTT_SAMPLE` lines.",
        "",
        "| Direction | QoS | Loss (%) | Runs | Samples | Mean ms | Median ms | P95 ms | P99 ms | Max ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['direction']} | {row['qos']} | {row['loss_pct']} | "
            f"{row['run_count_with_samples']} | {row['sample_count']} | "
            f"{row['rtt_message_mean_ms']:.3f} | {row['rtt_message_median_ms']:.3f} | "
            f"{row['rtt_message_p95_ms']:.3f} | {row['rtt_message_p99_ms']:.3f} | "
            f"{row['rtt_message_max_ms']:.3f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_csv_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    summaries = []
    for path in args.sample_csv_paths:
        try:
            qos, loss_pct, direction, rows = read_samples(path)
        except (OSError, ValueError, csv.Error) as exc:
            raise SystemExit(f"FAIL: {path}: {exc}") from exc
        summaries.append(summarize(path, qos, loss_pct, direction, rows))
    summaries.sort(key=lambda row: (row["direction"], row["loss_pct"], row["qos"]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "round4_rtt_message_summary.csv", summaries)
    write_markdown(args.output_dir / "round4_rtt_message_summary.md", summaries)
    print(f"Wrote {args.output_dir / 'round4_rtt_message_summary.csv'}")
    print(f"Wrote {args.output_dir / 'round4_rtt_message_summary.md'}")


if __name__ == "__main__":
    main()
