#!/usr/bin/env python3
"""Validate one excluded B2H IFB ingress-impairment smoke tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


PROFILE_BOUNDS = {
    "loss5_independent_b2h": (5.0, 2.0, 8.0),
    "loss15_independent_b2h": (15.0, 10.0, 20.0),
}
QDISC_COUNTER_RE = re.compile(
    r"Sent\s+\d+\s+bytes\s+(?P<packets>\d+)\s+pkt\s+"
    r"\(dropped\s+(?P<dropped>\d+),"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path, profile: str, board_ip: str, minimum_packets: int) -> dict:
    errors: list[str] = []
    manifest_path = root / "ingress_impairment_manifest.json"
    attempt_path = root / "attempt_manifest.json"
    pcap_path = root / "traffic.pcapng"
    policy_path = root / "policy_validation.txt"
    ifb_path = root / "tc_ifb_final.txt"
    after_path = root / "tc_after_cleanup.txt"
    required = (
        manifest_path, attempt_path, pcap_path, policy_path, ifb_path, after_path
    )
    for path in required:
        if not path.is_file():
            errors.append(f"missing:{path.name}")
    if errors:
        return {"status": "FAIL", "errors": errors}

    manifest = load_json(manifest_path)
    attempt = load_json(attempt_path)
    expected_loss, lower, upper = PROFILE_BOUNDS[profile]
    if manifest.get("classification") != "workload_ingress_impairment_engineering_smoke":
        errors.append("manifest:classification")
    if manifest.get("status") != "PASS" or manifest.get("runner_status") != "PASS":
        errors.append("manifest:status")
    if manifest.get("direction") != "board_to_host_ingress_only":
        errors.append("manifest:direction")
    if manifest.get("profile") != profile:
        errors.append("manifest:profile")
    if manifest.get("board_ip") != board_ip:
        errors.append("manifest:board_ip")
    if manifest.get("source_filter") != f"ip src {board_ip}/32":
        errors.append("manifest:source_filter")
    if not manifest.get("cleanup_ok") or manifest.get("wrapper_error") is not None:
        errors.append("manifest:cleanup")
    if manifest.get("pcap_sha256") != sha256(pcap_path):
        errors.append("manifest:pcap_sha256")
    if manifest.get("pcap_bytes") != pcap_path.stat().st_size or pcap_path.stat().st_size <= 0:
        errors.append("manifest:pcap_bytes")

    if attempt.get("status") != "PASS":
        errors.append("attempt:status")
    workload = attempt.get("workload", {})
    if workload.get("impairment") != profile:
        errors.append("attempt:impairment")
    if workload.get("delivery_policy") != "outcome":
        errors.append("attempt:delivery_policy")

    policy_text = policy_path.read_text(encoding="utf-8", errors="replace").strip()
    if not policy_text.startswith("PASS: family=history_depth "):
        errors.append("policy:history_depth_pass")

    ifb_text = ifb_path.read_text(encoding="utf-8", errors="replace")
    if f"loss {expected_loss:g}%" not in ifb_text:
        errors.append("ifb:configured_loss")
    match = QDISC_COUNTER_RE.search(ifb_text)
    packets = int(match.group("packets")) if match else 0
    dropped = int(match.group("dropped")) if match else 0
    if not match:
        errors.append("ifb:counters")
    if packets < minimum_packets:
        errors.append("ifb:minimum_packets")
    effective = 100.0 * dropped / packets if packets else 0.0
    if not lower <= effective <= upper:
        errors.append("ifb:effective_loss")

    after = after_path.read_text(encoding="utf-8", errors="replace")
    if "netem" in after or "ingress" in after or "clsact" in after:
        errors.append("cleanup:qdisc_residue")
    if "qdisc mq" not in after or after.count("qdisc fq_codel") < 1:
        errors.append("cleanup:canonical_root")
    return {
        "classification": "workload_ingress_impairment_smoke_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "profile": profile,
        "board_ip": board_ip,
        "packets": packets,
        "dropped": dropped,
        "effective_loss_percent": effective,
        "allowed_loss_percent": [lower, upper],
        "pcap_sha256": sha256(pcap_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--profile", choices=tuple(PROFILE_BOUNDS), required=True)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--minimum-packets", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.minimum_packets < 1:
        parser.error("--minimum-packets must be positive")
    report = validate(
        args.result_root.resolve(), args.profile, args.board_ip, args.minimum_packets
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
