#!/usr/bin/env python3
"""Shared constants and provenance helpers for the formal H2B campaign."""

import csv
import hashlib
from pathlib import Path
import subprocess


QOS_MODES = ("reliable", "best_effort")
LOSS_SPECS = {
    0: {"denominator": 0, "effective": 0.0},
    1: {"denominator": 100, "effective": 1.0},
    5: {"denominator": 20, "effective": 5.0},
    10: {"denominator": 10, "effective": 10.0},
    15: {"denominator": 7, "effective": 100.0 / 7.0},
}
LOSS_TARGETS = tuple(LOSS_SPECS)
ACCEPTED_RUNS_PER_VISIT = 3
EXPECTED_BLOCKS = 10
EXPECTED_VISITS = EXPECTED_BLOCKS * len(QOS_MODES) * len(LOSS_SPECS)
EXPECTED_ACCEPTED_RUNS = 300
SCHEDULE_SEED = 202607154


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path):
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def condition_for(qos, target_loss):
    if qos not in QOS_MODES or target_loss not in LOSS_SPECS:
        raise ValueError(f"unsupported H2B cell: {qos}, {target_loss}")
    return f"round4_transport_{qos}_{target_loss}pct_host_to_board"


def expected_injection(target_loss):
    spec = LOSS_SPECS[target_loss]
    base = (
        "transport_egress_gact_host_to_board_"
        f"target_{target_loss}pct_"
    )
    if target_loss == 0:
        return base + "effective_0pct"
    return (
        base
        + f"1of{spec['denominator']}_effective_{spec['effective']:.6f}pct"
    )


def count_host_to_board_udp_packets(pcap_path, board_ip):
    completed = subprocess.run(
        [
            "tshark",
            "-r",
            str(pcap_path),
            "-Y",
            f"ip.dst == {board_ip} && udp",
            "-T",
            "fields",
            "-e",
            "frame.number",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return sum(1 for line in completed.stdout.splitlines() if line.strip())


def parse_latest_capture(ledger_path, board_ip, qos, target_loss):
    lines = [
        line.strip()
        for line in Path(ledger_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError(f"empty H2B ledger: {ledger_path}")
    fields = {}
    for part in lines[-1].split(" | "):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    spec = LOSS_SPECS[target_loss]
    if fields.get("qos") != qos or fields.get("firmware") != qos:
        raise ValueError("H2B ledger QoS provenance mismatch")
    if fields.get("direction") != "host_to_board":
        raise ValueError("H2B ledger direction mismatch")
    if fields.get("target_loss") != f"{target_loss}%":
        raise ValueError("H2B ledger target-loss mismatch")
    expected_denominator = "n/a" if target_loss == 0 else str(spec["denominator"])
    if fields.get("denominator") != expected_denominator:
        raise ValueError("H2B ledger denominator mismatch")
    effective = float(fields.get("effective_loss", "").removesuffix("%"))
    if abs(effective - spec["effective"]) > 0.000001:
        raise ValueError("H2B ledger effective-loss mismatch")
    pcap = Path(fields["pcap"])
    tc_state = Path(fields["tc_state"])
    capture_log = Path(str(pcap) + ".log")
    if not pcap.is_file() or sha256_file(pcap) != fields["sha256"]:
        raise ValueError(f"H2B PCAP hash mismatch: {pcap}")
    if not tc_state.is_file() or sha256_file(tc_state) != fields["tc_state_sha256"]:
        raise ValueError(f"H2B tc-state hash mismatch: {tc_state}")
    if not capture_log.is_file():
        raise ValueError(f"H2B capture log missing: {capture_log}")
    return {
        "path": str(pcap),
        "sha256": fields["sha256"],
        "bytes": pcap.stat().st_size,
        "host_to_board_udp_packets": count_host_to_board_udp_packets(
            pcap, board_ip
        ),
        "tc_state_path": str(tc_state),
        "tc_state_sha256": fields["tc_state_sha256"],
        "capture_log_path": str(capture_log),
        "capture_log_sha256": sha256_file(capture_log),
        "target_loss_percent": target_loss,
        "gact_denominator": spec["denominator"],
        "effective_loss_percent": spec["effective"],
    }


def validate_schedule(schedule):
    if len(schedule) != EXPECTED_VISITS:
        raise ValueError(f"H2B schedule must contain {EXPECTED_VISITS} visits")
    expected_cells = {
        f"{qos}_target{loss:02d}"
        for qos in QOS_MODES
        for loss in LOSS_TARGETS
    }
    seen_orders = []
    for block in range(1, EXPECTED_BLOCKS + 1):
        rows = [row for row in schedule if int(row["block"]) == block]
        rows.sort(key=lambda row: int(row["visit"]))
        if len(rows) != len(expected_cells):
            raise ValueError(f"H2B block {block} has the wrong visit count")
        if {row["id"] for row in rows} != expected_cells:
            raise ValueError(f"H2B block {block} has the wrong cells")
        if [int(row["visit"]) for row in rows] != list(
            range(1, len(expected_cells) + 1)
        ):
            raise ValueError(f"H2B block {block} visit numbering mismatch")
        expected_start = (block - 1) * ACCEPTED_RUNS_PER_VISIT + 1
        if any(
            int(row["run_start"]) != expected_start
            or int(row["run_end"]) != expected_start + 2
            for row in rows
        ):
            raise ValueError(f"H2B block {block} accepted ordinals mismatch")
        seen_orders.append(tuple(row["id"] for row in rows))
    if len(set(seen_orders)) == 1:
        raise ValueError("H2B schedule did not randomize block order")
