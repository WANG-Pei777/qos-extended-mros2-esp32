#!/usr/bin/env python3
"""Validate a matched-workload smoke with telemetry compiled out."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from telemetry_control_probe import validate_control_probe
from validate_compare_rtt_samples import validate_text as validate_rtt_samples


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_record(line: str) -> dict[str, str]:
    return dict(token.split("=", 1) for token in line.split()[1:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("serial_log", type=Path)
    parser.add_argument("--system", required=True)
    parser.add_argument("--require-control-probe", action="store_true")
    parser.add_argument("--expected-qos", required=True)
    parser.add_argument("--expected-payload-bytes", type=int, required=True)
    parser.add_argument("--expected-rate-hz", type=int, required=True)
    parser.add_argument("--expected-target-tx", type=int, required=True)
    parser.add_argument("--expected-reply-grace-ms", type=int, required=True)
    parser.add_argument("--expected-rdh-depth", type=int, default=0)
    parser.add_argument("--expected-control-window-max-us", type=int)
    parser.add_argument("--allow-delivery-loss", action="store_true")
    parser.add_argument("--allow-publish-failures", action="store_true")
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
            expected_window_us=(
                args.expected_target_tx * 1_000_000 // args.expected_rate_hz
            ),
            expected_window_max_us=args.expected_control_window_max_us,
        )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    config = parse_record(configs[0])
    final = parse_record(finals[0])
    expected_config = {
        "system": args.system,
        "qos": args.expected_qos,
        "payload_bytes": str(args.expected_payload_bytes),
        "messages": str(args.expected_target_tx),
        "period_ms": str(1000 // args.expected_rate_hz),
        "grace_ms": str(args.expected_reply_grace_ms),
        "telemetry": "off",
        "rdh_enabled": "1" if args.expected_rdh_depth > 0 else "0",
    }
    if args.expected_rdh_depth > 0:
        expected_config.update(
            {
                "rdh_depth": str(args.expected_rdh_depth),
                "rdh_reliability": "RELIABLE",
                "rdh_durability": "TRANSIENT_LOCAL",
                "rdh_history": "KEEP_LAST",
            }
        )
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            print(f"FAIL: config {key}={config.get(key)!r}, expected {expected}", file=sys.stderr)
            return 1

    expected_final = {
        "system": args.system,
        "tx": str(args.expected_target_tx),
        "samples": final.get("rx", ""),
        "telemetry": "off",
        "duplicates": "0",
        "malformed": "0",
    }
    if not args.allow_delivery_loss:
        expected_final["rx"] = str(args.expected_target_tx)
    if not args.allow_publish_failures:
        expected_final["publish_failures"] = "0"
    for key, expected in expected_final.items():
        if final.get(key) != expected:
            print(f"FAIL: final {key}={final.get(key)!r}, expected {expected}", file=sys.stderr)
            return 1

    try:
        rtt_validation = validate_rtt_samples("\n".join(lines), args.system)
    except ValueError as exc:
        print(f"FAIL: per-sample RTT evidence: {exc}", file=sys.stderr)
        return 1

    summary = (
        f"system={args.system} tx={final['tx']} rx={final['rx']} "
        f"avg_us={final['avg_us']} "
        f"max_us={final['max_us']} ready_ms={final['ready_ms']} telemetry=off"
    )
    if control is not None:
        summary += f" control_cpu_mean_ppm={control['busy_mean_ppm']}"
    print("PASS: " + summary + f" sample_validation={rtt_validation['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
