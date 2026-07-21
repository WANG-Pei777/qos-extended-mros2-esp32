#!/usr/bin/env python3
"""Run or resume the frozen 60-run telemetry runtime-overhead pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SINGLE_RUNNER = REPO / "scripts/experiment/run_telemetry_control_probe_smoke.py"
MAX_ATTEMPTS = 3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_attempts(run_dir: Path) -> list[tuple[Path, dict]]:
    attempts = []
    for path in sorted(run_dir.glob("attempt_*/attempt_manifest.json")):
        try:
            attempts.append((path.parent, json.loads(path.read_text())))
        except (OSError, json.JSONDecodeError):
            attempts.append((path.parent, {"status": "UNREADABLE"}))
    for directory in sorted(run_dir.glob("attempt_*")):
        if not directory.is_dir():
            continue
        if not (directory / "attempt_manifest.json").exists():
            attempts.append((directory, {"status": "INTERRUPTED_NO_MANIFEST"}))
    return sorted(attempts, key=lambda item: item[0].name)


def load_exclusions(output: Path) -> dict[str, dict]:
    path = output / "protocol_exclusions.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {entry["relative_path"]: entry for entry in data.get("exclusions", [])}


def is_fatal_gate_failure(attempt_dir: Path, manifest: dict) -> bool:
    if manifest.get("status") != "FAIL":
        return False
    text = ""
    for name in ("serial.raw", "validation.txt", "capture.log"):
        path = attempt_dir / name
        if path.exists():
            text += path.read_bytes().decode("utf-8", errors="replace").lower()
    fatal_markers = (
        "watchdog",
        "backtrace:",
        "bench_smoke_error",
        "crc mismatch",
        "raw counters",
        "idle delta",
    )
    nonzero_fault = re.search(r"fault_flags=0x(?!00000000)[0-9a-f]{8}", text)
    return nonzero_fault is not None or any(marker in text for marker in fatal_markers)


def rebuild_ledgers(output: Path, schedule: list[dict[str, str]]) -> tuple[int, bool]:
    attempt_rows = []
    accepted_rows = []
    fatal_failure = False
    exclusions = load_exclusions(output)
    for row in schedule:
        run_dir = output / "runs" / f"{int(row['ordinal']):03d}_{row['run_id']}"
        for attempt_dir, manifest in load_attempts(run_dir):
            firmware = manifest.get("artifacts", {}).get("firmware", {})
            original_status = manifest.get("status", "UNKNOWN")
            relative_path = str(attempt_dir.relative_to(output))
            exclusion = exclusions.get(relative_path)
            status = (
                exclusion.get("classification", "SUPERSEDED")
                if exclusion is not None
                else original_status
            )
            fatal = is_fatal_gate_failure(attempt_dir, manifest)
            fatal_failure = fatal_failure or fatal
            attempt_rows.append(
                {
                    "ordinal": row["ordinal"],
                    "run_id": row["run_id"],
                    "pair_id": row["pair_id"],
                    "system": row["system"],
                    "telemetry": row["telemetry"],
                    "attempt": attempt_dir.name,
                    "status": status,
                    "original_status": original_status,
                    "fatal_gate_failure": int(fatal),
                    "firmware_sha256": firmware.get("sha256", ""),
                    "started_at_utc": manifest.get("started_at_utc", ""),
                    "completed_at_utc": manifest.get("completed_at_utc", ""),
                    "failure": manifest.get("failure", ""),
                    "relative_path": relative_path,
                }
            )
            if original_status == "PASS" and exclusion is None:
                accepted_rows.append(
                    {
                        "ordinal": row["ordinal"],
                        "run_id": row["run_id"],
                        "superblock": row["superblock"],
                        "pair_id": row["pair_id"],
                        "pair_position": row["pair_position"],
                        "system": row["system"],
                        "telemetry": row["telemetry"],
                        "firmware_sha256": firmware.get("sha256", ""),
                        "relative_path": relative_path,
                    }
                )
                break

    attempt_fields = [
        "ordinal",
        "run_id",
        "pair_id",
        "system",
        "telemetry",
        "attempt",
        "status",
        "original_status",
        "fatal_gate_failure",
        "firmware_sha256",
        "started_at_utc",
        "completed_at_utc",
        "failure",
        "relative_path",
    ]
    accepted_fields = [
        "ordinal",
        "run_id",
        "superblock",
        "pair_id",
        "pair_position",
        "system",
        "telemetry",
        "firmware_sha256",
        "relative_path",
    ]
    for path, fields, rows in (
        (output / "attempt_ledger.csv", attempt_fields, attempt_rows),
        (output / "accepted_runs.csv", accepted_fields, accepted_rows),
    ):
        temporary = path.with_suffix(".csv.tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    return len(accepted_rows), fatal_failure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--capture-timeout", type=float, default=180.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-new-runs", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.capture_timeout <= 0:
        parser.error("--capture-timeout must be positive")
    if args.max_new_runs is not None and args.max_new_runs < 1:
        parser.error("--max-new-runs must be positive")

    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    output = args.output if args.output.is_absolute() else REPO / args.output
    design_path = protocol / "design_manifest.json"
    schedule_path = protocol / "schedule.csv"
    design = json.loads(design_path.read_text())
    if design.get("status") != "FROZEN_NO_DATA":
        raise SystemExit("protocol is not FROZEN_NO_DATA")
    if sha256(schedule_path) != design.get("schedule_sha256"):
        raise SystemExit("protocol schedule hash mismatch")
    with schedule_path.open(newline="", encoding="utf-8") as stream:
        schedule = list(csv.DictReader(stream))
    if len(schedule) != design.get("total_scheduled_runs"):
        raise SystemExit("protocol run count mismatch")

    if args.dry_run:
        print(
            f"PASS: frozen protocol runs={len(schedule)} "
            f"schedule_sha256={design['schedule_sha256']}"
        )
        return 0

    if output.exists() and not args.resume:
        parser.error(f"output already exists; use --resume: {output}")
    if not output.exists():
        output.mkdir(parents=True)
        (output / "inputs").mkdir()
        (output / "runs").mkdir()
        shutil.copy2(schedule_path, output / "inputs/schedule.csv")
        shutil.copy2(design_path, output / "inputs/design_manifest.json")
        campaign = {
            "schema_version": 1,
            "classification": "telemetry_runtime_overhead_engineering_pilot",
            "status": "RUNNING",
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_schedule_sha256": design["schedule_sha256"],
            "protocol_design_sha256": sha256(design_path),
            "port": args.port,
            "capture_timeout_seconds": args.capture_timeout,
            "maximum_attempts_per_scheduled_run": MAX_ATTEMPTS,
        }
        write_json_atomic(output / "campaign_manifest.json", campaign)
    else:
        campaign = json.loads((output / "campaign_manifest.json").read_text())
        if campaign["protocol_schedule_sha256"] != design["schedule_sha256"]:
            raise SystemExit("resume protocol hash mismatch")

    accepted_count, fatal_failure = rebuild_ledgers(output, schedule)
    if fatal_failure:
        campaign["status"] = "FAILED_FATAL_GATE"
        write_json_atomic(output / "campaign_manifest.json", campaign)
        raise SystemExit("a retained attempt contains a fatal pilot-gate failure")

    new_runs = 0
    for row in schedule:
        run_dir = output / "runs" / f"{int(row['ordinal']):03d}_{row['run_id']}"
        run_dir.mkdir(exist_ok=True)
        attempts = load_attempts(run_dir)
        exclusions = load_exclusions(output)
        passing = [
            item
            for item in attempts
            if item[1].get("status") == "PASS"
            and str(item[0].relative_to(output)) not in exclusions
        ]
        if passing:
            actual_hash = passing[0][1]["artifacts"]["firmware"]["sha256"]
            if actual_hash != row["firmware_sha256"]:
                raise SystemExit(f"accepted firmware hash mismatch for {row['run_id']}")
            continue
        if len(attempts) >= MAX_ATTEMPTS:
            campaign["status"] = "STOPPED_ATTEMPT_LIMIT"
            campaign["stopped_run_id"] = row["run_id"]
            write_json_atomic(output / "campaign_manifest.json", campaign)
            rebuild_ledgers(output, schedule)
            raise SystemExit(f"attempt limit exhausted for {row['run_id']}")
        if args.max_new_runs is not None and new_runs >= args.max_new_runs:
            break

        attempt_number = len(attempts) + 1
        attempt_dir = run_dir / f"attempt_{attempt_number:02d}"
        command = [
            sys.executable,
            str(SINGLE_RUNNER),
            "--system",
            row["system"],
            "--mode",
            row["telemetry"],
            "--port",
            args.port,
            "--capture-timeout",
            str(args.capture_timeout),
            "--output",
            str(attempt_dir),
        ]
        log_path = run_dir / f"attempt_{attempt_number:02d}_runner.log"
        print(
            f"RUN {row['ordinal']}/{len(schedule)} {row['run_id']} "
            f"{row['system']}/{row['telemetry']} attempt={attempt_number}",
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
        if not (attempt_dir / "attempt_manifest.json").exists():
            print(f"FAIL {row['run_id']}: runner produced no manifest", flush=True)
        else:
            attempt = json.loads((attempt_dir / "attempt_manifest.json").read_text())
            actual_hash = attempt.get("artifacts", {}).get("firmware", {}).get("sha256")
            if actual_hash != row["firmware_sha256"]:
                campaign["status"] = "FAILED_FIRMWARE_HASH"
                campaign["stopped_run_id"] = row["run_id"]
                write_json_atomic(output / "campaign_manifest.json", campaign)
                rebuild_ledgers(output, schedule)
                raise SystemExit(f"firmware hash mismatch for {row['run_id']}")
            print(
                f"{attempt.get('status')} {row['run_id']} rc={completed.returncode}",
                flush=True,
            )
        new_runs += 1
        accepted_count, fatal_failure = rebuild_ledgers(output, schedule)
        state = {
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "accepted_runs": accepted_count,
            "scheduled_runs": len(schedule),
            "new_runs_this_invocation": new_runs,
            "fatal_gate_failure": fatal_failure,
        }
        write_json_atomic(output / "campaign_state.json", state)
        if fatal_failure:
            campaign["status"] = "FAILED_FATAL_GATE"
            campaign["stopped_run_id"] = row["run_id"]
            write_json_atomic(output / "campaign_manifest.json", campaign)
            raise SystemExit("fatal pilot-gate failure")

    accepted_count, _ = rebuild_ledgers(output, schedule)
    if accepted_count == len(schedule):
        campaign["status"] = "COMPLETE_UNAUDITED"
        campaign["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    else:
        campaign["status"] = "RUNNING"
    write_json_atomic(output / "campaign_manifest.json", campaign)
    print(f"STATUS accepted={accepted_count}/{len(schedule)} new_runs={new_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
