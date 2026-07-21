#!/usr/bin/env python3
"""Open and validate the independent P4 collection window."""

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_round6_smoke_gates import (
    flash_variant,
    git_output,
    require_network,
    run_smoke,
    sha256_file,
    validate_capture_seconds,
)
from p4_reset_recovery import recover_board_network


EARLIEST_DATE = date(2026, 7, 15)
COLLECTION_TIMEZONE = ZoneInfo("Asia/Tokyo")
QOS_MODES = ("reliable", "best_effort")
REQUIRED_RUNS_PER_QOS = 3
BOARD_NETWORK_TIMEOUT_SECONDS = 210


def require_collection_window(moment=None):
    moment = moment or datetime.now(COLLECTION_TIMEZONE)
    local_date = moment.astimezone(COLLECTION_TIMEZONE).date()
    if local_date < EARLIEST_DATE:
        raise ValueError(
            "P4 collection is frozen until 2026-07-15 Asia/Tokyo"
        )
    return moment.astimezone(COLLECTION_TIMEZONE)


def kernel_boot_time(path=Path("/proc/stat")):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("btime "):
            return datetime.fromtimestamp(
                int(line.split()[1]), tz=timezone.utc
            ).astimezone(COLLECTION_TIMEZONE)
    raise ValueError(f"kernel boot time unavailable in {path}")


def require_new_wsl_session(boot_time=None):
    boot_time = boot_time or kernel_boot_time()
    if boot_time.astimezone(COLLECTION_TIMEZONE).date() < EARLIEST_DATE:
        raise ValueError(
            "P4 requires a WSL session started on or after "
            "2026-07-15 Asia/Tokyo"
        )
    return boot_time.astimezone(COLLECTION_TIMEZONE)


def load_variants(set_root, master):
    variants = {}
    for qos in QOS_MODES:
        record = master["variants"][qos]
        manifest_path = set_root / record["manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["qos"] != qos:
            raise ValueError(f"P4 firmware QoS mismatch: {manifest_path}")
        manifest["variant"] = {"id": qos, "qos": qos}
        variants[qos] = manifest
    return variants


def command_output(command):
    return subprocess.check_output(command, text=True).strip()


def stale_processes(project_root):
    patterns = (
        str(project_root / "workspace/qos_eval/echo_reply.py"),
        str(project_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"),
        "tshark -i",
    )
    found = []
    for pattern in patterns:
        completed = subprocess.run(
            ["pgrep", "-af", pattern],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode == 0:
            found.extend(
                line for line in completed.stdout.splitlines() if line.strip()
            )
    return sorted(set(found))


def reset_board_network(serial_port, board_ip):
    return recover_board_network(serial_port, board_ip)


def write_window_evidence(
    results_root,
    board_ip,
    interface,
    local_start,
    boot_time,
    board_reset,
):
    results_root.mkdir(parents=True, exist_ok=True)
    ping_path = results_root / "window_link_health_ping.log"
    completed = subprocess.run(
        ["ping", "-c", "20", "-i", "0.2", "-W", "1", board_ip],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    ping_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise SystemExit(f"window link-health ping failed: {ping_path}")
    ip_json = json.loads(command_output(["ip", "-j", "addr", "show", "dev", interface]))
    qdisc = command_output(["sudo", "-n", "tc", "qdisc", "show", "dev", interface])
    evidence = {
        "window_start_local": local_start.isoformat(),
        "window_start_utc": local_start.astimezone(timezone.utc).isoformat(),
        "timezone": "Asia/Tokyo",
        "wsl_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "wsl_kernel_boot_local": boot_time.isoformat(),
        "board_ip": board_ip,
        "board_network_reassociation": board_reset,
        "capture_interface": interface,
        "interface_addresses": ip_json,
        "baseline_qdisc": qdisc,
        "link_health_ping": {
            "path": str(ping_path),
            "sha256": sha256_file(ping_path),
            "bytes": ping_path.stat().st_size,
        },
    }
    return evidence


def open_window_network(
    results_root,
    board_ip,
    interface,
    serial_port,
    local_start,
    boot_time,
):
    board_reset = reset_board_network(serial_port, board_ip)
    require_network(
        board_ip,
        interface,
        timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
    )
    return write_window_evidence(
        results_root,
        board_ip,
        interface,
        local_start,
        boot_time,
        board_reset,
    )


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--capture-seconds", type=int, default=60)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--new-window-ack", action="store_true")
    parser.add_argument("--network-reassociated-ack", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        local_start = require_collection_window()
        boot_time = require_new_wsl_session()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    validate_capture_seconds(args.capture_seconds)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.results_id):
        raise SystemExit("results-id contains unsupported characters")
    if not args.new_window_ack or not args.network_reassociated_ack:
        raise SystemExit(
            "P4 requires explicit new-window and network-reassociation acknowledgements"
        )
    project_root = args.project_root.resolve()
    set_root = args.firmware_set.resolve()
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("P4 smoke gates require a clean harness worktree")
    stale = stale_processes(project_root)
    if stale:
        raise SystemExit("stale experiment processes detected:\n" + "\n".join(stale))
    results_root = project_root / "results/experiments" / args.results_id
    try:
        network_evidence = open_window_network(
            results_root,
            args.board_ip,
            args.interface,
            args.serial_port,
            local_start,
            boot_time,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"board reset failed: {exc}") from exc
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    master_path = set_root / "manifest.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    if master.get("classification") != "p4_replication_firmware_set":
        raise SystemExit("firmware set is not a P4 replication set")
    variants = load_variants(set_root, master)
    smoke_root = results_root / "smoke"
    window_path = results_root / "window_manifest.json"
    if window_path.exists():
        window = json.loads(window_path.read_text(encoding="utf-8"))
        if window.get("status") == "PASS":
            print(f"[resume] P4 window smoke gate PASS: {window_path}")
            return
        raise SystemExit(f"existing incomplete P4 window requires review: {window_path}")
    window = {
        "schema_version": 1,
        "classification": "p4_independent_window_gate",
        "status": "IN_PROGRESS",
        "acknowledgements": {
            "new_wsl_network_session": True,
            "ap_or_board_network_reassociated": True,
        },
        "firmware_set_manifest": {
            "path": str(master_path),
            "sha256": sha256_file(master_path),
            "source_commit": master["source_commit"],
        },
        "harness_commit": harness_commit,
        "host_binary_sha256": sha256_file(
            project_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
        ),
        "network": network_evidence,
        "smoke_requirement": {
            "runs_per_qos": REQUIRED_RUNS_PER_QOS,
            "host_implementation": "cpp",
        },
    }
    window_path.write_text(
        json.dumps(window, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    cells = []
    for qos in QOS_MODES:
        variant = variants[qos]
        flash = flash_variant(
            project_root,
            set_root,
            variant,
            args.serial_port,
            args.flash_baud,
            smoke_root / qos,
        )
        require_network(
            args.board_ip,
            args.interface,
            timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
        )
        runs = [
            run_smoke(
                project_root,
                set_root,
                variant,
                run_number,
                args.serial_port,
                args.board_ip,
                args.interface,
                args.capture_seconds,
                smoke_root,
                harness_commit,
                host_implementation="cpp",
                classification="p4_independent_window_smoke_run",
            )
            for run_number in range(1, REQUIRED_RUNS_PER_QOS + 1)
        ]
        cells.append(
            {
                "qos": qos,
                "firmware_sha256": flash["firmware_sha256"],
                "flash": flash,
                "runs": [run["result"] for run in runs],
            }
        )
    window["status"] = "PASS"
    window["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    window["smoke"] = {
        "cells": cells,
        "runs_total": len(cells) * REQUIRED_RUNS_PER_QOS,
        "runs_pass": sum(len(cell["runs"]) for cell in cells),
    }
    window_path.write_text(
        json.dumps(window, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[complete] P4 independent window gate PASS: {window_path}")


if __name__ == "__main__":
    main()
