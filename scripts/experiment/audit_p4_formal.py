#!/usr/bin/env python3
"""Audit a completed P4 formal result set before confirmatory analysis."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_p4_formal import LOSS_SPECS, expected_injection
from run_round6_smoke_gates import sha256_file


EXPECTED_CELLS = {
    f"{qos}_target{loss:02d}"
    for qos in ("reliable", "best_effort")
    for loss in LOSS_SPECS
}
FINAL_GACT_RE = re.compile(
    r"phase=final.*?random type netrand drop val (\d+).*?"
    r"Sent \d+ bytes (\d+) pkt \(dropped (\d+),",
    re.DOTALL,
)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_tc_state(text, target_loss):
    if target_loss == 0:
        if "phase=baseline" not in text:
            raise ValueError("missing baseline tc state")
        if "random type netrand drop" in text:
            raise ValueError("0% control unexpectedly contains random gact")
        return {"packets": 0, "dropped": 0, "observed_rate": 0.0}
    match = FINAL_GACT_RE.search(text)
    if not match:
        raise ValueError("missing final gact statistics")
    denominator, packets, dropped = map(int, match.groups())
    expected_denominator = LOSS_SPECS[target_loss]["denominator"]
    if denominator != expected_denominator:
        raise ValueError(
            f"gact denominator {denominator} != {expected_denominator}"
        )
    if packets <= 0 or dropped <= 0 or dropped >= packets:
        raise ValueError(
            f"invalid gact counters: packets={packets}, dropped={dropped}"
        )
    return {
        "packets": packets,
        "dropped": dropped,
        "observed_rate": dropped / packets,
    }


def require_hash(path, expected, label, errors):
    path = Path(path)
    if not path.is_file():
        errors.append(f"{label}: missing file {path}")
        return False
    actual = sha256_file(path)
    if actual != expected:
        errors.append(f"{label}: hash mismatch {actual} != {expected}")
        return False
    return True


def audit(results_root):
    results_root = Path(results_root).resolve()
    errors = []
    design_path = results_root / "design_manifest.json"
    ledger_path = results_root / "acceptance_ledger.csv"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    ledger = read_csv(ledger_path)
    accepted = [row for row in ledger if row["accepted"] == "1"]
    rejected = [row for row in ledger if row["accepted"] != "1"]
    if design.get("classification") != "p4_independent_window_formal_replication":
        errors.append("unexpected design classification")
    if design.get("status") != "COMPLETE":
        errors.append(f"design status is {design.get('status')!r}, not COMPLETE")
    if design.get("accepted_runs_per_visit") != 3:
        errors.append("accepted_runs_per_visit is not 3")
    window_record = design.get("window_manifest", {})
    window_path = Path(window_record.get("path", ""))
    require_hash(
        window_path,
        window_record.get("sha256_at_start", ""),
        "window manifest",
        errors,
    )
    firmware_record = design.get("firmware_set_manifest", {})
    require_hash(
        firmware_record.get("path", ""),
        firmware_record.get("sha256", ""),
        "firmware set manifest",
        errors,
    )
    if len(accepted) != 180:
        errors.append(f"expected 180 accepted rows, got {len(accepted)}")

    cell_counts = Counter(row["cell"] for row in accepted)
    if set(cell_counts) != EXPECTED_CELLS:
        errors.append(
            f"cell set mismatch: missing={sorted(EXPECTED_CELLS - set(cell_counts))} "
            f"extra={sorted(set(cell_counts) - EXPECTED_CELLS)}"
        )
    for cell in sorted(EXPECTED_CELLS):
        if cell_counts[cell] != 30:
            errors.append(f"{cell}: expected 30 accepted rows, got {cell_counts[cell]}")

    block_counts = Counter(
        (int(row["block"]), row["cell"]) for row in accepted
    )
    for block in range(1, 11):
        for cell in EXPECTED_CELLS:
            if block_counts[(block, cell)] != 3:
                errors.append(
                    f"block {block} {cell}: expected 3 accepted rows, "
                    f"got {block_counts[(block, cell)]}"
                )
    ordinals = defaultdict(list)
    for row in accepted:
        ordinals[row["cell"]].append(int(row["accepted_ordinal"]))
    for cell, values in ordinals.items():
        if sorted(values) != list(range(1, 31)):
            errors.append(f"{cell}: accepted ordinals are not exactly 1..30")

    visit_paths = sorted((results_root / "visits").glob("*/manifest.json"))
    if len(visit_paths) != 60:
        errors.append(f"expected 60 visit manifests, got {len(visit_paths)}")
    visit_keys = set()
    for path in visit_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        schedule = manifest["schedule"]
        key = (int(schedule["block"]), int(schedule["visit"]), schedule["id"])
        visit_keys.add(key)
        if manifest.get("status") != "PASS":
            errors.append(f"{path}: visit status is not PASS")
        if len(manifest.get("accepted_runs", [])) != 3:
            errors.append(f"{path}: does not contain 3 accepted runs")
        if manifest.get("harness_commit") != design.get("harness_commit"):
            errors.append(f"{path}: harness commit mismatch")
    if len(visit_keys) != 60:
        errors.append("visit schedule keys are not unique")

    rows_by_condition = {}
    samples_by_condition = {}
    for condition in sorted({row["condition"] for row in ledger}):
        rows = read_csv(results_root / f"mros2qos_{condition}.csv")
        rows_by_condition[condition] = {row["run_id"]: row for row in rows}
        if len(rows_by_condition[condition]) != len(rows):
            errors.append(f"{condition}: duplicate raw run_id")
        sample_path = results_root / f"mros2qos_{condition}_rtt_samples.csv"
        grouped = Counter(row["run_id"] for row in read_csv(sample_path))
        samples_by_condition[condition] = grouped

    pcap_by_hash = {
        sha256_file(path): path for path in (results_root / "pcaps").glob("*.pcapng")
    }
    pcap_hashes = set()
    tc_hashes = set()
    serial_hashes = set()
    board_udp_counts = []
    observed_rates = defaultdict(list)
    for row in accepted:
        label = f"{row['cell']} run {row['run_id']}"
        raw = rows_by_condition.get(row["condition"], {}).get(row["run_id"])
        if raw is None:
            errors.append(f"{label}: missing raw result row")
            continue
        qos = row["qos"]
        target_loss = int(row["target_loss_percent"])
        expected = {
            "formal_run": "1",
            "condition": row["condition"],
            "qos_mode": qos,
            "firmware_mode": qos,
            "host_mode": "cpp",
            "injection_layer": expected_injection(target_loss),
            "commit_hash": design["harness_commit"],
            "worktree_state": "clean",
            "manifest_sha256": row["manifest_sha256"],
        }
        for field, value in expected.items():
            if raw.get(field) != value:
                errors.append(f"{label}: raw {field} mismatch")
        spec = LOSS_SPECS[target_loss]
        if int(row["gact_denominator"]) != spec["denominator"]:
            errors.append(f"{label}: acceptance denominator mismatch")
        if abs(float(row["effective_loss_percent"]) - spec["effective"]) > 1e-12:
            errors.append(f"{label}: acceptance effective-loss mismatch")
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
                parsed = parse_tc_state(
                    tc_path.read_text(encoding="utf-8"), target_loss
                )
                observed_rates[target_loss].append(parsed["observed_rate"])
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

    for label, values in (
        ("PCAP", pcap_hashes),
        ("tc state", tc_hashes),
        ("serial", serial_hashes),
    ):
        if len(values) != 180:
            errors.append(f"accepted {label} hashes are not unique: {len(values)}")
    rate_summary = {
        str(loss): {
            "n": len(values),
            "min": min(values, default=0),
            "mean": sum(values) / len(values) if values else 0,
            "max": max(values, default=0),
        }
        for loss, values in sorted(observed_rates.items())
    }
    return {
        "schema_version": 1,
        "classification": "p4_formal_audit",
        "status": "PASS" if not errors else "FAIL",
        "results_root": str(results_root),
        "design_manifest_sha256": sha256_file(design_path),
        "acceptance_ledger_sha256": sha256_file(ledger_path),
        "harness_commit": design.get("harness_commit"),
        "accepted_runs": len(accepted),
        "rejected_runs": len(rejected),
        "pass_visits": len(visit_paths),
        "accepted_per_cell": dict(sorted(cell_counts.items())),
        "unique_accepted_pcaps": len(pcap_hashes),
        "unique_accepted_tc_states": len(tc_hashes),
        "board_udp_packets_min": min(board_udp_counts, default=0),
        "board_udp_packets_max": max(board_udp_counts, default=0),
        "observed_gact_drop_rate_by_target": rate_summary,
        "errors": errors,
    }


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
