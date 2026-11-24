#!/usr/bin/env python3
"""Audit a completed frozen Seven-QoS mechanism campaign."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from run_seven_qos_mechanism_hardware_case import canonical_sha256, sha256, write_json
from validate_seven_qos_mechanism_frozen import validate_protocol


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def inventory(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = args.protocol.resolve()
    campaign = args.campaign.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output exists: {output}")
    output.mkdir(parents=True)

    design, claims, unit_rows, hardware_rows = validate_protocol(protocol)
    errors: list[str] = []
    manifest = load_json(campaign / "campaign_manifest.json")
    if manifest.get("status") != "COMPLETE":
        errors.append("campaign manifest is not COMPLETE")
    if manifest.get("protocol_design_sha256") != sha256(protocol / "design_manifest.json"):
        errors.append("campaign protocol design hash mismatch")
    for name in ("design_manifest.json", "claims.csv", "unit_schedule.csv", "hardware_schedule.csv"):
        if sha256(campaign / "inputs" / name) != sha256(protocol / name):
            errors.append(f"campaign input drift: {name}")

    accepted = read_csv(campaign / "accepted_cases.csv")
    accepted_keys = {(row["kind"], row["case_id"]): row for row in accepted}
    if len(accepted) != 59 or len(accepted_keys) != 59:
        errors.append(f"accepted execution count is {len(accepted)}, expected 59")
    claim_status: dict[str, dict[str, bool]] = {
        row["case_id"]: {"unit": False, "hardware": False} for row in claims
    }
    audited_rows: list[dict[str, Any]] = []
    for kind, rows in (("unit", unit_rows), ("hardware", hardware_rows)):
        for row in rows:
            key = (kind, row["case_id"])
            if key not in accepted_keys:
                errors.append(f"missing accepted execution: {kind} {row['case_id']}")
                continue
            accepted_row = accepted_keys[key]
            attempt = campaign / accepted_row["relative_path"]
            receipt_path = (
                campaign / "acceptance_receipts" / kind
                / f"{int(row['ordinal']):03d}_{row['case_id']}.json"
            )
            receipt = load_json(receipt_path)
            observed_inventory = inventory(attempt)
            if receipt.get("attempt_files") != observed_inventory:
                errors.append(f"attempt receipt drift: {kind} {row['case_id']}")
            frozen_row = load_json(attempt / "frozen_schedule_row.json")
            if frozen_row != row:
                errors.append(f"attempt schedule-row drift: {kind} {row['case_id']}")
            if kind == "unit":
                report = load_json(attempt / "unit_case_report.json")
                if report.get("status") != "PASS" or report.get("case_id") != row["case_id"]:
                    errors.append(f"unit report failed: {row['case_id']}")
            else:
                report = load_json(attempt / "run_metadata.json")
                board = load_json(attempt / "board_validation.json")
                qdisc = load_json(attempt / "qdisc_validation.json")
                if report.get("status") != "PASS" or report.get("execution_mode") != "frozen_artifacts":
                    errors.append(f"hardware report failed: {row['case_id']}")
                if report.get("frozen_bundle_manifest_sha256") != row["artifact_manifest_sha256"]:
                    errors.append(f"hardware bundle drift: {row['case_id']}")
                if board.get("status") != "PASS" or qdisc.get("status") != "PASS":
                    errors.append(f"board/qdisc validation failed: {row['case_id']}")
                before = (attempt / "qdisc_before.txt").read_text(encoding="utf-8").strip()
                if canonical_sha256(before) != design["hardware_and_network_gate"]["qdisc_sha256"]:
                    errors.append(f"qdisc baseline drift: {row['case_id']}")
                pcap = attempt / "capture.pcapng"
                if not pcap.is_file() or pcap.stat().st_size <= 24:
                    errors.append(f"missing PCAP: {row['case_id']}")
                firmware = attempt / "artifacts/firmware.bin"
                if sha256(firmware) != row["firmware_sha256"]:
                    errors.append(f"attempt firmware drift: {row['case_id']}")
                host_reports = load_json(attempt / "host_validation.json")
                if any(item.get("status") != "PASS" for item in host_reports):
                    errors.append(f"host validation failed: {row['case_id']}")
                if row["case_id"] == "DUR-TL-EPOCH":
                    if load_json(attempt / "epoch_validation.json").get("status") != "PASS":
                        errors.append("DUR-TL-EPOCH cross-reset validation failed")
            claim_status[row["case_id"]][kind] = True
            audited_rows.append({
                "kind": kind,
                "ordinal": int(row["ordinal"]),
                "case_id": row["case_id"],
                "attempt_tree_files": len(observed_inventory),
                "receipt_sha256": sha256(receipt_path),
                "status": "PASS",
            })

    claim_rows: list[dict[str, Any]] = []
    for claim in claims:
        case_id = claim["case_id"]
        expected_unit = claim["level"] in {"unit", "unit_and_hardware"}
        expected_hardware = claim["level"] in {"hardware", "unit_and_hardware"}
        observed = claim_status[case_id]
        passed = observed["unit"] == expected_unit and observed["hardware"] == expected_hardware
        if not passed:
            errors.append(f"claim coverage mismatch: {case_id}")
        claim_rows.append({
            "claim_ordinal": claim["claim_ordinal"],
            "case_id": case_id,
            "policy": claim["policy"],
            "level": claim["level"],
            "unit_pass": int(observed["unit"]),
            "hardware_pass": int(observed["hardware"]),
            "status": "PASS" if passed else "FAIL",
        })

    with (output / "audited_executions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audited_rows[0]))
        writer.writeheader()
        writer.writerows(audited_rows)
    with (output / "claim_coverage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(claim_rows[0]))
        writer.writeheader()
        writer.writerows(claim_rows)
    report = {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_formal_campaign_audit",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_design_sha256": sha256(protocol / "design_manifest.json"),
        "campaign_manifest_sha256": sha256(campaign / "campaign_manifest.json"),
        "claim_count": len(claim_rows),
        "unit_execution_count": sum(row["kind"] == "unit" for row in audited_rows),
        "hardware_execution_count": sum(row["kind"] == "hardware" for row in audited_rows),
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    write_json(output / "audit_report.json", report)
    print(
        f"AUDIT status={report['status']} claims={report['claim_count']} "
        f"unit={report['unit_execution_count']} hardware={report['hardware_execution_count']}"
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
