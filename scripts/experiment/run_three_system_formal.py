#!/usr/bin/env python3
"""Execute the preregistered 300-run three-system comparison."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from three_system_common import (
    ACCEPTED_RUNS_PER_VISIT,
    interface_ipv4,
    load_manifest,
    read_schedule,
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


LEDGER_FIELDS = (
    "block",
    "visit",
    "system",
    "attempt",
    "accepted",
    "accepted_ordinal",
    "rejection_reasons",
    "firmware_sha256",
    "host_binary_sha256",
    "serial_sha256",
    "pcap_sha256",
    "harness_commit",
)
RUN_FIELDS = (
    "block",
    "visit",
    "system",
    "accepted_ordinal",
    "runner_ready_ms",
    "firmware_ready_ms",
    "session_ms",
    "tx",
    "rx",
    "delivery_ratio",
    "free_heap_bytes",
    "board_udp_packets",
    "board_udp_bytes",
    "serial_path",
    "pcap_path",
)
MESSAGE_FIELDS = (
    "block",
    "visit",
    "system",
    "accepted_ordinal",
    "seq",
    "rtt_us",
)


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--asset-set", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--max-attempts-per-visit", type=int, default=20)
    parser.add_argument("--max-visits", type=int)
    return parser.parse_args()


def append_row(path, fields, row):
    path = Path(path)
    exists = path.exists()
    if exists:
        with path.open(newline="", encoding="utf-8") as handle:
            if tuple(next(csv.reader(handle), [])) != tuple(fields):
                raise ValueError(f"CSV schema mismatch: {path}")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def accepted_count(ledger_path, system):
    if not ledger_path.is_file():
        return 0
    with ledger_path.open(newline="", encoding="utf-8") as handle:
        return sum(
            row["system"] == system and row["accepted"] == "1"
            for row in csv.DictReader(handle)
        )


def validate_smoke(smoke_path, manifest_path, harness_commit, args):
    smoke = load_manifest(smoke_path)
    if smoke.get("status") != "PASS" or smoke.get("runs_pass") != 9:
        raise ValueError("all nine exact-binary smoke runs must pass")
    if smoke.get("asset_manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("smoke asset set differs from formal asset set")
    if smoke.get("harness_commit") != harness_commit:
        raise ValueError("formal harness differs from the smoke-tested harness")
    for key, expected in (
        ("board_ip", args.board_ip),
        ("interface", args.interface),
        ("serial_port", args.serial_port),
        ("host_ip", interface_ipv4(args.interface)),
    ):
        if smoke.get(key) != expected:
            raise ValueError(f"smoke/formal runtime mismatch: {key}")
    return smoke


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.results_id):
        raise SystemExit("results-id contains unsupported characters")
    if args.max_attempts_per_visit < ACCEPTED_RUNS_PER_VISIT:
        raise SystemExit("max-attempts-per-visit must be at least 10")
    project_root = args.project_root.resolve()
    harness_commit = require_clean_repo(project_root)
    set_root = args.asset_set.resolve()
    manifest_path = set_root / "manifest.json"
    manifest = load_manifest(manifest_path)
    actual_host_ip = interface_ipv4(args.interface)
    if actual_host_ip != manifest.get("runtime_peer_ipv4"):
        raise SystemExit(
            f"host IPv4 changed after sealing: {actual_host_ip} != "
            f"{manifest.get('runtime_peer_ipv4')}"
        )
    smoke = validate_smoke(
        set_root / "smoke/manifest.json", manifest_path, harness_commit, args
    )
    schedule_path = resolve_record(set_root, manifest["schedule"])
    schedule = read_schedule(schedule_path)
    host_binary = resolve_record(set_root, manifest["host_echo"]["artifact"])
    agent_command = verify_agent_runtime(manifest["micro_ros_agent"])

    results_root = project_root / "results/experiments" / args.results_id
    results_root.mkdir(parents=True, exist_ok=True)
    design_path = results_root / "design_manifest.json"
    design = {
        "schema_version": 1,
        "classification": "three_system_matched_workload_formal",
        "created_at_utc": utc_now(),
        "status": "IN_PROGRESS",
        "asset_manifest": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
        },
        "smoke_manifest": {
            "path": str(set_root / "smoke/manifest.json"),
            "sha256_at_start": sha256_file(set_root / "smoke/manifest.json"),
        },
        "schedule": {
            "path": str(schedule_path),
            "sha256": sha256_file(schedule_path),
        },
        "harness_commit": harness_commit,
        "host_binary_sha256": manifest["host_echo"]["artifact"]["sha256"],
        "runtime": {
            "serial_port": args.serial_port,
            "board_ip": args.board_ip,
            "interface": args.interface,
            "host_ip": actual_host_ip,
        },
        "accepted_runs_per_visit": ACCEPTED_RUNS_PER_VISIT,
        "acceptance_boundary": "instrumentation_only",
    }
    if design_path.exists():
        existing = load_manifest(design_path)
        for key in (
            "asset_manifest",
            "smoke_manifest",
            "schedule",
            "harness_commit",
            "host_binary_sha256",
            "runtime",
            "accepted_runs_per_visit",
            "acceptance_boundary",
        ):
            if existing.get(key) != design.get(key):
                raise SystemExit(f"formal design conflict: {key}")
        design = existing
    else:
        write_json(design_path, design)

    ledger_path = results_root / "acceptance_ledger.csv"
    runs_path = results_root / "accepted_runs.csv"
    messages_path = results_root / "accepted_messages.csv"
    selected = schedule if args.max_visits is None else schedule[: args.max_visits]
    completed_visits = 0
    for schedule_row in selected:
        block = int(schedule_row["block"])
        visit = int(schedule_row["visit"])
        system = schedule_row["system"]
        visit_id = f"block_{block:02d}_visit_{visit:02d}_{system}"
        visit_dir = results_root / "visits" / visit_id
        visit_manifest_path = visit_dir / "manifest.json"
        if visit_manifest_path.exists():
            existing = load_manifest(visit_manifest_path)
            if existing.get("status") == "PASS":
                completed_visits += 1
                print(f"[resume] {visit_id} PASS")
                continue
            raise SystemExit(f"incomplete visit requires review: {visit_dir}")
        visit_dir.mkdir(parents=True, exist_ok=True)
        expected_prior = int(schedule_row["run_start"]) - 1
        observed_prior = accepted_count(ledger_path, system)
        if observed_prior != expected_prior:
            raise SystemExit(
                f"accepted ordinal mismatch for {system}: "
                f"expected {expected_prior}, observed {observed_prior}"
            )
        flash = flash_system(
            project_root,
            set_root,
            manifest["systems"][system],
            args.serial_port,
            args.flash_baud,
            visit_dir,
        )
        wait_for_board(args.board_ip)
        accepted = []
        rejected = []
        with VisitProcesses(
            system, host_binary, agent_command, visit_dir
        ) as processes:
            for attempt in range(1, args.max_attempts_per_visit + 1):
                if len(accepted) >= ACCEPTED_RUNS_PER_VISIT:
                    break
                attempt_dir = visit_dir / f"attempt_{attempt:02d}"
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
                accepted_ordinal = (
                    int(schedule_row["run_start"]) + len(accepted)
                    if not reasons
                    else ""
                )
                evidence = {
                    "schema_version": 1,
                    "classification": "three_system_formal_attempt",
                    "block": block,
                    "visit": visit,
                    "system": system,
                    "attempt": attempt,
                    "accepted": not reasons,
                    "accepted_ordinal": accepted_ordinal,
                    "rejection_reasons": reasons,
                    "asset_manifest_sha256": sha256_file(manifest_path),
                    "harness_commit": harness_commit,
                    "firmware_sha256": flash["firmware_sha256"],
                    "host_binary_sha256": manifest["host_echo"]["artifact"]["sha256"],
                    "network_before": before,
                    "network_after": after,
                    "run": run,
                }
                attempt_manifest_path = attempt_dir / "manifest.json"
                write_json(attempt_manifest_path, evidence)
                append_row(
                    ledger_path,
                    LEDGER_FIELDS,
                    {
                        "block": block,
                        "visit": visit,
                        "system": system,
                        "attempt": attempt,
                        "accepted": int(not reasons),
                        "accepted_ordinal": accepted_ordinal,
                        "rejection_reasons": ";".join(reasons),
                        "firmware_sha256": flash["firmware_sha256"],
                        "host_binary_sha256": manifest["host_echo"]["artifact"]["sha256"],
                        "serial_sha256": run["serial"]["sha256"],
                        "pcap_sha256": run["pcap"]["sha256"] if run["pcap"] else "",
                        "harness_commit": harness_commit,
                    },
                )
                if not reasons:
                    protocol = run["protocol"]
                    append_row(
                        runs_path,
                        RUN_FIELDS,
                        {
                            "block": block,
                            "visit": visit,
                            "system": system,
                            "accepted_ordinal": accepted_ordinal,
                            "runner_ready_ms": run["reset_to_ready_ms"],
                            "firmware_ready_ms": protocol["ready_ms"],
                            "session_ms": protocol["session_ms"] if protocol["session_ms"] is not None else "",
                            "tx": protocol["tx"],
                            "rx": protocol["rx"],
                            "delivery_ratio": protocol["rx"] / protocol["tx"],
                            "free_heap_bytes": protocol["free_heap_bytes"],
                            "board_udp_packets": run["pcap_stats"]["board_udp_packets"],
                            "board_udp_bytes": run["pcap_stats"]["board_udp_bytes"],
                            "serial_path": run["serial"]["path"],
                            "pcap_path": run["pcap"]["path"],
                        },
                    )
                    for sample in protocol["rtts_us"]:
                        append_row(
                            messages_path,
                            MESSAGE_FIELDS,
                            {
                                "block": block,
                                "visit": visit,
                                "system": system,
                                "accepted_ordinal": accepted_ordinal,
                                "seq": sample["seq"],
                                "rtt_us": sample["rtt_us"],
                            },
                        )
                    accepted.append(str(attempt_manifest_path))
                else:
                    rejected.append(str(attempt_manifest_path))
                print(
                    f"[{'pass' if not reasons else 'reject'}] {visit_id} "
                    f"attempt={attempt} accepted={len(accepted)}/10 "
                    f"reasons={';'.join(reasons) or 'none'}"
                )
        status = "PASS" if len(accepted) == ACCEPTED_RUNS_PER_VISIT else "FAIL"
        visit_manifest = {
            "schema_version": 1,
            "classification": "three_system_formal_visit",
            "created_at_utc": utc_now(),
            "status": status,
            "schedule": schedule_row,
            "flash": flash,
            "processes": processes.evidence(),
            "accepted_runs": accepted,
            "rejected_attempts": rejected,
        }
        write_json(visit_manifest_path, visit_manifest)
        if status != "PASS":
            raise SystemExit(f"visit failed to obtain 10 accepted runs: {visit_dir}")
        completed_visits += 1
        print(f"[visit-pass] {visit_id} rejected={len(rejected)}")

    if args.max_visits is None and completed_visits == len(schedule):
        design["status"] = "COMPLETE"
        design["completed_at_utc"] = utc_now()
        write_json(design_path, design)
    print(f"[checkpoint] visits={completed_visits}/{len(schedule)} root={results_root}")


if __name__ == "__main__":
    main()
