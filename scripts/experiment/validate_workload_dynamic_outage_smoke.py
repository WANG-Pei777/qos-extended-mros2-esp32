#!/usr/bin/env python3
"""Validate a marker-aligned dynamic host-egress outage smoke tree."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


DROPPED_RE = re.compile(r"\bdropped\s+(\d+)\b")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(
    root: Path,
    profile: str,
    marker: str,
    expected_duration_seconds: float,
    expected_policy_family: str,
    tolerance_seconds: float,
) -> dict:
    errors: list[str] = []
    paths = {
        "manifest": root / "impairment_manifest.json",
        "attempt": root / "attempt_manifest.json",
        "outage": root / "tc_outage_final.txt",
        "after": root / "tc_after_cleanup.txt",
        "policy": root / "policy_validation.txt",
        "pcap": root / "traffic.pcapng",
    }
    for name, path in paths.items():
        if not path.is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {"status": "FAIL", "errors": errors}

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    attempt = json.loads(paths["attempt"].read_text(encoding="utf-8"))
    if manifest.get("classification") != "workload_impairment_engineering_smoke":
        errors.append("manifest:classification")
    if manifest.get("status") != "PASS" or manifest.get("runner_status") != "PASS":
        errors.append("manifest:status")
    if manifest.get("direction") != "host_to_board_dynamic_egress_only":
        errors.append("manifest:direction")
    if manifest.get("profile") != profile or manifest.get("dynamic_outage_kind") != profile:
        errors.append("manifest:profile")
    if manifest.get("dynamic_outage_marker") != marker:
        errors.append("manifest:marker")
    if manifest.get("dynamic_outage_marker_wait_seconds") is None:
        errors.append("manifest:marker_wait")
    if not manifest.get("cleanup_ok") or manifest.get("wrapper_error") is not None:
        errors.append("manifest:cleanup")
    if manifest.get("pcap_sha256") != sha256(paths["pcap"]):
        errors.append("manifest:pcap_sha256")
    if manifest.get("pcap_bytes") != paths["pcap"].stat().st_size:
        errors.append("manifest:pcap_bytes")

    actual_duration = -1.0
    try:
        started = datetime.fromisoformat(manifest["dynamic_outage_started_at_utc"])
        completed = datetime.fromisoformat(manifest["dynamic_outage_completed_at_utc"])
        actual_duration = (completed - started).total_seconds()
    except (KeyError, TypeError, ValueError):
        errors.append("manifest:outage_timestamps")
    if actual_duration >= 0 and not (
        expected_duration_seconds
        <= actual_duration
        <= expected_duration_seconds + tolerance_seconds
    ):
        errors.append("manifest:outage_duration")

    outage = paths["outage"].read_text(encoding="utf-8", errors="replace")
    dropped_match = DROPPED_RE.search(outage)
    dropped = int(dropped_match.group(1)) if dropped_match else 0
    if "qdisc netem" not in outage or "loss 100%" not in outage:
        errors.append("outage:qdisc")
    if dropped <= 0:
        errors.append("outage:no_drops")
    after = paths["after"].read_text(encoding="utf-8", errors="replace")
    if "netem" in after or "qdisc mq" not in after:
        errors.append("cleanup:qdisc")

    if attempt.get("status") != "PASS":
        errors.append("attempt:status")
    workload = attempt.get("workload", {})
    if workload.get("impairment") != profile:
        errors.append("attempt:profile")
    policy = paths["policy"].read_text(encoding="utf-8", errors="replace").strip()
    if not policy.startswith(f"PASS: family={expected_policy_family} "):
        errors.append("policy:status")
    return {
        "classification": "workload_dynamic_outage_smoke_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "profile": profile,
        "marker": marker,
        "expected_duration_seconds": expected_duration_seconds,
        "actual_duration_seconds": actual_duration,
        "dropped_packets": dropped,
        "pcap_sha256": sha256(paths["pcap"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--expected-duration-seconds", type=float, required=True)
    parser.add_argument("--expected-policy-family", required=True)
    parser.add_argument("--tolerance-seconds", type=float, default=0.25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.expected_duration_seconds <= 0 or args.tolerance_seconds < 0:
        parser.error("duration must be positive and tolerance nonnegative")
    report = validate(
        args.result_root.resolve(), args.profile, args.marker,
        args.expected_duration_seconds, args.expected_policy_family,
        args.tolerance_seconds,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
