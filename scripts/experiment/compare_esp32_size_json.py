#!/usr/bin/env python3
"""Compare two ESP-IDF idf_size JSON summaries."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


METRICS = (
    "iram_vectors",
    "iram_text",
    "used_iram",
    "diram_data",
    "diram_bss",
    "diram_text",
    "used_diram",
    "flash_code",
    "flash_rodata",
    "used_flash_non_ram",
    "total_size",
)


def load(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [metric for metric in METRICS if metric not in data]
    if missing:
        raise ValueError(f"{path}: missing metrics {missing}")
    return {metric: int(data[metric]) for metric in METRICS}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("telemetry_off", type=Path)
    parser.add_argument("telemetry_on", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        off = load(args.telemetry_off)
        on = load(args.telemetry_on)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    output = args.output.open("w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("metric", "telemetry_off_bytes", "telemetry_on_bytes", "delta_bytes", "delta_pct"))
        for metric in METRICS:
            delta = on[metric] - off[metric]
            delta_pct = "" if off[metric] == 0 else f"{100 * delta / off[metric]:.6f}"
            writer.writerow((metric, off[metric], on[metric], delta, delta_pct))
    finally:
        if args.output:
            output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
