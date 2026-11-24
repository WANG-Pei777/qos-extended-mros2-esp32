#!/usr/bin/env python3
"""Audit the excluded cross-family Seven-QoS mechanism smoke gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from run_seven_qos_mechanism_hardware_case import sha256, write_json


REPO = Path(__file__).resolve().parents[2]
EXPECTED_CASES = (
    "HIST-KL-ORDER",
    "HIST-DUP-ONCE",
    "DUR-TL-ORDER",
    "DUR-FRAG-CAPABILITY",
    "DL-BOUNDARY",
    "LS-EXPIRED",
    "LV-LOSS-ONCE",
    "RES-RECOVERY",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("smoke_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.smoke_root if args.smoke_root.is_absolute() else REPO / args.smoke_root
    root = root.resolve()
    output = args.output or root / "smoke_audit.json"
    output = output if output.is_absolute() else REPO / output
    errors: list[str] = []
    cases = []

    for case_id in EXPECTED_CASES:
        attempt = root / case_id
        required = (
            "run_metadata.json",
            "board_validation.json",
            "host_validation.json",
            "qdisc_validation.json",
            "artifact_manifest.json",
            "capture.pcapng",
        )
        missing = [name for name in required if not (attempt / name).is_file()]
        if missing:
            errors.append(f"{case_id}: missing {missing}")
            continue
        try:
            metadata = read_json(attempt / "run_metadata.json")
            board = read_json(attempt / "board_validation.json")
            host = read_json(attempt / "host_validation.json")
            qdisc = read_json(attempt / "qdisc_validation.json")
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{case_id}: unreadable evidence: {error}")
            continue
        if metadata.get("case_id") != case_id or metadata.get("status") != "PASS":
            errors.append(f"{case_id}: run metadata is not PASS")
        if metadata.get("execution_mode") != "build_from_source":
            errors.append(f"{case_id}: smoke did not build from source")
        if board.get("case_id") != case_id or board.get("status") != "PASS":
            errors.append(f"{case_id}: board validation is not PASS")
        host_records = host if isinstance(host, list) else [host]
        if not host_records or any(item.get("status") != "PASS" for item in host_records):
            errors.append(f"{case_id}: host validation is not PASS")
        if qdisc.get("status") != "PASS":
            errors.append(f"{case_id}: qdisc validation is not PASS")
        if (attempt / "capture.pcapng").stat().st_size <= 24:
            errors.append(f"{case_id}: capture is empty")
        cases.append({
            "case_id": case_id,
            "run_metadata_sha256": sha256(attempt / "run_metadata.json"),
            "board_validation_sha256": sha256(attempt / "board_validation.json"),
            "host_validation_sha256": sha256(attempt / "host_validation.json"),
            "qdisc_validation_sha256": sha256(attempt / "qdisc_validation.json"),
            "artifact_manifest_sha256": sha256(attempt / "artifact_manifest.json"),
            "pcap_sha256": sha256(attempt / "capture.pcapng"),
        })

    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    report = {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_excluded_smoke_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not errors and len(cases) == len(EXPECTED_CASES) else "FAIL",
        "source_commit": source_commit,
        "expected_cases": list(EXPECTED_CASES),
        "verified_cases": cases,
        "errors": errors,
        "evidence_boundary": "excluded engineering smoke; not an accepted deterministic campaign",
    }
    write_json(output, report)
    print(f"{report['status']}: verified={len(cases)}/{len(EXPECTED_CASES)}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
