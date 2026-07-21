#!/usr/bin/env python3
# flake8: noqa: E501
"""Run or resume the frozen 48-case compatibility campaign."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from run_seven_qos_compatibility_case import sha256, write_json_atomic
from validate_seven_qos_compatibility_frozen import validate_protocol


REPO = Path(__file__).resolve().parents[2]
SINGLE_RUNNER = REPO / "scripts/experiment/run_seven_qos_compatibility_case.py"
MAX_ATTEMPTS = 3
FATAL_MARKERS = (
    "guru meditation",
    "watchdog",
    "backtrace:",
    "stack smashing",
    "heap corruption",
    "assert failed",
    "qos_board_error",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_attempts(run_dir: Path) -> list[tuple[Path, dict]]:
    attempts = []
    for directory in sorted(run_dir.glob("attempt_*")):
        if not directory.is_dir():
            continue
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            attempts.append((directory, {"status": "INTERRUPTED_NO_MANIFEST"}))
            continue
        try:
            attempts.append(
                (
                    directory,
                    json.loads(manifest_path.read_text(encoding="utf-8")),
                )
            )
        except (OSError, json.JSONDecodeError):
            attempts.append((directory, {"status": "UNREADABLE_MANIFEST"}))
    return attempts


def is_fatal_attempt(attempt_dir: Path, manifest: dict) -> bool:
    if manifest.get("status") == "PASS":
        return False
    text = manifest.get("failure", "").lower()
    for name in ("serial.raw", "capture.log", "host.log", "flash.log"):
        path = attempt_dir / name
        if path.is_file():
            text += path.read_bytes().decode("utf-8", errors="replace").lower()
    return any(marker in text for marker in FATAL_MARKERS) or bool(
        re.search(r"panic(?:'ed)?|corrupt(?:ion|ed)", text)
    )


def acceptance_artifacts(attempt_dir: Path) -> dict[str, str]:
    required = (
        "manifest.json",
        "schedule_row.json",
        "serial.raw",
        "host.log",
        "host_validation.log",
        "board_validation.log",
        "capture.pcapng",
        "artifacts/firmware.bin",
        "artifacts/frozen_artifact_manifest.json",
    )
    values = {}
    for relative in required:
        path = attempt_dir / relative
        if not path.is_file():
            raise ValueError(f"accepted attempt missing {relative}")
        values[relative] = sha256(path)
    return values


def record_acceptance(
    output: Path, row: dict[str, str], attempt_dir: Path
) -> None:
    receipts = output / "acceptance_receipts"
    receipt_path = receipts / f"{int(row['ordinal']):03d}_{row['case_id']}.json"
    if receipt_path.exists():
        raise ValueError(f"acceptance receipt already exists: {row['case_id']}")
    manifest = json.loads((attempt_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise ValueError("cannot accept a non-PASS attempt")
    if manifest.get("frozen_bundle_manifest_sha256") != row["artifact_manifest_sha256"]:
        raise ValueError("accepted attempt used a different frozen bundle")
    artifacts = acceptance_artifacts(attempt_dir)
    if artifacts["artifacts/firmware.bin"] != row["firmware_sha256"]:
        raise ValueError("accepted attempt firmware differs from the schedule")
    receipt = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_acceptance_receipt",
        "accepted_at_utc": utc_now(),
        "ordinal": int(row["ordinal"]),
        "case_id": row["case_id"],
        "attempt_relative_path": str(attempt_dir.relative_to(output)),
        "firmware_sha256": row["firmware_sha256"],
        "artifact_manifest_sha256": row["artifact_manifest_sha256"],
        "artifacts": artifacts,
    }
    write_json_atomic(receipt_path, receipt)


def verify_receipt(
    output: Path, row: dict[str, str], attempt_dir: Path
) -> dict:
    path = (
        output
        / "acceptance_receipts"
        / f"{int(row['ordinal']):03d}_{row['case_id']}.json"
    )
    if not path.is_file():
        raise ValueError(f"missing acceptance receipt for {row['case_id']}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("attempt_relative_path") != str(attempt_dir.relative_to(output)):
        raise ValueError(f"acceptance receipt path drift for {row['case_id']}")
    if receipt.get("firmware_sha256") != row["firmware_sha256"]:
        raise ValueError(f"acceptance firmware drift for {row['case_id']}")
    if receipt.get("artifact_manifest_sha256") != row["artifact_manifest_sha256"]:
        raise ValueError(f"acceptance bundle drift for {row['case_id']}")
    actual = acceptance_artifacts(attempt_dir)
    if receipt.get("artifacts") != actual:
        raise ValueError(f"accepted evidence drift for {row['case_id']}")
    return receipt


def recover_unreceipted_passes(
    output: Path, schedule: list[dict[str, str]]
) -> list[str]:
    recovered = []
    for row in schedule:
        run_dir = output / "runs" / f"{int(row['ordinal']):03d}_{row['case_id']}"
        passing = [
            attempt_dir
            for attempt_dir, manifest in load_attempts(run_dir)
            if manifest.get("status") == "PASS"
        ]
        receipt = (
            output
            / "acceptance_receipts"
            / f"{int(row['ordinal']):03d}_{row['case_id']}.json"
        )
        if len(passing) == 1 and not receipt.exists():
            record_acceptance(output, row, passing[0])
            recovered.append(row["case_id"])
        elif len(passing) > 1:
            raise ValueError(f"multiple PASS attempts for {row['case_id']}")
    return recovered


def rebuild_ledgers(
    output: Path, schedule: list[dict[str, str]]
) -> tuple[int, bool]:
    attempt_rows = []
    accepted_rows = []
    fatal_seen = False
    for row in schedule:
        run_dir = output / "runs" / f"{int(row['ordinal']):03d}_{row['case_id']}"
        passing = []
        for attempt_dir, manifest in load_attempts(run_dir):
            fatal = is_fatal_attempt(attempt_dir, manifest)
            fatal_seen = fatal_seen or fatal
            manifest_path = attempt_dir / "manifest.json"
            attempt_rows.append(
                {
                    "ordinal": row["ordinal"],
                    "case_id": row["case_id"],
                    "policy": row["policy"],
                    "direction": row["direction"],
                    "endpoint_creation_order": row["endpoint_creation_order"],
                    "attempt": attempt_dir.name,
                    "status": manifest.get("status", "UNKNOWN"),
                    "fatal": int(fatal),
                    "started_at_utc": manifest.get("started_at_utc", ""),
                    "completed_at_utc": manifest.get("completed_at_utc", ""),
                    "failure": manifest.get("failure", ""),
                    "manifest_sha256": sha256(manifest_path) if manifest_path.is_file() else "",
                    "relative_path": str(attempt_dir.relative_to(output)),
                }
            )
            if manifest.get("status") == "PASS":
                passing.append((attempt_dir, manifest))
        if len(passing) > 1:
            raise ValueError(f"multiple PASS attempts for {row['case_id']}")
        if passing:
            attempt_dir, manifest = passing[0]
            receipt = verify_receipt(output, row, attempt_dir)
            accepted_rows.append(
                {
                    "ordinal": row["ordinal"],
                    "case_id": row["case_id"],
                    "policy": row["policy"],
                    "direction": row["direction"],
                    "endpoint_creation_order": row["endpoint_creation_order"],
                    "expected_match": int(manifest["case"]["expected_match"]),
                    "firmware_sha256": row["firmware_sha256"],
                    "artifact_manifest_sha256": row["artifact_manifest_sha256"],
                    "manifest_sha256": receipt["artifacts"]["manifest.json"],
                    "pcap_sha256": receipt["artifacts"]["capture.pcapng"],
                    "relative_path": str(attempt_dir.relative_to(output)),
                }
            )

    tables = (
        (output / "attempt_ledger.csv", attempt_rows),
        (output / "accepted_cases.csv", accepted_rows),
    )
    for path, rows in tables:
        if rows:
            fields = list(rows[0])
        elif path.name == "attempt_ledger.csv":
            fields = [
                "ordinal", "case_id", "policy", "direction",
                "endpoint_creation_order", "attempt", "status", "fatal",
                "started_at_utc", "completed_at_utc", "failure",
                "manifest_sha256", "relative_path",
            ]
        else:
            fields = [
                "ordinal", "case_id", "policy", "direction",
                "endpoint_creation_order", "expected_match",
                "firmware_sha256", "artifact_manifest_sha256",
                "manifest_sha256", "pcap_sha256", "relative_path",
            ]
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    return len(accepted_rows), fatal_seen


def verify_environment(design: dict, serial_port: str) -> dict:
    gate = design["hardware_and_network_gate"]
    expected_serial = Path(gate["serial_by_id"])
    actual_serial = Path(serial_port)
    if not expected_serial.exists() or not actual_serial.exists():
        raise ValueError("frozen serial device is not present")
    if expected_serial.resolve() != actual_serial.resolve():
        raise ValueError("serial port does not resolve to the frozen USB identity")
    interface = gate["interface"]
    mac_path = Path("/sys/class/net") / interface / "address"
    if mac_path.read_text(encoding="ascii").strip().lower() != gate["host_mac"].lower():
        raise ValueError("host interface MAC differs from frozen identity")
    address = subprocess.run(
        ["ip", "-j", "address", "show", "dev", interface],
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(address.stdout)
    ipv4 = {
        item["local"]
        for item in values[0]["addr_info"]
        if item["family"] == "inet"
    }
    if gate["host_ip"] not in ipv4:
        raise ValueError("host IPv4 address differs from frozen identity")
    return {
        "checked_at_utc": utc_now(),
        "serial_resolved": str(actual_serial.resolve()),
        "interface": interface,
        "host_mac": gate["host_mac"],
        "host_ip": gate["host_ip"],
        "board_ip": gate["board_ip"],
        "ap_ssid": gate["ap_ssid"],
        "ap_bssid": gate["ap_bssid"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-new-attempts", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.max_new_attempts is not None and args.max_new_attempts < 1:
        parser.error("--max-new-attempts must be positive")
    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    output = args.output if args.output.is_absolute() else REPO / args.output
    design, schedule = validate_protocol(protocol)
    if design["execution"]["maximum_attempts_per_case"] != MAX_ATTEMPTS:
        raise SystemExit("runner attempt limit differs from frozen protocol")
    environment = verify_environment(design, args.serial_port)
    if args.dry_run:
        print(
            f"PASS: frozen_cases={len(schedule)} serial={environment['serial_resolved']} "
            f"schedule_sha256={design['schedule_sha256']}"
        )
        return 0

    if output.exists() and not args.resume:
        parser.error(f"output already exists; use --resume: {output}")
    if not output.exists():
        output.mkdir(parents=True)
        (output / "inputs").mkdir()
        (output / "runs").mkdir()
        (output / "acceptance_receipts").mkdir()
        shutil.copy2(protocol / "schedule.csv", output / "inputs/schedule.csv")
        shutil.copy2(
            protocol / "design_manifest.json", output / "inputs/design_manifest.json"
        )
        campaign = {
            "schema_version": 1,
            "classification": "seven_qos_compatibility_formal_campaign",
            "status": "RUNNING",
            "started_at_utc": utc_now(),
            "protocol_path": str(protocol.resolve()),
            "protocol_design_sha256": sha256(protocol / "design_manifest.json"),
            "protocol_schedule_sha256": design["schedule_sha256"],
            "maximum_attempts_per_case": MAX_ATTEMPTS,
            "serial_port": args.serial_port,
            "environment_gate": environment,
        }
        write_json_atomic(output / "campaign_manifest.json", campaign)
    else:
        campaign = json.loads(
            (output / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        if campaign.get("protocol_design_sha256") != sha256(
            protocol / "design_manifest.json"
        ):
            raise SystemExit("resume protocol design SHA-256 mismatch")
        if campaign.get("protocol_schedule_sha256") != design["schedule_sha256"]:
            raise SystemExit("resume protocol schedule SHA-256 mismatch")

    recovered = recover_unreceipted_passes(output, schedule)
    if recovered:
        campaign.setdefault("recovered_acceptance_receipts", []).append(
            {"recovered_at_utc": utc_now(), "case_ids": recovered}
        )
        write_json_atomic(output / "campaign_manifest.json", campaign)
    accepted_count, fatal = rebuild_ledgers(output, schedule)
    if fatal:
        campaign["status"] = "FAILED_FATAL_GATE"
        write_json_atomic(output / "campaign_manifest.json", campaign)
        raise SystemExit("retained attempt contains a fatal failure")

    new_attempts = 0
    stop_for_limit = False
    for row in schedule:
        run_dir = output / "runs" / f"{int(row['ordinal']):03d}_{row['case_id']}"
        run_dir.mkdir(exist_ok=True)
        attempts = load_attempts(run_dir)
        if any(manifest.get("status") == "PASS" for _, manifest in attempts):
            continue
        while len(attempts) < MAX_ATTEMPTS:
            if args.max_new_attempts is not None and new_attempts >= args.max_new_attempts:
                stop_for_limit = True
                break
            attempt_number = len(attempts) + 1
            attempt_dir = run_dir / f"attempt_{attempt_number:02d}"
            bundle = protocol / Path(row["artifact_manifest_relative_path"]).parent
            command = [
                sys.executable,
                str(SINGLE_RUNNER),
                "--schedule", str(protocol / "schedule.csv"),
                "--case-id", row["case_id"],
                "--output", str(attempt_dir),
                "--serial-port", args.serial_port,
                "--board-ip", design["hardware_and_network_gate"]["board_ip"],
                "--interface", design["hardware_and_network_gate"]["interface"],
                "--profile", str(protocol / design["host_artifacts"]["profile_relative_path"]),
                "--host-probe", str(protocol / design["host_artifacts"]["probe_relative_path"]),
                "--frozen-artifacts", str(bundle),
                "--board-wait-ms", str(design["execution"]["board_wait_ms"]),
                "--post-match-ms", str(design["execution"]["post_match_ms"]),
            ]
            log_path = run_dir / f"attempt_{attempt_number:02d}_runner.log"
            print(
                f"RUN {row['ordinal']}/48 {row['case_id']} attempt={attempt_number}",
                flush=True,
            )
            with log_path.open("wb") as log:
                completed = subprocess.run(
                    command,
                    cwd=REPO,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            new_attempts += 1
            attempts = load_attempts(run_dir)
            current = next(
                (item for item in attempts if item[0] == attempt_dir), None
            )
            if current is None:
                print(f"FAIL {row['case_id']}: no attempt directory", flush=True)
                continue
            manifest = current[1]
            print(
                f"{manifest.get('status')} {row['case_id']} rc={completed.returncode}",
                flush=True,
            )
            if manifest.get("status") == "PASS":
                record_acceptance(output, row, attempt_dir)
            accepted_count, fatal = rebuild_ledgers(output, schedule)
            write_json_atomic(
                output / "campaign_state.json",
                {
                    "updated_at_utc": utc_now(),
                    "accepted_cases": accepted_count,
                    "scheduled_cases": len(schedule),
                    "new_attempts_this_invocation": new_attempts,
                    "fatal_failure": fatal,
                },
            )
            if fatal:
                campaign["status"] = "FAILED_FATAL_GATE"
                campaign["stopped_case_id"] = row["case_id"]
                write_json_atomic(output / "campaign_manifest.json", campaign)
                raise SystemExit("fatal compatibility-campaign failure")
            if manifest.get("status") == "PASS":
                break
        if stop_for_limit:
            break
        attempts = load_attempts(run_dir)
        if not any(manifest.get("status") == "PASS" for _, manifest in attempts):
            campaign["status"] = "STOPPED_ATTEMPT_LIMIT"
            campaign["stopped_case_id"] = row["case_id"]
            write_json_atomic(output / "campaign_manifest.json", campaign)
            raise SystemExit(f"attempt limit exhausted for {row['case_id']}")

    accepted_count, _ = rebuild_ledgers(output, schedule)
    if accepted_count == len(schedule):
        campaign["status"] = "COMPLETE_UNAUDITED"
        campaign["completed_at_utc"] = utc_now()
    else:
        campaign["status"] = "RUNNING"
    write_json_atomic(output / "campaign_manifest.json", campaign)
    print(
        f"STATUS accepted={accepted_count}/{len(schedule)} new_attempts={new_attempts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
