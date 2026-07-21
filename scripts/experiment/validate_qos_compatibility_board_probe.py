#!/usr/bin/env python3
"""Validate one case-driven ESP32 compatibility probe log."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_fields(line: str, prefix: str) -> dict[str, str]:
    if not line.startswith(prefix + " "):
        raise ValueError(f"expected {prefix}")
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            raise ValueError(f"malformed token {token!r} in {prefix}")
        key, value = token.split("=", 1)
        if key in fields:
            raise ValueError(f"duplicate field {key!r} in {prefix}")
        fields[key] = value
    return fields


def validate(
    lines: list[str],
    *,
    case_id: str,
    role: str,
    reliability: str,
    durability: str,
    deadline_ms: str,
    liveliness_lease_ms: str,
    expected_match: bool,
) -> dict[str, int]:
    clean = [ANSI_RE.sub("", line).strip() for line in lines]
    text = "\n".join(clean).lower()
    if "watchdog" in text or "backtrace:" in text:
        raise ValueError("crash/watchdog evidence found")
    if any(line.startswith("QOS_BOARD_ERROR ") for line in clean):
        raise ValueError("board emitted QOS_BOARD_ERROR")
    configs = [line for line in clean if line.startswith("QOS_BOARD_CONFIG ")]
    ready = [line for line in clean if line.startswith("QOS_BOARD_LOCAL_READY ")]
    finals = [line for line in clean if line.startswith("QOS_BOARD_FINAL ")]
    if len(configs) != 1 or len(ready) != 1 or len(finals) != 1:
        raise ValueError(
            "expected one config/local-ready/final, found "
            f"{len(configs)}/{len(ready)}/{len(finals)}"
        )
    config = parse_fields(configs[0], "QOS_BOARD_CONFIG")
    ready_fields = parse_fields(ready[0], "QOS_BOARD_LOCAL_READY")
    final = parse_fields(finals[0], "QOS_BOARD_FINAL")
    expected_text = "1" if expected_match else "0"
    expected_config = {
        "schema": "1",
        "case_id": case_id,
        "role": role,
        "reliability": reliability,
        "durability": durability,
        "deadline_ms": deadline_ms,
        "liveliness": "automatic",
        "liveliness_lease_ms": liveliness_lease_ms,
        "expected_match": expected_text,
    }
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            raise ValueError(
                f"config {key}={config.get(key)!r}, expected {expected!r}"
            )
    for record_name, record in (("ready", ready_fields), ("final", final)):
        for key, expected in (
            ("schema", "1"),
            ("case_id", case_id),
        ):
            if record.get(key) != expected:
                raise ValueError(
                    f"{record_name} {key}={record.get(key)!r}, expected {expected!r}"
                )
    for key, expected in (("role", role), ("expected_match", expected_text)):
        if final.get(key) != expected:
            raise ValueError(
                f"final {key}={final.get(key)!r}, expected {expected!r}"
            )
    if final.get("status") != "PASS":
        raise ValueError(f"final status={final.get('status')!r}")
    actual_match = int(final.get("actual_match", "-1"))
    tx_attempts = int(final.get("tx_attempts", "-1"))
    tx_accepted = int(final.get("tx_accepted", "-1"))
    rx = int(final.get("rx", "-1"))
    message_count = int(config.get("message_count", "-1"))
    if actual_match != int(expected_match):
        raise ValueError("actual match differs from expected match")
    if role == "publisher" and expected_match:
        if tx_attempts != message_count or tx_accepted != message_count:
            raise ValueError("matched publisher did not accept all configured messages")
    if role == "subscriber" and expected_match and rx <= 0:
        raise ValueError("matched subscriber received no application message")
    if not expected_match and (tx_attempts != 0 or tx_accepted != 0 or rx != 0):
        raise ValueError("mismatched endpoint has application traffic")
    return {
        "actual_match": actual_match,
        "tx_attempts": tx_attempts,
        "tx_accepted": tx_accepted,
        "rx": rx,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--role", choices=("publisher", "subscriber"), required=True)
    parser.add_argument(
        "--reliability", choices=("reliable", "best_effort"), required=True
    )
    parser.add_argument(
        "--durability", choices=("volatile", "transient_local"), required=True
    )
    parser.add_argument("--deadline-ms", required=True)
    parser.add_argument("--liveliness-lease-ms", required=True)
    parser.add_argument("--expected-match", choices=("0", "1"), required=True)
    args = parser.parse_args()
    try:
        summary = validate(
            args.log.read_text(encoding="utf-8", errors="replace").splitlines(),
            case_id=args.case_id,
            role=args.role,
            reliability=args.reliability,
            durability=args.durability,
            deadline_ms=args.deadline_ms,
            liveliness_lease_ms=args.liveliness_lease_ms,
            expected_match=args.expected_match == "1",
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: "
        f"case_id={args.case_id} role={args.role} "
        f"actual_match={summary['actual_match']} "
        f"tx={summary['tx_attempts']}/{summary['tx_accepted']} rx={summary['rx']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
