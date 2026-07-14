#!/usr/bin/env python3
"""Extract per-run Round 6 RTPS repair outcomes from accepted PCAPs."""

import argparse
import csv
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import reconstruct_rtps_app_samples as rtps
from analyze_round6_factorial import cell_from_condition, sha256_file


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def median_or_blank(values):
    return statistics.median(values) if values else ""


def select_board_run(events, board_runs, board_ip):
    counts = Counter(
        event["run_id"]
        for event in events
        if event["source_ip"] == board_ip
        and event["flow"] == "board_to_host_app"
        and event["event_type"] == "data"
        and event.get("run_id") is not None
    )
    if not counts:
        raise ValueError("no board application DATA run found")
    run_id, _count = counts.most_common(1)[0]
    if run_id not in board_runs.values():
        raise ValueError("selected board run is absent from GUID map")
    return run_id


def derive_wire_metrics(events, run_id):
    flow = "board_to_host_app"
    summary = rtps.summarize_flow(events, run_id, flow)
    links = rtps.reconstruct_nack_links(events, run_id, flow)
    heartbeat_events = sorted(
        (
            event for event in events
            if event.get("run_id") == run_id
            and event["flow"] == flow
            and event["event_type"] == "heartbeat"
        ),
        key=lambda event: event["time_s"],
    )
    unique_heartbeats = []
    for event in heartbeat_events:
        if (
            not unique_heartbeats
            or event["time_s"] - unique_heartbeats[-1]["time_s"] >= 0.010
        ):
            unique_heartbeats.append(event)
    heartbeats = [event["time_s"] for event in unique_heartbeats]
    heartbeat_intervals = [
        1000.0 * (right - left)
        for left, right in zip(heartbeats, heartbeats[1:])
    ]
    raw_heartbeat_observations = sum(
        1 for event in events
        if event.get("run_id") == run_id
        and event["flow"] == flow
        and event["event_type"] == "heartbeat"
    )
    final_heartbeat_time = heartbeats[-1] if heartbeats else None
    uncensored = [
        link for link in links
        if final_heartbeat_time is None
        or link["ack_time_s"] < final_heartbeat_time
    ]
    unresolved_all = {
        link["requested_sequence"]
        for link in links
        if not link["post_nack_data_observed"]
    }
    unresolved_uncensored = {
        link["requested_sequence"]
        for link in uncensored
        if not link["post_nack_data_observed"]
    }
    requested_all = {link["requested_sequence"] for link in links}
    requested_uncensored = {
        link["requested_sequence"] for link in uncensored
    }
    repaired_latencies = [
        float(link["nack_to_next_data_ms"])
        for link in links
        if link["post_nack_data_observed"]
    ]
    strong = any(
        link["prior_data_observed"]
        and link["post_nack_data_observed"]
        for link in links
    )
    return {
        "wire_prior_and_post_nack_data": int(strong),
        "wire_requested_unique_sequences": len(requested_all),
        "wire_unresolved_unique_sequences_all": len(unresolved_all),
        "wire_requested_unique_sequences_uncensored": len(requested_uncensored),
        "wire_unresolved_unique_sequences_uncensored": len(unresolved_uncensored),
        "wire_right_censored_request_observations": len(links) - len(uncensored),
        "wire_nack_to_data_median_ms": median_or_blank(repaired_latencies),
        "wire_acknack_observations": summary["acknack_observations"],
        "wire_data_observations": summary["data_observations"],
        "wire_data_duplicate_observations": summary["data_duplicate_observations"],
        "wire_data_repeated_sequences": summary["data_repeated_sequences"],
        "wire_heartbeat_observations": len(unique_heartbeats),
        "wire_heartbeat_raw_observations": raw_heartbeat_observations,
        "wire_heartbeat_interval_median_ms": median_or_blank(
            heartbeat_intervals
        ),
        "wire_link_observations": len(links),
        "wire_final_heartbeat_time_s": (
            final_heartbeat_time if final_heartbeat_time is not None else ""
        ),
    }


def analyze_one(task):
    ledger_row, pcap_path, board_ip, host_ip = task
    events = []
    for tshark_row in rtps.tshark_rows(Path(pcap_path)):
        event = rtps.classify_row(tshark_row, board_ip, host_ip)
        if event is not None:
            events.append(event)
    board_runs, host_runs = rtps.assign_runs(events, board_ip, host_ip)
    run_id = select_board_run(events, board_runs, board_ip)
    metrics = derive_wire_metrics(events, run_id)
    depth, heartbeat = cell_from_condition(ledger_row["condition"])
    return {
        "block": int(ledger_row["block"]),
        "visit": int(ledger_row["visit"]),
        "cell": ledger_row["cell"],
        "condition": ledger_row["condition"],
        "run_id": int(ledger_row["run_id"]),
        "accepted_ordinal": int(ledger_row["accepted_ordinal"]),
        "depth": depth,
        "heartbeat_ms": heartbeat,
        "pcap": str(pcap_path),
        "pcap_sha256": ledger_row["pcap_sha256"],
        "board_guid_runs": len(board_runs),
        "host_guid_runs": len(host_runs),
        **metrics,
    }


def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize_cells(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["depth"], row["heartbeat_ms"])].append(row)
    output = []
    for (depth, heartbeat), selected in sorted(grouped.items()):
        output.append({
            "depth": depth,
            "heartbeat_ms": heartbeat,
            "n_runs": len(selected),
            "runs_with_prior_and_post_nack_data": sum(
                row["wire_prior_and_post_nack_data"] for row in selected
            ),
            "proportion_prior_and_post_nack_data": statistics.mean(
                row["wire_prior_and_post_nack_data"] for row in selected
            ),
            "unresolved_unique_sequences_all_mean": statistics.mean(
                row["wire_unresolved_unique_sequences_all"] for row in selected
            ),
            "unresolved_unique_sequences_uncensored_mean": statistics.mean(
                row["wire_unresolved_unique_sequences_uncensored"]
                for row in selected
            ),
            "nack_to_data_median_run_median_ms": median_or_blank([
                float(row["wire_nack_to_data_median_ms"])
                for row in selected
                if row["wire_nack_to_data_median_ms"] != ""
            ]),
            "heartbeat_interval_run_median_ms": median_or_blank([
                float(row["wire_heartbeat_interval_median_ms"])
                for row in selected
                if row["wire_heartbeat_interval_median_ms"] != ""
            ]),
            "acknack_observations_mean": statistics.mean(
                row["wire_acknack_observations"] for row in selected
            ),
            "duplicate_data_observations_mean": statistics.mean(
                row["wire_data_duplicate_observations"] for row in selected
            ),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_root", type=Path)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--host-ip", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    accepted = [
        row for row in read_csv(args.results_root / "acceptance_ledger.csv")
        if row["accepted"] == "1"
    ]
    pcap_by_hash = {
        sha256_file(path): path
        for path in (args.results_root / "pcaps").glob("*.pcapng")
    }
    tasks = []
    for row in accepted:
        pcap = pcap_by_hash.get(row["pcap_sha256"])
        if pcap is None:
            raise SystemExit(f"missing accepted PCAP {row['pcap_sha256']}")
        tasks.append((row, str(pcap), args.board_ip, args.host_ip))

    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for index, row in enumerate(executor.map(analyze_one, tasks), start=1):
            rows.append(row)
            if index % 30 == 0:
                print(f"[wire] analyzed {index}/{len(tasks)}", flush=True)
    rows.sort(key=lambda row: (row["block"], row["visit"], row["accepted_ordinal"]))
    if len(rows) != 360:
        raise SystemExit(f"expected 360 wire rows, got {len(rows)}")
    cell_rows = summarize_cells(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_path = args.output_dir / "round6_wire_run_outcomes.csv"
    cell_path = args.output_dir / "round6_wire_cell_summary.csv"
    write_csv(run_path, rows)
    write_csv(cell_path, cell_rows)
    manifest = {
        "schema_version": 1,
        "classification": "round6_application_entity_rtps_reconstruction",
        "results_root": str(args.results_root.resolve()),
        "acceptance_ledger_sha256": sha256_file(
            args.results_root / "acceptance_ledger.csv"
        ),
        "analysis_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "board_ip": args.board_ip,
        "host_ip": args.host_ip,
        "accepted_pcaps": len(rows),
        "workers": args.workers,
        "run_outcomes_sha256": sha256_file(run_path),
        "cell_summary_sha256": sha256_file(cell_path),
        "right_censoring_rule": "exclude ACKNACK requests at or after the final observed board-writer heartbeat",
        "claim_boundary": "ingress capture can observe DATA before tc drops it; wire evidence is not application-delivery proof",
    }
    (args.output_dir / "wire_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
