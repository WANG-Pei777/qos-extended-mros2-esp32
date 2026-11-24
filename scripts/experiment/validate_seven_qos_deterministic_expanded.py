#!/usr/bin/env python3
"""Validate an expanded Seven-QoS deterministic no-data protocol tree."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from generate_seven_qos_deterministic_protocol import FIELDS, expand_cases, sha256
from validate_seven_qos_protocol import load_json, validate_deterministic


REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("protocol", type=Path)
    args = parser.parse_args()
    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    design_path = protocol / "design_manifest.json"
    schedule_path = protocol / "schedule.csv"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    source = REPO / design["source_deterministic_path"]
    source_data = load_json(source)
    compatibility, mechanism, total = validate_deterministic(source_data)
    expected = expand_cases(source_data)
    with schedule_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise SystemExit("FAIL: schedule schema mismatch")
        actual = list(reader)

    errors = []
    if design.get("status") != "DRAFT_EXPANDED_NO_DATA":
        errors.append("unexpected design status")
    if design.get("execution_gate_status") != "BLOCKED_HARNESS_BINDING":
        errors.append("execution gate is not blocked on harness binding")
    if design.get("performance_pooling_forbidden") is not True:
        errors.append("performance pooling is not forbidden")
    if sha256(source) != design.get("source_deterministic_sha256"):
        errors.append("source deterministic SHA-256 mismatch")
    if sha256(schedule_path) != design.get("schedule_sha256"):
        errors.append("schedule SHA-256 mismatch")
    if actual != expected:
        errors.append("expanded schedule differs from canonical source expansion")
    if design.get("compatibility_cases") != compatibility:
        errors.append("compatibility count mismatch")
    if design.get("mechanism_cases") != mechanism:
        errors.append("mechanism count mismatch")
    if design.get("total_cases") != total or len(actual) != total:
        errors.append("total count mismatch")
    if len({row["case_id"] for row in actual}) != len(actual):
        errors.append("duplicate case IDs")
    if dict(sorted(Counter(row["policy"] for row in actual).items())) != design.get(
        "policy_counts"
    ):
        errors.append("policy counts mismatch")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        f"PASS: expanded={total} compatibility={compatibility} mechanism={mechanism} "
        f"schedule_sha256={design['schedule_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
