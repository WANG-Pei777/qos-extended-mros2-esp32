#!/usr/bin/env python3
"""Extract per-run RTPS wire-cost metrics from accepted Round 6 PCAPs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


FIELDS = [
    "frame.number",
    "frame.time_relative",
    "ip.src",
    "ip.dst",
    "frame.len",
    "udp.length",
    "rtps.guidPrefix",
    "rtps.sm.id",
    "rtps.sm.wrEntityId.entityKey",
    "rtps.sm.wrEntityId.entityKind",
    "rtps.sm.rdEntityId.entityKey",
    "rtps.sm.rdEntityId.entityKind",
]

DATA_ID = 0x15
HEARTBEAT_ID = 0x07
ACKNACK_ID = 0x06
BOARD_WRITER = (0x000001, 0x03)
HOST_READER = (0x000012, 0x04)
HOST_WRITER = (0x000013, 0x03)
BOARD_READER = (0x000002, 0x04)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ints(value: str) -> set[int]:
    output = set()
    for item in value.replace(",", ";").split(";"):
        if not item:
            continue
        try:
            output.add(int(item, 0))
        except ValueError:
            continue
    return output


def contains_endpoint(
    writer_keys: set[int],
    writer_kinds: set[int],
    reader_keys: set[int],
    reader_kinds: set[int],
    writer: tuple[int, int],
    reader: tuple[int, int],
) -> bool:
    return (
        writer[0] in writer_keys
        and writer[1] in writer_kinds
        and reader[0] in reader_keys
        and reader[1] in reader_kinds
    )


def tshark_rows(
    tshark: str,
    pcap: Path,
    board_ip: str,
    host_ip: str,
):
    display_filter = (
        "rtps && "
        f"((ip.src == {board_ip} && ip.dst == {host_ip}) || "
        f"(ip.src == {host_ip} && ip.dst == {board_ip}))"
    )
    command = [
        tshark,
        "-r",
        str(pcap),
        "-Y",
        display_filter,
        "-T",
        "fields",
        "-E",
        "separator=\t",
        "-E",
        "occurrence=a",
        "-E",
        "aggregator=;",
    ]
    for field in FIELDS:
        command.extend(["-e", field])
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    for line in result.stdout.splitlines():
        values = line.split("\t")
        values.extend([""] * (len(FIELDS) - len(values)))
        yield dict(zip(FIELDS, values))


def analyze_pcap(task: tuple[dict[str, str], str, str, str, str, float | None]):
    mapping, repo_root, tshark, board_ip, host_ip, measurement_start_override_s = task
    pcap = Path(repo_root) / mapping["pcap"]
    frames: dict[int, dict[str, object]] = {}
    for row in tshark_rows(
        tshark,
        pcap,
        board_ip,
        host_ip,
    ):
        frame_number = int(row["frame.number"])
        submessages = parse_ints(row["rtps.sm.id"])
        writer_keys = parse_ints(row["rtps.sm.wrEntityId.entityKey"])
        writer_kinds = parse_ints(row["rtps.sm.wrEntityId.entityKind"])
        reader_keys = parse_ints(row["rtps.sm.rdEntityId.entityKey"])
        reader_kinds = parse_ints(row["rtps.sm.rdEntityId.entityKind"])
        forward = contains_endpoint(
            writer_keys,
            writer_kinds,
            reader_keys,
            reader_kinds,
            BOARD_WRITER,
            HOST_READER,
        )
        reply = contains_endpoint(
            writer_keys,
            writer_kinds,
            reader_keys,
            reader_kinds,
            HOST_WRITER,
            BOARD_READER,
        )
        frames[frame_number] = {
            "time_s": float(row["frame.time_relative"]),
            "source_ip": row["ip.src"],
            "guid_prefix": row["rtps.guidPrefix"],
            "frame_len": int(row["frame.len"]),
            "udp_len": int(row["udp.length"]),
            "is_target": forward or reply,
            "is_forward": forward,
            "is_reply": reply,
            "has_data": DATA_ID in submessages,
            "has_heartbeat": HEARTBEAT_ID in submessages,
            "has_acknack": ACKNACK_ID in submessages,
        }

    all_frames = list(frames.values())
    if not all_frames:
        raise ValueError(f"no RTPS frames between board and host: {pcap}")

    # Capture starts before the run admission gate. Four accepted Round 6
    # PCAPs contain two board GUID epochs because a 30 s link-health wait
    # occurred before the board reset. Align each PCAP to the first target
    # DATA frame from the latest board application GUID so admission traffic
    # and the stale pre-reset epoch cannot inflate per-run wire cost.
    first_target_data_by_guid: dict[str, float] = {}
    for frame in all_frames:
        guid = str(frame["guid_prefix"])
        if (
            frame["source_ip"] == board_ip
            and frame["is_forward"]
            and frame["has_data"]
            and guid
        ):
            first_target_data_by_guid[guid] = min(
                first_target_data_by_guid.get(guid, math.inf),
                float(frame["time_s"]),
            )
    if not first_target_data_by_guid:
        raise ValueError(f"no board target DATA GUID epoch: {pcap}")
    selected_guid, detected_start_s = max(
        first_target_data_by_guid.items(), key=lambda item: item[1]
    )
    measurement_start_s = (
        detected_start_s
        if measurement_start_override_s is None
        else measurement_start_override_s
    )
    selected = [
        frame for frame in all_frames if float(frame["time_s"]) >= measurement_start_s
    ]
    target = [frame for frame in selected if frame["is_target"]]
    if not target:
        raise ValueError(f"no target application frames: {pcap}")

    def count(items):
        return len(items)

    def wire_bytes(items):
        return sum(int(item["frame_len"]) for item in items)

    def udp_bytes(items):
        return sum(int(item["udp_len"]) for item in items)

    board_to_host = [f for f in selected if f["source_ip"] == board_ip]
    host_to_board = [f for f in selected if f["source_ip"] == host_ip]
    target_forward = [f for f in target if f["is_forward"]]
    target_reply = [f for f in target if f["is_reply"]]
    target_data = [f for f in target if f["has_data"]]
    target_control_only = [
        f
        for f in target
        if not f["has_data"] and (f["has_heartbeat"] or f["has_acknack"])
    ]
    target_mixed = [
        f
        for f in target
        if f["has_data"] and (f["has_heartbeat"] or f["has_acknack"])
    ]
    times = [float(frame["time_s"]) for frame in selected]
    measurement_span_s = max(times) - min(times) if len(times) > 1 else 0.0

    return {
        "block": int(mapping["block"]),
        "visit": int(mapping["visit"]),
        "cell": mapping["cell"],
        "condition": mapping["condition"],
        "run_id": int(mapping["run_id"]),
        "accepted_ordinal": int(mapping["accepted_ordinal"]),
        "depth": int(mapping["depth"]),
        "heartbeat_ms": int(mapping["heartbeat_ms"]),
        "pcap": mapping["pcap"],
        "pcap_sha256": mapping["pcap_sha256"],
        "measurement_start_s": measurement_start_s,
        "measurement_start_detected_s": detected_start_s,
        "measurement_board_guid_prefix": selected_guid,
        "measurement_board_guid_epochs": len(first_target_data_by_guid),
        "measurement_span_s": measurement_span_s,
        "pair_rtps_frames": count(selected),
        "pair_rtps_wire_bytes": wire_bytes(selected),
        "pair_rtps_udp_bytes": udp_bytes(selected),
        "pair_board_to_host_frames": count(board_to_host),
        "pair_board_to_host_wire_bytes": wire_bytes(board_to_host),
        "pair_host_to_board_frames": count(host_to_board),
        "pair_host_to_board_wire_bytes": wire_bytes(host_to_board),
        "target_frames": count(target),
        "target_wire_bytes": wire_bytes(target),
        "target_udp_bytes": udp_bytes(target),
        "target_forward_frames": count(target_forward),
        "target_forward_wire_bytes": wire_bytes(target_forward),
        "target_reply_frames": count(target_reply),
        "target_reply_wire_bytes": wire_bytes(target_reply),
        "target_data_frames": count(target_data),
        "target_data_wire_bytes": wire_bytes(target_data),
        "target_control_only_frames": count(target_control_only),
        "target_control_only_wire_bytes": wire_bytes(target_control_only),
        "target_mixed_data_control_frames": count(target_mixed),
        "target_mixed_data_control_wire_bytes": wire_bytes(target_mixed),
    }


def safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_mean_ci(
    values: list[float],
    seed_material: str,
    replicates: int,
) -> tuple[float, float, float]:
    clean = [value for value in values if math.isfinite(value)]
    mean = statistics.mean(clean)
    seed = int(hashlib.sha256(seed_material.encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    draws = [
        statistics.mean(rng.choices(clean, k=len(clean)))
        for _ in range(replicates)
    ]
    return mean, percentile(draws, 0.025), percentile(draws, 0.975)


def summarize_cells(
    rows: list[dict[str, object]],
    replicates: int,
) -> list[dict[str, object]]:
    metrics = [
        "delivery_pct",
        "rtt_p95_ms",
        "pair_rtps_wire_bytes_per_tx",
        "pair_rtps_wire_bytes_per_rx",
        "pair_rtps_frames_per_tx",
        "pair_rtps_frames_per_rx",
        "target_wire_bytes_per_tx",
        "target_wire_bytes_per_rx",
        "target_control_only_share_pct",
        "pair_rtps_kbit_s",
    ]
    grouped: dict[tuple[int, int], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault((int(row["depth"]), int(row["heartbeat_ms"])), []).append(row)
    output = []
    for (depth, heartbeat), selected in sorted(grouped.items()):
        summary: dict[str, object] = {
            "depth": depth,
            "heartbeat_ms": heartbeat,
            "cell": f"d{depth:02d}_h{heartbeat:04d}",
            "n_runs": len(selected),
        }
        for metric in metrics:
            mean, low, high = bootstrap_mean_ci(
                [float(row[metric]) for row in selected],
                f"{depth}|{heartbeat}|{metric}",
                replicates,
            )
            summary[f"{metric}_mean"] = mean
            summary[f"{metric}_ci_low"] = low
            summary[f"{metric}_ci_high"] = high
        output.append(summary)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wire-map", type=Path, required=True)
    parser.add_argument("--app-runs", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--host-ip", default="192.0.2.2")
    parser.add_argument(
        "--measurement-start-s",
        type=float,
        default=None,
        help="manual override; default aligns to first target DATA from latest board GUID",
    )
    parser.add_argument("--tshark", default="tshark")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    args = parser.parse_args()

    wire_map = read_csv(args.wire_map)
    app_rows = read_csv(args.app_runs)
    if len(wire_map) != 360 or len(app_rows) != 360:
        raise SystemExit(
            f"expected 360 wire rows and 360 app rows, got {len(wire_map)} and {len(app_rows)}"
        )
    app_by_key = {(row["condition"], int(row["run_id"])): row for row in app_rows}
    if len(app_by_key) != 360:
        raise SystemExit("application run keys are not unique")

    tasks = [
        (
            row,
            str(args.repo_root),
            args.tshark,
            args.board_ip,
            args.host_ip,
            args.measurement_start_s,
        )
        for row in wire_map
    ]
    extracted = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index, row in enumerate(executor.map(analyze_pcap, tasks), start=1):
            extracted.append(row)
            if index % 30 == 0:
                print(f"[wire-cost] analyzed {index}/360", flush=True)

    joined: list[dict[str, object]] = []
    for wire in extracted:
        key = (str(wire["condition"]), int(wire["run_id"]))
        app = app_by_key.get(key)
        if app is None:
            raise SystemExit(f"missing application row for {key}")
        tx_count = int(app["tx_count"])
        rx_count = int(app["rx_count"])
        measurement_span_s = float(wire["measurement_span_s"])
        row = {
            **wire,
            "tx_count": tx_count,
            "rx_count": rx_count,
            "delivery_ratio": float(app["delivery_ratio"]),
            "delivery_pct": float(app["delivery_pct"]),
            "rtt_p95_ms": float(app["rtt_p95_ms"]),
            "pair_rtps_wire_bytes_per_tx": safe_ratio(float(wire["pair_rtps_wire_bytes"]), tx_count),
            "pair_rtps_wire_bytes_per_rx": safe_ratio(float(wire["pair_rtps_wire_bytes"]), rx_count),
            "pair_rtps_frames_per_tx": safe_ratio(float(wire["pair_rtps_frames"]), tx_count),
            "pair_rtps_frames_per_rx": safe_ratio(float(wire["pair_rtps_frames"]), rx_count),
            "target_wire_bytes_per_tx": safe_ratio(float(wire["target_wire_bytes"]), tx_count),
            "target_wire_bytes_per_rx": safe_ratio(float(wire["target_wire_bytes"]), rx_count),
            "target_frames_per_tx": safe_ratio(float(wire["target_frames"]), tx_count),
            "target_frames_per_rx": safe_ratio(float(wire["target_frames"]), rx_count),
            "target_control_only_wire_bytes_per_tx": safe_ratio(float(wire["target_control_only_wire_bytes"]), tx_count),
            "target_control_only_wire_bytes_per_rx": safe_ratio(float(wire["target_control_only_wire_bytes"]), rx_count),
            "target_control_only_share_pct": 100.0 * safe_ratio(
                float(wire["target_control_only_wire_bytes"]),
                float(wire["target_wire_bytes"]),
            ),
            "pair_rtps_kbit_s": safe_ratio(
                8.0 * float(wire["pair_rtps_wire_bytes"]),
                1000.0 * measurement_span_s,
            ),
        }
        joined.append(row)

    joined.sort(key=lambda row: (int(row["block"]), int(row["visit"]), int(row["accepted_ordinal"])))
    if any(not math.isfinite(float(row["pair_rtps_wire_bytes_per_rx"])) for row in joined):
        raise SystemExit("at least one accepted run has zero delivered replies")
    cell_rows = summarize_cells(joined, args.bootstrap_replicates)
    if len(cell_rows) != 12 or any(int(row["n_runs"]) != 30 for row in cell_rows):
        raise SystemExit("cell balance check failed")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_path = args.output_dir / "round6_wire_cost_run_level.csv"
    cell_path = args.output_dir / "round6_wire_cost_cell_summary.csv"
    write_csv(run_path, joined)
    write_csv(cell_path, cell_rows)
    tshark_version = subprocess.check_output(
        [args.tshark, "--version"], text=True
    ).splitlines()[0]
    manifest = {
        "schema_version": 2,
        "analysis": "round6_rtps_wire_cost",
        "accepted_runs": len(joined),
        "cells": len(cell_rows),
        "runs_per_cell": 30,
        "board_ip": args.board_ip,
        "host_ip": args.host_ip,
        "measurement_start_override_s": args.measurement_start_s,
        "measurement_start_rule": (
            "first board-to-host target DATA frame from the latest board GUID epoch; "
            "manual override only when measurement_start_override_s is non-null"
        ),
        "tshark": tshark_version,
        "wire_map_sha256": sha256_file(args.wire_map),
        "app_runs_sha256": sha256_file(args.app_runs),
        "run_level_sha256": sha256_file(run_path),
        "cell_summary_sha256": sha256_file(cell_path),
        "bootstrap_replicates": args.bootstrap_replicates,
        "frame_accounting": "unique frame.number; captured frame.len; compound RTPS submessages are not double counted",
        "pair_scope": (
            "all RTPS frames between board and host from the dynamically aligned "
            "application-run start through capture end"
        ),
        "target_scope": "both application paths: board qos_eval writer to host reader and host qos_eval_reply writer to board reader",
        "control_only_definition": "target frames containing HEARTBEAT or ACKNACK and no DATA; mixed DATA/control frames remain in DATA cost",
        "claim_boundary": "captured frame.len excludes uncaptured physical-layer overhead; results apply to this capture boundary and workload",
    }
    manifest_path = args.output_dir / "round6_wire_cost_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
