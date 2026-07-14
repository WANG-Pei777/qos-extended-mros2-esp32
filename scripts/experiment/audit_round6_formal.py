#!/usr/bin/env python3
"""Audit a completed Round 6 formal result set before analysis."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


EXPECTED_CELLS = {
    f"d{depth:02d}_h{heartbeat:04d}"
    for depth in (5, 10, 20, 40)
    for heartbeat in (250, 1000, 4000)
}
TC_FINAL_RE = re.compile(
    r"phase=final.*?random type netrand drop val 7.*?"
    r"Sent \d+ bytes (\d+) pkt \(dropped (\d+),",
    re.DOTALL,
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_tc_state(text):
    match = TC_FINAL_RE.search(text)
    if not match:
        raise ValueError("missing final gact val 7 statistics")
    packets, dropped = map(int, match.groups())
    if packets <= 0 or dropped <= 0 or dropped >= packets:
        raise ValueError(
            f"invalid final gact counters: packets={packets}, dropped={dropped}"
        )
    return packets, dropped


def require_hash(path, expected, label, errors):
    candidate = Path(path)
    if not candidate.is_file():
        errors.append(f"{label}: missing file {candidate}")
        return
    actual = sha256_file(candidate)
    if actual != expected:
        errors.append(f"{label}: hash mismatch {actual} != {expected}")


def condition_csv(results_root, condition):
    return results_root / f"mros2qos_{condition}.csv"


def audit(results_root):
    results_root = Path(results_root).resolve()
    errors = []
    design_path = results_root / "design_manifest.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "COMPLETE":
        errors.append(f"design status is {design.get('status')!r}, not COMPLETE")
    if design.get("accepted_runs_per_visit") != 3:
        errors.append("accepted_runs_per_visit is not 3")
    impairment = design.get("impairment", {})
    if impairment.get("inverse_probability_denominator") != 7:
        errors.append("gact denominator is not 7")

    ledger_path = results_root / "acceptance_ledger.csv"
    ledger = read_csv(ledger_path)
    accepted = [row for row in ledger if row["accepted"] == "1"]
    rejected = [row for row in ledger if row["accepted"] != "1"]
    if len(accepted) != 360:
        errors.append(f"expected 360 accepted rows, got {len(accepted)}")

    cell_counts = Counter(row["cell"] for row in accepted)
    if set(cell_counts) != EXPECTED_CELLS:
        errors.append(
            f"cell set mismatch: missing={sorted(EXPECTED_CELLS - set(cell_counts))} "
            f"extra={sorted(set(cell_counts) - EXPECTED_CELLS)}"
        )
    for cell in sorted(EXPECTED_CELLS):
        if cell_counts[cell] != 30:
            errors.append(f"{cell}: expected 30 accepted rows, got {cell_counts[cell]}")

    block_cell_counts = Counter(
        (int(row["block"]), row["cell"]) for row in accepted
    )
    for block in range(1, 11):
        for cell in EXPECTED_CELLS:
            if block_cell_counts[(block, cell)] != 3:
                errors.append(
                    f"block {block} {cell}: expected 3 accepted rows, "
                    f"got {block_cell_counts[(block, cell)]}"
                )

    ordinals = defaultdict(list)
    for row in accepted:
        ordinals[row["cell"]].append(int(row["accepted_ordinal"]))
    for cell, values in ordinals.items():
        if sorted(values) != list(range(1, 31)):
            errors.append(f"{cell}: accepted ordinals are not exactly 1..30")

    visit_paths = sorted((results_root / "visits").glob("*/manifest.json"))
    if len(visit_paths) != 120:
        errors.append(f"expected 120 visit manifests, got {len(visit_paths)}")
    visit_keys = set()
    for path in visit_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        schedule = manifest["schedule"]
        key = (schedule["block"], schedule["visit"], schedule["cell"])
        visit_keys.add(key)
        if manifest.get("status") != "PASS":
            errors.append(f"{path}: visit status is not PASS")
        if len(manifest.get("accepted_runs", [])) != 3:
            errors.append(f"{path}: does not contain 3 accepted runs")
        if manifest.get("harness_commit") != design.get("harness_commit"):
            errors.append(f"{path}: harness commit mismatch")
    if len(visit_keys) != 120:
        errors.append("visit schedule keys are not unique")

    rows_by_condition = {}
    samples_by_condition = {}
    for condition in sorted({row["condition"] for row in ledger}):
        csv_path = condition_csv(results_root, condition)
        rows = read_csv(csv_path)
        rows_by_condition[condition] = {
            row["run_id"]: row for row in rows
        }
        if len(rows_by_condition[condition]) != len(rows):
            errors.append(f"{condition}: duplicate raw run_id")
        samples_path = results_root / f"mros2qos_{condition}_rtt_samples.csv"
        samples = read_csv(samples_path)
        grouped = Counter(row["run_id"] for row in samples)
        samples_by_condition[condition] = grouped

    pcap_hashes = set()
    tc_hashes = set()
    serial_hashes = set()
    actual_drop_rates = []
    board_udp_counts = []
    pcap_by_hash = {
        sha256_file(path): path
        for path in (results_root / "pcaps").glob("*.pcapng")
    }
    for row in accepted:
        label = f"{row['cell']} run {row['run_id']}"
        raw = rows_by_condition.get(row["condition"], {}).get(row["run_id"])
        if raw is None:
            errors.append(f"{label}: missing raw result row")
            continue
        expected = {
            "formal_run": "1",
            "condition": row["condition"],
            "qos_mode": "reliable",
            "firmware_mode": "reliable",
            "host_mode": "cpp",
            "commit_hash": design["harness_commit"],
            "worktree_state": "clean",
            "manifest_sha256": row["manifest_sha256"],
        }
        for field, value in expected.items():
            if raw.get(field) != value:
                errors.append(f"{label}: raw {field} mismatch")
        serial_path = results_root / (
            f"mros2qos_{row['condition']}_run{row['run_id']}_serial.log"
        )
        require_hash(serial_path, row["serial_sha256"], label, errors)
        serial_hashes.add(row["serial_sha256"])
        manifest_path = results_root / f"mros2qos_{row['condition']}_manifest.json"
        require_hash(manifest_path, row["manifest_sha256"], label, errors)

        pcap_path = pcap_by_hash.get(row["pcap_sha256"])
        if pcap_path is None:
            errors.append(f"{label}: PCAP hash not found")
        pcap_hashes.add(row["pcap_sha256"])
        board_count = int(row["pcap_board_to_host_udp_packets"])
        if board_count <= 0:
            errors.append(f"{label}: no board-to-host UDP packets")
        board_udp_counts.append(board_count)

        tc_path = None if pcap_path is None else Path(f"{pcap_path}.tc.txt")
        if tc_path is None or not tc_path.is_file():
            errors.append(f"{label}: tc state file missing")
        else:
            require_hash(tc_path, row["tc_state_sha256"], label, errors)
            try:
                packets, dropped = parse_tc_state(
                    tc_path.read_text(encoding="utf-8")
                )
                actual_drop_rates.append(dropped / packets)
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
        tc_hashes.add(row["tc_state_sha256"])

        expected_samples = int(raw["rtt_count"])
        observed_samples = samples_by_condition[row["condition"]][row["run_id"]]
        if observed_samples != expected_samples:
            errors.append(
                f"{label}: RTT sidecar count {observed_samples} != "
                f"row rtt_count {expected_samples}"
            )

    if len(pcap_hashes) != 360:
        errors.append(f"accepted PCAP hashes are not unique: {len(pcap_hashes)}")
    if len(tc_hashes) != 360:
        errors.append(f"accepted tc hashes are not unique: {len(tc_hashes)}")
    if len(serial_hashes) != 360:
        errors.append(f"accepted serial hashes are not unique: {len(serial_hashes)}")

    report = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "results_root": str(results_root),
        "design_manifest_sha256": sha256_file(design_path),
        "acceptance_ledger_sha256": sha256_file(ledger_path),
        "harness_commit": design.get("harness_commit"),
        "accepted_runs": len(accepted),
        "rejected_runs": len(rejected),
        "pass_visits": len(visit_paths),
        "cells": len(cell_counts),
        "accepted_per_cell": dict(sorted(cell_counts.items())),
        "unique_accepted_pcaps": len(pcap_hashes),
        "unique_accepted_tc_states": len(tc_hashes),
        "board_udp_packets_min": min(board_udp_counts, default=0),
        "board_udp_packets_max": max(board_udp_counts, default=0),
        "actual_drop_rate_min": min(actual_drop_rates, default=0),
        "actual_drop_rate_max": max(actual_drop_rates, default=0),
        "actual_drop_rate_mean": (
            sum(actual_drop_rates) / len(actual_drop_rates)
            if actual_drop_rates else 0
        ),
        "errors": errors,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.results_root)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
