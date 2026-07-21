#!/usr/bin/env python3
"""Frozen constants and validation for the three-system comparison."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import random
import subprocess
from typing import Any


SYSTEM_ORDER = ("mros2qos", "upstream", "microros")
SYSTEM_LABELS = {
    "mros2qos": "mROS2-QoS",
    "upstream": "upstream mros2-esp32",
    "microros": "micro-ROS",
}
SCHEDULE_SEED = 202607153
SUPERBLOCKS = 10
ACCEPTED_RUNS_PER_VISIT = 10
MEASUREMENT_MESSAGES = 40
PAYLOAD_BYTES = 64
PUBLISH_PERIOD_MS = 500
READY_SETTLE_MS = 1000
REPLY_GRACE_MS = 5000
SCHEDULE_FIELDS = (
    "block",
    "visit",
    "visit_in_block",
    "system",
    "run_start",
    "run_end",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, root: Path | None = None) -> dict[str, Any]:
    path = Path(path).resolve()
    display = path.relative_to(root.resolve()) if root else path
    return {
        "path": str(display),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def git_output(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *arguments], text=True
    ).strip()


def require_clean_repo(repo: Path) -> str:
    repo = Path(repo).resolve()
    status = git_output(repo, "status", "--porcelain")
    if status:
        raise ValueError(f"source repository is not clean: {repo}")
    return git_output(repo, "rev-parse", "HEAD")


def interface_ipv4(interface: str) -> str:
    output = subprocess.check_output(
        ["ip", "-4", "-o", "addr", "show", "dev", interface], text=True
    )
    for part in output.split():
        if "/" in part and part.split("/", 1)[0].count(".") == 3:
            return part.split("/", 1)[0]
    raise ValueError(f"no IPv4 address is assigned to interface {interface}")


def generate_schedule(seed: int = SCHEDULE_SEED) -> list[dict[str, int | str]]:
    generator = random.Random(seed)
    rows: list[dict[str, int | str]] = []
    visit = 0
    for block in range(1, SUPERBLOCKS + 1):
        systems = list(SYSTEM_ORDER)
        generator.shuffle(systems)
        run_start = (block - 1) * ACCEPTED_RUNS_PER_VISIT + 1
        for visit_in_block, system in enumerate(systems, start=1):
            visit += 1
            rows.append(
                {
                    "block": block,
                    "visit": visit,
                    "visit_in_block": visit_in_block,
                    "system": system,
                    "run_start": run_start,
                    "run_end": run_start + ACCEPTED_RUNS_PER_VISIT - 1,
                }
            )
    validate_schedule(rows)
    return rows


def validate_schedule(rows: list[dict[str, Any]]) -> None:
    if len(rows) != SUPERBLOCKS * len(SYSTEM_ORDER):
        raise ValueError("three-system schedule must contain exactly 30 visits")
    if [int(row["visit"]) for row in rows] != list(range(1, 31)):
        raise ValueError("schedule visits must be consecutive")
    for block in range(1, SUPERBLOCKS + 1):
        block_rows = [row for row in rows if int(row["block"]) == block]
        if len(block_rows) != 3:
            raise ValueError(f"superblock {block} does not contain three visits")
        if {row["system"] for row in block_rows} != set(SYSTEM_ORDER):
            raise ValueError(f"superblock {block} does not contain all systems")
        if sorted(int(row["visit_in_block"]) for row in block_rows) != [1, 2, 3]:
            raise ValueError(f"superblock {block} has invalid visit order")
        expected_start = (block - 1) * ACCEPTED_RUNS_PER_VISIT + 1
        for row in block_rows:
            if int(row["run_start"]) != expected_start:
                raise ValueError(f"superblock {block} has invalid run_start")
            if int(row["run_end"]) != expected_start + 9:
                raise ValueError(f"superblock {block} has invalid run_end")


def write_schedule(path: Path, rows: list[dict[str, Any]]) -> None:
    validate_schedule(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCHEDULE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_schedule(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or tuple(rows[0].keys()) != SCHEDULE_FIELDS:
        raise ValueError("schedule schema mismatch")
    validate_schedule(rows)
    return rows


def _compare_line(raw_line: str) -> str | None:
    offset = raw_line.find("COMPARE_")
    return raw_line[offset:].strip() if offset >= 0 else None


def _fields(line: str) -> tuple[str, dict[str, str]]:
    parts = line.split()
    return parts[0], {
        key: value
        for part in parts[1:]
        if "=" in part
        for key, value in [part.split("=", 1)]
    }


def _integer(fields: dict[str, str], key: str, errors: list[str]) -> int:
    try:
        return int(fields[key])
    except (KeyError, ValueError):
        errors.append(f"invalid_integer:{key}")
        return -1


def parse_compare_serial(serial_text: str, expected_system: str) -> dict[str, Any]:
    """Parse one run without using measured outcomes as acceptance thresholds."""
    if expected_system not in SYSTEM_ORDER:
        raise ValueError(f"unknown system: {expected_system}")
    records: list[tuple[int, str, dict[str, str]]] = []
    for line_number, raw_line in enumerate(serial_text.splitlines(), start=1):
        line = _compare_line(raw_line)
        if line:
            record_type, fields = _fields(line)
            records.append((line_number, record_type, fields))

    errors: list[str] = []
    by_type: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for line_number, record_type, fields in records:
        by_type.setdefault(record_type, []).append((line_number, fields))
        if fields.get("system") not in (None, expected_system):
            errors.append(f"system_mismatch:{record_type}")
    if by_type.get("COMPARE_FATAL"):
        errors.append("firmware_fatal")

    required_once = (
        "COMPARE_CONFIG",
        "COMPARE_READY",
        "COMPARE_RESOURCE",
        "COMPARE_FINAL",
    )
    for record_type in required_once:
        count = len(by_type.get(record_type, []))
        if count != 1:
            errors.append(f"record_count:{record_type}:{count}")

    config = by_type.get("COMPARE_CONFIG", [(0, {})])[-1][1]
    expected_config = {
        "system": expected_system,
        "qos": "BEST_EFFORT",
        "payload_bytes": str(PAYLOAD_BYTES),
        "messages": str(MEASUREMENT_MESSAGES),
        "period_ms": str(PUBLISH_PERIOD_MS),
        "settle_ms": str(READY_SETTLE_MS),
        "grace_ms": str(REPLY_GRACE_MS),
    }
    for key, value in expected_config.items():
        if config.get(key) != value:
            errors.append(f"config_mismatch:{key}")

    ready_fields = by_type.get("COMPARE_READY", [(0, {})])[-1][1]
    ready_ms = _integer(ready_fields, "ready_ms", errors)
    if ready_ms < 0:
        errors.append("ready_negative")

    resource = by_type.get("COMPARE_RESOURCE", [(0, {})])[-1][1]
    free_heap_bytes = _integer(resource, "free_heap_bytes", errors)
    if free_heap_bytes <= 0:
        errors.append("resource_heap_nonpositive")

    rtt_records = by_type.get("COMPARE_RTT", [])
    rtts: dict[int, int] = {}
    final_line = by_type.get("COMPARE_FINAL", [(10**9, {})])[-1][0]
    for line_number, fields in rtt_records:
        sequence = _integer(fields, "seq", errors)
        rtt_us = _integer(fields, "rtt_us", errors)
        if sequence < 0 or sequence >= MEASUREMENT_MESSAGES:
            errors.append(f"rtt_sequence_range:{sequence}")
        elif sequence in rtts:
            errors.append(f"rtt_duplicate:{sequence}")
        else:
            rtts[sequence] = rtt_us
        if rtt_us <= 0 or rtt_us >= 10_000_000:
            errors.append(f"rtt_value_range:{sequence}")
        if line_number > final_line:
            errors.append(f"rtt_after_final:{sequence}")

    final = by_type.get("COMPARE_FINAL", [(0, {})])[-1][1]
    final_values = {
        key: _integer(final, key, errors)
        for key in (
            "tx",
            "rx",
            "samples",
            "min_us",
            "avg_us",
            "max_us",
            "ready_ms",
            "payload_bytes",
            "period_ms",
            "grace_ms",
        )
    }
    if final.get("system") != expected_system:
        errors.append("final_system_mismatch")
    for key, expected in (
        ("tx", MEASUREMENT_MESSAGES),
        ("payload_bytes", PAYLOAD_BYTES),
        ("period_ms", PUBLISH_PERIOD_MS),
        ("grace_ms", REPLY_GRACE_MS),
    ):
        if final_values[key] != expected:
            errors.append(f"final_mismatch:{key}")
    if final_values["rx"] != final_values["samples"]:
        errors.append("final_rx_samples_mismatch")
    if final_values["samples"] != len(rtts):
        errors.append("final_rtt_count_mismatch")
    if final_values["ready_ms"] != ready_ms:
        errors.append("final_ready_mismatch")

    values = list(rtts.values())
    expected_min = min(values) if values else 0
    expected_max = max(values) if values else 0
    expected_average = sum(values) // len(values) if values else 0
    for key, expected in (
        ("min_us", expected_min),
        ("avg_us", expected_average),
        ("max_us", expected_max),
    ):
        if final_values[key] != expected:
            errors.append(f"final_stat_mismatch:{key}")

    if expected_system == "microros":
        sessions = by_type.get("COMPARE_SESSION", [])
        if len(sessions) != 1:
            errors.append(f"record_count:COMPARE_SESSION:{len(sessions)}")
            session_ms = -1
        else:
            session_ms = _integer(sessions[0][1], "established_ms", errors)
            if session_ms < 0 or (ready_ms >= 0 and session_ms > ready_ms):
                errors.append("session_ready_order")
        failures = _integer(final, "publish_failures", errors)
        if failures != 0:
            errors.append("publish_failures")
    else:
        session_ms = None

    return {
        "accepted": not errors,
        "errors": sorted(set(errors)),
        "system": expected_system,
        "ready_ms": ready_ms,
        "session_ms": session_ms,
        "free_heap_bytes": free_heap_bytes,
        "tx": final_values["tx"],
        "rx": final_values["rx"],
        "samples": final_values["samples"],
        "rtts_us": [
            {"seq": sequence, "rtt_us": rtts[sequence]}
            for sequence in sorted(rtts)
        ],
        "final": final,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_record(root: Path, record: dict[str, Any]) -> Path:
    root = Path(root).resolve()
    candidate = (root / record["path"]).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"artifact escapes set root: {candidate}") from exc
    if not candidate.is_file():
        raise ValueError(f"artifact is missing: {candidate}")
    if candidate.stat().st_size != record["bytes"]:
        raise ValueError(f"artifact size mismatch: {candidate}")
    if sha256_file(candidate) != record["sha256"]:
        raise ValueError(f"artifact hash mismatch: {candidate}")
    return candidate


def verify_agent_runtime(record: dict[str, Any]) -> list[str]:
    """Verify the exact Agent ELF, Snap launcher, and installed package revision."""

    verified: dict[str, Path] = {}
    for key in ("artifact", "launcher"):
        item = record[key]
        path = Path(item["path"]).resolve()
        if not path.is_file():
            raise ValueError(f"micro-ROS Agent {key} is missing: {path}")
        if path.stat().st_size != item["bytes"]:
            raise ValueError(f"micro-ROS Agent {key} size changed: {path}")
        if sha256_file(path) != item["sha256"]:
            raise ValueError(f"micro-ROS Agent {key} hash changed: {path}")
        verified[key] = path

    launch_command = [str(item) for item in record["launch_command"]]
    query_command = [str(item) for item in record["package_query_command"]]
    if (
        not launch_command
        or Path(launch_command[0]).resolve() != verified["launcher"]
    ):
        raise ValueError("micro-ROS Agent launch command does not use sealed launcher")
    if (
        not query_command
        or Path(query_command[0]).resolve() != verified["launcher"]
    ):
        raise ValueError("micro-ROS Agent package query does not use sealed launcher")
    package_output = subprocess.check_output(
        query_command, text=True, stderr=subprocess.STDOUT
    ).strip()
    if package_output != record["package_query_output"]:
        raise ValueError("micro-ROS Agent package revision changed after sealing")
    return launch_command
