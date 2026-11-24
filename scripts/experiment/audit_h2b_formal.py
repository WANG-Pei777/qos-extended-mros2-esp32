#!/usr/bin/env python3
"""Audit every accepted run and provenance edge in the formal H2B result set."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from h2b_formal_common import (
    ACCEPTED_RUNS_PER_VISIT,
    EXPECTED_ACCEPTED_RUNS,
    EXPECTED_BLOCKS,
    EXPECTED_VISITS,
    LOSS_SPECS,
    QOS_MODES,
    count_host_to_board_udp_packets,
    expected_injection,
    read_rows,
    sha256_file,
    validate_schedule,
)


def check_hash(path, expected, label, errors):
    candidate = Path(path)
    if not candidate.is_file():
        errors.append(f"missing {label}: {candidate}")
        return
    observed = sha256_file(candidate)
    if observed != expected:
        errors.append(
            f"{label} hash mismatch: {candidate}: {observed} != {expected}"
        )


def require_within_root(path, root, label, errors):
    try:
        Path(path).resolve().relative_to(root.resolve())
    except ValueError:
        errors.append(f"{label} escapes H2B result root: {path}")


def read_exact_rtt_evidence(path):
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"RTT evidence has no schema: {path}")
        return list(reader)


def safe_int(value, label, errors):
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"invalid integer for {label}: {value!r}")
        return -1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-pcap-recount", action="store_true")
    args = parser.parse_args()
    root = args.results_root.resolve()
    errors = []
    design_path = root / "design_manifest.json"
    acceptance_path = root / "acceptance_ledger.csv"
    if not design_path.is_file() or not acceptance_path.is_file():
        raise SystemExit("H2B audit requires design_manifest.json and acceptance_ledger.csv")
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("classification") != "h2b_per_message_formal_campaign":
        errors.append("H2B design classification mismatch")
    if design.get("status") != "COMPLETE":
        errors.append("H2B design status is not COMPLETE")
    schedule_path = root / "inputs/randomized_schedule.csv"
    schedule = read_rows(schedule_path)
    try:
        validate_schedule(schedule)
    except ValueError as exc:
        errors.append(str(exc))
    if sha256_file(schedule_path) != design.get("schedule_sha256"):
        errors.append("H2B schedule hash differs from design")

    ledger = read_rows(acceptance_path)
    accepted = [row for row in ledger if row.get("accepted") == "1"]
    rejected_rows = [row for row in ledger if row.get("accepted") == "0"]
    if len(accepted) != EXPECTED_ACCEPTED_RUNS:
        errors.append(
            f"H2B accepted-run count {len(accepted)} != {EXPECTED_ACCEPTED_RUNS}"
        )
    if any(row.get("accepted") not in {"0", "1"} for row in ledger):
        errors.append("H2B acceptance ledger contains invalid accepted values")

    expected_cells = {
        (qos, target) for qos in QOS_MODES for target in LOSS_SPECS
    }
    cell_counts = Counter(
        (row.get("qos"), safe_int(
            row.get("target_loss_percent"), "target_loss_percent", errors
        ))
        for row in accepted
    )
    if set(cell_counts) != expected_cells:
        errors.append(f"H2B accepted cells mismatch: {dict(cell_counts)}")
    if any(count != 30 for count in cell_counts.values()):
        errors.append(f"H2B accepted cell counts are not 30: {dict(cell_counts)}")
    block_counts = Counter(
        (
            safe_int(row.get("block"), "block", errors),
            row.get("qos"),
            safe_int(row.get("target_loss_percent"), "target_loss", errors),
        )
        for row in accepted
    )
    expected_block_keys = {
        (block, qos, target)
        for block in range(1, EXPECTED_BLOCKS + 1)
        for qos in QOS_MODES
        for target in LOSS_SPECS
    }
    if set(block_counts) != expected_block_keys:
        errors.append("H2B accepted block-cell keys are incomplete")
    if any(count != ACCEPTED_RUNS_PER_VISIT for count in block_counts.values()):
        errors.append("H2B accepted block-cell counts are not three")
    ordinals = defaultdict(list)
    for row in accepted:
        ordinals[(row["qos"], row["target_loss_percent"])].append(
            safe_int(row["accepted_ordinal"], "accepted_ordinal", errors)
        )
    if any(sorted(values) != list(range(1, 31)) for values in ordinals.values()):
        errors.append("H2B accepted ordinals are not exactly 1..30 per cell")

    visit_manifests = sorted((root / "visits").glob("*/manifest.json"))
    if len(visit_manifests) != EXPECTED_VISITS:
        errors.append(
            f"H2B visit count {len(visit_manifests)} != {EXPECTED_VISITS}"
        )
    no_row_attempts = 0
    rejected_visit_runs = 0
    for visit_path in visit_manifests:
        visit = json.loads(visit_path.read_text(encoding="utf-8"))
        if visit.get("classification") != "h2b_per_message_formal_visit":
            errors.append(f"visit classification mismatch: {visit_path}")
        if visit.get("status") != "PASS":
            errors.append(f"visit is not PASS: {visit_path}")
        if len(visit.get("accepted_runs", [])) != ACCEPTED_RUNS_PER_VISIT:
            errors.append(f"visit accepted count mismatch: {visit_path}")
        rejected_visit_runs += len(visit.get("rejected_runs", []))
        for attempt in visit.get("attempts", []):
            if not attempt.get("runs"):
                no_row_attempts += 1

    raw_by_key = {}
    sidecar_by_key = defaultdict(list)
    manifest_hashes = {}
    condition_manifests = {}
    for condition in sorted({row["condition"] for row in accepted}):
        raw_path = root / f"mros2qos_{condition}.csv"
        sample_path = root / f"mros2qos_{condition}_rtt_samples.csv"
        condition_manifest_path = root / f"mros2qos_{condition}_manifest.json"
        if not raw_path.is_file() or not sample_path.is_file():
            errors.append(f"missing H2B condition CSVs: {condition}")
            continue
        for row in read_rows(raw_path):
            key = (condition, row["run_id"])
            if key in raw_by_key:
                errors.append(f"duplicate raw H2B run: {key}")
            raw_by_key[key] = row
        for row in read_rows(sample_path):
            sidecar_by_key[(condition, row["run_id"])].append(row)
        if condition_manifest_path.is_file():
            manifest_hashes[condition] = sha256_file(condition_manifest_path)
            condition_manifests[condition] = json.loads(
                condition_manifest_path.read_text(encoding="utf-8")
            )
        else:
            errors.append(f"missing H2B condition manifest: {condition}")

    pcap_hashes = set()
    tc_hashes = set()
    pcap_packet_counts = []
    for row in accepted:
        key = (row["condition"], row["run_id"])
        raw = raw_by_key.get(key)
        if raw is None:
            errors.append(f"missing raw H2B outcome row: {key}")
            continue
        expected_raw = {
            "formal_run": "1",
            "qos_mode": row["qos"],
            "firmware_mode": row["qos"],
            "host_mode": "cpp",
            "injection_layer": expected_injection(
                safe_int(row["target_loss_percent"], "target_loss", errors)
            ),
            "commit_hash": design.get("harness_commit"),
            "worktree_state": "clean",
            "matched_pub": "1",
            "matched_sub": "1",
            "manifest_sha256": row["manifest_sha256"],
        }
        for field, expected in expected_raw.items():
            if raw.get(field) != expected:
                errors.append(f"raw H2B field mismatch {key}: {field}")
        if row["manifest_sha256"] != manifest_hashes.get(row["condition"]):
            errors.append(f"condition manifest hash mismatch: {key}")
        if row.get("harness_commit") != design.get("harness_commit"):
            errors.append(f"acceptance ledger harness mismatch: {key}")
        condition_manifest = condition_manifests.get(row["condition"], {})
        expected_manifest = {
            "system": "mros2qos",
            "condition": row["condition"],
            "formal_run": 1,
            "qos_mode": row["qos"],
            "firmware_mode": row["qos"],
            "host_mode": "cpp",
            "injection_layer": expected_raw["injection_layer"],
            "board_ip": design["runtime"]["board_ip"],
        }
        for field, expected in expected_manifest.items():
            if condition_manifest.get("experiment", {}).get(field) != expected:
                errors.append(f"condition manifest field mismatch {key}: {field}")
        if condition_manifest.get("source", {}).get("commit_hash") != design.get(
            "harness_commit"
        ):
            errors.append(f"condition manifest harness mismatch: {key}")
        if condition_manifest.get("host_binary", {}).get("sha256") != design.get(
            "host_binary_sha256"
        ):
            errors.append(f"condition manifest host hash mismatch: {key}")
        if condition_manifest.get("firmware_binary", {}).get(
            "sha256"
        ) != row["firmware_sha256"]:
            errors.append(f"condition manifest firmware hash mismatch: {key}")
        for binary_key in ("host_binary", "firmware_binary"):
            archive_path = condition_manifest.get(binary_key, {}).get("path", "")
            archive = Path(archive_path)
            if not archive.is_absolute():
                archive = SCRIPT_DIR.parents[1] / archive
            check_hash(
                archive,
                condition_manifest.get(binary_key, {}).get("sha256", ""),
                f"archived {binary_key}",
                errors,
            )
        for field, hash_field, label in (
            ("serial_path", "serial_sha256", "serial"),
            ("host_path", "host_sha256", "host log"),
            ("rtt_evidence_path", "rtt_evidence_sha256", "RTT evidence"),
            ("pcap_path", "pcap_sha256", "PCAP"),
            ("tc_state_path", "tc_state_sha256", "tc state"),
        ):
            require_within_root(row[field], root, label, errors)
            check_hash(row[field], row[hash_field], label, errors)
        require_within_root(row["pcap_path"] + ".log", root, "capture log", errors)
        check_hash(
            row["pcap_path"] + ".log",
            row["capture_log_sha256"],
            "capture log",
            errors,
        )
        try:
            rtt_evidence = read_exact_rtt_evidence(row["rtt_evidence_path"])
        except (OSError, ValueError, csv.Error) as exc:
            errors.append(str(exc))
            rtt_evidence = []
        expected_rtt_count = safe_int(raw.get("rtt_count"), "rtt_count", errors)
        if len(rtt_evidence) != expected_rtt_count:
            errors.append(f"RTT evidence count mismatch: {key}")
        if safe_int(row["rtt_evidence_rows"], "rtt_evidence_rows", errors) != len(
            rtt_evidence
        ):
            errors.append(f"RTT ledger count mismatch: {key}")
        cumulative = sidecar_by_key.get(key, [])
        if rtt_evidence != cumulative:
            errors.append(f"RTT evidence content mismatch: {key}")
        pcap_hashes.add(row["pcap_sha256"])
        tc_hashes.add(row["tc_state_sha256"])
        tc_text = Path(row["tc_state_path"]).read_text(
            encoding="utf-8", errors="replace"
        ) if Path(row["tc_state_path"]).is_file() else ""
        target = safe_int(row["target_loss_percent"], "target_loss", errors)
        if "phase=post_cleanup" not in tc_text:
            errors.append(f"tc post-cleanup record missing: {key}")
        if target > 0:
            if "qdisc clsact" not in tc_text or "gact" not in tc_text:
                errors.append(f"tc egress gact evidence missing: {key}")
            if f"denominator={LOSS_SPECS[target]['denominator']}" not in tc_text:
                errors.append(f"tc denominator evidence mismatch: {key}")
        recorded_packets = safe_int(
            row["pcap_host_to_board_udp_packets"], "pcap packets", errors
        )
        if recorded_packets <= 0:
            errors.append(f"accepted H2B capture has no host UDP: {key}")
        if not args.skip_pcap_recount and Path(row["pcap_path"]).is_file():
            try:
                observed_packets = count_host_to_board_udp_packets(
                    row["pcap_path"], design["runtime"]["board_ip"]
                )
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"PCAP recount failed {key}: {exc}")
            else:
                if observed_packets != recorded_packets:
                    errors.append(f"PCAP packet recount mismatch: {key}")
                pcap_packet_counts.append(observed_packets)

    if len(pcap_hashes) != len(accepted):
        errors.append(
            f"H2B unique accepted PCAP hashes {len(pcap_hashes)} != {len(accepted)}"
        )
    if len(tc_hashes) != len(accepted):
        errors.append(
            f"H2B unique accepted tc hashes {len(tc_hashes)} != {len(accepted)}"
        )
    if rejected_visit_runs != len(rejected_rows):
        errors.append(
            "H2B rejected row count differs between visit manifests and ledger"
        )

    report = {
        "schema_version": 1,
        "classification": "h2b_per_message_formal_audit",
        "status": "PASS" if not errors else "FAIL",
        "results_root": str(root),
        "harness_commit": design.get("harness_commit"),
        "accepted_runs": len(accepted),
        "accepted_per_cell": {
            f"{qos}_target{target:02d}": cell_counts[(qos, target)]
            for qos, target in sorted(expected_cells)
        },
        "pass_visits": sum(
            json.loads(path.read_text(encoding="utf-8")).get("status") == "PASS"
            for path in visit_manifests
        ),
        "rejected_runs": len(rejected_rows),
        "attempts_without_outcome_row": no_row_attempts,
        "unique_accepted_pcaps": len(pcap_hashes),
        "unique_accepted_tc_states": len(tc_hashes),
        "pcap_host_to_board_udp_packets_min": (
            min(pcap_packet_counts) if pcap_packet_counts else None
        ),
        "pcap_host_to_board_udp_packets_max": (
            max(pcap_packet_counts) if pcap_packet_counts else None
        ),
        "pcap_recount_skipped": args.skip_pcap_recount,
        "acceptance_boundary": {
            "type": "instrumentation_only",
            "rx_delivery_or_rtt_threshold_used": False,
        },
        "errors": errors,
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    output = args.output or root / "formal_audit_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(text, end="")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
