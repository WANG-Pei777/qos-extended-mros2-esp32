#!/usr/bin/env python3
"""Execute one frozen Seven-QoS deterministic unit oracle."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from seven_qos_mechanism_oracles import UNIT_ORACLES

PASS_RE = re.compile(r"^\[PASS\] (.+)$", re.MULTILINE)


def contained_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    candidate.relative_to(root.resolve())
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--binary-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.case_id not in UNIT_ORACLES:
        parser.error(f"case has no unit oracle: {args.case_id}")
    if args.output_dir.exists():
        parser.error(f"output directory already exists: {args.output_dir}")
    args.output_dir.mkdir(parents=True)

    oracle = UNIT_ORACLES[args.case_id]
    binary = contained_file(args.binary_dir, oracle["binary"])
    completed = subprocess.run(
        [str(binary)], check=False, capture_output=True, text=True, timeout=60
    )
    (args.output_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (args.output_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")

    observed_labels = sorted(set(PASS_RE.findall(completed.stdout)))
    missing_labels = sorted(set(oracle["required_pass_labels"]) - set(observed_labels))
    source_results = []
    source_errors = []
    for assertion in oracle["source_assertions"]:
        source = contained_file(args.source_root, assertion["path"])
        count = source.read_text(encoding="utf-8").count(assertion["pattern"])
        minimum = int(assertion.get("minimum_count", 1))
        passed = count >= minimum
        source_results.append({**assertion, "observed_count": count, "passed": passed})
        if not passed:
            source_errors.append(
                f"{assertion['path']}: expected {minimum} occurrences of "
                f"{assertion['pattern']!r}, found {count}"
            )

    errors = []
    if completed.returncode != 0:
        errors.append(f"binary exit code {completed.returncode}")
    if missing_labels:
        errors.append(f"missing PASS labels: {missing_labels}")
    errors.extend(source_errors)
    report = {
        "schema_version": 1,
        "classification": "seven_qos_deterministic_mechanism_unit_case",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_id": args.case_id,
        "binary": oracle["binary"],
        "returncode": completed.returncode,
        "required_pass_labels": oracle["required_pass_labels"],
        "observed_pass_labels": observed_labels,
        "missing_pass_labels": missing_labels,
        "source_assertions": source_results,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    (args.output_dir / "unit_case_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"UNIT_CASE case_id={args.case_id} status={report['status']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
