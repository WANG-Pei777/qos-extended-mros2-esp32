#!/usr/bin/env python3
"""Validate a matched-workload smoke with telemetry compiled out."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from telemetry_control_probe import validate_control_probe


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_record(line: str) -> dict[str, str]:
    return dict(token.split("=", 1) for token in line.split()[1:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("serial_log", type=Path)
    parser.add_argument("--system", required=True)
    parser.add_argument("--require-control-probe", action="store_true")
    args = parser.parse_args()

    text = args.serial_log.read_bytes().decode("utf-8", errors="replace")
    lines = [ANSI_RE.sub("", line).strip() for line in text.splitlines()]
    configs = [line for line in lines if line.startswith("COMPARE_CONFIG ")]
    finals = [line for line in lines if line.startswith("COMPARE_FINAL ")]
    if len(configs) != 1 or len(finals) != 1:
        print(
            f"FAIL: expected one config/final, found {len(configs)}/{len(finals)}",
            file=sys.stderr,
        )
        return 1
    if any(line.startswith("BENCH_") for line in lines):
        print("FAIL: telemetry-off log contains BENCH records", file=sys.stderr)
        return 1
    if "Backtrace:" in text or "watchdog" in text.lower():
        print("FAIL: crash/watchdog evidence found", file=sys.stderr)
        return 1

    try:
        control = validate_control_probe(
            lines,
            system=args.system,
            telemetry="off",
            required=args.require_control_probe,
        )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    config = parse_record(configs[0])
    final = parse_record(finals[0])
    expected_config = {
        "system": args.system,
        "qos": "BEST_EFFORT",
        "payload_bytes": "64",
        "messages": "200",
        "period_ms": "100",
        "telemetry": "off",
    }
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            print(f"FAIL: config {key}={config.get(key)!r}, expected {expected}", file=sys.stderr)
            return 1

    expected_final = {
        "system": args.system,
        "tx": "200",
        "rx": "200",
        "samples": "200",
        "telemetry": "off",
        "publish_failures": "0",
        "duplicates": "0",
        "malformed": "0",
    }
    for key, expected in expected_final.items():
        if final.get(key) != expected:
            print(f"FAIL: final {key}={final.get(key)!r}, expected {expected}", file=sys.stderr)
            return 1

    summary = (
        f"system={args.system} tx=200 rx=200 avg_us={final['avg_us']} "
        f"max_us={final['max_us']} ready_ms={final['ready_ms']} telemetry=off"
    )
    if control is not None:
        summary += f" control_cpu_mean_ppm={control['busy_mean_ppm']}"
    print("PASS: " + summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
