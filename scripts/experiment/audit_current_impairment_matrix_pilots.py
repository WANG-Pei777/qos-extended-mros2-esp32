#!/usr/bin/env python3
"""Audit and summarize the current-implementation N=1 impairment pilots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / "results/audits/20260720_current_impairment_matrix_pilots"
TC_STATS = re.compile(
    r"Sent (?P<bytes>\d+) bytes (?P<sent>\d+) pkt "
    r"\(dropped (?P<dropped>\d+), overlimits (?P<overlimits>\d+) "
    r"requeues (?P<requeues>\d+)\)"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_key_values(line: str) -> dict[str, str]:
    values = {}
    for token in line.strip().split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def last_record(path: Path, prefix: str) -> dict[str, str]:
    match = None
    for raw in path.read_bytes().splitlines():
        line = raw.decode("utf-8", errors="ignore")
        if line.startswith(prefix):
            match = parse_key_values(line)
    if match is None:
        raise ValueError(f"{path}: missing {prefix}")
    return match


def capinfos(path: Path) -> tuple[int, float]:
    result = subprocess.run(
        ["capinfos", "-Tm", "-c", "-u", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = list(csv.DictReader(result.stdout.splitlines()))
    if len(rows) != 1:
        raise ValueError(f"{path}: capinfos returned {len(rows)} rows")
    return int(rows[0]["Number of packets"]), float(
        rows[0]["Capture duration (seconds)"]
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_cell(
    entry: dict[str, object], errors: list[str]
) -> tuple[dict[str, object], dict[str, object]]:
    root = REPO / str(entry["relative_path"])
    attempt = json.loads((root / "attempt_manifest.json").read_text(encoding="utf-8"))
    impairment = json.loads(
        (root / "impairment_manifest.json").read_text(encoding="utf-8")
    )
    compare = last_record(root / "serial.raw", "COMPARE_FINAL")
    config = last_record(root / "serial.raw", "BENCH_CONFIG")
    validation = parse_key_values(
        (root / "validation.txt").read_text(encoding="utf-8")
    )

    cell_id = f"{entry['qos']}/{entry['profile']}"
    expected = {
        "attempt_status": (attempt["status"], "PASS"),
        "impairment_status": (impairment["status"], "PASS"),
        "cleanup_ok": (impairment["cleanup_ok"], True),
        "qos": (config["qos"], entry["qos"]),
        "profile": (config["impairment"], entry["profile"]),
        "payload_bytes": (int(config["payload_bytes"]), 512),
        "rate_hz": (int(config["rate_hz"]), 50),
        "target_tx": (int(config["target_tx"]), 1000),
        "compare_tx": (int(compare["tx"]), 1000),
    }
    for name, (actual, wanted) in expected.items():
        if actual != wanted:
            errors.append(f"{cell_id}: {name}={actual!r} != {wanted!r}")

    validator = subprocess.run(
        attempt["commands"]["validator"],
        capture_output=True,
        text=True,
        check=False,
    )
    if validator.returncode != 0 or not validator.stdout.startswith("PASS:"):
        errors.append(f"{cell_id}: offline validator failed")

    for name, artifact in attempt["artifacts"].items():
        path = root / artifact["path"]
        if sha256(path) != artifact["sha256"]:
            errors.append(f"{cell_id}: {name} hash mismatch")
    for name, recorded_hash in impairment["tc_state_sha256"].items():
        if sha256(root / name) != recorded_hash:
            errors.append(f"{cell_id}: {name} hash mismatch")

    pcap = root / "traffic.pcapng"
    pcap_hash = sha256(pcap)
    if pcap_hash != impairment["pcap_sha256"]:
        errors.append(f"{cell_id}: PCAP hash mismatch")
    packets, duration = capinfos(pcap)

    tc_final = (root / "tc_final.txt").read_text(encoding="utf-8")
    stats_match = TC_STATS.search(tc_final)
    if stats_match:
        stats = {key: int(value) for key, value in stats_match.groupdict().items()}
    else:
        stats = {
            "bytes": 0,
            "sent": 0,
            "dropped": 0,
            "overlimits": 0,
            "requeues": 0,
        }
    profile = str(entry["profile"])
    if profile == "clean" and "netem" in tc_final:
        errors.append(f"{cell_id}: clean cell unexpectedly has netem")
    if profile != "clean" and f"qdisc netem" not in tc_final:
        errors.append(f"{cell_id}: configured netem state is absent")
    after = (root / "tc_after_cleanup.txt").read_text(encoding="utf-8")
    if "netem" in after or "qdisc mq" not in after:
        errors.append(f"{cell_id}: qdisc cleanup evidence failed")

    offered = stats["sent"] + stats["dropped"]
    observability_present = all(
        key in compare
        for key in (
            "missing",
            "missing_runs",
            "max_missing_run",
            "arrival_inversions",
            "rtt_sum_us",
            "rtt_sum_sq_us2",
        )
    )
    delivered = int(compare["rx"])
    if observability_present and delivered:
        rtt_mean_exact = int(compare["rtt_sum_us"]) / delivered
        rtt_variance = max(
            0.0,
            int(compare["rtt_sum_sq_us2"]) / delivered - rtt_mean_exact**2,
        )
        rtt_stddev_us: object = f"{math.sqrt(rtt_variance):.6f}"
    else:
        rtt_stddev_us = ""
    row = {
        "qos": entry["qos"],
        "profile": profile,
        "tx": int(compare["tx"]),
        "rx": int(compare["rx"]),
        "delivery_ratio": int(compare["rx"]) / int(compare["tx"]),
        "rtt_mean_us": int(compare["avg_us"]),
        "rtt_min_us": int(compare["min_us"]),
        "rtt_max_us": int(compare["max_us"]),
        "rtt_stddev_us": rtt_stddev_us,
        "missing": int(compare["missing"]) if observability_present else "",
        "missing_runs": (
            int(compare["missing_runs"]) if observability_present else ""
        ),
        "max_missing_run": (
            int(compare["max_missing_run"]) if observability_present else ""
        ),
        "arrival_inversions": (
            int(compare["arrival_inversions"]) if observability_present else ""
        ),
        "cpu_mean_ppm": int(validation["cpu_mean_ppm"]),
        "cpu_p95_ppm": int(validation["cpu_p95_ppm"]),
        "min_internal_heap_bytes": int(validation["min_internal_heap"]),
        "min_stack_hwm_bytes": int(validation["min_stack_hwm"]),
        "tc_sent_packets": stats["sent"],
        "tc_dropped_packets": stats["dropped"],
        "tc_offered_packets": offered,
        "tc_drop_ratio": stats["dropped"] / offered if offered else 0.0,
        "tc_requeues": stats["requeues"],
        "pcap_packets": packets,
        "pcap_duration_seconds": f"{duration:.9f}",
        "firmware_sha256": attempt["artifacts"]["firmware"]["sha256"],
        "cmake_cache_archived": "cmake_cache" in attempt["artifacts"],
        "relative_path": entry["relative_path"],
    }
    pcap_row = {
        "qos": entry["qos"],
        "profile": profile,
        "packets": packets,
        "capture_duration_seconds": f"{duration:.9f}",
        "sha256": pcap_hash,
        "relative_path": f"{entry['relative_path']}/traffic.pcapng",
    }
    return row, pcap_row


def efficacy_rows(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(row["qos"], row["profile"]): row for row in summary}
    rows = []
    for row in summary:
        qos = str(row["qos"])
        profile = str(row["profile"])
        clean = by_key[(qos, "clean")]
        delta_us = int(row["rtt_mean_us"]) - int(clean["rtt_mean_us"])
        status = "PASS"
        reason = "clean control has no netem qdisc"
        expected_value = "none"
        observed_value = "none"

        if profile.startswith("loss5_") or profile.startswith("loss15_"):
            target = 0.05 if profile.startswith("loss5_") else 0.15
            observed = float(row["tc_drop_ratio"])
            n = int(row["tc_offered_packets"])
            tolerance = max(0.02, 3.0 * math.sqrt(target * (1.0 - target) / n))
            status = "PASS" if abs(observed - target) <= tolerance else "FAIL"
            reason = "tc drop ratio is within the preregistration-pilot tolerance"
            expected_value = f"{target:.6f}"
            observed_value = f"{observed:.6f}"
        elif profile.startswith("delay20ms_h2b"):
            status = "PASS" if abs(delta_us - 20000) <= 8000 else "FAIL"
            reason = "mean application RTT shift checks the one-way host-egress delay"
            expected_value = "20000 us"
            observed_value = f"{delta_us} us"
        elif profile.startswith("delay50ms_h2b"):
            status = "PASS" if abs(delta_us - 50000) <= 8000 else "FAIL"
            reason = "mean application RTT shift checks the one-way host-egress delay"
            expected_value = "50000 us"
            observed_value = f"{delta_us} us"
        elif "jitter" in profile:
            status = "BLOCKED_OBSERVABILITY"
            reason = "aggregate min/mean/max cannot verify the injected RTT variance"
            expected_value = "10 ms normal delay variation"
            observed_value = f"mean shift {delta_us} us only"
        elif "reorder" in profile:
            status = "BLOCKED_OBSERVABILITY"
            reason = "tc requeues prove activity but not board-side arrival inversions"
            expected_value = "25% reorder, 50% correlation, gap 5"
            observed_value = f"tc_requeues={row['tc_requeues']}"
        elif profile.startswith("burst_"):
            status = "BLOCKED_OBSERVABILITY"
            reason = "total drops do not identify consecutive missing-message runs"
            expected_value = "Gilbert-Elliott burst structure"
            observed_value = f"tc_drop_ratio={float(row['tc_drop_ratio']):.6f}"

        rows.append(
            {
                "qos": qos,
                "profile": profile,
                "gate_status": status,
                "expected": expected_value,
                "observed": observed_value,
                "reason": reason,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.audit_root.resolve()
    ledger = json.loads((root / "collection_ledger.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if ledger["expected_cells"] != 16 or ledger["collected_cells"] != 16:
        errors.append("collection ledger is not 16/16")

    summary_rows = []
    pcap_rows = []
    for entry in ledger["entries"]:
        try:
            summary, pcap = audit_cell(entry, errors)
            summary_rows.append(summary)
            pcap_rows.append(pcap)
        except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
            errors.append(f"{entry.get('qos')}/{entry.get('profile')}: {exc}")

    gates = efficacy_rows(summary_rows) if len(summary_rows) == 16 else []
    write_csv(root / "pilot_summary.csv", summary_rows)
    write_csv(root / "pcap_inventory.csv", pcap_rows)
    if gates:
        write_csv(root / "efficacy_gate.csv", gates)
    blocked = sum(row["gate_status"] == "BLOCKED_OBSERVABILITY" for row in gates)
    failed = sum(row["gate_status"] == "FAIL" for row in gates)
    report = {
        "schema_version": 1,
        "classification": "current_impairment_matrix_engineering_pilot_audit",
        "evidence_boundary": "excluded N=1 efficacy pilots; never formal comparison data",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_status": "PASS" if not errors else "FAIL",
        "protocol_freeze_status": (
            "BLOCKED_EFFICACY_OBSERVABILITY" if blocked else "READY"
        ),
        "cells": len(summary_rows),
        "pcaps": len(pcap_rows),
        "efficacy_pass": sum(row["gate_status"] == "PASS" for row in gates),
        "efficacy_blocked": blocked,
        "efficacy_failed": failed,
        "cmake_cache_archived_cells": sum(
            bool(row["cmake_cache_archived"]) for row in summary_rows
        ),
        "energy_gate": "BLOCKED_EXTERNAL_CALIBRATED_MONITOR_AND_GPIO_ALIGNMENT",
        "errors": errors,
    }
    (root / "audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if errors or failed:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        f"PASS: cells=16 pcaps=16 efficacy_pass={16 - blocked} "
        f"efficacy_blocked={blocked} protocol_freeze=BLOCKED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
