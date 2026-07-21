#!/usr/bin/env python3
"""Validate machine-readable output from qos_compatibility_probe."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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
    lines: list[str], case_id: str, role: str, expected_match: bool
) -> dict[str, int | str]:
    if any(line.startswith("QOS_HOST_ERROR ") for line in lines):
        raise ValueError("host probe emitted QOS_HOST_ERROR")
    configs = [line for line in lines if line.startswith("QOS_HOST_CONFIG ")]
    finals = [line for line in lines if line.startswith("QOS_HOST_FINAL ")]
    if len(configs) != 1 or len(finals) != 1:
        raise ValueError(
            f"expected one config/final, found {len(configs)}/{len(finals)}"
        )
    config = parse_fields(configs[0], "QOS_HOST_CONFIG")
    final = parse_fields(finals[0], "QOS_HOST_FINAL")
    expected_text = "1" if expected_match else "0"
    for record_name, record in (("config", config), ("final", final)):
        for key, expected in (
            ("schema", "1"),
            ("case_id", case_id),
            ("role", role),
            ("expected_match", expected_text),
        ):
            if record.get(key) != expected:
                raise ValueError(
                    f"{record_name} {key}={record.get(key)!r}, expected {expected!r}"
                )
    if final.get("status") != "PASS":
        raise ValueError(f"final status={final.get('status')!r}")
    actual_match = int(final.get("actual_match", "-1"))
    maximum_match_count = int(final.get("max_match_count", "-1"))
    tx = int(final.get("tx", "-1"))
    rx = int(final.get("rx", "-1"))
    message_count = int(config.get("message_count", "-1"))
    if actual_match != int(expected_match):
        raise ValueError("actual match differs from expected match")
    if (maximum_match_count > 0) != expected_match:
        raise ValueError("maximum match count contradicts expected match")
    if role == "publisher" and expected_match and tx != message_count:
        raise ValueError("matched publisher did not send the configured message count")
    if role == "subscriber" and expected_match and rx <= 0:
        raise ValueError("matched subscriber received no application message")
    if not expected_match and (tx != 0 or rx != 0):
        raise ValueError("mismatched endpoint has application traffic")
    if tx < 0 or rx < 0:
        raise ValueError("negative message counter")
    return {
        "actual_match": actual_match,
        "max_match_count": maximum_match_count,
        "tx": tx,
        "rx": rx,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--role", choices=("publisher", "subscriber"), required=True)
    parser.add_argument("--expected-match", choices=("0", "1"), required=True)
    args = parser.parse_args()
    try:
        lines = args.log.read_text(encoding="utf-8", errors="replace").splitlines()
        summary = validate(
            lines, args.case_id, args.role, args.expected_match == "1"
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: "
        f"case_id={args.case_id} role={args.role} "
        f"actual_match={summary['actual_match']} "
        f"max_match_count={summary['max_match_count']} "
        f"tx={summary['tx']} rx={summary['rx']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
