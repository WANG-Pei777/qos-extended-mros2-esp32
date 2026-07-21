#!/usr/bin/env python3
"""Run three exact-binary smoke attempts for each comparison system."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from three_system_common import (
    SYSTEM_ORDER,
    git_output,
    interface_ipv4,
    load_manifest,
    require_clean_repo,
    resolve_record,
    sha256_file,
    verify_agent_runtime,
)
from three_system_runner import (
    VisitProcesses,
    capture_serial_run,
    evaluate_attempt,
    flash_system,
    network_snapshot,
    utc_now,
    wait_for_board,
    write_json,
)


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--asset-set", type=Path, required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--runs-per-system", type=int, default=3)
    parser.add_argument("--max-attempts-per-system", type=int, default=6)
    return parser.parse_args()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    project_root = args.project_root.resolve()
    harness_commit = require_clean_repo(project_root)
    set_root = args.asset_set.resolve()
    manifest_path = set_root / "manifest.json"
    manifest = load_manifest(manifest_path)
    if manifest.get("status") != "SEALED":
        raise SystemExit("three-system asset set is not sealed")
    actual_host_ip = interface_ipv4(args.interface)
    if actual_host_ip != manifest.get("runtime_peer_ipv4"):
        raise SystemExit(
            f"host IPv4 changed after sealing: {actual_host_ip} != "
            f"{manifest.get('runtime_peer_ipv4')}"
        )
    for system, commit in manifest["source_commits"].items():
        repo = Path(manifest["systems"][system]["source_repo"])
        if require_clean_repo(repo) != commit:
            raise SystemExit(f"source state changed after sealing: {system}")
    if args.runs_per_system != 3:
        raise SystemExit("the preregistered smoke gate requires three runs per system")

    smoke_root = set_root / "smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    host_binary = resolve_record(set_root, manifest["host_echo"]["artifact"])
    agent_command = verify_agent_runtime(manifest["micro_ros_agent"])
    completed_systems = []
    for system in SYSTEM_ORDER:
        system_dir = smoke_root / system
        summary_path = system_dir / "manifest.json"
        if summary_path.exists():
            existing = load_manifest(summary_path)
            if existing.get("status") == "PASS":
                completed_systems.append(existing)
                print(f"[resume] smoke {system} PASS")
                continue
            raise SystemExit(f"failed smoke evidence requires review: {summary_path}")
        system_dir.mkdir(parents=True)
        flash = flash_system(
            project_root,
            set_root,
            manifest["systems"][system],
            args.serial_port,
            args.flash_baud,
            system_dir,
        )
        wait_for_board(args.board_ip)
        accepted = []
        rejected = []
        with VisitProcesses(
            system, host_binary, agent_command, system_dir
        ) as processes:
            for attempt in range(1, args.max_attempts_per_system + 1):
                if len(accepted) >= args.runs_per_system:
                    break
                attempt_dir = system_dir / f"attempt_{attempt:02d}"
                before = network_snapshot(args.interface, args.board_ip)
                run = capture_serial_run(
                    system,
                    args.serial_port,
                    args.board_ip,
                    args.interface,
                    attempt_dir,
                )
                after = network_snapshot(args.interface, args.board_ip)
                reasons = evaluate_attempt(
                    run, before, after, processes.alive_reasons()
                )
                evidence = {
                    "schema_version": 1,
                    "classification": "three_system_exact_binary_smoke_attempt",
                    "system": system,
                    "attempt": attempt,
                    "accepted": not reasons,
                    "rejection_reasons": reasons,
                    "asset_manifest_sha256": sha256_file(manifest_path),
                    "harness_commit": harness_commit,
                    "firmware_sha256": flash["firmware_sha256"],
                    "host_binary_sha256": manifest["host_echo"]["artifact"]["sha256"],
                    "network_before": before,
                    "network_after": after,
                    "run": run,
                }
                write_json(attempt_dir / "manifest.json", evidence)
                (accepted if not reasons else rejected).append(evidence)
                print(
                    f"[{'pass' if not reasons else 'reject'}] smoke {system} "
                    f"attempt={attempt} reasons={';'.join(reasons) or 'none'}"
                )
        process_evidence = processes.evidence()
        status = "PASS" if len(accepted) == args.runs_per_system else "FAIL"
        summary = {
            "schema_version": 1,
            "classification": "three_system_exact_binary_smoke_system",
            "created_at_utc": utc_now(),
            "status": status,
            "system": system,
            "required_runs": args.runs_per_system,
            "accepted_runs": len(accepted),
            "rejected_attempts": len(rejected),
            "asset_manifest_sha256": sha256_file(manifest_path),
            "harness_commit": harness_commit,
            "flash": flash,
            "processes": process_evidence,
            "attempt_manifests": [
                str(system_dir / f"attempt_{item['attempt']:02d}" / "manifest.json")
                for item in accepted + rejected
            ],
        }
        write_json(summary_path, summary)
        if status != "PASS":
            raise SystemExit(f"smoke gate failed: {summary_path}")
        completed_systems.append(summary)

    wsl_boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    summary = {
        "schema_version": 1,
        "classification": "three_system_exact_binary_smoke_set",
        "created_at_utc": utc_now(),
        "status": "PASS",
        "asset_manifest_sha256": sha256_file(manifest_path),
        "harness_commit": harness_commit,
        "runs_required": 9,
        "runs_pass": sum(item["accepted_runs"] for item in completed_systems),
        "systems_pass": len(completed_systems),
        "wsl_boot_id": wsl_boot_id,
        "board_ip": args.board_ip,
        "interface": args.interface,
        "host_ip": actual_host_ip,
        "serial_port": args.serial_port,
        "systems": {
            item["system"]: {
                "manifest": str(smoke_root / item["system"] / "manifest.json"),
                "status": item["status"],
            }
            for item in completed_systems
        },
    }
    write_json(smoke_root / "manifest.json", summary)
    print(f"[complete] smoke PASS: {smoke_root / 'manifest.json'}")


if __name__ == "__main__":
    main()
