#!/usr/bin/env python3
"""Run one excluded workload smoke under a bounded host-egress netem profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from seven_qos_evidence_identity import (
    EVIDENCE_MODES,
    validate_evidence_identity,
)


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts/experiment/run_telemetry_control_probe_smoke.py"
ACK_TEXT = "I_ACKNOWLEDGE_DEDICATED_ETH1"
RUN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
PROFILES = {
    "clean": (),
    "rdh_s0_h2b": (),
    "rdh_s1_h2b": (
        "loss",
        "gemodel",
        "0.25%",
        "50%",
        "70%",
        "0.01%",
    ),
    "rdh_s2_h2b": (
        "loss",
        "gemodel",
        "0.5%",
        "33.333%",
        "80%",
        "0.05%",
    ),
    "rdh_s3_h2b": (
        "loss",
        "gemodel",
        "1%",
        "25%",
        "95%",
        "0.1%",
    ),
    "rdh_s4_h2b": (
        "loss",
        "gemodel",
        "1.5%",
        "20%",
        "97%",
        "0.2%",
    ),
    "rdh_s5_h2b": (
        "loss",
        "gemodel",
        "2%",
        "16.667%",
        "98%",
        "0.3%",
    ),
    "rdh_s6_h2b": (
        "loss",
        "gemodel",
        "3%",
        "12.5%",
        "99%",
        "0.5%",
    ),
    "tail_outage_h2b": (),
    "liveliness_outage_h2b": (),
    "resource_ack_suppression_h2b": (),
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
DYNAMIC_OUTAGE_PROFILES = {
    "liveliness_outage_h2b",
    "resource_ack_suppression_h2b",
    "tail_outage_h2b",
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


def wait_for_output_marker(
    raw_path: Path,
    marker: bytes,
    process: subprocess.Popen[str],
    timeout_seconds: float = 120.0,
) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        if process.poll() is not None:
            raise RuntimeError("runner exited before dynamic outage marker")
        if raw_path.exists() and marker in raw_path.read_bytes():
            return time.monotonic() - started
        time.sleep(0.05)
    raise RuntimeError(
        f"dynamic outage marker not seen within {timeout_seconds:.1f} seconds"
    )


def write_text(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def chown_tree(root: Path, user_name: str) -> None:
    account = pwd.getpwnam(user_name)
    for path in [root, *root.rglob("*")]:
        os.chown(path, account.pw_uid, account.pw_gid)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=("mros2qos", "upstream", "microros"), required=True)
    parser.add_argument("--telemetry-mode", choices=("on", "off"), default="on")
    parser.add_argument("--qos", choices=("BEST_EFFORT", "RELIABLE"), required=True)
    parser.add_argument("--payload-bytes", type=int, required=True)
    parser.add_argument("--rate-hz", type=int, required=True)
    parser.add_argument("--target-tx", type=int, required=True)
    parser.add_argument("--expected-reply-grace-ms", type=int, default=5000)
    parser.add_argument("--expected-rdh-depth", type=int, default=0)
    parser.add_argument(
        "--expected-firmware-token",
        "--expected-run-token",
        dest="expected_firmware_token",
    )
    parser.add_argument(
        "--evidence-mode", choices=EVIDENCE_MODES, default="engineering_smoke"
    )
    parser.add_argument("--campaign-run-token")
    parser.add_argument("--protocol-schedule-sha256")
    parser.add_argument("--schedule-ordinal", type=int)
    parser.add_argument("--cell-id")
    parser.add_argument("--allow-publish-failures", action="store_true")
    parser.add_argument(
        "--host-durability", choices=("volatile", "transient_local"),
        default="volatile",
    )
    parser.add_argument("--host-history-depth", type=int, default=10)
    parser.add_argument("--host-rdh-only", action="store_true")
    parser.add_argument("--host-start-delay-seconds", type=float, default=0.0)
    parser.add_argument(
        "--micro-host-restart-after-seconds", type=float, default=0.0
    )
    parser.add_argument("--host-start-marker")
    parser.add_argument("--host-reply-liveliness-lease-ms", type=int, default=0)
    parser.add_argument("--dynamic-outage-marker")
    parser.add_argument("--dynamic-outage-delay-seconds", type=float, default=0.0)
    parser.add_argument("--dynamic-outage-seconds", type=float, default=0.0)
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--min-host-free-gib", type=float, default=5.0)
    parser.add_argument("--run-user", default=os.environ.get("SUDO_USER") or os.environ.get("USER", ""))
    parser.add_argument("--network-change-ack", required=True)
    parser.add_argument("--micro-dds-mtu-profile", action="store_true")
    parser.add_argument("--micro-agent-refs", type=Path)
    parser.add_argument(
        "--micro-agent-backend", choices=("local", "snap"), default="local"
    )
    parser.add_argument("--echo-node", type=Path)
    parser.add_argument("--fastdds-profile", type=Path)
    parser.add_argument("--idf-python", type=Path)
    parser.add_argument("--esptool", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if os.geteuid() != 0:
        parser.error("this wrapper must run as root so qdisc cleanup is unconditional")
    if args.network_change_ack != ACK_TEXT:
        parser.error(f"--network-change-ack must be {ACK_TEXT}")
    if args.payload_bytes <= 0 or args.target_tx <= 0:
        parser.error("payload bytes and target TX must be positive")
    if not 1000 <= args.expected_reply_grace_ms <= 30000:
        parser.error("--expected-reply-grace-ms must be in 1000..30000")
    if not 0 <= args.expected_rdh_depth <= 40:
        parser.error("--expected-rdh-depth must be in 0..40")
    if args.expected_firmware_token is not None and not RUN_TOKEN_RE.fullmatch(
        args.expected_firmware_token
    ):
        parser.error("--expected-firmware-token is not machine-safe")
    try:
        evidence_identity = validate_evidence_identity(
            mode=args.evidence_mode,
            campaign_run_token=args.campaign_run_token,
            protocol_schedule_sha256=args.protocol_schedule_sha256,
            schedule_ordinal=args.schedule_ordinal,
            cell_id=args.cell_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.rate_hz <= 0 or 1000 % args.rate_hz:
        parser.error("rate must be a positive divisor of 1000 Hz")
    if args.host_start_delay_seconds < 0:
        parser.error("host start delay must be nonnegative")
    if not 1 <= args.host_history_depth <= 1000:
        parser.error("--host-history-depth must be in 1..1000")
    if args.expected_rdh_depth > 0 and (
        args.system == "upstream"
        or args.qos != "RELIABLE"
        or args.host_durability != "transient_local"
        or args.host_history_depth != args.expected_rdh_depth
    ):
        parser.error(
            "RDH mode requires a non-upstream Reliable system and matching "
            "Transient Local host depth"
        )
    if not 0 <= args.host_reply_liveliness_lease_ms <= 10000:
        parser.error("host reply Liveliness lease must be in 0..10000 ms")
    if (args.dynamic_outage_marker is None) != (
        args.dynamic_outage_seconds == 0.0
    ):
        parser.error("dynamic outage marker and positive duration are required together")
    if args.dynamic_outage_marker is None and args.dynamic_outage_delay_seconds:
        parser.error("dynamic outage delay requires a dynamic outage marker")
    if not 0.0 <= args.dynamic_outage_seconds <= 30.0:
        parser.error("dynamic outage duration must be in 0..30 seconds")
    if not 0.0 <= args.dynamic_outage_delay_seconds <= 30.0:
        parser.error("--dynamic-outage-delay-seconds must be in 0..30 seconds")
    if args.dynamic_outage_marker is not None:
        try:
            dynamic_marker = args.dynamic_outage_marker.encode("ascii")
        except UnicodeEncodeError:
            parser.error("--dynamic-outage-marker must be ASCII")
        if not dynamic_marker or not RUN_TOKEN_RE.fullmatch(
            args.dynamic_outage_marker
        ):
            parser.error("--dynamic-outage-marker must be machine-safe")
    else:
        dynamic_marker = None
    dynamic_outage = dynamic_marker is not None
    if dynamic_outage != (args.profile in DYNAMIC_OUTAGE_PROFILES):
        parser.error(
            "dynamic outage profiles and marker/duration options must be used together"
        )
    if args.system != "microros" and args.micro_dds_mtu_profile:
        parser.error("--micro-dds-mtu-profile only applies to micro-ROS")
    if args.system != "microros" and args.micro_agent_refs is not None:
        parser.error("--micro-agent-refs only applies to micro-ROS")
    if args.system != "microros" and args.micro_host_restart_after_seconds > 0:
        parser.error("--micro-host-restart-after-seconds only applies to micro-ROS")
    if args.system != "microros" and args.micro_agent_backend != "local":
        parser.error("--micro-agent-backend only applies to micro-ROS")
    if args.min_host_free_gib < 0:
        parser.error("--min-host-free-gib must be nonnegative")
    for command in ("tc", "tshark", "runuser"):
        if shutil.which(command) is None:
            parser.error(f"required command is unavailable: {command}")

    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    allowed_root = (
        REPO / "results/experiments"
        if args.evidence_mode == "formal_candidate"
        else REPO / "results/diagnostics"
    ).resolve()
    if allowed_root not in output.parents:
        parser.error(f"output must be below {allowed_root}")
    if output.exists():
        parser.error(f"output already exists: {output}")

    # The outer impairment wrapper runs as root, while the telemetry runner is
    # deliberately demoted to --run-user. Ensure a newly-created profile
    # directory is writable before the runner creates its rN output directory.
    output.parent.mkdir(parents=True, exist_ok=True)
    run_account = pwd.getpwnam(args.run_user)
    os.chown(output.parent, run_account.pw_uid, run_account.pw_gid)

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
    direction = (
        "host_to_board_dynamic_egress_only"
        if dynamic_outage
        else "host_to_board_egress_only"
        if netem_args
        else "none_clean"
    )
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
        args.telemetry_mode,
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
        "--expected-reply-grace-ms",
        str(args.expected_reply_grace_ms),
        "--expected-rdh-depth",
        str(args.expected_rdh_depth),
        "--expected-impairment",
        args.profile,
        "--port",
        args.port,
        "--min-host-free-gib",
        str(args.min_host_free_gib),
        "--output",
        str(output),
    ]
    if netem_args or dynamic_outage:
        runner_command.append("--allow-delivery-loss")
    runner_command.extend(("--evidence-mode", args.evidence_mode))
    for option, value in (
        ("--campaign-run-token", args.campaign_run_token),
        ("--protocol-schedule-sha256", args.protocol_schedule_sha256),
        ("--schedule-ordinal", args.schedule_ordinal),
        ("--cell-id", args.cell_id),
    ):
        if value is not None:
            runner_command.extend((option, str(value)))
    if args.expected_firmware_token is not None:
        runner_command.extend(
            ("--expected-firmware-token", args.expected_firmware_token)
        )
    if args.allow_publish_failures:
        runner_command.append("--allow-publish-failures")
    runner_command.extend(("--host-durability", args.host_durability))
    runner_command.extend(("--host-history-depth", str(args.host_history_depth)))
    if args.host_rdh_only:
        runner_command.append("--host-rdh-only")
    if args.host_start_delay_seconds > 0:
        runner_command.extend(
            ("--host-start-delay-seconds", str(args.host_start_delay_seconds))
        )
    if args.micro_host_restart_after_seconds > 0:
        runner_command.extend(
            (
                "--micro-host-restart-after-seconds",
                str(args.micro_host_restart_after_seconds),
            )
        )
    if args.host_start_marker is not None:
        runner_command.extend(("--host-start-marker", args.host_start_marker))
    if args.host_reply_liveliness_lease_ms > 0:
        runner_command.extend(
            (
                "--host-reply-liveliness-lease-ms",
                str(args.host_reply_liveliness_lease_ms),
            )
        )
    if args.micro_dds_mtu_profile:
        runner_command.append("--micro-dds-mtu-profile")
    if args.micro_agent_refs is not None:
        runner_command.extend(("--micro-agent-refs", str(args.micro_agent_refs.resolve())))
    if args.system == "microros":
        runner_command.extend((
            "--micro-agent-backend", args.micro_agent_backend,
        ))
    for option, value in (
        ("--echo-node", args.echo_node),
        ("--fastdds-profile", args.fastdds_profile),
        ("--idf-python", args.idf_python),
        ("--esptool", args.esptool),
    ):
        if value is not None:
            runner_command.extend((option, str(value.expanduser().absolute())))

    if args.dry_run:
        print(json.dumps({
            "profile": args.profile,
            "direction": direction,
            "evidence_identity": evidence_identity.as_dict(),
            "tc_command": tc_command,
            "runner_command": runner_command,
        }, indent=2))
        return 0

    capture_process: subprocess.Popen[bytes] | None = None
    runner_process: subprocess.Popen[str] | None = None
    runner_result: subprocess.CompletedProcess[str] | None = None
    configured = ""
    final = ""
    after = ""
    wrapper_error = ""
    netem_active = False
    dynamic_marker_wait_seconds: float | None = None
    dynamic_outage_started_at = None
    dynamic_outage_completed_at = None
    outage_state = ""
    outage_final_state = ""
    post_outage_state = ""
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
            if dynamic_outage:
                runner_process = subprocess.Popen(
                    runner_command,
                    cwd=REPO,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                dynamic_marker_wait_seconds = wait_for_output_marker(
                    output / "serial.raw", dynamic_marker, runner_process
                )
                if args.dynamic_outage_delay_seconds:
                    time.sleep(args.dynamic_outage_delay_seconds)
                dynamic_outage_started_at = datetime.now(timezone.utc).isoformat()
                subprocess.run(
                    [
                        "tc", "qdisc", "replace", "dev", args.interface,
                        "root", "netem", "loss", "100%",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                netem_active = True
                outage_state = qdisc_state(args.interface)
                time.sleep(args.dynamic_outage_seconds)
                outage_final_state = qdisc_state(args.interface)
                subprocess.run(
                    ["tc", "qdisc", "del", "dev", args.interface, "root"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                netem_active = False
                dynamic_outage_completed_at = datetime.now(timezone.utc).isoformat()
                post_outage_state = qdisc_state(args.interface)
                stdout, stderr = runner_process.communicate()
                runner_result = subprocess.CompletedProcess(
                    runner_command, runner_process.returncode, stdout, stderr
                )
            else:
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
            stop_process(runner_process)
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
    if dynamic_outage:
        write_text(output / "tc_outage.txt", outage_state)
        write_text(output / "tc_outage_final.txt", outage_final_state)
        write_text(output / "tc_post_outage.txt", post_outage_state)

    pcap = output / "traffic.pcapng"
    runner_status = "NOT_RUN"
    if runner_result is not None:
        runner_status = "PASS" if runner_result.returncode == 0 else "FAIL"
        write_text(output / "wrapper_runner_stdout.txt", runner_result.stdout)
        write_text(output / "wrapper_runner_stderr.txt", runner_result.stderr)
    cleanup_ok = "netem" not in after and bool(after.strip())
    manifest = {
        "schema_version": 1,
        "classification": (
            "seven_qos_performance_formal_network_attempt"
            if args.evidence_mode == "formal_candidate"
            else "workload_impairment_engineering_smoke"
        ),
        "evidence_boundary": (
            "formal candidate only; acceptance ledger determines inclusion"
            if args.evidence_mode == "formal_candidate"
            else "excluded N=1 efficacy pilot; never formal comparison data"
        ),
        "evidence_identity": evidence_identity.as_dict(),
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "interface": args.interface,
        "board_ip": args.board_ip,
        "profile": args.profile,
        "firmware_run_token": args.expected_firmware_token,
        "publish_failure_policy": (
            "outcome" if args.allow_publish_failures else "zero"
        ),
        "host_durability": args.host_durability,
        "host_history_depth": args.host_history_depth,
        "host_rdh_only": args.host_rdh_only,
        "rdh_depth": args.expected_rdh_depth,
        "telemetry_mode": args.telemetry_mode,
        "host_start_delay_seconds": args.host_start_delay_seconds,
        "host_start_marker": args.host_start_marker,
        "host_reply_liveliness_lease_ms": (
            args.host_reply_liveliness_lease_ms
        ),
        "dynamic_outage_marker": args.dynamic_outage_marker,
        "dynamic_outage_kind": args.profile if dynamic_outage else None,
        "dynamic_outage_seconds": args.dynamic_outage_seconds,
        "dynamic_outage_delay_seconds": args.dynamic_outage_delay_seconds,
        "dynamic_outage_marker_wait_seconds": dynamic_marker_wait_seconds,
        "dynamic_outage_started_at_utc": dynamic_outage_started_at,
        "dynamic_outage_completed_at_utc": dynamic_outage_completed_at,
        "netem_arguments": netem_args,
        "tc_command": tc_command,
        "dynamic_tc_command": (
            [
                "tc", "qdisc", "replace", "dev", args.interface,
                "root", "netem", "loss", "100%",
            ]
            if dynamic_outage
            else None
        ),
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
                *(("tc_outage.txt", "tc_outage_final.txt", "tc_post_outage.txt")
                  if dynamic_outage else ()),
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
