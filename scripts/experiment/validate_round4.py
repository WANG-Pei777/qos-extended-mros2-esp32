#!/usr/bin/env python3
"""Fail closed on formal ROUND4 CSV rows that violate the evidence protocol."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys


REQUIRED_COLUMNS = {
    "run_id", "system", "condition", "formal_run", "tx_count", "rx_count",
    "rx_raw_count", "rx_duplicate_count", "rx_malformed_count",
    "rx_pre_measurement_count", "rx_tracker_overflow_count", "rtt_count",
    "matched_pub", "matched_sub", "manifest_sha256", "worktree_state",
    "link_ping_avg_ms",
}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integer(row, field, errors):
    try:
        value = int(row[field])
        if value < 0:
            raise ValueError
        return value
    except (KeyError, ValueError):
        errors.append(f"run {row.get('run_id', '?')}: invalid {field}")
        return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--link-gate-ms", type=float, default=100.0)
    parser.add_argument("--allow-nonformal", action="store_true")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows or not REQUIRED_COLUMNS.issubset(rows[0]):
        raise SystemExit("FAIL: CSV does not use the top-tier ROUND4 schema")

    errors = []
    manifest_cache = {}
    for row in rows:
        run_id = row.get("run_id", "?")
        if not args.allow_nonformal and row["formal_run"] != "1":
            errors.append(f"run {run_id}: non-formal row")
        if row["worktree_state"] != "clean":
            errors.append(f"run {run_id}: worktree is not clean")

        tx = integer(row, "tx_count", errors)
        unique_rx = integer(row, "rx_count", errors)
        raw_rx = integer(row, "rx_raw_count", errors)
        duplicates = integer(row, "rx_duplicate_count", errors)
        malformed = integer(row, "rx_malformed_count", errors)
        pre_measurement = integer(row, "rx_pre_measurement_count", errors)
        overflow = integer(row, "rx_tracker_overflow_count", errors)
        rtt_count = integer(row, "rtt_count", errors)

        if tx == 0 or rtt_count == 0:
            errors.append(f"run {run_id}: missing TX or RTT evidence")
        if unique_rx > tx:
            errors.append(f"run {run_id}: unique RX exceeds TX")
        if raw_rx != unique_rx + duplicates + malformed + pre_measurement + overflow:
            errors.append(f"run {run_id}: RX classification does not reconcile")
        if rtt_count > unique_rx:
            errors.append(f"run {run_id}: RTT samples exceed unique RX")
        if row["matched_pub"] != "1" or row["matched_sub"] != "1":
            errors.append(f"run {run_id}: endpoint match failed")
        try:
            if float(row["link_ping_avg_ms"]) >= args.link_gate_ms:
                errors.append(f"run {run_id}: link gate failed")
        except ValueError:
            errors.append(f"run {run_id}: invalid link ping")

        manifest_name = f"{row['system']}_{row['condition']}_manifest.json"
        manifest_path = csv_path.parent / manifest_name
        if manifest_path not in manifest_cache:
            try:
                manifest_cache[manifest_path] = (file_hash(manifest_path), json.loads(manifest_path.read_text()))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"run {run_id}: unreadable manifest ({exc})")
                continue
        actual_hash, manifest = manifest_cache[manifest_path]
        if row["manifest_sha256"] != actual_hash:
            errors.append(f"run {run_id}: manifest checksum mismatch")
        if manifest["experiment"]["condition"] != row["condition"]:
            errors.append(f"run {run_id}: manifest condition mismatch")

    if errors:
        print("FAIL:")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)

    print(f"PASS: {len(rows)} rows satisfy the ROUND4 evidence protocol")


if __name__ == "__main__":
    main()
