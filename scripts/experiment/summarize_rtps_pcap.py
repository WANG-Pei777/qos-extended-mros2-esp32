#!/usr/bin/env python3
"""Summarize RTPS submessage evidence from pcapng captures."""

import argparse
import csv
import hashlib
import subprocess
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rtps_infos(path):
    result = subprocess.run(
        ["tshark", "-r", str(path), "-Y", "rtps", "-T", "fields", "-e", "_ws.col.Info"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.splitlines()


def summarize(path):
    infos = rtps_infos(path)
    return {
        "pcap": str(path),
        "sha256": sha256_file(path),
        "rtps_packets": len(infos),
        "data_packets": sum("DATA" in info for info in infos),
        "heartbeat_packets": sum("HEARTBEAT" in info for info in infos),
        "acknack_packets": sum("ACKNACK" in info for info in infos),
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path, rows):
    lines = [
        "# ROUND4 RTPS Capture Summary",
        "",
        "| PCAP | RTPS packets | DATA | HEARTBEAT | ACKNACK | SHA-256 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {Path(row['pcap']).name} | {row['rtps_packets']} | "
            f"{row['data_packets']} | {row['heartbeat_packets']} | "
            f"{row['acknack_packets']} | `{row['sha256']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcap_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    rows = [summarize(path) for path in args.pcap_paths]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "round4_rtps_capture_summary.csv", rows)
    write_markdown(args.output_dir / "round4_rtps_capture_summary.md", rows)
    print(f"Wrote {args.output_dir / 'round4_rtps_capture_summary.csv'}")
    print(f"Wrote {args.output_dir / 'round4_rtps_capture_summary.md'}")


if __name__ == "__main__":
    main()
