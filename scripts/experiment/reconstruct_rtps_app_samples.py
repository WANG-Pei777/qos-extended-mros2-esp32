#!/usr/bin/env python3
"""Reconstruct conservative application-entity RTPS sequence evidence."""

import argparse
import csv
import hashlib
import re
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path


CONDITION_RE = re.compile(
    r"round4_transport_(reliable|best_effort)_(\d+)pct_"
    r"(host_to_board|board_to_host)"
)
FIELDS = [
    "frame.number",
    "frame.time_relative",
    "ip.src",
    "ip.dst",
    "rtps.guidPrefix.src",
    "rtps.guidPrefix.dst",
    "rtps.sm.id",
    "rtps.sm.rdEntityId.entityKey",
    "rtps.sm.rdEntityId.entityKind",
    "rtps.sm.wrEntityId.entityKey",
    "rtps.sm.wrEntityId.entityKind",
    "rtps.sm.seqNumber",
    "rtps.bitmap.num_bits",
    "rtps.bitmap",
    "rtps.acknack.count",
    "rtps.heartbeat_count",
    "_ws.col.Info",
]

DATA_ID = 0x15
HEARTBEAT_ID = 0x07
ACKNACK_ID = 0x06

BOARD_WRITER = (0x000001, 0x03)
HOST_READER = (0x000012, 0x04)
HOST_WRITER = (0x000013, 0x03)
BOARD_READER = (0x000002, 0x04)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_values(value):
    return [item for item in value.split(",") if item]


def parsed_ints(value):
    output = []
    for item in split_values(value):
        try:
            output.append(int(item, 0))
        except ValueError:
            continue
    return output


def first_int(value):
    values = parsed_ints(value)
    return values[0] if values else None


def normalize_guid(value):
    return value.replace(":", "").lower()


def decode_sequence_set(base_sequence, num_bits, bitmap):
    """Decode RTPS SequenceNumberSet words as displayed by tshark."""
    if base_sequence is None or not num_bits or not bitmap:
        return []
    raw = bytes.fromhex(bitmap.replace(":", ""))
    missing = []
    for bit_index in range(num_bits):
        word_offset = (bit_index // 32) * 4
        word_bytes = raw[word_offset:word_offset + 4]
        if len(word_bytes) < 4:
            break
        word = int.from_bytes(word_bytes, byteorder="little")
        mask = 1 << (31 - (bit_index % 32))
        if word & mask:
            missing.append(base_sequence + bit_index)
    return missing


def tshark_rows(path):
    command = [
        "tshark",
        "-r",
        str(path),
        "-Y",
        "rtps",
        "-T",
        "fields",
        "-E",
        "separator=\t",
        "-E",
        "occurrence=a",
    ]
    for field in FIELDS:
        command.extend(["-e", field])
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    for line in result.stdout.splitlines():
        values = line.split("\t")
        values.extend([""] * (len(FIELDS) - len(values)))
        yield dict(zip(FIELDS, values))


def condition_from_path(path):
    match = CONDITION_RE.search(path.name)
    if match is None:
        raise ValueError(f"cannot parse QoS/loss/direction from {path.name}")
    return match.group(1), int(match.group(2)), match.group(3)


def endpoint_tuple(row, prefix):
    key = first_int(row[f"rtps.sm.{prefix}EntityId.entityKey"])
    kind = first_int(row[f"rtps.sm.{prefix}EntityId.entityKind"])
    return key, kind


def classify_row(row, board_ip, host_ip):
    submessages = set(parsed_ints(row["rtps.sm.id"]))
    writer = endpoint_tuple(row, "wr")
    reader = endpoint_tuple(row, "rd")
    source_guid = normalize_guid(row["rtps.guidPrefix.src"])
    destination_guid = normalize_guid(row["rtps.guidPrefix.dst"])
    source_ip = row["ip.src"]
    time_s = float(row["frame.time_relative"])

    flow = None
    event_type = None
    if writer == BOARD_WRITER and reader == HOST_READER:
        flow = "board_to_host_app"
        if DATA_ID in submessages and source_ip == board_ip:
            event_type = "data"
        elif HEARTBEAT_ID in submessages and source_ip == board_ip:
            event_type = "heartbeat"
        elif ACKNACK_ID in submessages and source_ip == host_ip:
            event_type = "acknack"
    elif writer == HOST_WRITER and reader == BOARD_READER:
        flow = "host_to_board_reply"
        if DATA_ID in submessages and source_ip == host_ip:
            event_type = "data"
        elif HEARTBEAT_ID in submessages and source_ip == host_ip:
            event_type = "heartbeat"
        elif ACKNACK_ID in submessages and source_ip == board_ip:
            event_type = "acknack"
    if event_type is None:
        return None

    sequences = parsed_ints(row["rtps.sm.seqNumber"])
    event = {
        "frame_number": int(row["frame.number"]),
        "time_s": time_s,
        "flow": flow,
        "event_type": event_type,
        "source_guid": source_guid,
        "destination_guid": destination_guid,
        "source_ip": source_ip,
        "destination_ip": row["ip.dst"],
        "sequence": sequences[0] if sequences else None,
        "last_sequence": sequences[-1] if sequences else None,
        "acknack_count": first_int(row["rtps.acknack.count"]),
        "heartbeat_count": first_int(row["rtps.heartbeat_count"]),
        "requested_sequences": [],
    }
    if event_type == "acknack":
        num_bits = first_int(row["rtps.bitmap.num_bits"]) or 0
        bitmaps = split_values(row["rtps.bitmap"])
        bitmap = bitmaps[0] if bitmaps else ""
        event["requested_sequences"] = decode_sequence_set(
            event["sequence"],
            num_bits,
            bitmap,
        )
    return event


def guid_run_map(events, flow, source_ip, event_type):
    first_seen = {}
    for event in events:
        if (
            event["flow"] == flow
            and event["source_ip"] == source_ip
            and event["event_type"] == event_type
            and event["source_guid"]
        ):
            first_seen.setdefault(event["source_guid"], event["time_s"])
    ordered = sorted(first_seen, key=first_seen.get)
    return {guid: index + 1 for index, guid in enumerate(ordered)}


def assign_runs(events, board_ip, host_ip):
    board_runs = guid_run_map(events, "board_to_host_app", board_ip, "data")
    host_runs = guid_run_map(events, "host_to_board_reply", host_ip, "data")
    for event in events:
        if (
            event["event_type"] == "acknack"
            and event["flow"] == "board_to_host_app"
        ):
            event["run_id"] = (
                board_runs.get(event["destination_guid"])
                or host_runs.get(event["source_guid"])
            )
        elif (
            event["event_type"] == "acknack"
            and event["flow"] == "host_to_board_reply"
        ):
            event["run_id"] = (
                host_runs.get(event["destination_guid"])
                or board_runs.get(event["source_guid"])
            )
        elif event["source_ip"] == board_ip:
            event["run_id"] = board_runs.get(event["source_guid"])
        elif event["source_ip"] == host_ip:
            event["run_id"] = host_runs.get(event["source_guid"])
        else:
            event["run_id"] = None
    return board_runs, host_runs


def median_or_blank(values):
    return statistics.median(values) if values else ""


def max_or_blank(values):
    return max(values) if values else ""


def summarize_flow(events, run_id, flow):
    selected = [
        event
        for event in events
        if event["run_id"] == run_id and event["flow"] == flow
    ]
    data = [event for event in selected if event["event_type"] == "data"]
    heartbeats = [
        event for event in selected if event["event_type"] == "heartbeat"
    ]
    acknacks = [event for event in selected if event["event_type"] == "acknack"]
    by_sequence = defaultdict(list)
    for event in data:
        if event["sequence"] is not None:
            by_sequence[event["sequence"]].append(event["time_s"])
    for times in by_sequence.values():
        times.sort()

    repeated = {sequence: times for sequence, times in by_sequence.items() if len(times) > 1}
    first_retry_delays = [
        1000.0 * (times[1] - times[0])
        for times in repeated.values()
    ]
    retry_spans = [
        1000.0 * (times[-1] - times[0])
        for times in repeated.values()
    ]
    heartbeat_times = sorted(event["time_s"] for event in heartbeats)
    heartbeat_intervals = [
        1000.0 * (right - left)
        for left, right in zip(heartbeat_times, heartbeat_times[1:])
    ]
    requested = [
        sequence
        for event in acknacks
        for sequence in event["requested_sequences"]
    ]
    return {
        "run_id": run_id,
        "flow": flow,
        "data_observations": len(data),
        "data_unique_sequences": len(by_sequence),
        "data_duplicate_observations": sum(
            len(times) - 1 for times in repeated.values()
        ),
        "data_repeated_sequences": len(repeated),
        "data_max_observations_per_sequence": max(
            (len(times) for times in by_sequence.values()),
            default=0,
        ),
        "first_retry_delay_median_ms": median_or_blank(first_retry_delays),
        "retry_span_max_ms": max_or_blank(retry_spans),
        "heartbeat_observations": len(heartbeats),
        "heartbeat_interval_median_ms": median_or_blank(heartbeat_intervals),
        "acknack_observations": len(acknacks),
        "acknack_with_requests": sum(
            bool(event["requested_sequences"]) for event in acknacks
        ),
        "requested_sequence_observations": len(requested),
        "requested_unique_sequences": len(set(requested)),
    }


def reconstruct_nack_links(events, run_id, flow):
    data_times = defaultdict(list)
    for event in events:
        if (
            event["run_id"] == run_id
            and event["flow"] == flow
            and event["event_type"] == "data"
            and event["sequence"] is not None
        ):
            data_times[event["sequence"]].append(event["time_s"])
    for times in data_times.values():
        times.sort()

    links = []
    for event in events:
        if (
            event["run_id"] != run_id
            or event["flow"] != flow
            or event["event_type"] != "acknack"
        ):
            continue
        for sequence in event["requested_sequences"]:
            times = data_times.get(sequence, [])
            before = [time_s for time_s in times if time_s < event["time_s"]]
            after = [time_s for time_s in times if time_s > event["time_s"]]
            next_time = after[0] if after else None
            links.append({
                "run_id": run_id,
                "flow": flow,
                "ack_frame_number": event["frame_number"],
                "ack_time_s": event["time_s"],
                "acknack_count": event["acknack_count"],
                "requested_sequence": sequence,
                "prior_data_observed": int(bool(before)),
                "post_nack_data_observed": int(next_time is not None),
                "next_data_time_s": next_time if next_time is not None else "",
                "nack_to_next_data_ms": (
                    1000.0 * (next_time - event["time_s"])
                    if next_time is not None
                    else ""
                ),
            })
    return links


def condition_summary(per_run, links, metadata):
    rows = [
        row
        for row in per_run
        if row["flow"] == "board_to_host_app"
    ]
    link_rows = [
        row
        for row in links
        if row["flow"] == "board_to_host_app"
    ]
    matched_links = [
        float(row["nack_to_next_data_ms"])
        for row in link_rows
        if row["post_nack_data_observed"]
    ]
    strong_sequences = {
        (row["run_id"], row["requested_sequence"])
        for row in link_rows
        if row["prior_data_observed"] and row["post_nack_data_observed"]
    }
    strong_runs = {run_id for run_id, _sequence in strong_sequences}
    heartbeat_intervals = [
        float(row["heartbeat_interval_median_ms"])
        for row in rows
        if row["heartbeat_interval_median_ms"] != ""
    ]
    return {
        **metadata,
        "runs_observed": len(rows),
        "app_data_observations": sum(row["data_observations"] for row in rows),
        "app_data_unique_sequences": sum(
            row["data_unique_sequences"] for row in rows
        ),
        "app_data_duplicate_observations": sum(
            row["data_duplicate_observations"] for row in rows
        ),
        "app_data_repeated_sequences": sum(
            row["data_repeated_sequences"] for row in rows
        ),
        "acknack_observations": sum(row["acknack_observations"] for row in rows),
        "requested_sequence_observations": sum(
            row["requested_sequence_observations"] for row in rows
        ),
        "nack_links_with_post_data": sum(
            row["post_nack_data_observed"] for row in link_rows
        ),
        "unique_sequences_with_prior_and_post_nack_data": len(strong_sequences),
        "runs_with_prior_and_post_nack_data": len(strong_runs),
        "nack_to_next_data_median_ms": median_or_blank(matched_links),
        "nack_to_next_data_max_ms": max_or_blank(matched_links),
        "heartbeat_interval_run_median_ms": median_or_blank(heartbeat_intervals),
    }


def analyze(path, board_ip, host_ip):
    qos, loss_pct, impairment_direction = condition_from_path(path)
    events = []
    for row in tshark_rows(path):
        event = classify_row(row, board_ip, host_ip)
        if event is not None:
            events.append(event)
    board_runs, host_runs = assign_runs(events, board_ip, host_ip)
    run_count = max(len(board_runs), len(host_runs))
    per_run = []
    links = []
    for run_id in range(1, run_count + 1):
        for flow in ("board_to_host_app", "host_to_board_reply"):
            per_run.append(summarize_flow(events, run_id, flow))
            links.extend(reconstruct_nack_links(events, run_id, flow))
    metadata = {
        "pcap": str(path),
        "pcap_sha256": sha256_file(path),
        "qos": qos,
        "loss_pct": loss_pct,
        "impairment_direction": impairment_direction,
        "board_guid_runs": len(board_runs),
        "host_guid_runs": len(host_runs),
    }
    summary = condition_summary(per_run, links, metadata)
    for row in per_run:
        row.update(metadata)
    for row in links:
        row.update(metadata)
    return summary, per_run, links


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    return f"{value:.3f}" if isinstance(value, float) else value


def write_markdown(path, summaries):
    lines = [
        "# ROUND4 Application-Entity RTPS Reconstruction",
        "",
        "This analysis isolates the application writer/reader entity IDs and",
        "links ACKNACK SequenceNumberSet requests to later DATA observations",
        "with the same RTPS writer sequence number.",
        "",
        "The ingress capture can observe a packet before `tc` drops it. Therefore",
        "a pre-NACK DATA observation is wire evidence, not proof of application",
        "delivery. A post-NACK DATA observation is reported conservatively and",
        "is not by itself a complete implementation-level mechanism proof.",
        "",
        "| QoS | Loss (%) | Runs | App DATA obs | Unique seq | Duplicate obs | "
        "ACKNACK obs | Requested seq obs | Post-NACK DATA links | "
        "Unique seq with DATA before+after NACK | Runs with DATA before+after "
        "NACK | NACK->DATA median ms | "
        "Heartbeat interval run-median ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: |",
    ]
    for row in sorted(summaries, key=lambda item: (item["loss_pct"], item["qos"])):
        lines.append(
            f"| {row['qos']} | {row['loss_pct']} | {row['runs_observed']} | "
            f"{row['app_data_observations']} | {row['app_data_unique_sequences']} | "
            f"{row['app_data_duplicate_observations']} | "
            f"{row['acknack_observations']} | "
            f"{row['requested_sequence_observations']} | "
            f"{row['nack_links_with_post_data']} | "
            f"{row['unique_sequences_with_prior_and_post_nack_data']} | "
            f"{row['runs_with_prior_and_post_nack_data']} | "
            f"{fmt(row['nack_to_next_data_median_ms'])} | "
            f"{fmt(row['heartbeat_interval_run_median_ms'])} |"
        )
    lines.extend([
        "",
        "Application entity mapping:",
        "",
        "- board `/qos_eval` writer `0x000001:0x03` to host reader "
        "`0x000012:0x04`",
        "- host `/qos_eval_reply` writer `0x000013:0x03` to board reader "
        "`0x000002:0x04`",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcap_paths", nargs="+", type=Path)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--host-ip", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    summaries = []
    per_run = []
    links = []
    for path in args.pcap_paths:
        try:
            summary, run_rows, link_rows = analyze(
                path,
                args.board_ip,
                args.host_ip,
            )
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            raise SystemExit(f"FAIL: {path}: {exc}") from exc
        summaries.append(summary)
        per_run.extend(run_rows)
        links.extend(link_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "round4_rtps_app_reconstruction_summary.csv"
    run_path = args.output_dir / "round4_rtps_app_reconstruction_runs.csv"
    link_path = args.output_dir / "round4_rtps_app_nack_data_links.csv"
    markdown_path = args.output_dir / "round4_rtps_app_reconstruction_summary.md"
    write_csv(summary_path, summaries)
    write_csv(run_path, per_run)
    write_csv(link_path, links)
    write_markdown(markdown_path, summaries)
    print(f"Wrote {summary_path}")
    print(f"Wrote {run_path}")
    print(f"Wrote {link_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
