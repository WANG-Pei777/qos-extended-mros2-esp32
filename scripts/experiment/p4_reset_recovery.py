#!/usr/bin/env python3
"""Qualify and record P4 board recovery without collecting outcomes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


DEFAULT_MAX_ATTEMPTS = 1
DEFAULT_REACHABILITY_TIMEOUT_SECONDS = 210


class BoardRecoveryError(RuntimeError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_firmware_provenance(firmware, flash_log):
    if firmware is None and flash_log is None:
        return None
    if firmware is None or flash_log is None:
        raise ValueError("firmware and flash_log must be provided together")
    firmware = Path(firmware).resolve()
    flash_log = Path(flash_log).resolve()
    if not firmware.is_file():
        raise ValueError(f"firmware is unavailable: {firmware}")
    if not flash_log.is_file():
        raise ValueError(f"flash log is unavailable: {flash_log}")
    flash_text = flash_log.read_text(encoding="utf-8", errors="replace")
    verified_segments = flash_text.count("Hash of data verified.")
    if verified_segments != 3:
        raise ValueError(
            f"flash log must verify exactly 3 segments, observed {verified_segments}"
        )
    return {
        "firmware": {
            "path": str(firmware),
            "bytes": firmware.stat().st_size,
            "sha256": sha256_file(firmware),
        },
        "flash_log": {
            "path": str(flash_log),
            "bytes": flash_log.stat().st_size,
            "sha256": sha256_file(flash_log),
            "verified_segments": verified_segments,
        },
    }


def board_reachable(board_ip, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while True:
        completed = subprocess.run(
            ["ping", "-c", "1", "-W", "1", board_ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(1)


def esptool_reset_command(serial_port, idf_path=None, python=None):
    raw_idf_path = idf_path or os.environ.get("IDF_PATH")
    if not raw_idf_path:
        raise ValueError("IDF_PATH is unavailable; source the ESP-IDF environment")
    idf_path = Path(raw_idf_path)
    esptool = idf_path / "components/esptool_py/esptool/esptool.py"
    return [
        python or sys.executable,
        str(esptool),
        "--chip",
        "esp32s3",
        "-p",
        serial_port,
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "chip_id",
    ]


def recover_board_network(
    serial_port,
    board_ip,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    reachability_timeout_seconds=DEFAULT_REACHABILITY_TIMEOUT_SECONDS,
    idf_path=None,
    python=None,
):
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    command = esptool_reset_command(serial_port, idf_path=idf_path, python=python)
    attempts = []
    for attempt_number in range(1, max_attempts + 1):
        started = datetime.now(timezone.utc)
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        reachable = completed.returncode == 0 and board_reachable(
            board_ip,
            reachability_timeout_seconds,
        )
        attempts.append(
            {
                "attempt": attempt_number,
                "started_at_utc": started.isoformat(),
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "command": command,
                "returncode": completed.returncode,
                "board_reachable": reachable,
                "stdout_sha256": sha256_text(completed.stdout),
                "stdout": completed.stdout,
            }
        )
        if reachable:
            return {
                "method": "serial_rts_hardware_reset",
                "implementation": "esptool_default_reset_hard_reset_retry",
                "serial_port": serial_port,
                "board_ip": board_ip,
                "attempts_allowed": max_attempts,
                "attempts_used": attempt_number,
                "reachability_timeout_seconds": reachability_timeout_seconds,
                "attempts": attempts,
            }
    raise BoardRecoveryError(
        f"board {board_ip} did not recover after {max_attempts} reset attempts",
        attempts,
    )


def qualify_reset_recovery(
    serial_port,
    board_ip,
    cycles,
    max_attempts,
    reachability_timeout_seconds,
    cycle_settle_seconds,
    firmware_provenance=None,
):
    if cycles < 1:
        raise ValueError("cycles must be positive")
    if cycle_settle_seconds < 0:
        raise ValueError("cycle_settle_seconds must not be negative")
    started = datetime.now(timezone.utc)
    records = []
    failure = None
    for cycle in range(1, cycles + 1):
        try:
            recovery = recover_board_network(
                serial_port,
                board_ip,
                max_attempts=max_attempts,
                reachability_timeout_seconds=reachability_timeout_seconds,
            )
        except BoardRecoveryError as exc:
            failure = {
                "cycle": cycle,
                "message": str(exc),
                "attempts": exc.attempts,
            }
            break
        records.append({"cycle": cycle, "recovery": recovery})
        print(
            f"[pass] reset qualification cycle {cycle}/{cycles}: "
            f"attempts={recovery['attempts_used']}",
            flush=True,
        )
        if cycle < cycles:
            time.sleep(cycle_settle_seconds)
    status = "PASS" if len(records) == cycles else "FAIL"
    return {
        "schema_version": 1,
        "classification": "p4_precollection_reset_recovery_qualification",
        "status": status,
        "started_at_utc": started.isoformat(),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "serial_port": serial_port,
        "board_ip": board_ip,
        "cycles_required": cycles,
        "cycles_pass": len(records),
        "max_attempts_per_cycle": max_attempts,
        "reachability_timeout_seconds": reachability_timeout_seconds,
        "cycle_settle_seconds": cycle_settle_seconds,
        "firmware_provenance": firmware_provenance,
        "cycles": records,
        "failure": failure,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--reachability-timeout-seconds",
        type=int,
        default=DEFAULT_REACHABILITY_TIMEOUT_SECONDS,
    )
    parser.add_argument("--cycle-settle-seconds", type=int, default=75)
    parser.add_argument("--firmware", type=Path)
    parser.add_argument("--flash-log", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        firmware_provenance = load_firmware_provenance(
            args.firmware,
            args.flash_log,
        )
        report = qualify_reset_recovery(
            args.serial_port,
            args.board_ip,
            args.cycles,
            args.max_attempts,
            args.reachability_timeout_seconds,
            args.cycle_settle_seconds,
            firmware_provenance=firmware_provenance,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if report["status"] != "PASS":
        raise SystemExit(
            f"P4 reset recovery qualification FAIL: {args.output}"
        )
    print(f"[complete] P4 reset recovery qualification PASS: {args.output}")


if __name__ == "__main__":
    main()
