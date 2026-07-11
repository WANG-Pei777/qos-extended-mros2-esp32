#!/usr/bin/env python3
"""Audit a ROUND4 transport result set for analysis-level provenance consistency."""

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def load_rows(csv_path):
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_manifest(csv_path, row):
    manifest_path = csv_path.parent / f"{row['system']}_{row['condition']}_manifest.json"
    with manifest_path.open(encoding="utf-8") as handle:
        return manifest_path, json.load(handle)


def validator_path():
    return Path(__file__).with_name("validate_round4.py")


def validate_csv(csv_path):
    command = [sys.executable, str(validator_path()), str(csv_path)]
    return subprocess.run(command, check=False, text=True, capture_output=True)


def one_value(name, values, errors):
    if len(values) != 1:
        errors.append(f"{name} is not unique: {sorted(values)}")
        return None
    return next(iter(values))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_paths", nargs="+", type=Path)
    parser.add_argument("--expected-n", type=int, default=30)
    return parser.parse_args()


def main():
    args = parse_args()
    errors = []
    rows_by_condition = {}
    manifests = {}

    for csv_path in args.csv_paths:
        result = validate_csv(csv_path)
        if result.returncode != 0:
            errors.append(f"{csv_path}: validate_round4.py failed\n{result.stdout}{result.stderr}")
            continue

        rows = load_rows(csv_path)
        if len(rows) != args.expected_n:
            errors.append(f"{csv_path}: expected {args.expected_n} rows, got {len(rows)}")
            continue

        conditions = {row["condition"] for row in rows}
        if len(conditions) != 1:
            errors.append(f"{csv_path}: multiple conditions in one CSV: {sorted(conditions)}")
            continue

        condition = next(iter(conditions))
        if condition in rows_by_condition:
            errors.append(f"duplicate condition: {condition}")
            continue

        manifest_path, manifest = load_manifest(csv_path, rows[0])
        rows_by_condition[condition] = rows
        manifests[condition] = manifest
        if manifest["experiment"]["condition"] != condition:
            errors.append(f"{manifest_path}: condition mismatch")

    if errors:
        print("FAIL:")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)

    commit_hashes = {manifest["source"]["commit_hash"] for manifest in manifests.values()}
    worktree_states = {manifest["source"]["worktree_state"] for manifest in manifests.values()}
    board_ips = {manifest["experiment"]["board_ip"] for manifest in manifests.values()}
    host_binary_hashes = {manifest["host_binary"]["sha256"] for manifest in manifests.values()}
    link_gates = {manifest["experiment"]["link_gate_ms"] for manifest in manifests.values()}

    one_value("source commit", commit_hashes, errors)
    one_value("worktree state", worktree_states, errors)
    one_value("board IP", board_ips, errors)
    one_value("host binary sha256", host_binary_hashes, errors)
    one_value("link gate", link_gates, errors)
    if worktree_states != {"clean"}:
        errors.append(f"worktree state must be clean, got {sorted(worktree_states)}")

    firmware_by_qos = defaultdict(set)
    for condition, manifest in manifests.items():
        experiment = manifest["experiment"]
        qos_mode = experiment["qos_mode"]
        firmware_by_qos[qos_mode].add(manifest["firmware_binary"]["sha256"])
        if experiment["firmware_mode"] != qos_mode:
            errors.append(f"{condition}: firmware_mode does not match qos_mode")
        if not experiment["injection_layer"].startswith("transport_egress_netem_host_to_board_"):
            errors.append(f"{condition}: injection layer is not host-to-board netem")

    for qos_mode, firmware_hashes in sorted(firmware_by_qos.items()):
        one_value(f"{qos_mode} firmware sha256", firmware_hashes, errors)

    expected_conditions = {
        f"round4_transport_{qos}_{loss}pct"
        for qos in ("reliable", "best_effort")
        for loss in ("0", "1", "5", "10", "15")
    }
    actual_conditions = set(rows_by_condition)
    if actual_conditions != expected_conditions:
        errors.append(
            "condition set mismatch: "
            f"missing={sorted(expected_conditions - actual_conditions)} "
            f"extra={sorted(actual_conditions - expected_conditions)}"
        )

    if errors:
        print("FAIL:")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)

    print(f"PASS: {len(rows_by_condition)} conditions, {args.expected_n} rows each")
    print(f"commit={one_value('source commit', commit_hashes, [])}")
    print(f"board_ip={one_value('board IP', board_ips, [])}")
    for qos_mode, firmware_hashes in sorted(firmware_by_qos.items()):
        print(f"{qos_mode}_firmware_sha256={one_value(qos_mode, firmware_hashes, [])}")


if __name__ == "__main__":
    main()
