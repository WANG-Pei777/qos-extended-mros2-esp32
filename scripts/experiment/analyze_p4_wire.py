#!/usr/bin/env python3
"""Extract prespecified P4 RTPS packet-level secondary outcomes."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_rtps_timeline import ints, sha256_file, tshark_rows


DATA_ID = 0x15
HEARTBEAT_ID = 0x07
ACKNACK_ID = 0x06


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def endpoint_for(source, destination, board_ip, host_ip):
    if source == board_ip:
        return "board_to_host" if destination == host_ip else "board_to_multicast"
    if source == host_ip:
        return "host_to_board" if destination == board_ip else "host_to_multicast"
    return "other"


def summarize_rows(rows, board_ip, host_ip):
    counts = Counter()
    times = []
    for row in rows:
        if row["frame.time_relative"]:
            times.append(float(row["frame.time_relative"]))
        endpoint = endpoint_for(row["ip.src"], row["ip.dst"], board_ip, host_ip)
        for submessage_id in ints(row["rtps.sm.id"]):
            if submessage_id == DATA_ID:
                counts[(endpoint, "data")] += 1
            elif submessage_id == HEARTBEAT_ID:
                counts[(endpoint, "heartbeat")] += 1
            elif submessage_id == ACKNACK_ID:
                counts[(endpoint, "acknack")] += 1
    return {
        "duration_s": max(times) - min(times) if times else 0.0,
        "rtps_packets": len(rows),
        "board_to_host_data": counts[("board_to_host", "data")],
        "board_to_host_heartbeat": counts[("board_to_host", "heartbeat")],
        "board_to_host_acknack": counts[("board_to_host", "acknack")],
        "host_to_board_data": counts[("host_to_board", "data")],
        "host_to_board_heartbeat": counts[("host_to_board", "heartbeat")],
        "host_to_board_acknack": counts[("host_to_board", "acknack")],
        "board_to_multicast_data": counts[("board_to_multicast", "data")],
        "board_to_multicast_heartbeat": counts[
            ("board_to_multicast", "heartbeat")
        ],
        "host_to_multicast_acknack": counts[
            ("host_to_multicast", "acknack")
        ],
    }


def summarize_pcap(path, board_ip, host_ip):
    rows = list(tshark_rows(path))
    summary = summarize_rows(rows, board_ip, host_ip)
    summary.update({
        "pcap": str(path),
        "pcap_sha256": sha256_file(path),
    })
    return summary


def mean(values):
    return sum(values) / len(values)


def cell_summary(rows):
    metrics = (
        "rtps_packets",
        "board_to_host_data",
        "board_to_host_heartbeat",
        "host_to_board_acknack",
        "host_to_board_data",
        "host_to_board_heartbeat",
        "board_to_host_acknack",
    )
    grouped = {}
    for row in rows:
        grouped.setdefault(
            (row["qos"], row["target_loss_percent"]), []
        ).append(row)
    output = []
    for (qos, loss), selected in sorted(grouped.items()):
        record = {
            "qos": qos,
            "target_loss_percent": loss,
            "n_runs": len(selected),
        }
        for metric in metrics:
            values = [float(row[metric]) for row in selected]
            record[f"{metric}_mean"] = mean(values)
            record[f"{metric}_min"] = min(values)
            record[f"{metric}_max"] = max(values)
        output.append(record)
    return output


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--host-ip", required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit_report.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS":
        raise SystemExit("P4 wire analysis requires a PASS formal audit")
    accepted = [
        row for row in read_csv(args.results_root / "acceptance_ledger.csv")
        if row["accepted"] == "1"
    ]
    pcap_by_hash = {
        sha256_file(path): path
        for path in (args.results_root / "pcaps").glob("*.pcapng")
    }
    rows = []
    for index, ledger_row in enumerate(accepted, start=1):
        pcap = pcap_by_hash.get(ledger_row["pcap_sha256"])
        if pcap is None:
            raise SystemExit(
                f"accepted PCAP unavailable: {ledger_row['pcap_sha256']}"
            )
        record = {
            "block": int(ledger_row["block"]),
            "visit": int(ledger_row["visit"]),
            "cell": ledger_row["cell"],
            "condition": ledger_row["condition"],
            "run_id": int(ledger_row["run_id"]),
            "accepted_ordinal": int(ledger_row["accepted_ordinal"]),
            "qos": ledger_row["qos"],
            "target_loss_percent": int(ledger_row["target_loss_percent"]),
        }
        record.update(summarize_pcap(pcap, args.board_ip, args.host_ip))
        rows.append(record)
        print(f"[wire] {index}/180 {ledger_row['cell']} run {ledger_row['run_id']}")
    if len(rows) != 180:
        raise SystemExit(f"expected 180 accepted wire runs, got {len(rows)}")
    summaries = cell_summary(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_path = args.output_dir / "p4_wire_run_outcomes.csv"
    cell_path = args.output_dir / "p4_wire_cell_summary.csv"
    write_csv(run_path, rows)
    write_csv(cell_path, summaries)
    manifest = {
        "schema_version": 1,
        "classification": "p4_rtps_packet_level_secondary_analysis",
        "analysis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "audit_report_sha256": sha256_file(args.audit_report),
        "acceptance_ledger_sha256": sha256_file(
            args.results_root / "acceptance_ledger.csv"
        ),
        "wire_run_outcomes_sha256": sha256_file(run_path),
        "wire_cell_summary_sha256": sha256_file(cell_path),
        "accepted_runs": len(rows),
        "board_ip": args.board_ip,
        "host_ip": args.host_ip,
        "claim_boundary": (
            "Packet-level observations at the capture hook; ingress capture may "
            "precede tc drop and does not independently prove retransmission."
        ),
    }
    (args.output_dir / "p4_wire_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
