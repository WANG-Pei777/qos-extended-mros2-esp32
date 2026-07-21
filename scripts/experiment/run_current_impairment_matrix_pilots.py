#!/usr/bin/env python3
"""Collect the resumable current-implementation N=1 impairment pilot matrix."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "workspace/telemetry_compare"
WRAPPER = REPO / "scripts/experiment/run_workload_impairment_smoke.py"
ACK_TEXT = "I_ACKNOWLEDGE_DEDICATED_ETH1"
PROFILES = (
    "clean",
    "delay20ms_h2b",
    "delay50ms_h2b",
    "delay20ms_jitter10ms_normal_h2b",
    "delay20ms_reorder25_corr50_gap5_h2b",
    "loss5_independent_h2b",
    "loss15_independent_h2b",
    "burst_ge_p1_r25_h95_k999_h2b",
)
EXISTING_OUTPUTS = {
    ("BEST_EFFORT", "clean"): "20260720_impair_be_p512_r50_clean_smoke",
    ("BEST_EFFORT", "delay20ms_h2b"): (
        "20260720_impair_be_p512_r50_delay20ms_h2b_smoke"
    ),
}


def chown_tree(root: Path, user_name: str) -> None:
    account = pwd.getpwnam(user_name)
    for path in [root, *root.rglob("*")]:
        os.chown(path, account.pw_uid, account.pw_gid)


def output_name(qos: str, profile: str) -> str:
    existing = EXISTING_OUTPUTS.get((qos, profile))
    if existing:
        return existing
    qos_label = "be" if qos == "BEST_EFFORT" else "rel"
    return f"20260720_impair_{qos_label}_p512_r50_{profile}_smoke"


def write_ledger(path: Path, entries: list[dict[str, object]]) -> None:
    complete = sum(entry["collection_status"] == "COLLECTED" for entry in entries)
    retained_failures = sum(entry.get("smoke_status") == "FAIL" for entry in entries)
    report = {
        "schema_version": 1,
        "classification": "current_impairment_matrix_engineering_pilot",
        "evidence_boundary": "excluded N=1 efficacy pilots; never formal comparison data",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_cells": len(PROFILES) * 2,
        "collected_cells": complete,
        "retained_failures": retained_failures,
        "energy_gate": "BLOCKED_EXTERNAL_CALIBRATED_MONITOR_AND_GPIO_ALIGNMENT",
        "entries": entries,
    }
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def existing_result(output: Path) -> tuple[str, bool]:
    manifest_path = output / "impairment_manifest.json"
    if not manifest_path.is_file():
        return "INCOMPLETE", False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collected = bool(manifest.get("cleanup_ok")) and (output / "traffic.pcapng").is_file()
    return str(manifest.get("status", "UNKNOWN")), collected


def build_firmware(
    user_name: str,
    qos: str,
    profile: str,
    build_dir: Path,
    build_log: Path,
) -> subprocess.CompletedProcess[str]:
    reliable = "ON" if qos == "RELIABLE" else "OFF"
    command = [
        "idf.py",
        "-B",
        str(build_dir),
        "-DMATCHED_BENCH_TELEMETRY_ENABLED=ON",
        f"-DMATCHED_BENCH_RELIABLE={reliable}",
        "-DMATCHED_BENCH_PAYLOAD_BYTES=512",
        "-DMATCHED_BENCH_PUBLISH_RATE_HZ=50",
        "-DMATCHED_BENCH_WINDOW_MS=20000",
        f"-DMATCHED_BENCH_IMPAIRMENT={profile}",
        "build",
    ]
    shell_command = (
        "source ${IDF_PATH:?Set_IDF_PATH}/export.sh >/dev/null 2>&1 && "
        f"cd {shlex.quote(str(PROJECT))} && {shlex.join(command)}"
    )
    result = subprocess.run(
        ["/usr/sbin/runuser", "-u", user_name, "--", "bash", "-lc", shell_command],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    build_log.write_text(
        result.stdout + "\n--- STDERR ---\n" + result.stderr,
        encoding="utf-8",
    )
    return result


def verify_build(build_dir: Path, qos: str, profile: str) -> None:
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    expected_reliable = "ON" if qos == "RELIABLE" else "OFF"
    expected_lines = (
        f"MATCHED_BENCH_IMPAIRMENT:STRING={profile}",
        "MATCHED_BENCH_PAYLOAD_BYTES:STRING=512",
        "MATCHED_BENCH_PUBLISH_RATE_HZ:STRING=50",
        f"MATCHED_BENCH_RELIABLE:BOOL={expected_reliable}",
    )
    missing = [line for line in expected_lines if line not in cache]
    if missing:
        raise RuntimeError(f"build cache mismatch: {missing}")
    elf = build_dir / "mros2qos_telemetry_compare.elf"
    if profile.encode("ascii") not in elf.read_bytes():
        raise RuntimeError(f"ELF does not contain impairment profile {profile}")


def run_smoke(
    args: argparse.Namespace,
    qos: str,
    profile: str,
    build_dir: Path,
    output: Path,
    run_log: Path,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(WRAPPER),
        "--system",
        "mros2qos",
        "--qos",
        qos,
        "--payload-bytes",
        "512",
        "--rate-hz",
        "50",
        "--target-tx",
        "1000",
        "--profile",
        profile,
        "--build-dir",
        str(build_dir),
        "--app-name",
        "mros2qos_telemetry_compare",
        "--output",
        str(output),
        "--interface",
        args.interface,
        "--board-ip",
        args.board_ip,
        "--run-user",
        args.run_user,
        "--network-change-ack",
        ACK_TEXT,
    ]
    result = subprocess.run(
        command,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    run_log.write_text(
        result.stdout + "\n--- STDERR ---\n" + result.stderr,
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-user", default="wsde-47")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--network-change-ack", required=True)
    parser.add_argument(
        "--qos",
        choices=("BEST_EFFORT", "RELIABLE", "both"),
        default="both",
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("this matrix runner must run as root")
    if args.network_change_ack != ACK_TEXT:
        parser.error(f"--network-change-ack must be {ACK_TEXT}")
    if shutil.disk_usage("/mnt/c").free < 5 * 1024**3:
        parser.error("host storage gate failed: less than 5 GiB free on /mnt/c")

    audit_root = REPO / "results/audits/20260720_current_impairment_matrix_pilots"
    audit_root.mkdir(parents=True, exist_ok=True)
    ledger_path = audit_root / "collection_ledger.json"
    entries: list[dict[str, object]] = []
    if ledger_path.is_file():
        entries = json.loads(ledger_path.read_text(encoding="utf-8")).get(
            "entries", []
        )
    by_key = {(entry["qos"], entry["profile"]): entry for entry in entries}

    qoses = (
        ("BEST_EFFORT", "RELIABLE") if args.qos == "both" else (args.qos,)
    )
    fatal_error = False
    for qos in qoses:
        qos_label = "be" if qos == "BEST_EFFORT" else "rel"
        build_dir = PROJECT / f"build_impair_{qos_label}_p512_r50_matrix"
        for profile in PROFILES:
            key = (qos, profile)
            output = REPO / "results/diagnostics" / output_name(qos, profile)
            smoke_status, collected = existing_result(output)
            entry = by_key.get(
                key,
                {
                    "qos": qos,
                    "profile": profile,
                    "relative_path": output.relative_to(REPO).as_posix(),
                },
            )
            by_key[key] = entry
            if collected:
                entry.update(
                    {
                        "collection_status": "COLLECTED",
                        "smoke_status": smoke_status,
                        "disposition": "existing evidence retained",
                    }
                )
                entries = list(by_key.values())
                write_ledger(ledger_path, entries)
                print(f"SKIP: {qos}/{profile} already collected", flush=True)
                continue

            build_log = audit_root / f"build_{qos_label}_{profile}.log"
            run_log = audit_root / f"run_{qos_label}_{profile}.log"
            print(f"BUILD: {qos}/{profile}", flush=True)
            try:
                build = build_firmware(
                    args.run_user, qos, profile, build_dir, build_log
                )
                if build.returncode != 0:
                    raise RuntimeError(f"build returned {build.returncode}")
                verify_build(build_dir, qos, profile)
                print(f"RUN: {qos}/{profile}", flush=True)
                run = run_smoke(
                    args, qos, profile, build_dir, output, run_log
                )
                smoke_status, collected = existing_result(output)
                entry.update(
                    {
                        "build_returncode": build.returncode,
                        "wrapper_returncode": run.returncode,
                        "collection_status": (
                            "COLLECTED" if collected else "INCOMPLETE"
                        ),
                        "smoke_status": smoke_status,
                        "disposition": (
                            "retained performance/capacity outcome"
                            if collected and smoke_status == "FAIL"
                            else "engineering efficacy smoke"
                        ),
                    }
                )
                if not collected:
                    fatal_error = True
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                entry.update(
                    {
                        "collection_status": "INCOMPLETE",
                        "smoke_status": "ERROR",
                        "disposition": str(exc),
                    }
                )
                fatal_error = True
                print(f"ERROR: {qos}/{profile}: {exc}", file=sys.stderr, flush=True)

            entries = list(by_key.values())
            write_ledger(ledger_path, entries)
            chown_tree(audit_root, args.run_user)
            if fatal_error:
                break
        if fatal_error:
            break

    entries = list(by_key.values())
    write_ledger(ledger_path, entries)
    chown_tree(audit_root, args.run_user)
    collected_count = sum(
        entry.get("collection_status") == "COLLECTED" for entry in entries
    )
    print(
        f"DONE: ledger_cells={len(entries)} collected={collected_count} "
        f"fatal_error={fatal_error}",
        flush=True,
    )
    return 1 if fatal_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
