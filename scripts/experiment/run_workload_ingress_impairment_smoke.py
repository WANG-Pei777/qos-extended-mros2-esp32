#!/usr/bin/env python3
"""Run one excluded B2H workload smoke through an IFB ingress impairment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile

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
    "loss5_independent_b2h": ("loss", "random", "5%"),
    "loss15_independent_b2h": ("loss", "random", "15%"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str]) -> str:
    return subprocess.run(
        command, check=True, capture_output=True, text=True
    ).stdout


def qdisc_state(device: str) -> str:
    return command_output(["tc", "-s", "-d", "qdisc", "show", "dev", device])


def filter_state(interface: str) -> str:
    return command_output(
        ["tc", "-s", "-d", "filter", "show", "dev", interface, "parent", "ffff:"]
    )


def ingress_commands(
    interface: str, ifb: str, board_ip: str, netem_args: tuple[str, ...]
) -> list[list[str]]:
    return [
        ["modprobe", "ifb", "numifbs=1"],
        ["ip", "link", "set", "dev", ifb, "up"],
        ["tc", "qdisc", "add", "dev", interface, "handle", "ffff:", "ingress"],
        [
            "tc", "filter", "add", "dev", interface, "parent", "ffff:",
            "protocol", "ip", "priority", "10", "u32", "match", "ip", "src",
            f"{board_ip}/32", "action", "mirred", "egress", "redirect", "dev", ifb,
        ],
        ["tc", "qdisc", "replace", "dev", ifb, "root", "netem", *netem_args],
    ]


def cleanup_commands(interface: str, ifb: str) -> list[list[str]]:
    return [
        ["tc", "qdisc", "del", "dev", interface, "ingress"],
        ["tc", "qdisc", "del", "dev", ifb, "root"],
        ["ip", "link", "set", "dev", ifb, "down"],
    ]


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
    parser.add_argument("--telemetry-mode", choices=("on", "off"), default="on")
    parser.add_argument("--qos", choices=("BEST_EFFORT", "RELIABLE"), required=True)
    parser.add_argument("--payload-bytes", type=int, required=True)
    parser.add_argument("--rate-hz", type=int, required=True)
    parser.add_argument("--target-tx", type=int, required=True)
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
    parser.add_argument("--profile", choices=tuple(PROFILES), required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--ifb", default="ifb0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--min-host-free-gib", type=float, default=5.0)
    parser.add_argument("--run-user", default=os.environ.get("SUDO_USER") or os.environ.get("USER", ""))
    parser.add_argument("--network-change-ack", required=True)
    parser.add_argument(
        "--micro-agent-backend", choices=("local", "snap"), default="local"
    )
    parser.add_argument("--micro-agent-refs", type=Path)
    parser.add_argument("--micro-dds-mtu-profile", action="store_true")
    parser.add_argument(
        "--host-durability",
        choices=("volatile", "transient_local"),
        default="volatile",
    )
    parser.add_argument("--host-history-depth", type=int, default=10)
    parser.add_argument("--host-rdh-only", action="store_true")
    parser.add_argument("--host-start-delay-seconds", type=float, default=0.0)
    parser.add_argument(
        "--micro-host-restart-after-seconds", type=float, default=0.0
    )
    parser.add_argument("--echo-node", type=Path)
    parser.add_argument("--fastdds-profile", type=Path)
    parser.add_argument("--idf-python", type=Path)
    parser.add_argument("--esptool", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if os.geteuid() != 0:
        parser.error("this wrapper must run as root so ingress cleanup is unconditional")
    if args.network_change_ack != ACK_TEXT:
        parser.error(f"--network-change-ack must be {ACK_TEXT}")
    if args.payload_bytes <= 0 or args.target_tx <= 0:
        parser.error("payload bytes and target TX must be positive")
    if args.rate_hz <= 0 or 1000 % args.rate_hz:
        parser.error("rate must be a positive divisor of 1000 Hz")
    if args.system != "microros" and args.micro_agent_backend != "local":
        parser.error("--micro-agent-backend only applies to micro-ROS")
    if args.system != "microros" and args.micro_agent_refs is not None:
        parser.error("--micro-agent-refs only applies to micro-ROS")
    if args.system != "microros" and args.micro_dds_mtu_profile:
        parser.error("--micro-dds-mtu-profile only applies to micro-ROS")
    if args.min_host_free_gib < 0:
        parser.error("--min-host-free-gib must be nonnegative")
    if args.system != "microros" and args.micro_host_restart_after_seconds > 0:
        parser.error("--micro-host-restart-after-seconds only applies to micro-ROS")
    if args.host_start_delay_seconds < 0:
        parser.error("--host-start-delay-seconds must be nonnegative")
    if not 1 <= args.host_history_depth <= 1000:
        parser.error("--host-history-depth must be in 1..1000")
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
    for command in ("ip", "modprobe", "runuser", "tc", "tshark"):
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

    netem_args = PROFILES[args.profile]
    use_ifb = bool(netem_args)
    before = qdisc_state(args.interface)
    root_lines = [line for line in before.splitlines() if " root " in line]
    if not root_lines or any("netem" in line for line in root_lines):
        parser.error(f"unexpected pre-existing root qdisc on {args.interface}")
    preexisting_ingress = subprocess.run(
        ["tc", "qdisc", "show", "dev", args.interface],
        check=True, capture_output=True, text=True,
    ).stdout
    if " ingress " in preexisting_ingress or " clsact " in preexisting_ingress:
        parser.error(f"pre-existing ingress/clsact qdisc on {args.interface}")

    runner_command = [
        "/usr/sbin/runuser", "-u", args.run_user, "--", "/usr/bin/python3",
        str(RUNNER), "--system", args.system, "--mode", args.telemetry_mode,
        "--build-dir", str(args.build_dir.resolve()), "--app-name", args.app_name,
        "--expected-qos", args.qos,
        "--expected-payload-bytes", str(args.payload_bytes),
        "--expected-rate-hz", str(args.rate_hz),
        "--expected-target-tx", str(args.target_tx),
        "--expected-impairment", args.profile,
        "--port", args.port,
        "--min-host-free-gib", str(args.min_host_free_gib),
        "--allow-delivery-loss", "--output", str(output),
    ]
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
    runner_command.extend(
        (
            "--host-durability", args.host_durability,
            "--host-history-depth", str(args.host_history_depth),
        )
    )
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
    if args.system == "microros":
        runner_command.extend(("--micro-agent-backend", args.micro_agent_backend))
    if args.micro_agent_refs is not None:
        runner_command.extend(("--micro-agent-refs", str(args.micro_agent_refs.resolve())))
    if args.micro_dds_mtu_profile:
        runner_command.append("--micro-dds-mtu-profile")
    for option, value in (
        ("--echo-node", args.echo_node),
        ("--fastdds-profile", args.fastdds_profile),
        ("--idf-python", args.idf_python),
        ("--esptool", args.esptool),
    ):
        if value is not None:
            runner_command.extend((option, str(value.expanduser().absolute())))

    setup = ingress_commands(args.interface, args.ifb, args.board_ip, netem_args)
    cleanup = cleanup_commands(args.interface, args.ifb)
    if args.dry_run:
        print(json.dumps({
            "profile": args.profile,
            "direction": "board_to_host_ingress_only",
            "evidence_identity": evidence_identity.as_dict(),
            "setup_commands": setup if use_ifb else [],
            "runner_command": runner_command,
            "cleanup_commands": cleanup if use_ifb else [],
        }, indent=2))
        return 0

    capture_process: subprocess.Popen[bytes] | None = None
    runner_result: subprocess.CompletedProcess[str] | None = None
    configured_filter = ""
    configured_ifb = ""
    final_ifb = ""
    after = ""
    wrapper_error = ""
    setup_count = 0
    started_at = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="workload-ingress-") as temp_name:
        temp = Path(temp_name)
        pcap_temp = temp / "traffic.pcapng"
        capture_log_temp = temp / "tshark.log"
        capture_log = capture_log_temp.open("wb")
        try:
            if use_ifb:
                for command in setup:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                    setup_count += 1
                configured_filter = filter_state(args.interface)
                configured_ifb = qdisc_state(args.ifb)
            capture_process = subprocess.Popen(
                ["tshark", "-i", args.interface, "-f", f"host {args.board_ip} and udp",
                 "-w", str(pcap_temp)],
                stdout=capture_log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            runner_result = subprocess.run(
                runner_command, cwd=REPO, capture_output=True, text=True, check=False
            )
            if use_ifb:
                final_ifb = qdisc_state(args.ifb)
        except Exception as exc:
            wrapper_error = str(exc)
        finally:
            stop_process(capture_process)
            capture_log.close()
            if use_ifb and setup_count:
                for command in cleanup:
                    subprocess.run(command, check=False, capture_output=True, text=True)
            try:
                after = qdisc_state(args.interface)
            except subprocess.CalledProcessError as exc:
                wrapper_error += f"; cleanup state failed: {exc}"
        output.mkdir(parents=True, exist_ok=True)
        if pcap_temp.exists():
            shutil.copy2(pcap_temp, output / "traffic.pcapng")
        if capture_log_temp.exists():
            shutil.copy2(capture_log_temp, output / "tshark.log")

    write_text(output / "tc_before.txt", before)
    write_text(output / "tc_ingress_filter.txt", configured_filter)
    write_text(output / "tc_ifb_configured.txt", configured_ifb)
    write_text(output / "tc_ifb_final.txt", final_ifb)
    write_text(output / "tc_after_cleanup.txt", after)
    if runner_result is not None:
        write_text(output / "wrapper_runner_stdout.txt", runner_result.stdout)
        write_text(output / "wrapper_runner_stderr.txt", runner_result.stderr)
    pcap = output / "traffic.pcapng"
    cleanup_qdisc = subprocess.run(
        ["tc", "qdisc", "show", "dev", args.interface],
        check=True, capture_output=True, text=True,
    ).stdout
    cleanup_ok = (
        " ingress " not in cleanup_qdisc
        and " clsact " not in cleanup_qdisc
        and "netem" not in after
        and bool(after.strip())
    )
    runner_status = (
        "NOT_RUN" if runner_result is None
        else "PASS" if runner_result.returncode == 0
        else "FAIL"
    )
    manifest = {
        "schema_version": 1,
        "classification": (
            "seven_qos_performance_formal_ingress_attempt"
            if args.evidence_mode == "formal_candidate"
            else "workload_ingress_impairment_engineering_smoke"
        ),
        "evidence_boundary": (
            "formal candidate only; acceptance ledger determines inclusion"
            if args.evidence_mode == "formal_candidate"
            else "excluded N=1 ingress-efficacy pilot; never formal comparison data"
        ),
        "evidence_identity": evidence_identity.as_dict(),
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "direction": "board_to_host_ingress_only",
        "interface": args.interface,
        "ifb": args.ifb,
        "board_ip": args.board_ip,
        "profile": args.profile,
        "firmware_run_token": args.expected_firmware_token,
        "micro_dds_mtu_profile": (
            args.micro_dds_mtu_profile if args.system == "microros" else None
        ),
        "netem_arguments": list(netem_args),
        "source_filter": f"ip src {args.board_ip}/32",
        "setup_commands": setup if use_ifb else [],
        "runner_command": runner_command,
        "cleanup_commands": cleanup if use_ifb else [],
        "runner_status": runner_status,
        "runner_returncode": runner_result.returncode if runner_result else None,
        "pcap_sha256": sha256(pcap) if pcap.is_file() else None,
        "pcap_bytes": pcap.stat().st_size if pcap.is_file() else None,
        "tc_state_sha256": {
            name: sha256(output / name)
            for name in (
                "tc_before.txt", "tc_ingress_filter.txt", "tc_ifb_configured.txt",
                "tc_ifb_final.txt", "tc_after_cleanup.txt",
            )
        },
        "cleanup_ok": cleanup_ok,
        "wrapper_error": wrapper_error or None,
        "status": (
            "PASS" if runner_status == "PASS" and cleanup_ok and not wrapper_error
            else "FAIL"
        ),
    }
    (output / "ingress_impairment_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    chown_tree(output, args.run_user)
    if manifest["status"] != "PASS":
        print(
            f"FAIL: runner={runner_status} cleanup_ok={cleanup_ok} "
            f"error={wrapper_error or 'none'}", file=sys.stderr,
        )
        return 1
    print(f"PASS: profile={args.profile} direction=board_to_host_ingress_only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
