#!/usr/bin/env python3
"""Audit the complete 300-run three-system result set."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from three_system_common import (
    SYSTEM_ORDER,
    load_manifest,
    read_schedule,
    sha256_file,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def csv_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def check(condition, name, failures, details=None):
    if not condition:
        failures.append(name if details is None else f"{name}: {details}")


def main():
    args = parse_args()
    root = args.results_root.resolve()
    output = args.output.resolve() if args.output else root / "audit"
    output.mkdir(parents=True, exist_ok=True)
    failures = []

    design_path = root / "design_manifest.json"
    design = load_manifest(design_path)
    check(design.get("status") == "COMPLETE", "design_not_complete", failures)
    asset_manifest_path = Path(design["asset_manifest"]["path"])
    smoke_manifest_path = Path(design["smoke_manifest"]["path"])
    schedule_path = Path(design["schedule"]["path"])
    check(
        sha256_file(asset_manifest_path) == design["asset_manifest"]["sha256"],
        "asset_manifest_hash",
        failures,
    )
    check(
        sha256_file(smoke_manifest_path)
        == design["smoke_manifest"]["sha256_at_start"],
        "smoke_manifest_hash",
        failures,
    )
    check(
        sha256_file(schedule_path) == design["schedule"]["sha256"],
        "schedule_hash",
        failures,
    )
    asset_manifest = load_manifest(asset_manifest_path)
    smoke = load_manifest(smoke_manifest_path)
    check(smoke.get("status") == "PASS", "smoke_not_pass", failures)
    schedule = read_schedule(schedule_path)

    ledger = csv_rows(root / "acceptance_ledger.csv")
    accepted_ledger = [row for row in ledger if row["accepted"] == "1"]
    rejected_ledger = [row for row in ledger if row["accepted"] == "0"]
    check(len(accepted_ledger) == 300, "accepted_ledger_count", failures, len(accepted_ledger))
    check(
        all(row["rejection_reasons"] for row in rejected_ledger),
        "rejected_without_reason",
        failures,
    )
    check(
        all(not row["rejection_reasons"] for row in accepted_ledger),
        "accepted_with_reason",
        failures,
    )

    runs = csv_rows(root / "accepted_runs.csv")
    messages = csv_rows(root / "accepted_messages.csv")
    check(len(runs) == 300, "accepted_run_count", failures, len(runs))
    for system in SYSTEM_ORDER:
        system_runs = [row for row in runs if row["system"] == system]
        ordinals = sorted(int(row["accepted_ordinal"]) for row in system_runs)
        check(len(system_runs) == 100, f"system_run_count:{system}", failures, len(system_runs))
        check(ordinals == list(range(1, 101)), f"system_ordinals:{system}", failures)
    check(
        sum(int(row["rx"]) for row in runs) == len(messages),
        "message_count_vs_rx",
        failures,
    )

    key_counts = {}
    for row in messages:
        key = (row["system"], row["accepted_ordinal"])
        key_counts[key] = key_counts.get(key, 0) + 1
    for row in runs:
        key = (row["system"], row["accepted_ordinal"])
        check(
            key_counts.get(key, 0) == int(row["rx"]),
            "run_message_count",
            failures,
            key,
        )

    visits = []
    accepted_attempts = []
    rejected_attempts = []
    for schedule_row in schedule:
        visit_id = (
            f"block_{int(schedule_row['block']):02d}_"
            f"visit_{int(schedule_row['visit']):02d}_{schedule_row['system']}"
        )
        visit_path = root / "visits" / visit_id / "manifest.json"
        check(visit_path.is_file(), "visit_manifest_missing", failures, visit_id)
        if not visit_path.is_file():
            continue
        visit = load_manifest(visit_path)
        visits.append(visit)
        check(visit.get("status") == "PASS", "visit_not_pass", failures, visit_id)
        check(len(visit.get("accepted_runs", [])) == 10, "visit_accepted_count", failures, visit_id)
        for path in visit.get("accepted_runs", []):
            accepted_attempts.append(load_manifest(Path(path)))
        for path in visit.get("rejected_attempts", []):
            rejected_attempts.append(load_manifest(Path(path)))
    check(len(visits) == 30, "visit_count", failures, len(visits))
    check(len(accepted_attempts) == 300, "accepted_attempt_manifest_count", failures, len(accepted_attempts))
    check(
        len(rejected_attempts) == len(rejected_ledger),
        "rejected_attempt_manifest_count",
        failures,
        (len(rejected_attempts), len(rejected_ledger)),
    )

    pcap_paths = set()
    pcap_hashes = set()
    serial_paths = set()
    for attempt in accepted_attempts + rejected_attempts:
        run = attempt["run"]
        serial = run["serial"]
        serial_path = Path(serial["path"])
        check(serial_path.is_file(), "serial_missing", failures, serial_path)
        if serial_path.is_file():
            check(sha256_file(serial_path) == serial["sha256"], "serial_hash", failures, serial_path)
        if attempt["accepted"]:
            check(not attempt["rejection_reasons"], "accepted_attempt_reasons", failures)
            check(run["protocol"]["accepted"], "accepted_protocol_invalid", failures)
            check(run["reset_to_ready_ms"] is not None, "accepted_ready_missing", failures)
            check(run["pcap_stats"]["board_udp_packets"] > 0, "accepted_pcap_empty", failures)
            check("netem" not in attempt["network_before"]["qdisc"], "accepted_netem_before", failures)
            check("netem" not in attempt["network_after"]["qdisc"], "accepted_netem_after", failures)
            pcap = run["pcap"]
            pcap_path = Path(pcap["path"])
            check(pcap_path.is_file(), "pcap_missing", failures, pcap_path)
            if pcap_path.is_file():
                check(sha256_file(pcap_path) == pcap["sha256"], "pcap_hash", failures, pcap_path)
            pcap_paths.add(str(pcap_path.resolve()))
            pcap_hashes.add(pcap["sha256"])
            serial_paths.add(str(serial_path.resolve()))
        else:
            check(bool(attempt["rejection_reasons"]), "rejected_attempt_no_reason", failures)
    check(len(pcap_paths) == 300, "unique_pcap_paths", failures, len(pcap_paths))
    check(len(pcap_hashes) == 300, "unique_pcap_hashes", failures, len(pcap_hashes))
    check(len(serial_paths) == 300, "unique_serial_paths", failures, len(serial_paths))

    for row in accepted_ledger:
        expected_firmware = asset_manifest["systems"][row["system"]]["artifacts"]["firmware"]["sha256"]
        check(row["firmware_sha256"] == expected_firmware, "ledger_firmware_hash", failures)
        check(
            row["host_binary_sha256"] == asset_manifest["host_echo"]["artifact"]["sha256"],
            "ledger_host_hash",
            failures,
        )
        check(row["harness_commit"] == design["harness_commit"], "ledger_harness_commit", failures)

    report = {
        "schema_version": 1,
        "classification": "three_system_formal_audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "results_root": str(root),
        "accepted_runs": len(accepted_ledger),
        "rejected_attempts": len(rejected_ledger),
        "visits": len(visits),
        "unique_pcaps": len(pcap_hashes),
        "messages": len(messages),
        "failures": failures,
        "acceptance_boundary": {
            "type": "instrumentation_only",
            "rx_or_rtt_threshold_used": False,
        },
    }
    report_path = output / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = [
        "# Three-System Formal Audit",
        "",
        f"- Status: **{report['status']}**",
        f"- Accepted runs: {report['accepted_runs']}",
        f"- Rejected attempts retained: {report['rejected_attempts']}",
        f"- Visits: {report['visits']}",
        f"- Unique accepted PCAPs: {report['unique_pcaps']}",
        f"- Accepted RTT messages: {report['messages']}",
        "- Acceptance used instrumentation/provenance only; no RX or RTT threshold.",
    ]
    if failures:
        markdown.extend(["", "## Failures", ""] + [f"- {item}" for item in failures])
    (output / "audit_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(f"[audit] {report['status']} accepted={len(accepted_ledger)} pcaps={len(pcap_hashes)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
