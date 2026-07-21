#!/usr/bin/env python3
"""Validate unit-oracle coverage against the 36-case deterministic draft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from seven_qos_mechanism_oracles import UNIT_ORACLES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    mechanism_cases = data["mechanism_cases"]
    expected = {
        case["id"]
        for case in mechanism_cases
        if case["level"] in {"unit", "unit_and_hardware"}
    }
    actual = set(UNIT_ORACLES)
    errors = []
    if len(mechanism_cases) != 36:
        errors.append(f"expected 36 mechanism cases, found {len(mechanism_cases)}")
    if expected != actual:
        errors.append(f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    for case_id, oracle in sorted(UNIT_ORACLES.items()):
        if not oracle["binary"] or not oracle["required_pass_labels"]:
            errors.append(f"{case_id}: empty binary or PASS-label binding")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"PASS: mechanism_cases={len(mechanism_cases)} "
        f"unit_oracles={len(actual)} hardware_cases="
        f"{sum(c['level'] in {'hardware', 'unit_and_hardware'} for c in mechanism_cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
