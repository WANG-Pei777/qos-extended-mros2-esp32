#!/usr/bin/env python3
"""Execute the frozen Round 6 schedule with exact archived firmware."""

import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_round6_smoke_gates import (
    count_board_udp_packets,
    flash_variant,
    git_output,
    require_network,
    resolve_artifact,
    sha256_file,
    validate_serial,
)


TARGET_LOSS_PERCENT = 15
GACT_DENOMINATOR = 7
EFFECTIVE_LOSS_PERCENT = 100.0 / GACT_DENOMINATOR
ACCEPTED_RUNS_PER_VISIT = 3


def condition_for(cell_id):
    return (
        f"round6_{cell_id}_b2h_target15_"
        "gact1of7_eff14p285714"
    )


def read_rows(path):
    if not Path(path).is_file():
        return []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evaluate_row(
    row,
    serial_text,
    parameters,
    app_version,
    capture,
    expected_row,
):
    reasons = []
    if row.get("formal_run") != "1":
        reasons.append("not_formal")
    if row.get("worktree_state") != "clean":
        reasons.append("dirty_harness")
    if row.get("matched_pub") != "1" or row.get("matched_sub") != "1":
        reasons.append("endpoint_match_failed")
    if "All phases complete." not in serial_text:
        reasons.append("behavior_incomplete")
    if "VALIDATION NOT READY" in serial_text:
        reasons.append("validation_not_ready")
    if not capture:
        reasons.append("capture_missing")
    elif capture["board_to_host_udp_packets"] <= 0:
        reasons.append("capture_no_board_to_host_udp")
    for field, expected in expected_row.items():
        if row.get(field) != expected:
            reasons.append(f"row_provenance:{field}")
    reasons.extend(
        f"missing_serial:{item}"
        for item in validate_serial(serial_text, parameters, app_version)
    )
    return reasons


def latest_pcap_from_ledger(ledger_path, board_ip):
    lines = [
        line.strip()
        for line in Path(ledger_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError(f"empty ingress ledger: {ledger_path}")
    fields = {}
    for part in lines[-1].split(" | "):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    pcap = Path(fields["pcap"])
    expected = fields["sha256"]
    if not pcap.is_file() or sha256_file(pcap) != expected:
        raise ValueError(f"PCAP ledger hash mismatch: {pcap}")
    if fields.get("target_loss") != f"{TARGET_LOSS_PERCENT}%":
        raise ValueError("ingress ledger target-loss mismatch")
    if fields.get("denominator") != str(GACT_DENOMINATOR):
        raise ValueError("ingress ledger denominator mismatch")
    effective = float(fields.get("effective_loss", "").removesuffix("%"))
    if abs(effective - EFFECTIVE_LOSS_PERCENT) > 0.000001:
        raise ValueError("ingress ledger effective-loss mismatch")
    tc_state = Path(fields["tc_state"])
    tc_expected = fields["tc_state_sha256"]
    if not tc_state.is_file() or sha256_file(tc_state) != tc_expected:
        raise ValueError(f"tc state ledger hash mismatch: {tc_state}")
    board_packets = count_board_udp_packets(pcap, board_ip)
    return {
        "path": str(pcap),
        "sha256": expected,
        "bytes": pcap.stat().st_size,
        "board_to_host_udp_packets": board_packets,
        "tc_state_path": str(tc_state),
        "tc_state_sha256": tc_expected,
        "target_loss_percent": TARGET_LOSS_PERCENT,
        "gact_denominator": GACT_DENOMINATOR,
        "effective_loss_percent": EFFECTIVE_LOSS_PERCENT,
    }


def append_acceptance_rows(path, records):
    fields = [
        "block",
        "visit",
        "cell",
        "condition",
        "run_id",
        "accepted_ordinal",
        "accepted",
        "rejection_reason",
        "firmware_sha256",
        "serial_sha256",
        "manifest_sha256",
        "pcap_sha256",
        "pcap_board_to_host_udp_packets",
        "tc_state_sha256",
        "harness_commit",
    ]
    path = Path(path)
    exists = path.exists()
    if exists:
        with path.open(newline="", encoding="utf-8") as handle:
            existing_fields = next(csv.reader(handle), [])
        if existing_fields != fields:
            raise ValueError(f"acceptance ledger schema mismatch: {path}")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows(records)


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="10.219.224.107")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--max-visits", type=int)
    parser.add_argument("--max-attempts-per-visit", type=int, default=6)
    return parser.parse_args()


def main():
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.results_id):
        raise SystemExit("results-id contains unsupported characters")
    if args.max_visits is not None and args.max_visits < 1:
        raise SystemExit("max-visits must be positive")
    if args.max_attempts_per_visit < ACCEPTED_RUNS_PER_VISIT:
        raise SystemExit("max-attempts-per-visit must be at least 3")
    project_root = args.project_root.resolve()
    firmware_set = args.firmware_set.resolve()
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("formal execution requires a clean harness worktree")
    wrapper = project_root / "scripts/experiment/run_transport_ingress_gact.sh"
    host_binary = (
        project_root
        / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
    )
    for executable in (wrapper, host_binary):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise SystemExit(f"formal executable unavailable: {executable}")
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    set_manifest_path = firmware_set / "manifest.json"
    set_manifest = json.loads(set_manifest_path.read_text(encoding="utf-8"))
    schedule = list(
        csv.DictReader(
            (firmware_set / "randomized_schedule.csv").open(
                newline="",
                encoding="utf-8",
            )
        )
    )
    variants = {
        item["id"]: json.loads(
            (
                firmware_set
                / "variants"
                / item["id"]
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        for item in set_manifest["variants"]
    }
    variant_ids = set(variants)
    if len(schedule) != 120 or len(variant_ids) != 12:
        raise SystemExit("frozen design must contain 120 visits and 12 variants")
    for block in range(1, 11):
        block_rows = [row for row in schedule if int(row["block"]) == block]
        if len(block_rows) != 12 or {row["id"] for row in block_rows} != variant_ids:
            raise SystemExit(f"invalid randomized superblock {block}")
        expected_start = (block - 1) * ACCEPTED_RUNS_PER_VISIT + 1
        if any(
            int(row["run_start"]) != expected_start
            or int(row["run_end"]) != expected_start + 2
            for row in block_rows
        ):
            raise SystemExit(f"invalid accepted-run ordinals in block {block}")
    results_root = (
        project_root / "results/experiments" / args.results_id
    )
    visits_root = results_root / "visits"
    pcaps_root = results_root / "pcaps"
    visits_root.mkdir(parents=True, exist_ok=True)
    pcaps_root.mkdir(parents=True, exist_ok=True)
    design_path = results_root / "design_manifest.json"
    design = {
        "schema_version": 1,
        "classification": "round6_formal_factorial",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "IN_PROGRESS",
        "firmware_set_manifest": {
            "path": str(set_manifest_path),
            "sha256": sha256_file(set_manifest_path),
            "source_commit": set_manifest["source_commit"],
        },
        "harness_commit": harness_commit,
        "runtime": {
            "board_ip": args.board_ip,
            "capture_interface": args.interface,
            "capture_filter": "board source IP and UDP ports 7400-7420",
            "serial_port": args.serial_port,
        },
        "schedule_sha256": sha256_file(
            firmware_set / "randomized_schedule.csv"
        ),
        "accepted_runs_per_visit": ACCEPTED_RUNS_PER_VISIT,
        "impairment": {
            "direction": "board_to_host_ingress",
            "implementation": "tc_gact_random_netrand",
            "nominal_target_percent": TARGET_LOSS_PERCENT,
            "inverse_probability_denominator": GACT_DENOMINATOR,
            "configured_effective_percent": EFFECTIVE_LOSS_PERCENT,
        },
    }
    if design_path.exists():
        existing = json.loads(design_path.read_text(encoding="utf-8"))
        for key in (
            "firmware_set_manifest",
            "harness_commit",
            "schedule_sha256",
            "accepted_runs_per_visit",
            "impairment",
            "runtime",
        ):
            if existing.get(key) != design[key]:
                raise SystemExit(f"formal design conflict at {key}")
        design = existing
    else:
        design_path.write_text(
            json.dumps(design, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    acceptance_path = results_root / "acceptance_ledger.csv"
    selected = schedule
    if args.max_visits is not None:
        selected = schedule[: args.max_visits]
    completed_visits = 0
    for schedule_row in selected:
        block = int(schedule_row["block"])
        visit = int(schedule_row["visit"])
        cell_id = schedule_row["id"]
        visit_id = f"block_{block:02d}_visit_{visit:02d}_{cell_id}"
        visit_dir = visits_root / visit_id
        visit_manifest_path = visit_dir / "manifest.json"
        if visit_manifest_path.exists():
            existing = json.loads(
                visit_manifest_path.read_text(encoding="utf-8")
            )
            if existing.get("status") == "PASS":
                print(f"[resume] {visit_id} PASS")
                completed_visits += 1
                continue
            raise SystemExit(f"incomplete visit requires review: {visit_dir}")

        visit_dir.mkdir(parents=True, exist_ok=True)
        variant = variants[cell_id]
        parameters = variant["parameters"]
        prior_accepted = sum(
            row["cell"] == cell_id and row["accepted"] == "1"
            for row in read_rows(acceptance_path)
        )
        expected_prior = int(schedule_row["run_start"]) - 1
        if prior_accepted != expected_prior:
            raise SystemExit(
                f"accepted-run ordinal mismatch for {visit_id}: "
                f"expected {expected_prior}, observed {prior_accepted}"
            )
        firmware = resolve_artifact(
            firmware_set,
            variant["artifacts"]["firmware"],
        )
        require_network(args.board_ip, args.interface)
        flash = flash_variant(
            project_root,
            firmware_set,
            variant,
            args.serial_port,
            args.flash_baud,
            visit_dir,
        )
        require_network(args.board_ip, args.interface)
        condition = condition_for(cell_id)
        expected_injection = (
            "transport_ingress_gact_board_to_host_target_15pct_"
            "1of7_effective_14.285714pct"
        )
        csv_path = results_root / f"mros2qos_{condition}.csv"
        accepted = []
        rejected = []
        attempts = []
        ledger_path = results_root / "TRANSPORT_INGRESS_GACT_LEDGER.md"

        for attempt in range(1, args.max_attempts_per_visit + 1):
            if len(accepted) >= ACCEPTED_RUNS_PER_VISIT:
                break
            before_rows = read_rows(csv_path)
            before_ledger_count = len(
                ledger_path.read_text(encoding="utf-8").splitlines()
            ) if ledger_path.is_file() else 0
            run_log = visit_dir / f"attempt_{attempt:02d}.log"
            environment = os.environ.copy()
            environment.update(
                {
                    "FIRMWARE_MODE": "reliable",
                    "FIRMWARE_BINARY": str(firmware),
                    "NETEM_INTERFACE": args.interface,
                    "CAPTURE_INTERFACE": args.interface,
                    "BOARD_IP": args.board_ip,
                    "NETWORK_CHANGE_ACK": "1",
                    "RESULTS_DATE": args.results_id,
                    "CONDITION_OVERRIDE": condition,
                    "PCAP_DIR_OVERRIDE": str(pcaps_root),
                    "SERIAL_PORT": args.serial_port,
                }
            )
            command = [
                str(
                    project_root
                    / "scripts/experiment/run_transport_ingress_gact.sh"
                ),
                "reliable",
                str(TARGET_LOSS_PERCENT),
                "1",
            ]
            with run_log.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    command,
                    cwd=project_root,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            after_rows = read_rows(csv_path)
            new_rows = after_rows[len(before_rows) :]
            if len(new_rows) > 1:
                raise SystemExit(
                    f"row-count mismatch for {visit_id}: "
                    f"expected at most 1, observed {len(new_rows)}"
                )
            pcap = None
            capture_error = ""
            after_ledger_count = len(
                ledger_path.read_text(encoding="utf-8").splitlines()
            ) if ledger_path.is_file() else 0
            if after_ledger_count == before_ledger_count + 1:
                try:
                    pcap = latest_pcap_from_ledger(
                        ledger_path,
                        args.board_ip,
                    )
                except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
                    capture_error = str(exc)
            else:
                capture_error = (
                    "ingress ledger line-count mismatch: "
                    f"before={before_ledger_count} after={after_ledger_count}"
                )
            condition_manifest_path = (
                results_root / f"mros2qos_{condition}_manifest.json"
            )
            condition_manifest = None
            condition_manifest_sha = ""
            if condition_manifest_path.is_file():
                condition_manifest_sha = sha256_file(condition_manifest_path)
                condition_manifest = json.loads(
                    condition_manifest_path.read_text(encoding="utf-8")
                )
            attempt_records = []
            for row in new_rows:
                run_id = int(row["run_id"])
                serial_path = (
                    results_root
                    / f"mros2qos_{condition}_run{run_id}_serial.log"
                )
                serial_text = serial_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                reasons = evaluate_row(
                    row,
                    serial_text,
                    parameters,
                    variant.get("app_version"),
                    pcap,
                    {
                        "condition": condition,
                        "qos_mode": "reliable",
                        "firmware_mode": "reliable",
                        "host_mode": "cpp",
                        "injection_layer": expected_injection,
                        "commit_hash": harness_commit,
                        "manifest_sha256": condition_manifest_sha,
                    },
                )
                if not condition_manifest:
                    reasons.append("condition_manifest_missing")
                elif (
                    condition_manifest["firmware_binary"]["sha256"]
                    != flash["firmware_sha256"]
                ):
                    reasons.append("condition_manifest_firmware_mismatch")
                if completed.returncode != 0:
                    reasons.append(f"runner_exit:{completed.returncode}")
                accepted_ordinal = (
                    int(schedule_row["run_start"]) + len(accepted)
                    if not reasons
                    else ""
                )
                record = {
                    "block": block,
                    "visit": visit,
                    "cell": cell_id,
                    "condition": condition,
                    "run_id": run_id,
                    "accepted_ordinal": accepted_ordinal,
                    "accepted": int(not reasons),
                    "rejection_reason": ";".join(reasons),
                    "firmware_sha256": flash["firmware_sha256"],
                    "serial_sha256": sha256_file(serial_path),
                    "manifest_sha256": condition_manifest_sha,
                    "pcap_sha256": pcap["sha256"] if pcap else "",
                    "pcap_board_to_host_udp_packets": (
                        pcap["board_to_host_udp_packets"] if pcap else ""
                    ),
                    "tc_state_sha256": (
                        pcap["tc_state_sha256"] if pcap else ""
                    ),
                    "harness_commit": harness_commit,
                }
                append_acceptance_rows(acceptance_path, [record])
                evidence = {
                    "run_id": run_id,
                    "accepted": not reasons,
                    "rejection_reasons": reasons,
                    "serial_path": str(serial_path),
                    "serial_sha256": record["serial_sha256"],
                    "condition_manifest_path": str(condition_manifest_path),
                    "condition_manifest_sha256": condition_manifest_sha,
                    "accepted_ordinal": accepted_ordinal,
                    "capture": pcap,
                }
                (accepted if not reasons else rejected).append(evidence)
                attempt_records.append(evidence)
            attempts.append(
                {
                    "attempt": attempt,
                    "requested_runs": 1,
                    "runner_returncode": completed.returncode,
                    "capture_error": capture_error,
                    "run_log": {
                        "path": str(run_log),
                        "sha256": sha256_file(run_log),
                    },
                    "pcap": pcap,
                    "runs": attempt_records,
                }
            )

        if len(accepted) != ACCEPTED_RUNS_PER_VISIT:
            status = "FAIL"
        else:
            status = "PASS"
        visit_manifest = {
            "schema_version": 1,
            "classification": "round6_formal_schedule_visit",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "schedule": {
                "block": block,
                "visit": visit,
                "cell": cell_id,
                "run_start": int(schedule_row["run_start"]),
                "run_end": int(schedule_row["run_end"]),
            },
            "condition": condition,
            "parameters": parameters,
            "firmware_sha256": flash["firmware_sha256"],
            "firmware_source_commit": variant["source_commit"],
            "harness_commit": harness_commit,
            "flash": flash,
            "accepted_runs": accepted,
            "rejected_runs": rejected,
            "attempts": attempts,
        }
        visit_manifest_path.write_text(
            json.dumps(visit_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if status != "PASS":
            raise SystemExit(
                f"{visit_id} failed to obtain "
                f"{ACCEPTED_RUNS_PER_VISIT} accepted runs; "
                f"review {visit_manifest_path}"
            )
        completed_visits += 1
        print(
            f"[pass] {visit_id}: accepted={len(accepted)} "
            f"rejected={len(rejected)}"
        )

    if args.max_visits is None and completed_visits == len(schedule):
        design["status"] = "COMPLETE"
        design["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        design_path.write_text(
            json.dumps(design, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"[checkpoint] completed_visits={completed_visits}/"
        f"{len(schedule)} design={design_path}"
    )


if __name__ == "__main__":
    main()
