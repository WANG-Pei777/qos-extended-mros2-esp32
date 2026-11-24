#!/usr/bin/env python3
"""Generate coverage, PCAP, and static-resource tables for Seven-QoS."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from run_seven_qos_mechanism_hardware_case import sha256, write_json
from validate_seven_qos_mechanism_frozen import validate_protocol


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def elf_size(path: Path) -> dict[str, int]:
    command = (
        "source ${IDF_PATH:?Set_IDF_PATH}/export.sh >/dev/null 2>&1; "
        f"xtensa-esp32s3-elf-size {path}"
    )
    completed = subprocess.run(
        ["bash", "-lc", command], check=True, capture_output=True, text=True
    )
    fields = completed.stdout.strip().splitlines()[-1].split()
    return {
        "text_bytes": int(fields[0]),
        "data_bytes": int(fields[1]),
        "bss_bytes": int(fields[2]),
        "dec_bytes": int(fields[3]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = args.protocol.resolve()
    campaign = args.campaign.resolve()
    audit = args.audit.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output exists: {output}")
    output.mkdir(parents=True)
    design, claims, _, hardware_rows = validate_protocol(protocol)
    audit_report = json.loads((audit / "audit_report.json").read_text(encoding="utf-8"))
    if audit_report.get("status") != "PASS":
        raise SystemExit("campaign audit is not PASS")
    coverage = read_csv(audit / "claim_coverage.csv")
    write_csv(output / "claim_coverage.csv", coverage)

    accepted = {
        (row["kind"], row["case_id"]): row
        for row in read_csv(campaign / "accepted_cases.csv")
    }
    pcap_rows: list[dict[str, Any]] = []
    resource_rows: list[dict[str, Any]] = []
    for row in hardware_rows:
        case_id = row["case_id"]
        attempt = campaign / accepted[("hardware", case_id)]["relative_path"]
        pcap = attempt / "capture.pcapng"
        pcap_rows.append({
            "ordinal": row["ordinal"],
            "case_id": case_id,
            "policy": row["policy"],
            "pcap_bytes": pcap.stat().st_size,
            "pcap_sha256": sha256(pcap),
            "relative_path": str(pcap.relative_to(campaign)),
        })
        bundle = protocol / row["bundle_relative_path"]
        bundle_manifest = json.loads(
            (bundle / "artifact_manifest.json").read_text(encoding="utf-8")
        )
        sizes = elf_size(bundle / bundle_manifest["elf_relative_path"])
        resource_rows.append({
            "ordinal": row["ordinal"],
            "case_id": case_id,
            "policy": row["policy"],
            **sizes,
            "firmware_bytes": (bundle / bundle_manifest["app_relative_path"]).stat().st_size,
            "firmware_sha256": row["firmware_sha256"],
            "map_sha256": sha256(bundle / bundle_manifest["map_relative_path"]),
        })
    write_csv(output / "pcap_inventory.csv", pcap_rows)
    write_csv(output / "static_resource_table.csv", resource_rows)
    policy_rows = []
    counts = Counter(row["policy"] for row in coverage if row["status"] == "PASS")
    for policy in sorted({row["policy"] for row in claims}):
        total = sum(row["policy"] == policy for row in claims)
        passed = counts[policy]
        policy_rows.append({
            "policy": policy, "claims": total, "passed": passed,
            "status": "PASS" if passed == total else "FAIL",
        })
    write_csv(output / "policy_summary.csv", policy_rows)
    summary = {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_formal_analysis",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_design_sha256": sha256(protocol / "design_manifest.json"),
        "campaign_manifest_sha256": sha256(campaign / "campaign_manifest.json"),
        "audit_report_sha256": sha256(audit / "audit_report.json"),
        "claims_passed": sum(row["status"] == "PASS" for row in coverage),
        "claims_total": len(coverage),
        "pcaps": len(pcap_rows),
        "resource_rows": len(resource_rows),
        "performance_pooling": "forbidden",
        "status": "PASS" if all(row["status"] == "PASS" for row in coverage) else "FAIL",
    }
    write_json(output / "analysis_summary.json", summary)
    print(
        f"ANALYSIS status={summary['status']} claims={summary['claims_passed']}/"
        f"{summary['claims_total']} pcaps={summary['pcaps']}"
    )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
