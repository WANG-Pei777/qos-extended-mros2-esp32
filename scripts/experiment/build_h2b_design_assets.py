#!/usr/bin/env python3
"""Freeze and seal the formal H2B randomized schedule and design identity."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from h2b_formal_common import (
    ACCEPTED_RUNS_PER_VISIT,
    EXPECTED_ACCEPTED_RUNS,
    EXPECTED_BLOCKS,
    EXPECTED_VISITS,
    LOSS_SPECS,
    QOS_MODES,
    SCHEDULE_SEED,
    sha256_file,
    validate_schedule,
)
from seal_result_tree import inventory, tree_digest, write_manifest
from verify_result_tree_seal import verify as verify_result_tree


def git_output(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True
    ).strip()


def build_schedule():
    cells = [
        {
            "id": f"{qos}_target{target:02d}",
            "qos": qos,
            "target_loss_percent": target,
        }
        for qos in QOS_MODES
        for target in LOSS_SPECS
    ]
    rng = random.Random(SCHEDULE_SEED)
    rows = []
    for block in range(1, EXPECTED_BLOCKS + 1):
        order = list(cells)
        rng.shuffle(order)
        start = (block - 1) * ACCEPTED_RUNS_PER_VISIT + 1
        for visit, cell in enumerate(order, start=1):
            rows.append({
                "block": block,
                "visit": visit,
                "id": cell["id"],
                "qos": cell["qos"],
                "target_loss_percent": cell["target_loss_percent"],
                "run_start": start,
                "run_end": start + ACCEPTED_RUNS_PER_VISIT - 1,
            })
    validate_schedule(rows)
    return rows


def main():
    repo_root = SCRIPT_DIR.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=repo_root / "docs/benchmark/H2B_PER_MESSAGE_PREREGISTRATION.md",
    )
    args = parser.parse_args()
    if git_output(repo_root, "status", "--porcelain"):
        raise SystemExit("H2B design freeze requires a clean worktree")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"H2B design output already exists: {output_dir}")
    firmware_set = args.firmware_set.resolve()
    firmware_verification = verify_result_tree(firmware_set)
    if firmware_verification.get("status") != "PASS":
        raise SystemExit("P4 firmware-set release seal verification failed")
    firmware_manifest_path = firmware_set / "manifest.json"
    firmware_manifest = json.loads(
        firmware_manifest_path.read_text(encoding="utf-8")
    )
    if firmware_manifest.get("classification") != "p4_replication_firmware_set":
        raise SystemExit("H2B requires the sealed P4 firmware set")
    protocol = args.protocol.resolve()
    if not protocol.is_file():
        raise SystemExit(f"missing H2B preregistration: {protocol}")

    output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = output_dir / "randomized_schedule.csv"
    rows = build_schedule()
    with schedule_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    host_binary = repo_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
    manifest = {
        "schema_version": 1,
        "classification": "h2b_formal_design_assets",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "harness_commit": git_output(repo_root, "rev-parse", "HEAD"),
        "protocol": {
            "path": str(protocol),
            "sha256": sha256_file(protocol),
        },
        "firmware_set": {
            "path": str(firmware_set),
            "manifest_sha256": sha256_file(firmware_manifest_path),
            "tree_sha256": firmware_verification["tree_sha256"],
            "source_commit": firmware_manifest["source_commit"],
        },
        "host_binary_sha256": sha256_file(host_binary),
        "schedule": {
            "path": str(schedule_path),
            "sha256": sha256_file(schedule_path),
            "seed": SCHEDULE_SEED,
            "blocks": EXPECTED_BLOCKS,
            "visits": EXPECTED_VISITS,
            "accepted_runs_per_visit": ACCEPTED_RUNS_PER_VISIT,
            "accepted_runs_total": EXPECTED_ACCEPTED_RUNS,
        },
        "loss_specs": {str(key): value for key, value in LOSS_SPECS.items()},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = inventory(output_dir)
    release_manifest = output_dir / "release_file_manifest.csv"
    write_manifest(release_manifest, rows)
    seal = {
        "schema_version": 1,
        "classification": "experiment_result_tree_release_seal",
        "root": str(output_dir),
        "file_count": len(rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "tree_sha256": tree_digest(rows),
        "file_manifest_sha256": sha256_file(release_manifest),
        "excluded_self_referential_files": [
            "release_file_manifest.csv",
            "release_seal.json",
        ],
    }
    (output_dir / "release_seal.json").write_text(
        json.dumps(seal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = verify_result_tree(output_dir)
    if report.get("status") != "PASS":
        raise SystemExit("H2B design-asset seal verification failed")
    print(json.dumps({"manifest": manifest, "seal": seal}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
