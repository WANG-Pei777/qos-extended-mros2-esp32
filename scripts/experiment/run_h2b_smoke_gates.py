#!/usr/bin/env python3
"""Run the four exact-binary precollection smoke gates for formal H2B."""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from h2b_formal_common import (
    expected_injection,
    parse_latest_capture,
    read_rows,
    sha256_file,
)
from run_p4_smoke_gates import load_variants, stale_processes
from run_round6_smoke_gates import (
    flash_variant,
    git_output,
    require_network,
    resolve_artifact,
    validate_serial,
)
from verify_result_tree_seal import verify as verify_result_tree


SMOKE_TARGETS = (0, 15)
SMOKE_QOS = ("reliable", "best_effort")
BOARD_NETWORK_TIMEOUT_SECONDS = 210


def ledger_line_count(path):
    if not Path(path).is_file():
        return 0
    return sum(
        1
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def write_rtt_evidence(path, rows):
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--design-assets", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--flash-baud", type=int, default=460800)
    return parser.parse_args()


def main():
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.results_id):
        raise SystemExit("results-id contains unsupported characters")
    project_root = args.project_root.resolve()
    firmware_set = args.firmware_set.resolve()
    design_assets = args.design_assets.resolve()
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("H2B smoke requires a clean harness worktree")
    stale = stale_processes(project_root)
    if stale:
        raise SystemExit("stale experiment processes detected:\n" + "\n".join(stale))
    for root, label in (
        (firmware_set, "firmware set"),
        (design_assets, "design assets"),
    ):
        report = verify_result_tree(root)
        if report.get("status") != "PASS":
            raise SystemExit(f"H2B {label} release seal verification failed")

    design_manifest_path = design_assets / "manifest.json"
    design = json.loads(design_manifest_path.read_text(encoding="utf-8"))
    firmware_manifest_path = firmware_set / "manifest.json"
    firmware_master = json.loads(
        firmware_manifest_path.read_text(encoding="utf-8")
    )
    if design["firmware_set"]["manifest_sha256"] != sha256_file(
        firmware_manifest_path
    ):
        raise SystemExit("H2B design and firmware-set hashes differ")
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    if design["harness_commit"] != harness_commit:
        raise SystemExit("H2B smoke harness differs from frozen design")
    host_binary = project_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
    if design["host_binary_sha256"] != sha256_file(host_binary):
        raise SystemExit("H2B host binary differs from frozen design")
    variants = load_variants(firmware_set, firmware_master)
    wrapper = project_root / "scripts/experiment/run_transport_egress_gact.sh"
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        raise SystemExit(f"H2B wrapper is not executable: {wrapper}")
    require_network(
        args.board_ip,
        args.interface,
        timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
    )

    results_root = project_root / "results/experiments" / args.results_id
    results_root.mkdir(parents=True, exist_ok=True)
    smoke_manifest_path = results_root / "smoke_manifest.json"
    if smoke_manifest_path.exists():
        existing = json.loads(smoke_manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") == "PASS":
            print(f"[resume] H2B smoke PASS: {smoke_manifest_path}")
            return
        raise SystemExit(f"incomplete H2B smoke requires review: {results_root}")
    smoke = {
        "schema_version": 1,
        "classification": "h2b_exact_binary_smoke_gate",
        "status": "IN_PROGRESS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "harness_commit": harness_commit,
        "design_assets": {
            "path": str(design_assets),
            "manifest_sha256": sha256_file(design_manifest_path),
            "tree_sha256": json.loads(
                (design_assets / "release_seal.json").read_text(encoding="utf-8")
            )["tree_sha256"],
        },
        "firmware_set_manifest_sha256": sha256_file(firmware_manifest_path),
        "host_binary_sha256": sha256_file(host_binary),
        "wsl_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "board_ip": args.board_ip,
        "capture_interface": args.interface,
        "serial_port": args.serial_port,
        "required_cells": [
            {"qos": qos, "target_loss_percent": target}
            for qos in SMOKE_QOS
            for target in SMOKE_TARGETS
        ],
        "runs": [],
    }
    smoke_manifest_path.write_text(
        json.dumps(smoke, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pcaps_root = results_root / "pcaps"
    ledger = results_root / "TRANSPORT_EGRESS_GACT_LEDGER.md"
    for qos in SMOKE_QOS:
        variant = variants[qos]
        qos_root = results_root / qos
        flash = flash_variant(
            project_root,
            firmware_set,
            variant,
            args.serial_port,
            args.flash_baud,
            qos_root,
        )
        firmware = resolve_artifact(
            firmware_set, variant["artifacts"]["firmware"]
        )
        require_network(
            args.board_ip,
            args.interface,
            timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
        )
        for target in SMOKE_TARGETS:
            condition = f"h2b_smoke_{qos}_target{target:02d}"
            csv_path = results_root / f"mros2qos_{condition}.csv"
            sample_path = results_root / f"mros2qos_{condition}_rtt_samples.csv"
            before_rows = len(read_rows(csv_path))
            before_samples = len(read_rows(sample_path))
            before_ledger = ledger_line_count(ledger)
            run_log = qos_root / f"target_{target:02d}_runner.log"
            environment = os.environ.copy()
            environment.update({
                "FORMAL_RUN_OVERRIDE": "0",
                "FIRMWARE_MODE": qos,
                "FIRMWARE_BINARY": str(firmware),
                "NETEM_INTERFACE": args.interface,
                "CAPTURE_INTERFACE": args.interface,
                "BOARD_IP": args.board_ip,
                "NETWORK_CHANGE_ACK": "1",
                "RESULTS_DATE": args.results_id,
                "CONDITION_OVERRIDE": condition,
                "PCAP_DIR_OVERRIDE": str(pcaps_root),
                "SERIAL_PORT": args.serial_port,
            })
            with run_log.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    [str(wrapper), qos, str(target), "1"],
                    cwd=project_root,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            new_rows = read_rows(csv_path)[before_rows:]
            new_samples = read_rows(sample_path)[before_samples:]
            reasons = []
            if completed.returncode != 0:
                reasons.append(f"runner_exit:{completed.returncode}")
            if len(new_rows) != 1:
                reasons.append(f"outcome_rows:{len(new_rows)}")
            if ledger_line_count(ledger) != before_ledger + 1:
                reasons.append("ledger_count")
            capture = None
            try:
                capture = parse_latest_capture(
                    ledger, args.board_ip, qos, target
                )
            except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
                reasons.append(f"capture:{exc}")
            row = new_rows[0] if len(new_rows) == 1 else {}
            run_id = row.get("run_id", "missing")
            serial_path = results_root / f"mros2qos_{condition}_run{run_id}_serial.log"
            host_path = results_root / f"mros2qos_{condition}_run{run_id}_host.log"
            serial_text = ""
            if serial_path.is_file():
                serial_text = serial_path.read_text(
                    encoding="utf-8", errors="replace"
                )
            else:
                reasons.append("serial_missing")
            if not host_path.is_file():
                reasons.append("host_log_missing")
            expected = {
                "formal_run": "0",
                "condition": condition,
                "qos_mode": qos,
                "firmware_mode": qos,
                "host_mode": "cpp",
                "injection_layer": expected_injection(target),
                "commit_hash": harness_commit,
                "worktree_state": "clean",
                "matched_pub": "1",
                "matched_sub": "1",
            }
            for field, value in expected.items():
                if row.get(field) != value:
                    reasons.append(f"row:{field}")
            if serial_text and "All phases complete." not in serial_text:
                reasons.append("behavior_incomplete")
            if serial_text:
                reasons.extend(
                    f"serial:{item}"
                    for item in validate_serial(
                        serial_text,
                        variant["parameters"],
                        variant.get("app_version"),
                        qos,
                    )
                )
            matching_samples = [
                sample for sample in new_samples
                if sample.get("run_id") == str(run_id)
            ]
            if len(matching_samples) != int(row.get("rtt_count") or -1):
                reasons.append("rtt_sidecar_count")
            if not matching_samples:
                reasons.append("rtt_smoke_empty")
            rtt_evidence_path = qos_root / f"target_{target:02d}_rtt_samples.csv"
            write_rtt_evidence(rtt_evidence_path, matching_samples)
            condition_manifest_path = results_root / f"mros2qos_{condition}_manifest.json"
            if not condition_manifest_path.is_file():
                reasons.append("condition_manifest_missing")
                condition_manifest = {}
            else:
                condition_manifest = json.loads(
                    condition_manifest_path.read_text(encoding="utf-8")
                )
                if row.get("manifest_sha256") != sha256_file(
                    condition_manifest_path
                ):
                    reasons.append("condition_manifest_row_hash")
                if condition_manifest.get("firmware_binary", {}).get(
                    "sha256"
                ) != flash["firmware_sha256"]:
                    reasons.append("condition_manifest_firmware")
            if capture and capture["host_to_board_udp_packets"] <= 0:
                reasons.append("capture_no_h2b_udp")
            record = {
                "qos": qos,
                "target_loss_percent": target,
                "status": "PASS" if not reasons else "FAIL",
                "reasons": reasons,
                "flash": flash,
                "run_id": run_id,
                "row": row,
                "serial_path": str(serial_path),
                "serial_sha256": sha256_file(serial_path) if serial_path.is_file() else "",
                "host_path": str(host_path),
                "host_sha256": sha256_file(host_path) if host_path.is_file() else "",
                "rtt_evidence_path": str(rtt_evidence_path),
                "rtt_evidence_sha256": sha256_file(rtt_evidence_path),
                "condition_manifest_sha256": (
                    sha256_file(condition_manifest_path)
                    if condition_manifest_path.is_file()
                    else ""
                ),
                "runner_log_path": str(run_log),
                "runner_log_sha256": sha256_file(run_log),
                "capture": capture,
            }
            smoke["runs"].append(record)
            smoke_manifest_path.write_text(
                json.dumps(smoke, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if reasons:
                raise SystemExit(
                    f"H2B smoke failed for {qos} target {target}: {reasons}"
                )
            require_network(
                args.board_ip,
                args.interface,
                timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
            )

    smoke["status"] = "PASS"
    smoke["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    smoke["runs_total"] = len(smoke["runs"])
    smoke["runs_pass"] = sum(
        run["status"] == "PASS" for run in smoke["runs"]
    )
    smoke_manifest_path.write_text(
        json.dumps(smoke, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[complete] H2B exact-binary smoke PASS: {smoke_manifest_path}")


if __name__ == "__main__":
    main()
