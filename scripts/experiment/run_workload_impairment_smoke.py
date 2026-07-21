#!/usr/bin/env python3
"""Run one excluded workload smoke under a bounded host-egress netem profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts/experiment/run_telemetry_control_probe_smoke.py"
ACK_TEXT = "I_ACKNOWLEDGE_DEDICATED_ETH1"
PROFILES = {
    "clean": (),
    "loss5_independent_h2b": ("loss", "random", "5%"),
    "loss15_independent_h2b": ("loss", "random", "15%"),
    "burst_ge_p1_r25_h95_k999_h2b": (
        "loss",
        "gemodel",
        "1%",
        "25%",
        "95%",
        "0.1%",
    ),
    "delay20ms_h2b": ("delay", "20ms"),
    "delay50ms_h2b": ("delay", "50ms"),
    "delay20ms_jitter10ms_normal_h2b": (
        "delay",
        "20ms",
        "10ms",
        "distribution",
        "normal",
    ),
    "delay20ms_reorder25_corr50_gap5_h2b": (
        "delay",
        "20ms",
        "reorder",
        "25%",
        "50%",
        "gap",
        "5",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qdisc_state(interface: str) -> str:
    return subprocess.run(
        ["tc", "-s", "-d", "qdisc", "show", "dev", interface],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    for sig, timeout in ((signal.SIGINT, 3.0), (signal.SIGTERM, 2.0)):
        try:
            os.killpg(process.pid, sig)
            process.wait(timeout=timeout)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2.0)


def write_text(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def chown_tree(root: Path, user_name: str) -> None:
    account = pwd.getpwnam(user_name)
    for path in [root, *root.rglob("*")]:
        os.chown(path, account.pw_uid, account.pw_gid)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=("mros2qos", "upstream", "microros"), required=True)
    parser.add_argument("--qos", choices=("BEST_EFFORT", "RELIABLE"), required=True)
    parser.add_argument("--payload-bytes", type=int, required=True)
    parser.add_argument("--rate-hz", type=int, required=True)
    parser.add_argument("--target-tx", type=int, required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--run-user", default="wsde-47")
    parser.add_argument("--network-change-ack", required=True)
    parser.add_argument("--micro-dds-mtu-profile", action="store_true")
    args = parser.parse_args()

    if os.geteuid() != 0:
        parser.error("this wrapper must run as root so qdisc cleanup is unconditional")
    if args.network_change_ack != ACK_TEXT:
        parser.error(f"--network-change-ack must be {ACK_TEXT}")
    if args.payload_bytes <= 0 or args.target_tx <= 0:
        parser.error("payload bytes and target TX must be positive")
    if args.rate_hz <= 0 or 1000 % args.rate_hz:
        parser.error("rate must be a positive divisor of 1000 Hz")
    if args.system != "microros" and args.micro_dds_mtu_profile:
        parser.error("--micro-dds-mtu-profile only applies to micro-ROS")
    for command in ("tc", "tshark", "runuser"):
        if shutil.which(command) is None:
            parser.error(f"required command is unavailable: {command}")

    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    diagnostics_root = (REPO / "results/diagnostics").resolve()
    if diagnostics_root not in output.parents:
        parser.error(f"output must be below {diagnostics_root}")
    if output.exists():
        parser.error(f"output already exists: {output}")

    before = qdisc_state(args.interface)
    root_lines = [line for line in before.splitlines() if " root " in line]
    if not root_lines or any("netem" in line for line in root_lines):
        parser.error(f"unexpected pre-existing root qdisc on {args.interface}")

    netem_args = list(PROFILES[args.profile])
    tc_command = (
        [
            "tc",
            "qdisc",
            "replace",
            "dev",
            args.interface,
            "root",
            "netem",
            *netem_args,
        ]
        if netem_args
        else []
    )
    direction = "host_to_board_egress_only" if netem_args else "none_clean"
    runner_command = [
        "/usr/sbin/runuser",
        "-u",
        args.run_user,
        "--",
        "/usr/bin/python3",
        str(RUNNER),
        "--system",
        args.system,
        "--mode",
        "on",
        "--build-dir",
        str(args.build_dir.resolve()),
        "--app-name",
        args.app_name,
        "--expected-qos",
        args.qos,
        "--expected-payload-bytes",
        str(args.payload_bytes),
        "--expected-rate-hz",
        str(args.rate_hz),
        "--expected-target-tx",
        str(args.target_tx),
        "--expected-impairment",
        args.profile,
        "--allow-delivery-loss",
        "--output",
        str(output),
    ]
    if args.micro_dds_mtu_profile:
        runner_command.append("--micro-dds-mtu-profile")

    capture_process: subprocess.Popen[bytes] | None = None
    runner_result: subprocess.CompletedProcess[str] | None = None
    configured = ""
    final = ""
    after = ""
    wrapper_error = ""
    netem_active = False
    started_at = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="workload-netem-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        pcap_temp = temp_dir / "traffic.pcapng"
        capture_log_temp = temp_dir / "tshark.log"
        capture_log = capture_log_temp.open("wb")
        try:
            if tc_command:
                subprocess.run(tc_command, check=True, capture_output=True, text=True)
                netem_active = True
            configured = qdisc_state(args.interface)
            capture_process = subprocess.Popen(
                [
                    "tshark",
                    "-i",
                    args.interface,
                    "-f",
                    f"host {args.board_ip} and udp",
                    "-w",
                    str(pcap_temp),
                ],
                stdout=capture_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            runner_result = subprocess.run(
                runner_command,
                cwd=REPO,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            wrapper_error = str(exc)
        finally:
            stop_process(capture_process)
            capture_log.close()
            try:
                final = qdisc_state(args.interface)
            except subprocess.CalledProcessError as exc:
                wrapper_error += f"; final qdisc state failed: {exc}"
            if netem_active:
                subprocess.run(
                    ["tc", "qdisc", "del", "dev", args.interface, "root"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            try:
                after = qdisc_state(args.interface)
            except subprocess.CalledProcessError as exc:
                wrapper_error += f"; cleanup qdisc state failed: {exc}"

        output.mkdir(parents=True, exist_ok=True)
        if pcap_temp.exists():
            shutil.copy2(pcap_temp, output / "traffic.pcapng")
        if capture_log_temp.exists():
            shutil.copy2(capture_log_temp, output / "tshark.log")

    write_text(output / "tc_before.txt", before)
    write_text(output / "tc_configured.txt", configured)
    write_text(output / "tc_final.txt", final)
    write_text(output / "tc_after_cleanup.txt", after)

    pcap = output / "traffic.pcapng"
    runner_status = "NOT_RUN"
    if runner_result is not None:
        runner_status = "PASS" if runner_result.returncode == 0 else "FAIL"
        write_text(output / "wrapper_runner_stdout.txt", runner_result.stdout)
        write_text(output / "wrapper_runner_stderr.txt", runner_result.stderr)
    cleanup_ok = "netem" not in after and bool(after.strip())
    manifest = {
        "schema_version": 1,
        "classification": "workload_impairment_engineering_smoke",
        "evidence_boundary": "excluded N=1 efficacy pilot; never formal comparison data",
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "interface": args.interface,
        "board_ip": args.board_ip,
        "profile": args.profile,
        "netem_arguments": netem_args,
        "tc_command": tc_command,
        "runner_command": runner_command,
        "runner_status": runner_status,
        "runner_returncode": runner_result.returncode if runner_result else None,
        "pcap_sha256": sha256(pcap) if pcap.is_file() else None,
        "pcap_bytes": pcap.stat().st_size if pcap.is_file() else None,
        "tc_state_sha256": {
            name: sha256(output / name)
            for name in (
                "tc_before.txt",
                "tc_configured.txt",
                "tc_final.txt",
                "tc_after_cleanup.txt",
            )
        },
        "cleanup_ok": cleanup_ok,
        "wrapper_error": wrapper_error or None,
        "status": (
            "PASS"
            if runner_status == "PASS" and cleanup_ok and not wrapper_error
            else "FAIL"
        ),
    }
    (output / "impairment_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    chown_tree(output, args.run_user)

    if manifest["status"] != "PASS":
        print(
            f"FAIL: runner={runner_status} cleanup_ok={cleanup_ok} "
            f"error={wrapper_error or 'none'}",
            file=sys.stderr,
        )
        return 1
    print(f"PASS: profile={args.profile} direction={direction}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
