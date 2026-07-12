#!/usr/bin/env python3
"""Extract conservative RTPS timeline evidence from pcapng captures.

This is not a full RTPS semantic decoder. It records packet-level timing,
direction, submessage labels, ACKNACK bitmap presence, and exposed RTPS counters
from tshark so paper claims can distinguish observed wire behavior from
mechanism-level interpretation.
"""

import argparse
import csv
import hashlib
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


FIELDS = [
    "frame.time_relative",
    "ip.src",
    "ip.dst",
    "rtps.sm.id",
    "rtps.sm.seqNumber",
    "rtps.sequence",
    "rtps.bitmap.num_bits",
    "rtps.bitmap",
    "rtps.acknack.count",
    "rtps.heartbeat_count",
    "_ws.col.Info",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_values(value):
    return [item for item in value.split(",") if item]


def ints(value):
    output = []
    for item in split_values(value):
        try:
            output.append(int(item, 0))
        except ValueError:
            continue
    return output


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


def count_label(info, label):
    return info.count(label)


def summarize(path, board_ip, host_ip):
    rows = list(tshark_rows(path))
    times = [float(row["frame.time_relative"]) for row in rows if row["frame.time_relative"]]
    by_endpoint = Counter()
    ack_bitmap_by_endpoint = Counter()
    ack_counts = []
    heartbeat_counts = []
    data_sequences = defaultdict(Counter)

    for row in rows:
        src = row["ip.src"]
        dst = row["ip.dst"]
        if src == board_ip:
            endpoint = "board_to_host" if dst == host_ip else "board_to_multicast"
        elif src == host_ip:
            endpoint = "host_to_board" if dst == board_ip else "host_to_multicast"
        else:
            endpoint = "other"

        info = row["_ws.col.Info"]
        data_count = count_label(info, "DATA")
        heartbeat_count = count_label(info, "HEARTBEAT")
        acknack_count = count_label(info, "ACKNACK")
        by_endpoint[(endpoint, "data")] += data_count
        by_endpoint[(endpoint, "heartbeat")] += heartbeat_count
        by_endpoint[(endpoint, "acknack")] += acknack_count

        bitmaps = split_values(row["rtps.bitmap"])
        bitmap_bits = ints(row["rtps.bitmap.num_bits"])
        if acknack_count and (any(bitmap != "" and int(bitmap, 16) != 0 for bitmap in bitmaps) or any(bit > 0 for bit in bitmap_bits)):
            ack_bitmap_by_endpoint[endpoint] += acknack_count

        ack_counts.extend(ints(row["rtps.acknack.count"]))
        heartbeat_counts.extend(ints(row["rtps.heartbeat_count"]))
        if data_count:
            for seq in ints(row["rtps.sm.seqNumber"]):
                data_sequences[endpoint][seq] += 1

    sequence_metrics = {}
    for endpoint, counter in data_sequences.items():
        total = sum(counter.values())
        unique = len(counter)
        duplicates = sum(count - 1 for count in counter.values() if count > 1)
        sequence_metrics[endpoint] = (total, unique, duplicates)

    def metric(endpoint, kind):
        return by_endpoint[(endpoint, kind)]

    def seq_metric(endpoint, index):
        return sequence_metrics.get(endpoint, (0, 0, 0))[index]

    return {
        "pcap": str(path),
        "sha256": sha256_file(path),
        "duration_s": max(times) - min(times) if times else 0.0,
        "rtps_packets": len(rows),
        "board_to_host_data": metric("board_to_host", "data"),
        "board_to_host_heartbeat": metric("board_to_host", "heartbeat"),
        "board_to_host_acknack": metric("board_to_host", "acknack"),
        "host_to_board_data": metric("host_to_board", "data"),
        "host_to_board_heartbeat": metric("host_to_board", "heartbeat"),
        "host_to_board_acknack": metric("host_to_board", "acknack"),
        "board_acknack_with_bitmap": ack_bitmap_by_endpoint["board_to_host"],
        "host_acknack_with_bitmap": ack_bitmap_by_endpoint["host_to_board"],
        "acknack_count_max": max(ack_counts) if ack_counts else "",
        "heartbeat_count_max": max(heartbeat_counts) if heartbeat_counts else "",
        "board_to_host_data_seq_observations": seq_metric("board_to_host", 0),
        "board_to_host_data_seq_unique": seq_metric("board_to_host", 1),
        "board_to_host_data_seq_duplicate_observations": seq_metric("board_to_host", 2),
        "host_to_board_data_seq_observations": seq_metric("host_to_board", 0),
        "host_to_board_data_seq_unique": seq_metric("host_to_board", 1),
        "host_to_board_data_seq_duplicate_observations": seq_metric("host_to_board", 2),
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    if isinstance(value, float):
        return f"{value:.3f}"
    return value


def write_markdown(path, rows):
    lines = [
        "# ROUND4 RTPS Timeline Evidence",
        "",
        "This is packet-level evidence extracted from tshark fields. It supports",
        "claims about observed wire traffic only; it does not by itself prove a",
        "specific RTPS retransmission mechanism.",
        "",
        "| PCAP | Duration s | RTPS packets | B2H DATA | B2H HEARTBEAT | B2H ACKNACK | H2B DATA | H2B HEARTBEAT | H2B ACKNACK | B2H ACK bitmap | H2B ACK bitmap | Max ACKNACK count | Max HEARTBEAT count |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {Path(row['pcap']).name} | {fmt(row['duration_s'])} | {row['rtps_packets']} | "
            f"{row['board_to_host_data']} | {row['board_to_host_heartbeat']} | {row['board_to_host_acknack']} | "
            f"{row['host_to_board_data']} | {row['host_to_board_heartbeat']} | {row['host_to_board_acknack']} | "
            f"{row['board_acknack_with_bitmap']} | {row['host_acknack_with_bitmap']} | "
            f"{row['acknack_count_max']} | {row['heartbeat_count_max']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcap_paths", nargs="+", type=Path)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--host-ip", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    rows = [summarize(path, args.board_ip, args.host_ip) for path in args.pcap_paths]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "round4_rtps_timeline_evidence.csv", rows)
    write_markdown(args.output_dir / "round4_rtps_timeline_evidence.md", rows)
    print(f"Wrote {args.output_dir / 'round4_rtps_timeline_evidence.csv'}")
    print(f"Wrote {args.output_dir / 'round4_rtps_timeline_evidence.md'}")


if __name__ == "__main__":
    main()
