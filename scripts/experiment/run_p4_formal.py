#!/usr/bin/env python3
"""Execute the frozen P4 independent-window replication schedule."""

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

from run_p4_smoke_gates import EARLIEST_DATE, QOS_MODES, load_variants
from run_round6_smoke_gates import (
    count_board_udp_packets,
    flash_variant,
    git_output,
    require_network,
    resolve_artifact,
    sha256_file,
    validate_serial,
)


ACCEPTED_RUNS_PER_VISIT = 3
EXPECTED_VISITS = 60
LOSS_SPECS = {
    0: {"denominator": 0, "effective": 0.0},
    5: {"denominator": 20, "effective": 5.0},
    15: {"denominator": 7, "effective": 100.0 / 7.0},
}


def condition_for(qos, target_loss):
    spec = LOSS_SPECS[target_loss]
    if target_loss == 0:
        suffix = "target00_eff0"
    else:
        effective = f"{spec['effective']:.6f}".replace(".", "p")
        suffix = (
            f"target{target_loss:02d}_gact1of{spec['denominator']}_"
            f"eff{effective}"
        )
    return f"p4_{qos}_{suffix}"


def expected_injection(target_loss):
    spec = LOSS_SPECS[target_loss]
    if target_loss == 0:
        return "transport_ingress_gact_board_to_host_target_0pct_effective_0pct"
    return (
        "transport_ingress_gact_board_to_host_"
        f"target_{target_loss}pct_1of{spec['denominator']}_"
        f"effective_{spec['effective']:.6f}pct"
    )


def read_rows(path):
    if not Path(path).is_file():
        return []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evaluate_row(row, serial_text, parameters, app_version, qos, capture, expected):
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
    for field, value in expected.items():
        if row.get(field) != value:
            reasons.append(f"row_provenance:{field}")
    reasons.extend(
        f"missing_serial:{item}"
        for item in validate_serial(serial_text, parameters, app_version, qos)
    )
    return reasons


def latest_pcap_from_ledger(ledger_path, board_ip, qos, target_loss):
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
    spec = LOSS_SPECS[target_loss]
    if fields.get("qos") != qos or fields.get("firmware") != qos:
        raise ValueError("ingress ledger QoS provenance mismatch")
    if fields.get("target_loss") != f"{target_loss}%":
        raise ValueError("ingress ledger target-loss mismatch")
    expected_denominator = "n/a" if target_loss == 0 else str(spec["denominator"])
    if fields.get("denominator") != expected_denominator:
        raise ValueError("ingress ledger denominator mismatch")
    effective = float(fields.get("effective_loss", "").removesuffix("%"))
    if abs(effective - spec["effective"]) > 0.000001:
        raise ValueError("ingress ledger effective-loss mismatch")
    pcap = Path(fields["pcap"])
    tc_state = Path(fields["tc_state"])
    if not pcap.is_file() or sha256_file(pcap) != fields["sha256"]:
        raise ValueError(f"PCAP ledger hash mismatch: {pcap}")
    if not tc_state.is_file() or sha256_file(tc_state) != fields["tc_state_sha256"]:
        raise ValueError(f"tc state ledger hash mismatch: {tc_state}")
    return {
        "path": str(pcap),
        "sha256": fields["sha256"],
        "bytes": pcap.stat().st_size,
        "board_to_host_udp_packets": count_board_udp_packets(pcap, board_ip),
        "tc_state_path": str(tc_state),
        "tc_state_sha256": fields["tc_state_sha256"],
        "target_loss_percent": target_loss,
        "gact_denominator": spec["denominator"],
        "effective_loss_percent": spec["effective"],
    }


LEDGER_FIELDS = [
    "block", "visit", "cell", "qos", "target_loss_percent",
    "gact_denominator", "effective_loss_percent", "condition", "run_id",
    "accepted_ordinal", "accepted", "rejection_reason", "firmware_sha256",
    "serial_sha256", "manifest_sha256", "pcap_sha256",
    "pcap_board_to_host_udp_packets", "tc_state_sha256", "harness_commit",
]


def append_acceptance_row(path, record):
    path = Path(path)
    exists = path.exists()
    if exists:
        with path.open(newline="", encoding="utf-8") as handle:
            if next(csv.reader(handle), []) != LEDGER_FIELDS:
                raise ValueError(f"acceptance ledger schema mismatch: {path}")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(record)


def validate_schedule(schedule):
    if len(schedule) != EXPECTED_VISITS:
        raise ValueError(f"P4 schedule must contain {EXPECTED_VISITS} visits")
    expected_cells = {
        f"{qos}_target{loss:02d}" for qos in QOS_MODES for loss in LOSS_SPECS
    }
    for block in range(1, 11):
        rows = [row for row in schedule if int(row["block"]) == block]
        if len(rows) != 6 or {row["id"] for row in rows} != expected_cells:
            raise ValueError(f"invalid P4 randomized superblock {block}")
        expected_start = (block - 1) * ACCEPTED_RUNS_PER_VISIT + 1
        if any(
            int(row["run_start"]) != expected_start
            or int(row["run_end"]) != expected_start + 2
            for row in rows
        ):
            raise ValueError(f"invalid accepted-run ordinals in block {block}")


def validate_window(
    window_path,
    results_root,
    firmware_manifest,
    project_root,
    harness_commit,
    args,
):
    window_path = window_path.resolve()
    if window_path.parent != results_root.resolve():
        raise ValueError("window manifest must belong to the P4 results directory")
    window = json.loads(window_path.read_text(encoding="utf-8"))
    if window.get("classification") != "p4_independent_window_gate":
        raise ValueError("invalid P4 window classification")
    if window.get("status") != "PASS" or window.get("smoke", {}).get("runs_pass") != 6:
        raise ValueError("P4 window has not passed all six smoke runs")
    local_date = datetime.fromisoformat(
        window["network"]["window_start_local"]
    ).date()
    if local_date < EARLIEST_DATE:
        raise ValueError("P4 window predates the frozen earliest collection date")
    if datetime.fromisoformat(
        window["network"]["wsl_kernel_boot_local"]
    ).date() < EARLIEST_DATE:
        raise ValueError("P4 WSL session predates the frozen earliest date")
    if window["network"].get("board_network_reassociation", {}).get(
        "method"
    ) != "serial_rts_hardware_reset":
        raise ValueError("P4 window lacks machine-recorded board reassociation")
    if window["network"]["wsl_boot_id"] != Path(
        "/proc/sys/kernel/random/boot_id"
    ).read_text().strip():
        raise ValueError("WSL session changed after the P4 smoke gate")
    if window["network"]["board_ip"] != args.board_ip:
        raise ValueError("board IP differs from the P4 smoke window")
    if window["network"]["capture_interface"] != args.interface:
        raise ValueError("capture interface differs from the P4 smoke window")
    if window["firmware_set_manifest"]["sha256"] != sha256_file(firmware_manifest):
        raise ValueError("firmware set differs from the P4 smoke window")
    if window["harness_commit"] != harness_commit:
        raise ValueError("harness commit differs from the P4 smoke window")
    host_binary = project_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
    if window["host_binary_sha256"] != sha256_file(host_binary):
        raise ValueError("host binary differs from the P4 smoke window")
    return window


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--window-manifest", type=Path, required=True)
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
        raise SystemExit("P4 formal execution requires a clean harness worktree")
    wrapper = project_root / "scripts/experiment/run_transport_ingress_gact.sh"
    host_binary = project_root / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
    for executable in (wrapper, host_binary):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise SystemExit(f"formal executable unavailable: {executable}")
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    set_manifest_path = firmware_set / "manifest.json"
    set_manifest = json.loads(set_manifest_path.read_text(encoding="utf-8"))
    variants = load_variants(firmware_set, set_manifest)
    schedule_path = firmware_set / "randomized_schedule.csv"
    with schedule_path.open(newline="", encoding="utf-8") as handle:
        schedule = list(csv.DictReader(handle))
    validate_schedule(schedule)
    results_root = project_root / "results/experiments" / args.results_id
    results_root.mkdir(parents=True, exist_ok=True)
    window = validate_window(
        args.window_manifest,
        results_root,
        set_manifest_path,
        project_root,
        harness_commit,
        args,
    )
    require_network(args.board_ip, args.interface)
    visits_root = results_root / "visits"
    pcaps_root = results_root / "pcaps"
    visits_root.mkdir(exist_ok=True)
    pcaps_root.mkdir(exist_ok=True)
    design_path = results_root / "design_manifest.json"
    design = {
        "schema_version": 1,
        "classification": "p4_independent_window_formal_replication",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "IN_PROGRESS",
        "firmware_set_manifest": {
            "path": str(set_manifest_path),
            "sha256": sha256_file(set_manifest_path),
            "source_commit": set_manifest["source_commit"],
        },
        "window_manifest": {
            "path": str(args.window_manifest.resolve()),
            "sha256_at_start": sha256_file(args.window_manifest),
            "window_start_local": window["network"]["window_start_local"],
            "wsl_boot_id": window["network"]["wsl_boot_id"],
        },
        "harness_commit": harness_commit,
        "host_binary_sha256": sha256_file(host_binary),
        "schedule_sha256": sha256_file(schedule_path),
        "accepted_runs_per_visit": ACCEPTED_RUNS_PER_VISIT,
        "runtime": {
            "board_ip": args.board_ip,
            "capture_interface": args.interface,
            "serial_port": args.serial_port,
            "impairment_direction": "board_to_host_ingress",
        },
        "loss_specs": {str(key): value for key, value in LOSS_SPECS.items()},
    }
    if design_path.exists():
        existing = json.loads(design_path.read_text(encoding="utf-8"))
        for key in (
            "firmware_set_manifest", "window_manifest", "harness_commit",
            "host_binary_sha256", "schedule_sha256", "accepted_runs_per_visit",
            "runtime", "loss_specs",
        ):
            if existing.get(key) != design[key]:
                raise SystemExit(f"P4 formal design conflict at {key}")
        design = existing
    else:
        design_path.write_text(
            json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    acceptance_path = results_root / "acceptance_ledger.csv"
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
                print(f"[resume] {visit_id} PASS")
                completed_visits += 1
                continue
            raise SystemExit(f"incomplete P4 visit requires review: {visit_dir}")
        visit_dir.mkdir(parents=True, exist_ok=True)
        variant = variants[qos]
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
        firmware = resolve_artifact(firmware_set, variant["artifacts"]["firmware"])
        require_network(args.board_ip, args.interface)
        flash = flash_variant(
            project_root, firmware_set, variant, args.serial_port,
            args.flash_baud, visit_dir,
        )
        require_network(args.board_ip, args.interface)
        condition = condition_for(qos, target_loss)
        csv_path = results_root / f"mros2qos_{condition}.csv"
        transport_ledger = results_root / "TRANSPORT_INGRESS_GACT_LEDGER.md"
        accepted = []
        rejected = []
        attempts = []
        for attempt in range(1, args.max_attempts_per_visit + 1):
            if len(accepted) >= ACCEPTED_RUNS_PER_VISIT:
                break
            before_rows = read_rows(csv_path)
            before_ledger = len(transport_ledger.read_text().splitlines()) if transport_ledger.is_file() else 0
            run_log = visit_dir / f"attempt_{attempt:02d}.log"
            environment = os.environ.copy()
            environment.update({
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
            command = [str(wrapper), qos, str(target_loss), "1"]
            with run_log.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    command, cwd=project_root, env=environment,
                    stdout=log, stderr=subprocess.STDOUT, text=True,
                )
            new_rows = read_rows(csv_path)[len(before_rows):]
            if len(new_rows) > 1:
                raise SystemExit(f"row-count mismatch for {visit_id}")
            after_ledger = len(transport_ledger.read_text().splitlines()) if transport_ledger.is_file() else 0
            capture = None
            capture_error = ""
            if after_ledger == before_ledger + 1:
                try:
                    capture = latest_pcap_from_ledger(
                        transport_ledger, args.board_ip, qos, target_loss
                    )
                except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
                    capture_error = str(exc)
            else:
                capture_error = f"ingress ledger count {before_ledger}->{after_ledger}"
            condition_manifest_path = results_root / f"mros2qos_{condition}_manifest.json"
            condition_manifest = None
            condition_manifest_sha = ""
            if condition_manifest_path.is_file():
                condition_manifest_sha = sha256_file(condition_manifest_path)
                condition_manifest = json.loads(condition_manifest_path.read_text())
            attempt_runs = []
            for row in new_rows:
                run_id = int(row["run_id"])
                serial_path = results_root / f"mros2qos_{condition}_run{run_id}_serial.log"
                serial_text = serial_path.read_text(encoding="utf-8", errors="replace")
                reasons = evaluate_row(
                    row, serial_text, variant["parameters"],
                    variant.get("app_version"), qos, capture,
                    {
                        "condition": condition,
                        "qos_mode": qos,
                        "firmware_mode": qos,
                        "host_mode": "cpp",
                        "injection_layer": expected_injection(target_loss),
                        "commit_hash": harness_commit,
                        "manifest_sha256": condition_manifest_sha,
                    },
                )
                if not condition_manifest:
                    reasons.append("condition_manifest_missing")
                elif condition_manifest["firmware_binary"]["sha256"] != flash["firmware_sha256"]:
                    reasons.append("condition_manifest_firmware_mismatch")
                if completed.returncode != 0:
                    reasons.append(f"runner_exit:{completed.returncode}")
                ordinal = int(schedule_row["run_start"]) + len(accepted) if not reasons else ""
                record = {
                    "block": block, "visit": visit, "cell": cell_id, "qos": qos,
                    "target_loss_percent": target_loss,
                    "gact_denominator": spec["denominator"],
                    "effective_loss_percent": spec["effective"],
                    "condition": condition, "run_id": run_id,
                    "accepted_ordinal": ordinal, "accepted": int(not reasons),
                    "rejection_reason": ";".join(reasons),
                    "firmware_sha256": flash["firmware_sha256"],
                    "serial_sha256": sha256_file(serial_path),
                    "manifest_sha256": condition_manifest_sha,
                    "pcap_sha256": capture["sha256"] if capture else "",
                    "pcap_board_to_host_udp_packets": capture["board_to_host_udp_packets"] if capture else "",
                    "tc_state_sha256": capture["tc_state_sha256"] if capture else "",
                    "harness_commit": harness_commit,
                }
                append_acceptance_row(acceptance_path, record)
                evidence = {
                    "run_id": run_id, "accepted": not reasons,
                    "rejection_reasons": reasons,
                    "accepted_ordinal": ordinal, "serial_path": str(serial_path),
                    "serial_sha256": record["serial_sha256"], "capture": capture,
                }
                (accepted if not reasons else rejected).append(evidence)
                attempt_runs.append(evidence)
            attempts.append({
                "attempt": attempt, "runner_returncode": completed.returncode,
                "capture_error": capture_error,
                "run_log": {"path": str(run_log), "sha256": sha256_file(run_log)},
                "capture": capture, "runs": attempt_runs,
            })
        status = "PASS" if len(accepted) == ACCEPTED_RUNS_PER_VISIT else "FAIL"
        visit_manifest = {
            "schema_version": 1,
            "classification": "p4_independent_window_formal_visit",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status, "schedule": schedule_row,
            "condition": condition, "parameters": variant["parameters"],
            "qos": qos, "target_loss_percent": target_loss,
            "gact_denominator": spec["denominator"],
            "effective_loss_percent": spec["effective"],
            "firmware_sha256": flash["firmware_sha256"],
            "firmware_source_commit": variant["source_commit"],
            "harness_commit": harness_commit, "flash": flash,
            "accepted_runs": accepted, "rejected_runs": rejected,
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
        print(f"[pass] {visit_id}: accepted={len(accepted)} rejected={len(rejected)}")
    if args.max_visits is None and completed_visits == len(schedule):
        design["status"] = "COMPLETE"
        design["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        design_path.write_text(
            json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"[checkpoint] completed_visits={completed_visits}/{len(schedule)} design={design_path}")


if __name__ == "__main__":
    main()
