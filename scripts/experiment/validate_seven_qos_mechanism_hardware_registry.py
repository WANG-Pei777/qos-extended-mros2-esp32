#!/usr/bin/env python3
"""Validate hardware registry coverage against the deterministic draft."""

from __future__ import annotations

import csv
from pathlib import Path

from seven_qos_mechanism_hardware_cases import HARDWARE_CASES


REPO = Path(__file__).resolve().parents[2]
SCHEDULE = (
    REPO
    / "results/protocols/20260717_seven_qos_deterministic_expanded_draft"
    / "schedule.csv"
)


def main() -> int:
    with SCHEDULE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = {
        row["case_id"]
        for row in rows
        if row["case_type"] == "mechanism" and "hardware" in row["level"]
    }
    actual = set(HARDWARE_CASES)
    errors: list[str] = []
    if actual != expected:
        errors.append(f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    kinds = [value["kind"] for value in HARDWARE_CASES.values()]
    if len(kinds) != len(set(kinds)):
        errors.append("hardware kind names are not unique")
    for case_id, value in HARDWARE_CASES.items():
        expected_capacity = 100 if case_id.startswith("RES-") else 40
        if value["capacity"] != expected_capacity:
            errors.append(f"{case_id}: capacity={value['capacity']}")
        host = value["host"]
        if host and host["role"] == "publisher" and host["pre_publish_ms"] < 15000:
            errors.append(f"{case_id}: host publisher lacks the frozen SEDP gate")
        if host and host["role"] == "subscriber" and host["post_match_ms"] < 20000:
            errors.append(f"{case_id}: host subscriber hold is too short")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        f"PASS: hardware_cases={len(actual)} unique_kinds={len(kinds)} "
        f"schedule={SCHEDULE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
