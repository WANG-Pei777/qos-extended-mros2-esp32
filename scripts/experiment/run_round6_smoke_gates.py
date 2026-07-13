#!/usr/bin/env python3
"""Run three hardware and capture smoke gates for every Round 6 cell."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(project_root, *args):
    return subprocess.check_output(
        ["git", "-C", str(project_root), *args],
        text=True,
    ).strip()


def resolve_artifact(set_root, record):
    set_root = Path(set_root).resolve()
    candidate = (set_root / record["path"]).resolve()
    try:
        candidate.relative_to(set_root)
    except ValueError as exc:
        raise ValueError(f"artifact escapes firmware set: {candidate}") from exc
    if not candidate.is_file():
        raise ValueError(f"missing artifact: {candidate}")
    if candidate.stat().st_size != record["bytes"]:
        raise ValueError(f"artifact size mismatch: {candidate}")
    if sha256_file(candidate) != record["sha256"]:
        raise ValueError(f"artifact hash mismatch: {candidate}")
    return candidate


def parse_verification(stdout):
    lines = stdout.splitlines()
    passed = sum(line.startswith("[PASS]") for line in lines)
    failed = sum(line.startswith("[FAIL]") for line in lines)
    result = "PASS" if "[verify] RESULT: PASS" in lines else "FAIL"
    return {"pass": passed, "fail": failed, "result": result}


def expected_serial_lines(parameters):
    return [
        f"History    : KEEP_LAST({parameters['MROS2_QOS_HISTORY_DEPTH']})",
        (
            "Resources  : "
            f"{parameters['MROS2_QOS_RESOURCE_MAX_SAMPLES']} samples, "
            f"{parameters['MROS2_QOS_RESOURCE_MAX_BYTES']} bytes"
        ),
        (
            "Mechanism    : "
            f"capacity={parameters['MROS2_RTPS_HISTORY_CAPACITY']}, "
            f"heartbeat={parameters['MROS2_RTPS_HEARTBEAT_PERIOD_MS']}ms"
        ),
    ]


def validate_serial(serial_text, parameters, app_version):
    missing = [
        line
        for line in expected_serial_lines(parameters)
        if line not in serial_text
    ]
    if app_version and f"App version:      {app_version}" not in serial_text:
        missing.append(f"App version:      {app_version}")
    return missing


def validate_capture_seconds(value):
    if value < 45:
        raise ValueError(
            "capture window must be at least 45 seconds for the complete behavior phase"
        )
    return value


def require_clean_harness(project_root):
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("smoke gates require a clean harness worktree")


def require_network(board_ip, interface, timeout_seconds=45):
    deadline = time.monotonic() + timeout_seconds
    while True:
        completed = subprocess.run(
            ["ping", "-c", "1", "-W", "1", board_ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"board {board_ip} did not become reachable within "
                f"{timeout_seconds}s"
            )
        time.sleep(2)
    tc = subprocess.check_output(
        ["sudo", "-n", "tc", "qdisc", "show", "dev", interface],
        text=True,
    )
    if "netem" in tc:
        raise SystemExit(f"netem is active on {interface}")


def flash_variant(
    project_root,
    set_root,
    variant_manifest,
    serial_port,
    baud,
    output_dir,
):
    artifacts = variant_manifest["artifacts"]
    firmware = resolve_artifact(set_root, artifacts["firmware"])
    bootloader = resolve_artifact(set_root, artifacts["bootloader"])
    partition = resolve_artifact(set_root, artifacts["partition_table"])
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        raise SystemExit("IDF_PATH is unavailable; source the ESP-IDF environment")
    esptool = Path(idf_path) / "components/esptool_py/esptool/esptool.py"
    command = [
        sys.executable,
        str(esptool),
        "--chip",
        "esp32s3",
        "-p",
        serial_port,
        "-b",
        str(baud),
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
        "--flash_mode",
        "dio",
        "--flash_freq",
        "80m",
        "--flash_size",
        "2MB",
        "0x0",
        str(bootloader),
        "0x10000",
        str(firmware),
        "0x8000",
        str(partition),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "flash.log"
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(
            command,
            cwd=project_root,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if text.count("Hash of data verified.") < 3:
        raise SystemExit(f"flash verification incomplete: {log_path}")
    return {
        "command": command,
        "log": {
            "path": str(log_path),
            "sha256": sha256_file(log_path),
            "bytes": log_path.stat().st_size,
        },
        "firmware_sha256": artifacts["firmware"]["sha256"],
    }


def count_board_udp_packets(pcap_path, board_ip):
    result = subprocess.run(
        [
            "tshark",
            "-n",
            "-r",
            str(pcap_path),
            "-Y",
            f"udp && ip.addr == {board_ip}",
            "-T",
            "fields",
            "-e",
            "frame.number",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return sum(bool(line.strip()) for line in result.stdout.splitlines())


def run_smoke(
    project_root,
    set_root,
    variant_manifest,
    run_number,
    serial_port,
    board_ip,
    interface,
    capture_seconds,
    smoke_root,
    harness_commit,
):
    variant = variant_manifest["variant"]
    parameters = variant_manifest["parameters"]
    run_dir = smoke_root / variant["id"] / f"run_{run_number:02d}"
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("result") == "PASS":
            print(f"[resume] {variant['id']} run {run_number} PASS")
            return existing
        raise SystemExit(f"existing failed smoke requires review: {manifest_path}")
    run_dir.mkdir(parents=True, exist_ok=True)
    require_network(board_ip, interface)

    pcap_path = run_dir / "capture.pcapng"
    capture_log_path = run_dir / "capture.log"
    capture_log = capture_log_path.open("w", encoding="utf-8")
    capture = subprocess.Popen(
        [
            "tshark",
            "-i",
            interface,
            "-a",
            f"duration:{capture_seconds + 40}",
            "-w",
            str(pcap_path),
        ],
        stdout=capture_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    verify_stdout_path = run_dir / "verify_stdout.log"
    environment = os.environ.copy()
    environment.update(
        {
            "QOS_VERIFY_SERIAL_LOG": str(run_dir / "serial.log"),
            "QOS_VERIFY_HOST_LOG": str(run_dir / "host.log"),
            "QOS_VERIFY_TOPIC_LOG": str(run_dir / "topic.log"),
            "QOS_VERIFY_EXPECT_HISTORY_DEPTH": str(
                parameters["MROS2_QOS_HISTORY_DEPTH"]
            ),
            "QOS_VERIFY_EXPECT_HISTORY_CAPACITY": str(
                parameters["MROS2_RTPS_HISTORY_CAPACITY"]
            ),
            "QOS_VERIFY_EXPECT_HEARTBEAT_MS": str(
                parameters["MROS2_RTPS_HEARTBEAT_PERIOD_MS"]
            ),
            "QOS_VERIFY_EXPECT_RESOURCE_MAX_SAMPLES": str(
                parameters["MROS2_QOS_RESOURCE_MAX_SAMPLES"]
            ),
            "QOS_VERIFY_EXPECT_RESOURCE_MAX_BYTES": str(
                parameters["MROS2_QOS_RESOURCE_MAX_BYTES"]
            ),
        }
    )
    command = [
        str(project_root / "scripts/validation/qos_verify.sh"),
        serial_port,
        str(capture_seconds),
    ]
    try:
        with verify_stdout_path.open("w", encoding="utf-8") as verify_stdout:
            completed = subprocess.run(
                command,
                cwd=project_root,
                env=environment,
                stdout=verify_stdout,
                stderr=subprocess.STDOUT,
                text=True,
            )
    finally:
        if capture.poll() is None:
            capture.send_signal(signal.SIGINT)
        try:
            capture.wait(timeout=15)
        except subprocess.TimeoutExpired:
            capture.kill()
            capture.wait()
        capture_log.close()

    verify_text = verify_stdout_path.read_text(encoding="utf-8", errors="replace")
    verification = parse_verification(verify_text)
    serial_path = run_dir / "serial.log"
    serial_text = serial_path.read_text(encoding="utf-8", errors="replace")
    missing_serial = validate_serial(
        serial_text,
        parameters,
        variant_manifest.get("app_version"),
    )
    board_udp_packets = (
        count_board_udp_packets(pcap_path, board_ip)
        if pcap_path.is_file() and pcap_path.stat().st_size > 0
        else 0
    )
    passed = (
        completed.returncode == 0
        and verification == {"pass": 22, "fail": 0, "result": "PASS"}
        and not missing_serial
        and board_udp_packets > 0
    )
    files = {}
    for name in (
        "serial.log",
        "host.log",
        "topic.log",
        "verify_stdout.log",
        "capture.log",
        "capture.pcapng",
    ):
        path = run_dir / name
        if path.is_file():
            files[name] = {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
    manifest = {
        "schema_version": 1,
        "classification": "round6_prefactorial_smoke_gate",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "variant": variant,
        "parameters": parameters,
        "firmware_source_commit": variant_manifest["source_commit"],
        "harness_commit": harness_commit,
        "firmware_sha256": variant_manifest["artifacts"]["firmware"]["sha256"],
        "run_number": run_number,
        "verification": verification,
        "verification_exit_code": completed.returncode,
        "missing_serial_evidence": missing_serial,
        "board_udp_packets": board_udp_packets,
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not passed:
        raise SystemExit(f"smoke gate failed: {manifest_path}")
    print(
        f"[pass] {variant['id']} run {run_number}: "
        f"22/22, board_udp_packets={board_udp_packets}"
    )
    return manifest


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="10.219.224.107")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--capture-seconds", type=int, default=60)
    parser.add_argument("--runs-per-cell", type=int, default=3)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument(
        "--cell",
        action="append",
        help="Run only the named cell; repeat for multiple cells",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        validate_capture_seconds(args.capture_seconds)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    project_root = args.project_root.resolve()
    set_root = args.firmware_set.resolve()
    require_clean_harness(project_root)
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    master = json.loads((set_root / "manifest.json").read_text(encoding="utf-8"))
    smoke_root = set_root / "smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    completed = []
    variant_items = master["variants"]
    if args.cell:
        requested = set(args.cell)
        known = {item["id"] for item in variant_items}
        unknown = requested - known
        if unknown:
            raise SystemExit(f"unknown Round 6 cells: {sorted(unknown)}")
        variant_items = [
            item for item in variant_items if item["id"] in requested
        ]

    for item in variant_items:
        manifest_path = set_root / "variants" / item["id"] / "manifest.json"
        variant_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require_network(args.board_ip, args.interface)
        flash = flash_variant(
            project_root,
            set_root,
            variant_manifest,
            args.serial_port,
            args.flash_baud,
            smoke_root / item["id"],
        )
        runs = [
            run_smoke(
                project_root,
                set_root,
                variant_manifest,
                run_number,
                args.serial_port,
                args.board_ip,
                args.interface,
                args.capture_seconds,
                smoke_root,
                harness_commit,
            )
            for run_number in range(1, args.runs_per_cell + 1)
        ]
        completed.append(
            {
                "variant": variant_manifest["variant"],
                "firmware_sha256": item["firmware"]["sha256"],
                "flash": flash,
                "runs": [run["result"] for run in runs],
                "status": "PASS",
            }
        )

    summary = {
        "schema_version": 1,
        "classification": "round6_prefactorial_smoke_gate_set",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "firmware_set_manifest_sha256": sha256_file(set_root / "manifest.json"),
        "firmware_source_commit": master["source_commit"],
        "harness_commit": harness_commit,
        "required_runs_per_cell": args.runs_per_cell,
        "cells_total": len(variant_items),
        "cells_pass": len(completed),
        "runs_total": len(completed) * args.runs_per_cell,
        "runs_pass": sum(len(cell["runs"]) for cell in completed),
        "result": "PASS",
        "cells": completed,
    }
    summary_path = smoke_root / "manifest.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[complete] smoke gates PASS: {summary_path}")


if __name__ == "__main__":
    main()
