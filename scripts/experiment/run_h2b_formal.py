#!/usr/bin/env python3
"""Execute the frozen 300-run H2B per-message RTT schedule."""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from h2b_formal_common import (
    ACCEPTED_RUNS_PER_VISIT,
    EXPECTED_VISITS,
    LOSS_SPECS,
    condition_for,
    expected_injection,
    parse_latest_capture,
    read_rows,
    sha256_file,
    validate_schedule,
)
from run_p4_smoke_gates import load_variants
from run_round6_smoke_gates import (
    flash_variant,
    git_output,
    require_network,
    resolve_artifact,
    validate_serial,
)
from verify_result_tree_seal import verify as verify_result_tree


BOARD_NETWORK_TIMEOUT_SECONDS = 210
RTT_FIELDS = [
    "run_id", "timestamp", "system", "condition", "qos_mode",
    "firmware_mode", "injection_layer", "sequence", "rtt_us",
    "manifest_sha256", "commit_hash",
]
LEDGER_FIELDS = [
    "block", "visit", "cell", "qos", "target_loss_percent",
    "gact_denominator", "effective_loss_percent", "condition", "run_id",
    "accepted_ordinal", "accepted", "rejection_reason", "firmware_sha256",
    "serial_path", "serial_sha256", "host_path", "host_sha256",
    "rtt_evidence_path", "rtt_evidence_sha256", "rtt_evidence_rows",
    "manifest_sha256", "pcap_path", "pcap_sha256",
    "pcap_host_to_board_udp_packets", "tc_state_path", "tc_state_sha256",
    "capture_log_sha256", "harness_commit",
]


def ledger_line_count(path):
    if not Path(path).is_file():
        return 0
    return sum(
        1
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def append_acceptance_row(path, record):
    path = Path(path)
    exists = path.exists()
    if exists:
        with path.open(newline="", encoding="utf-8") as handle:
            if next(csv.reader(handle), []) != LEDGER_FIELDS:
                raise ValueError(f"H2B acceptance ledger schema mismatch: {path}")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(record)


def write_rtt_evidence(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RTT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def validate_smoke(
    smoke_path,
    design_assets,
    firmware_manifest_path,
    host_binary,
    harness_commit,
    args,
):
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    if smoke.get("classification") != "h2b_exact_binary_smoke_gate":
        raise ValueError("invalid H2B smoke classification")
    if smoke.get("status") != "PASS" or smoke.get("runs_pass") != 4:
        raise ValueError("H2B smoke has not passed all four cells")
    if smoke.get("harness_commit") != harness_commit:
        raise ValueError("H2B formal harness differs from smoke")
    if smoke.get("design_assets", {}).get("manifest_sha256") != sha256_file(
        design_assets / "manifest.json"
    ):
        raise ValueError("H2B design assets differ from smoke")
    if smoke.get("firmware_set_manifest_sha256") != sha256_file(
        firmware_manifest_path
    ):
        raise ValueError("H2B firmware set differs from smoke")
    if smoke.get("host_binary_sha256") != sha256_file(host_binary):
        raise ValueError("H2B host binary differs from smoke")
    if smoke.get("wsl_boot_id") != Path(
        "/proc/sys/kernel/random/boot_id"
    ).read_text().strip():
        raise ValueError("WSL session changed after H2B smoke")
    if smoke.get("board_ip") != args.board_ip:
        raise ValueError("H2B board IP differs from smoke")
    if smoke.get("capture_interface") != args.interface:
        raise ValueError("H2B interface differs from smoke")
    return smoke


def evaluate_row(
    row,
    serial_text,
    variant,
    qos,
    condition,
    target_loss,
    harness_commit,
    condition_manifest_sha,
    firmware_sha,
    condition_manifest,
    capture,
    rtt_rows,
):
    reasons = []
    expected = {
        "formal_run": "1",
        "worktree_state": "clean",
        "condition": condition,
        "qos_mode": qos,
        "firmware_mode": qos,
        "host_mode": "cpp",
        "injection_layer": expected_injection(target_loss),
        "commit_hash": harness_commit,
        "manifest_sha256": condition_manifest_sha,
        "matched_pub": "1",
        "matched_sub": "1",
    }
    for field, value in expected.items():
        if row.get(field) != value:
            reasons.append(f"row:{field}")
    if "All phases complete." not in serial_text:
        reasons.append("behavior_incomplete")
    if "VALIDATION NOT READY" in serial_text:
        reasons.append("validation_not_ready")
    reasons.extend(
        f"serial:{item}"
        for item in validate_serial(
            serial_text,
            variant["parameters"],
            variant.get("app_version"),
            qos,
        )
    )
    if len(rtt_rows) != int(row.get("rtt_count") or -1):
        reasons.append("rtt_sidecar_count")
    if not condition_manifest:
        reasons.append("condition_manifest_missing")
    elif condition_manifest.get("firmware_binary", {}).get(
        "sha256"
    ) != firmware_sha:
        reasons.append("condition_manifest_firmware")
    if not capture:
        reasons.append("capture_missing")
    elif capture["host_to_board_udp_packets"] <= 0:
        reasons.append("capture_no_h2b_udp")
    return reasons


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--design-assets", type=Path, required=True)
    parser.add_argument("--smoke-manifest", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
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
        raise SystemExit("max attempts must be at least three")
    project_root = args.project_root.resolve()
    firmware_set = args.firmware_set.resolve()
    design_assets = args.design_assets.resolve()
    smoke_path = args.smoke_manifest.resolve()
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("H2B formal execution requires a clean worktree")
    for root, label in (
        (firmware_set, "firmware set"),
        (design_assets, "design assets"),
    ):
        report = verify_result_tree(root)
        if report.get("status") != "PASS":
            raise SystemExit(f"H2B {label} release seal verification failed")
    wrapper = project_root / "scripts/experiment/run_transport_egress_gact.sh"
    host_binary = project_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
    for executable in (wrapper, host_binary):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise SystemExit(f"H2B executable unavailable: {executable}")
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    design_manifest_path = design_assets / "manifest.json"
    design_assets_manifest = json.loads(
        design_manifest_path.read_text(encoding="utf-8")
    )
    if design_assets_manifest.get("harness_commit") != harness_commit:
        raise SystemExit("H2B formal harness differs from design freeze")
    firmware_manifest_path = firmware_set / "manifest.json"
    firmware_master = json.loads(
        firmware_manifest_path.read_text(encoding="utf-8")
    )
    if design_assets_manifest["firmware_set"]["manifest_sha256"] != sha256_file(
        firmware_manifest_path
    ):
        raise SystemExit("H2B formal firmware set differs from design freeze")
    smoke = validate_smoke(
        smoke_path,
        design_assets,
        firmware_manifest_path,
        host_binary,
        harness_commit,
        args,
    )
    variants = load_variants(firmware_set, firmware_master)
    schedule_path = design_assets / "randomized_schedule.csv"
    schedule = read_rows(schedule_path)
    validate_schedule(schedule)
    require_network(
        args.board_ip,
        args.interface,
        timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
    )

    results_root = project_root / "results/experiments" / args.results_id
    results_root.mkdir(parents=True, exist_ok=True)
    visits_root = results_root / "visits"
    pcaps_root = results_root / "pcaps"
    inputs_root = results_root / "inputs"
    for path in (visits_root, pcaps_root, inputs_root):
        path.mkdir(exist_ok=True)
    inputs = {
        "design_manifest.json": design_manifest_path,
        "design_release_seal.json": design_assets / "release_seal.json",
        "randomized_schedule.csv": schedule_path,
        "smoke_manifest.json": smoke_path,
        "firmware_set_manifest.json": firmware_manifest_path,
        "firmware_set_release_seal.json": firmware_set / "release_seal.json",
    }
    input_records = {}
    for name, source in inputs.items():
        destination = inputs_root / name
        if destination.exists():
            if sha256_file(destination) != sha256_file(source):
                raise SystemExit(f"H2B frozen input copy conflict: {destination}")
        else:
            shutil.copyfile(source, destination)
        input_records[name] = {
            "path": str(destination),
            "sha256": sha256_file(destination),
        }

    design_path = results_root / "design_manifest.json"
    formal_design = {
        "schema_version": 1,
        "classification": "h2b_per_message_formal_campaign",
        "status": "IN_PROGRESS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "harness_commit": harness_commit,
        "host_binary_sha256": sha256_file(host_binary),
        "firmware_set_manifest_sha256": sha256_file(firmware_manifest_path),
        "design_assets_manifest_sha256": sha256_file(design_manifest_path),
        "smoke_manifest_sha256": sha256_file(smoke_path),
        "smoke_wsl_boot_id": smoke["wsl_boot_id"],
        "schedule_sha256": sha256_file(schedule_path),
        "accepted_runs_per_visit": ACCEPTED_RUNS_PER_VISIT,
        "expected_visits": EXPECTED_VISITS,
        "runtime": {
            "board_ip": args.board_ip,
            "capture_interface": args.interface,
            "serial_port": args.serial_port,
            "impairment_direction": "host_to_board_egress_gact",
        },
        "loss_specs": {str(key): value for key, value in LOSS_SPECS.items()},
        "frozen_inputs": input_records,
    }
    if design_path.exists():
        existing = json.loads(design_path.read_text(encoding="utf-8"))
        for key in (
            "harness_commit", "host_binary_sha256",
            "firmware_set_manifest_sha256", "design_assets_manifest_sha256",
            "smoke_manifest_sha256", "smoke_wsl_boot_id", "schedule_sha256",
            "accepted_runs_per_visit", "expected_visits", "runtime",
            "loss_specs", "frozen_inputs",
        ):
            if existing.get(key) != formal_design[key]:
                raise SystemExit(f"H2B formal design conflict at {key}")
        formal_design = existing
    else:
        design_path.write_text(
            json.dumps(formal_design, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    acceptance_path = results_root / "acceptance_ledger.csv"
    transport_ledger = results_root / "TRANSPORT_EGRESS_GACT_LEDGER.md"
    selected = schedule if args.max_visits is None else schedule[: args.max_visits]
    completed_visits = 0
    for schedule_row in selected:
        block = int(schedule_row["block"])
        visit = int(schedule_row["visit"])
        cell_id = schedule_row["id"]
        qos = schedule_row["qos"]
        target_loss = int(schedule_row["target_loss_percent"])
        spec = LOSS_SPECS[target_loss]
        visit_id = f"block_{block:02d}_visit_{visit:02d}_{cell_id}"
        visit_dir = visits_root / visit_id
        visit_manifest_path = visit_dir / "manifest.json"
        if visit_manifest_path.exists():
            existing = json.loads(visit_manifest_path.read_text(encoding="utf-8"))
            if existing.get("status") == "PASS":
                print(f"[resume] {visit_id} PASS", flush=True)
                completed_visits += 1
                continue
            raise SystemExit(f"incomplete H2B visit requires review: {visit_dir}")
        visit_dir.mkdir(parents=True, exist_ok=True)
        prior_accepted = sum(
            row["cell"] == cell_id and row["accepted"] == "1"
            for row in read_rows(acceptance_path)
        )
        expected_prior = int(schedule_row["run_start"]) - 1
        if prior_accepted != expected_prior:
            raise SystemExit(
                f"H2B accepted ordinal mismatch for {visit_id}: "
                f"expected {expected_prior}, observed {prior_accepted}"
            )
        variant = variants[qos]
        flash = flash_variant(
            project_root,
            firmware_set,
            variant,
            args.serial_port,
            args.flash_baud,
            visit_dir,
        )
        firmware = resolve_artifact(
            firmware_set, variant["artifacts"]["firmware"]
        )
        require_network(
            args.board_ip,
            args.interface,
            timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
        )
        condition = condition_for(qos, target_loss)
        csv_path = results_root / f"mros2qos_{condition}.csv"
        sample_path = results_root / f"mros2qos_{condition}_rtt_samples.csv"
        accepted = []
        rejected = []
        attempts = []
        for attempt in range(1, args.max_attempts_per_visit + 1):
            if len(accepted) >= ACCEPTED_RUNS_PER_VISIT:
                break
            before_rows = len(read_rows(csv_path))
            before_samples = len(read_rows(sample_path))
            before_ledger = ledger_line_count(transport_ledger)
            run_log = visit_dir / f"attempt_{attempt:02d}_runner.log"
            environment = os.environ.copy()
            environment.update({
                "FORMAL_RUN_OVERRIDE": "1",
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
                    [str(wrapper), qos, str(target_loss), "1"],
                    cwd=project_root,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            new_rows = read_rows(csv_path)[before_rows:]
            new_samples = read_rows(sample_path)[before_samples:]
            if len(new_rows) > 1:
                raise SystemExit(f"H2B row-count mismatch for {visit_id}")
            capture = None
            capture_error = ""
            if ledger_line_count(transport_ledger) == before_ledger + 1:
                try:
                    capture = parse_latest_capture(
                        transport_ledger, args.board_ip, qos, target_loss
                    )
                except (
                    KeyError, OSError, ValueError, subprocess.SubprocessError
                ) as exc:
                    capture_error = str(exc)
            else:
                capture_error = "transport ledger count mismatch"
            attempt_record = {
                "attempt": attempt,
                "runner_returncode": completed.returncode,
                "runner_log_path": str(run_log),
                "runner_log_sha256": sha256_file(run_log),
                "capture_error": capture_error,
                "capture": capture,
                "runs": [],
            }
            for row in new_rows:
                run_id = int(row["run_id"])
                serial_path = results_root / f"mros2qos_{condition}_run{run_id}_serial.log"
                host_path = results_root / f"mros2qos_{condition}_run{run_id}_host.log"
                serial_text = serial_path.read_text(
                    encoding="utf-8", errors="replace"
                ) if serial_path.is_file() else ""
                matching_samples = [
                    sample for sample in new_samples
                    if sample.get("run_id") == str(run_id)
                ]
                rtt_evidence_path = (
                    visit_dir / f"attempt_{attempt:02d}_run_{run_id}_rtt_samples.csv"
                )
                write_rtt_evidence(rtt_evidence_path, matching_samples)
                condition_manifest_path = (
                    results_root / f"mros2qos_{condition}_manifest.json"
                )
                condition_manifest = (
                    json.loads(condition_manifest_path.read_text(encoding="utf-8"))
                    if condition_manifest_path.is_file()
                    else {}
                )
                condition_manifest_sha = (
                    sha256_file(condition_manifest_path)
                    if condition_manifest_path.is_file()
                    else ""
                )
                reasons = evaluate_row(
                    row,
                    serial_text,
                    variant,
                    qos,
                    condition,
                    target_loss,
                    harness_commit,
                    condition_manifest_sha,
                    flash["firmware_sha256"],
                    condition_manifest,
                    capture,
                    matching_samples,
                )
                if not serial_path.is_file():
                    reasons.append("serial_missing")
                if not host_path.is_file():
                    reasons.append("host_log_missing")
                if completed.returncode != 0:
                    reasons.append(f"runner_exit:{completed.returncode}")
                ordinal = (
                    int(schedule_row["run_start"]) + len(accepted)
                    if not reasons
                    else ""
                )
                record = {
                    "block": block,
                    "visit": visit,
                    "cell": cell_id,
                    "qos": qos,
                    "target_loss_percent": target_loss,
                    "gact_denominator": spec["denominator"],
                    "effective_loss_percent": spec["effective"],
                    "condition": condition,
                    "run_id": run_id,
                    "accepted_ordinal": ordinal,
                    "accepted": int(not reasons),
                    "rejection_reason": ";".join(reasons),
                    "firmware_sha256": flash["firmware_sha256"],
                    "serial_path": str(serial_path),
                    "serial_sha256": (
                        sha256_file(serial_path) if serial_path.is_file() else ""
                    ),
                    "host_path": str(host_path),
                    "host_sha256": (
                        sha256_file(host_path) if host_path.is_file() else ""
                    ),
                    "rtt_evidence_path": str(rtt_evidence_path),
                    "rtt_evidence_sha256": sha256_file(rtt_evidence_path),
                    "rtt_evidence_rows": len(matching_samples),
                    "manifest_sha256": condition_manifest_sha,
                    "pcap_path": capture["path"] if capture else "",
                    "pcap_sha256": capture["sha256"] if capture else "",
                    "pcap_host_to_board_udp_packets": (
                        capture["host_to_board_udp_packets"] if capture else ""
                    ),
                    "tc_state_path": capture["tc_state_path"] if capture else "",
                    "tc_state_sha256": (
                        capture["tc_state_sha256"] if capture else ""
                    ),
                    "capture_log_sha256": (
                        capture["capture_log_sha256"] if capture else ""
                    ),
                    "harness_commit": harness_commit,
                }
                append_acceptance_row(acceptance_path, record)
                evidence = {
                    "run_id": run_id,
                    "accepted": not reasons,
                    "accepted_ordinal": ordinal,
                    "rejection_reasons": reasons,
                    "record": record,
                    "capture": capture,
                }
                (accepted if not reasons else rejected).append(evidence)
                attempt_record["runs"].append(evidence)
            attempts.append(attempt_record)
        status = "PASS" if len(accepted) == ACCEPTED_RUNS_PER_VISIT else "FAIL"
        visit_manifest = {
            "schema_version": 1,
            "classification": "h2b_per_message_formal_visit",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "schedule": schedule_row,
            "condition": condition,
            "qos": qos,
            "target_loss_percent": target_loss,
            "gact_denominator": spec["denominator"],
            "effective_loss_percent": spec["effective"],
            "parameters": variant["parameters"],
            "firmware_source_commit": variant["source_commit"],
            "firmware_sha256": flash["firmware_sha256"],
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
                f"{visit_id} failed to obtain {ACCEPTED_RUNS_PER_VISIT} accepted runs"
            )
        completed_visits += 1
        print(
            f"[pass] {visit_id}: accepted={len(accepted)} "
            f"rejected={len(rejected)}",
            flush=True,
        )
    if args.max_visits is None and completed_visits == len(schedule):
        formal_design["status"] = "COMPLETE"
        formal_design["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        design_path.write_text(
            json.dumps(formal_design, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    require_network(
        args.board_ip,
        args.interface,
        timeout_seconds=BOARD_NETWORK_TIMEOUT_SECONDS,
    )
    print(
        f"[checkpoint] completed_visits={completed_visits}/{len(schedule)} "
        f"design={design_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
