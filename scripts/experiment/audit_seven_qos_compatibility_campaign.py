#!/usr/bin/env python3
# flake8: noqa: E501
"""Audit the formal Seven-QoS compatibility campaign end to end."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from run_seven_qos_compatibility_campaign import (
    rebuild_ledgers,
    verify_receipt,
)
from run_seven_qos_compatibility_case import sha256
from validate_seven_qos_compatibility_frozen import validate_protocol


REPO = Path(__file__).resolve().parents[2]
HOST_VALIDATOR = REPO / "scripts/experiment/validate_qos_compatibility_host_probe.py"
BOARD_VALIDATOR = REPO / "scripts/experiment/validate_qos_compatibility_board_probe.py"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    campaign_dir = args.campaign if args.campaign.is_absolute() else REPO / args.campaign
    protocol_dir = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    output = args.output or campaign_dir / "audit/audit_report.json"
    output = output if output.is_absolute() else REPO / output
    errors = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    try:
        design, schedule = validate_protocol(protocol_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: protocol validation failed: {error}")
        return 1
    campaign = json.loads(
        (campaign_dir / "campaign_manifest.json").read_text(encoding="utf-8")
    )
    try:
        rebuild_ledgers(campaign_dir, schedule)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"ledger rebuild failed: {error}")
    accepted = read_csv(campaign_dir / "accepted_cases.csv")
    attempts = read_csv(campaign_dir / "attempt_ledger.csv")
    require(campaign.get("status") == "COMPLETE_UNAUDITED", "campaign is not complete")
    require(
        campaign.get("protocol_design_sha256")
        == sha256(protocol_dir / "design_manifest.json"),
        "campaign design SHA-256 mismatch",
    )
    require(
        campaign.get("protocol_schedule_sha256") == design["schedule_sha256"],
        "campaign schedule SHA-256 mismatch",
    )
    require(len(schedule) == 48, "protocol does not contain 48 cases")
    require(len(accepted) == 48, "accepted ledger does not contain 48 cases")

    accepted_by_case = defaultdict(list)
    for row in accepted:
        accepted_by_case[row["case_id"]].append(row)
    validator_failures = []
    pcap_rows = []
    observed_counts = Counter()
    for scheduled in schedule:
        case_id = scheduled["case_id"]
        rows = accepted_by_case.get(case_id, [])
        require(len(rows) == 1, f"{case_id}: expected one accepted attempt")
        if len(rows) != 1:
            continue
        accepted_row = rows[0]
        for field in (
            "ordinal",
            "case_id",
            "policy",
            "direction",
            "endpoint_creation_order",
            "firmware_sha256",
            "artifact_manifest_sha256",
        ):
            require(
                accepted_row.get(field) == scheduled.get(field),
                f"{case_id}: accepted {field} differs from schedule",
            )
        attempt_dir = campaign_dir / accepted_row["relative_path"]
        manifest_path = attempt_dir / "manifest.json"
        require(manifest_path.is_file(), f"{case_id}: missing manifest")
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require(manifest.get("status") == "PASS", f"{case_id}: manifest is not PASS")
        require(
            manifest.get("execution_mode") == "frozen_artifacts",
            f"{case_id}: accepted attempt rebuilt firmware",
        )
        require(
            manifest.get("schedule_sha256") == design["schedule_sha256"],
            f"{case_id}: schedule SHA-256 mismatch",
        )
        require(
            manifest.get("frozen_bundle_manifest_sha256")
            == scheduled["artifact_manifest_sha256"],
            f"{case_id}: frozen bundle SHA-256 mismatch",
        )
        require(
            manifest.get("case", {}).get("case_id") == case_id,
            f"{case_id}: manifest case mismatch",
        )
        require(
            manifest.get("schedule_row") == scheduled,
            f"{case_id}: manifest schedule row mismatch",
        )
        require(
            manifest.get("serial_port") == campaign["serial_port"],
            f"{case_id}: serial port differs from campaign",
        )
        require(
            manifest.get("board_ip")
            == design["hardware_and_network_gate"]["board_ip"],
            f"{case_id}: board IP differs from protocol",
        )
        require(
            manifest.get("interface")
            == design["hardware_and_network_gate"]["interface"],
            f"{case_id}: interface differs from protocol",
        )
        require(
            all(code == 0 for code in manifest.get("return_codes", {}).values()),
            f"{case_id}: one or more recorded return codes are nonzero",
        )
        try:
            verify_receipt(campaign_dir, scheduled, attempt_dir)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"{case_id}: {error}")

        case = manifest["case"]
        expected = str(int(case["expected_match"]))
        host_command = [
            sys.executable,
            str(HOST_VALIDATOR),
            str(attempt_dir / "host.log"),
            "--case-id", case_id,
            "--role", case["host_role"],
            "--expected-match", expected,
        ]
        board_qos = case["board_qos"]
        board_command = [
            sys.executable,
            str(BOARD_VALIDATOR),
            str(attempt_dir / "serial.raw"),
            "--case-id", case_id,
            "--role", case["board_role"],
            "--reliability", board_qos["reliability"],
            "--durability", board_qos["durability"],
            "--deadline-ms", board_qos["deadline_ms"],
            "--liveliness-lease-ms", board_qos["liveliness_lease_ms"],
            "--expected-match", expected,
        ]
        for endpoint, command in (("host", host_command), ("board", board_command)):
            validation = subprocess.run(command, capture_output=True, text=True)
            if validation.returncode:
                validator_failures.append(
                    {
                        "case_id": case_id,
                        "endpoint": endpoint,
                        "output": (validation.stdout + validation.stderr).strip(),
                    }
                )

        flash_text = (attempt_dir / "flash.log").read_text(
            encoding="utf-8", errors="replace"
        )
        require(
            design["hardware_and_network_gate"]["board_mac"] in flash_text,
            f"{case_id}: board MAC missing from flash evidence",
        )
        require(
            "ESP32-S3" in flash_text,
            f"{case_id}: expected board chip missing from flash evidence",
        )

        pcap = attempt_dir / "capture.pcapng"
        require(pcap.is_file() and pcap.stat().st_size > 0, f"{case_id}: empty PCAP")
        packet_count = ""
        if pcap.is_file():
            info = subprocess.run(
                ["capinfos", "-c", str(pcap)],
                check=False,
                capture_output=True,
                text=True,
            )
            require(info.returncode == 0, f"{case_id}: capinfos rejected PCAP")
            for line in info.stdout.splitlines():
                if "Number of packets" in line:
                    packet_count = line.split(":", 1)[1].strip()
            try:
                numeric_packet_count = int(packet_count.replace(",", ""))
            except ValueError:
                numeric_packet_count = 0
            require(
                numeric_packet_count > 0,
                f"{case_id}: PCAP contains no packets",
            )
            pcap_rows.append(
                {
                    "ordinal": scheduled["ordinal"],
                    "case_id": case_id,
                    "bytes": pcap.stat().st_size,
                    "sha256": sha256(pcap),
                    "packet_count": packet_count,
                    "relative_path": str(pcap.relative_to(campaign_dir)),
                }
            )
        observed_counts[(scheduled["policy"], scheduled["direction"])] += 1

    require(not validator_failures, "one or more accepted endpoint logs failed revalidation")
    attempts_by_case = defaultdict(list)
    fatal_attempts = []
    for row in attempts:
        attempts_by_case[row["case_id"]].append(row)
        if row["fatal"] != "0":
            fatal_attempts.append(row)
    for scheduled in schedule:
        count = len(attempts_by_case[scheduled["case_id"]])
        require(1 <= count <= 3, f"{scheduled['case_id']}: invalid attempt count {count}")
    require(not fatal_attempts, "attempt ledger contains fatal failures")

    pcap_inventory = output.parent / "pcap_inventory.csv"
    pcap_inventory.parent.mkdir(parents=True, exist_ok=True)
    with pcap_inventory.open("w", newline="", encoding="utf-8") as stream:
        fields = ["ordinal", "case_id", "bytes", "sha256", "packet_count", "relative_path"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(pcap_rows)
    report = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_formal_campaign_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "scheduled_cases": len(schedule),
        "accepted_cases": len(accepted),
        "attempts": len(attempts),
        "attempt_status_counts": dict(sorted(Counter(row["status"] for row in attempts).items())),
        "fatal_attempts": len(fatal_attempts),
        "revalidated_endpoints": len(accepted) * 2 - len(validator_failures),
        "validator_failures": validator_failures,
        "pcaps": len(pcap_rows),
        "pcap_inventory_sha256": sha256(pcap_inventory),
        "policy_direction_counts": {
            f"{policy}_{direction}": count
            for (policy, direction), count in sorted(observed_counts.items())
        },
        "evidence_boundary": design["evidence_boundary"],
        "errors": errors,
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{report['status']}: accepted={len(accepted)}/48 "
        f"attempts={len(attempts)} pcaps={len(pcap_rows)}"
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
