#!/usr/bin/env python3
"""Run or resume the frozen Seven-QoS deterministic mechanism campaign."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from run_seven_qos_mechanism_hardware_case import canonical_sha256, sha256, write_json
from validate_seven_qos_mechanism_frozen import validate_protocol


REPO = Path(__file__).resolve().parents[2]
UNIT_RUNNER = REPO / "scripts/experiment/run_seven_qos_mechanism_unit_case.py"
HARDWARE_RUNNER = REPO / "scripts/experiment/run_seven_qos_mechanism_hardware_case.py"
MAX_ATTEMPTS = 3
FATAL_RE = re.compile(
    r"guru meditation|watchdog|backtrace:|stack overflow|heap corruption|"
    r"assert failed|loadprohibited|storeprohibited",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def attempt_inventory(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def read_status(kind: str, attempt: Path) -> tuple[str, str]:
    path = attempt / (
        "unit_case_report.json" if kind == "unit" else "run_metadata.json"
    )
    if not path.is_file():
        return "INTERRUPTED", "missing terminal report"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return "UNREADABLE", str(error)
    return str(report.get("status", "UNKNOWN")), str(report.get("error") or "")


def fatal_attempt(attempt: Path) -> bool:
    text = ""
    for path in attempt.glob("*.log"):
        text += path.read_text(encoding="utf-8", errors="replace")
    return bool(FATAL_RE.search(text))


def accepted_attempt(run_dir: Path, kind: str) -> Path | None:
    passing = []
    for attempt in sorted(run_dir.glob("attempt_*")):
        if attempt.is_dir() and read_status(kind, attempt)[0] == "PASS":
            passing.append(attempt)
    if len(passing) > 1:
        raise ValueError(f"multiple passing attempts: {run_dir}")
    return passing[0] if passing else None


def record_receipt(
    output: Path, kind: str, row: dict[str, str], attempt: Path
) -> None:
    receipt = output / "acceptance_receipts" / kind / f"{int(row['ordinal']):03d}_{row['case_id']}.json"
    if receipt.exists():
        return
    status, error = read_status(kind, attempt)
    if status != "PASS":
        raise ValueError(f"cannot accept {row['case_id']}: {status} {error}")
    value = {
        "schema_version": 1,
        "classification": f"seven_qos_mechanism_{kind}_acceptance_receipt",
        "accepted_at_utc": utc_now(),
        "ordinal": int(row["ordinal"]),
        "case_id": row["case_id"],
        "attempt_relative_path": str(attempt.relative_to(output)),
        "attempt_files": attempt_inventory(attempt),
    }
    if kind == "hardware":
        value.update({
            "firmware_sha256": row["firmware_sha256"],
            "artifact_manifest_sha256": row["artifact_manifest_sha256"],
        })
    write_json(receipt, value)


def verify_receipt(
    output: Path, kind: str, row: dict[str, str], attempt: Path
) -> None:
    receipt = output / "acceptance_receipts" / kind / f"{int(row['ordinal']):03d}_{row['case_id']}.json"
    value = json.loads(receipt.read_text(encoding="utf-8"))
    if value.get("attempt_relative_path") != str(attempt.relative_to(output)):
        raise ValueError(f"receipt path drift: {row['case_id']}")
    if value.get("attempt_files") != attempt_inventory(attempt):
        raise ValueError(f"receipt file drift: {row['case_id']}")
    if kind == "hardware" and (
        value.get("firmware_sha256") != row["firmware_sha256"]
        or value.get("artifact_manifest_sha256") != row["artifact_manifest_sha256"]
    ):
        raise ValueError(f"receipt firmware drift: {row['case_id']}")


def check_environment(design: dict[str, Any]) -> dict[str, Any]:
    gate = design["hardware_and_network_gate"]
    serial = Path(gate["serial_by_id"])
    if not serial.exists() or str(serial.resolve()) != gate["serial_resolved"]:
        raise ValueError("serial identity differs from frozen protocol")
    address = json.loads(subprocess.run(
        ["ip", "-j", "address", "show", "dev", gate["interface"]],
        check=True, capture_output=True, text=True,
    ).stdout)[0]
    ipv4 = {item["local"] for item in address["addr_info"] if item["family"] == "inet"}
    if address["address"].lower() != gate["host_mac"].lower() or gate["host_ip"] not in ipv4:
        raise ValueError("host interface differs from frozen protocol")
    qdisc = subprocess.run(
        ["tc", "qdisc", "show", "dev", gate["interface"]],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if canonical_sha256(qdisc) != gate["qdisc_sha256"]:
        raise ValueError("qdisc baseline differs from frozen protocol")
    neighbor = subprocess.run(
        ["ip", "neigh", "show", gate["board_ip"]],
        check=True, capture_output=True, text=True,
    ).stdout.lower()
    if gate["board_mac"].lower() not in neighbor:
        raise ValueError("board MAC differs from frozen protocol")
    wlan = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "netsh wlan show interfaces"],
        check=False, capture_output=True, text=True,
    ).stdout.lower()
    if gate["ap_ssid"].lower() not in wlan or gate["ap_bssid"].lower() not in wlan:
        raise ValueError("AP identity differs from frozen protocol")
    return {
        "checked_at_utc": utc_now(),
        "serial_resolved": str(serial.resolve()),
        "interface": gate["interface"],
        "host_ip": gate["host_ip"],
        "host_mac": gate["host_mac"],
        "board_ip": gate["board_ip"],
        "board_mac": gate["board_mac"],
        "ap_ssid": gate["ap_ssid"],
        "ap_bssid": gate["ap_bssid"],
        "qdisc_sha256": canonical_sha256(qdisc),
    }


def rebuild_ledgers(
    output: Path, unit_rows: list[dict[str, str]], hardware_rows: list[dict[str, str]]
) -> tuple[int, int, bool]:
    attempts: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    fatal = False
    for kind, rows in (("unit", unit_rows), ("hardware", hardware_rows)):
        for row in rows:
            run_dir = output / "runs" / kind / f"{int(row['ordinal']):03d}_{row['case_id']}"
            passing = accepted_attempt(run_dir, kind)
            for attempt in sorted(run_dir.glob("attempt_*")):
                if not attempt.is_dir():
                    continue
                status, error = read_status(kind, attempt)
                is_fatal = fatal_attempt(attempt)
                fatal = fatal or is_fatal
                attempts.append({
                    "kind": kind, "ordinal": row["ordinal"],
                    "case_id": row["case_id"], "attempt": attempt.name,
                    "status": status, "fatal": int(is_fatal),
                    "error": error, "relative_path": str(attempt.relative_to(output)),
                })
            if passing is not None:
                record_receipt(output, kind, row, passing)
                verify_receipt(output, kind, row, passing)
                accepted.append({
                    "kind": kind, "ordinal": row["ordinal"],
                    "claim_ordinal": row["claim_ordinal"],
                    "case_id": row["case_id"], "policy": row["policy"],
                    "attempt": passing.name,
                    "relative_path": str(passing.relative_to(output)),
                })
    write_csv(
        output / "attempt_ledger.csv", attempts,
        ["kind", "ordinal", "case_id", "attempt", "status", "fatal", "error", "relative_path"],
    )
    write_csv(
        output / "accepted_cases.csv", accepted,
        ["kind", "ordinal", "claim_ordinal", "case_id", "policy", "attempt", "relative_path"],
    )
    return (
        sum(row["kind"] == "unit" for row in accepted),
        sum(row["kind"] == "hardware" for row in accepted),
        fatal,
    )


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def write_campaign_manifest(
    output: Path, protocol: Path, accepted_unit: int, accepted_hardware: int,
    new_attempts: int, fatal: bool, status: str, error: str | None = None,
) -> None:
    write_json(output / "campaign_manifest.json", {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_formal_campaign",
        "updated_at_utc": utc_now(),
        "protocol_design_sha256": sha256(protocol / "design_manifest.json"),
        "accepted_unit": accepted_unit,
        "accepted_hardware": accepted_hardware,
        "new_attempts_this_invocation": new_attempts,
        "fatal_seen": fatal,
        "error": error,
        "status": status,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-new-attempts", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.max_new_attempts is not None and args.max_new_attempts < 1:
        parser.error("--max-new-attempts must be positive")
    protocol = args.protocol.resolve()
    output = args.output.resolve()
    design, claims, unit_rows, hardware_rows = validate_protocol(protocol)
    environment = check_environment(design)
    if args.dry_run:
        print(
            f"PASS: claims={len(claims)} unit={len(unit_rows)} "
            f"hardware={len(hardware_rows)} serial={environment['serial_resolved']}"
        )
        return 0
    if output.exists() and not args.resume:
        parser.error(f"output exists; use --resume: {output}")
    if not output.exists():
        for relative in (
            "inputs", "runs/unit", "runs/hardware",
            "acceptance_receipts/unit", "acceptance_receipts/hardware",
        ):
            (output / relative).mkdir(parents=True, exist_ok=True)
        for name in ("design_manifest.json", "claims.csv", "unit_schedule.csv", "hardware_schedule.csv"):
            source = protocol / name
            target = output / "inputs" / name
            target.write_bytes(source.read_bytes())
        write_json(output / "environment_gate.json", environment)

    accepted_unit, accepted_hardware, fatal = rebuild_ledgers(
        output, unit_rows, hardware_rows
    )
    if fatal:
        write_campaign_manifest(
            output, protocol, accepted_unit, accepted_hardware, 0, fatal,
            "FAILED", "fatal marker exists in retained attempt",
        )
        raise SystemExit("fatal marker exists in retained attempt; campaign stopped")
    new_attempts = 0
    stop = False
    for kind, rows in (("unit", unit_rows), ("hardware", hardware_rows)):
        for row in rows:
            run_dir = output / "runs" / kind / f"{int(row['ordinal']):03d}_{row['case_id']}"
            run_dir.mkdir(parents=True, exist_ok=True)
            if accepted_attempt(run_dir, kind) is not None:
                continue
            existing = sorted(path for path in run_dir.glob("attempt_*") if path.is_dir())
            while len(existing) < MAX_ATTEMPTS:
                if args.max_new_attempts is not None and new_attempts >= args.max_new_attempts:
                    stop = True
                    break
                attempt = run_dir / f"attempt_{len(existing) + 1:02d}"
                print(
                    f"RUN {kind} {row['ordinal']}/{len(rows)} {row['case_id']} "
                    f"attempt={len(existing) + 1}", flush=True,
                )
                if kind == "unit":
                    command = [
                        sys.executable, str(UNIT_RUNNER), "--case-id", row["case_id"],
                        "--binary-dir", str(protocol / design["unit_artifacts"]["binary_root"]),
                        "--source-root", str(protocol / design["unit_artifacts"]["source_root"]),
                        "--output-dir", str(attempt),
                    ]
                else:
                    check_environment(design)
                    command = [
                        sys.executable, str(HARDWARE_RUNNER), "--case-id", row["case_id"],
                        "--output", str(attempt), "--serial-port",
                        design["hardware_and_network_gate"]["serial_by_id"],
                        "--interface", design["hardware_and_network_gate"]["interface"],
                        "--host-probe", str(protocol / design["host_artifacts"]["probe_relative_path"]),
                        "--profile", str(protocol / design["host_artifacts"]["profile_relative_path"]),
                        "--frozen-artifacts", str(protocol / row["bundle_relative_path"]),
                    ]
                completed = run_command(command)
                if not attempt.exists():
                    attempt.mkdir(parents=True)
                (attempt / "runner.log").write_text(
                    completed.stdout + completed.stderr, encoding="utf-8"
                )
                write_json(attempt / "frozen_schedule_row.json", row)
                new_attempts += 1
                existing.append(attempt)
                status, _ = read_status(kind, attempt)
                if status == "PASS":
                    record_receipt(output, kind, row, attempt)
                    print(f"PASS {kind} {row['case_id']}", flush=True)
                    break
                if fatal_attempt(attempt):
                    accepted_unit, accepted_hardware, fatal = rebuild_ledgers(
                        output, unit_rows, hardware_rows
                    )
                    write_campaign_manifest(
                        output, protocol, accepted_unit, accepted_hardware,
                        new_attempts, fatal, "FAILED",
                        f"fatal attempt: {kind} {row['case_id']}",
                    )
                    raise SystemExit(f"fatal attempt: {kind} {row['case_id']}")
                print(f"RETRYABLE_FAIL {kind} {row['case_id']} status={status}", flush=True)
            if stop:
                break
            if accepted_attempt(run_dir, kind) is None and len(existing) >= MAX_ATTEMPTS:
                accepted_unit, accepted_hardware, fatal = rebuild_ledgers(
                    output, unit_rows, hardware_rows
                )
                error = f"attempt limit exhausted: {kind} {row['case_id']}"
                write_campaign_manifest(
                    output, protocol, accepted_unit, accepted_hardware,
                    new_attempts, fatal, "FAILED", error,
                )
                raise SystemExit(error)
        if stop:
            break

    accepted_unit, accepted_hardware, fatal = rebuild_ledgers(
        output, unit_rows, hardware_rows
    )
    complete = accepted_unit == 27 and accepted_hardware == 32 and not fatal
    write_campaign_manifest(
        output, protocol, accepted_unit, accepted_hardware, new_attempts,
        fatal, "COMPLETE" if complete else "IN_PROGRESS",
    )
    print(
        f"CAMPAIGN status={'COMPLETE' if complete else 'IN_PROGRESS'} "
        f"unit={accepted_unit}/27 hardware={accepted_hardware}/32"
    )
    return 0 if complete or stop else 1


if __name__ == "__main__":
    raise SystemExit(main())
