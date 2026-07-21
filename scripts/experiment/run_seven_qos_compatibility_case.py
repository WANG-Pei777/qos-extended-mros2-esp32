#!/usr/bin/env python3
"""Build and run one hardware compatibility row from the Seven-QoS schedule."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time


REPO = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve()
WORKSPACE = REPO / "workspace/seven_qos_compatibility"
DEFAULT_HOST_PROBE = (
    REPO
    / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/qos_compatibility_probe"
)
CAPTURE = REPO / "scripts/experiment/capture_benchmark_telemetry_smoke.py"
HOST_VALIDATOR = (
    REPO / "scripts/experiment/validate_qos_compatibility_host_probe.py"
)
BOARD_VALIDATOR = (
    REPO / "scripts/experiment/validate_qos_compatibility_board_probe.py"
)
DEFAULT_SCHEDULE = (
    REPO
    / "results/protocols/20260717_seven_qos_deterministic_expanded_draft"
    / "schedule.csv"
)
DEFAULT_PROFILE = (
    REPO / "tools/echo_cpp/config/seven_qos_esp32_initial_peer.xml"
)


@dataclass(frozen=True)
class EndpointQos:
    reliability: str = "reliable"
    durability: str = "volatile"
    deadline_ms: str = "infinite"
    liveliness_lease_ms: str = "infinite"


@dataclass(frozen=True)
class ResolvedCase:
    case_id: str
    policy: str
    direction: str
    endpoint_creation_order: str
    expected_match: bool
    board_role: str
    host_role: str
    board_qos: EndpointQos
    host_qos: EndpointQos


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_frozen_bundle(bundle_dir: Path, case_id: str) -> dict:
    manifest_path = bundle_dir / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("case_id") != case_id:
        raise ValueError("frozen bundle case ID mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("frozen bundle has no file inventory")
    for relative, record in files.items():
        path = (bundle_dir / relative).resolve()
        if not path.is_relative_to(bundle_dir):
            raise ValueError("frozen bundle path escapes its root")
        if not path.is_file():
            raise ValueError(f"missing frozen bundle file: {relative}")
        if path.stat().st_size != record.get("bytes"):
            raise ValueError(f"frozen bundle size mismatch: {relative}")
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"frozen bundle SHA-256 mismatch: {relative}")
    return manifest


def frozen_flash_command(
    idf_export: Path,
    serial_port: str,
    bundle_dir: Path,
    manifest: dict,
) -> list[str]:
    flash = manifest.get("flash", {})
    arguments = [
        "python",
        "-m",
        "esptool",
        "--chip",
        flash["chip"],
        "--port",
        serial_port,
        "--baud",
        str(flash["baud"]),
        "--before",
        flash["before"],
        "--after",
        flash["after"],
        "write_flash",
        *flash["write_flash_args"],
    ]
    for item in flash["flash_files"]:
        path = (bundle_dir / item["relative_path"]).resolve()
        if not path.is_relative_to(bundle_dir):
            raise ValueError("frozen flash path escapes its root")
        arguments.extend((item["offset"], str(path)))
    body = (
        f"source {shlex.quote(str(idf_export))} >/dev/null 2>&1 && "
        f"exec {shlex.join(arguments)}"
    )
    return ["bash", "-lc", body]


def load_case(schedule: Path, case_id: str) -> dict[str, str]:
    with schedule.open(newline="", encoding="utf-8") as stream:
        matches = [
            row for row in csv.DictReader(stream) if row["case_id"] == case_id
        ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one schedule row for {case_id!r}")
    row = matches[0]
    if row["case_type"] != "compatibility" or row["level"] != "hardware":
        raise ValueError("case must be a hardware compatibility row")
    return row


def resolve_case(row: dict[str, str]) -> ResolvedCase:
    policy = row["policy"]
    direction = row["direction"]
    order = row["endpoint_creation_order"]
    if policy not in {"reliability", "durability", "deadline", "liveliness"}:
        raise ValueError(f"unsupported compatibility policy: {policy}")
    if direction not in {"b2h", "h2b"}:
        raise ValueError(f"unsupported direction: {direction}")
    if order not in {"remote_first", "local_first"}:
        raise ValueError(f"unsupported endpoint creation order: {order}")

    configuration = json.loads(row["configuration_json"])
    expected = json.loads(row["expected_json"])
    if set(expected) != {"expected_match"} or not isinstance(
        expected["expected_match"], bool
    ):
        raise ValueError(
            "expected_json must contain one boolean expected_match"
        )

    offered = EndpointQos()
    requested = EndpointQos()
    if policy == "reliability":
        offered = EndpointQos(reliability=configuration["offered"])
        requested = EndpointQos(reliability=configuration["requested"])
    elif policy == "durability":
        offered = EndpointQos(durability=configuration["offered"])
        requested = EndpointQos(durability=configuration["requested"])
    elif policy == "deadline":
        offered = EndpointQos(deadline_ms=str(configuration["offered_ms"]))
        requested = EndpointQos(deadline_ms=str(configuration["requested_ms"]))
    else:
        if configuration.get("kind") != "automatic":
            raise ValueError("only automatic liveliness is supported")
        offered = EndpointQos(
            liveliness_lease_ms=str(configuration["offered_lease_ms"])
        )
        requested = EndpointQos(
            liveliness_lease_ms=str(configuration["requested_lease_ms"])
        )

    allowed = {
        "reliability": {"reliable", "best_effort"},
        "durability": {"volatile", "transient_local"},
    }
    for endpoint in (offered, requested):
        if endpoint.reliability not in allowed["reliability"]:
            raise ValueError("invalid reliability value")
        if endpoint.durability not in allowed["durability"]:
            raise ValueError("invalid durability value")

    board_is_publisher = direction == "b2h"
    return ResolvedCase(
        case_id=row["case_id"],
        policy=policy,
        direction=direction,
        endpoint_creation_order=order,
        expected_match=expected["expected_match"],
        board_role="publisher" if board_is_publisher else "subscriber",
        host_role="subscriber" if board_is_publisher else "publisher",
        board_qos=offered if board_is_publisher else requested,
        host_qos=requested if board_is_publisher else offered,
    )


def cmake_duration(value: str) -> str:
    return "0" if value == "infinite" else value


def wait_for_marker(
    path: Path, marker: bytes, process: subprocess.Popen[bytes], timeout: float
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and marker in path.read_bytes():
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def idf_command(
    export: Path, workspace: Path, arguments: list[str]
) -> list[str]:
    body = (
        f"source {shlex.quote(str(export))} >/dev/null 2>&1 && "
        f"cd {shlex.quote(str(workspace))} && "
        f"idf.py {shlex.join(arguments)}"
    )
    return ["bash", "-lc", body]


def run_logged(command: list[str], log: Path, *, cwd: Path = REPO) -> int:
    with log.open("wb") as stream:
        return subprocess.run(
            command,
            cwd=cwd,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode


def host_command(
    case: ResolvedCase,
    host_probe: Path,
    profile: Path,
    ros_setup: Path,
    gate: Path | None,
    host_wait_ms: int,
    post_match_ms: int,
) -> list[str]:
    arguments = [
        str(host_probe),
        "--case-id",
        case.case_id,
        "--role",
        case.host_role,
        "--topic",
        "/seven_qos_compatibility",
        "--reliability",
        case.host_qos.reliability,
        "--durability",
        case.host_qos.durability,
        "--deadline-ms",
        case.host_qos.deadline_ms,
        "--liveliness-lease-ms",
        case.host_qos.liveliness_lease_ms,
        "--expected-match",
        str(int(case.expected_match)),
        "--wait-ms",
        str(host_wait_ms),
        "--post-match-ms",
        str(post_match_ms),
        "--message-count",
        "10",
        "--period-ms",
        "100",
    ]
    if gate is not None:
        arguments += [
            "--endpoint-gate",
            str(gate),
            "--endpoint-gate-timeout-ms",
            str(host_wait_ms + 20000),
        ]
    body = (
        f"source {shlex.quote(str(ros_setup))} && "
        "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
        "export FASTRTPS_DEFAULT_PROFILES_FILE="
        f"{shlex.quote(str(profile))} && "
        "exec timeout "
        f"{max(60, (host_wait_ms + post_match_ms) // 1000 + 30)} "
        f"{shlex.join(arguments)}"
    )
    return ["bash", "-lc", body]


def validator_commands(
    case: ResolvedCase, output: Path
) -> tuple[list[str], list[str]]:
    expected = str(int(case.expected_match))
    host = [
        sys.executable,
        str(HOST_VALIDATOR),
        str(output / "host.log"),
        "--case-id",
        case.case_id,
        "--role",
        case.host_role,
        "--expected-match",
        expected,
    ]
    board = [
        sys.executable,
        str(BOARD_VALIDATOR),
        str(output / "serial.raw"),
        "--case-id",
        case.case_id,
        "--role",
        case.board_role,
        "--reliability",
        case.board_qos.reliability,
        "--durability",
        case.board_qos.durability,
        "--deadline-ms",
        case.board_qos.deadline_ms,
        "--liveliness-lease-ms",
        case.board_qos.liveliness_lease_ms,
        "--expected-match",
        expected,
    ]
    return host, board


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--host-probe", type=Path, default=DEFAULT_HOST_PROBE
    )
    parser.add_argument(
        "--frozen-artifacts",
        type=Path,
        help=(
            "prebuilt case bundle; disables compilation and flashes exact "
            "bytes"
        ),
    )
    parser.add_argument(
        "--idf-export",
        type=Path,
        default=Path.home() / "esp-idf/export.sh",
    )
    parser.add_argument(
        "--ros-setup",
        type=Path,
        default=Path("/opt/ros/humble/setup.bash"),
    )
    parser.add_argument(
        "--build-dir", default="build_compatibility_case_runner"
    )
    parser.add_argument("--board-wait-ms", type=int, default=20000)
    parser.add_argument("--post-match-ms", type=int, default=20000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    schedule = args.schedule.resolve()
    profile = args.profile.resolve()
    host_probe = args.host_probe.resolve()
    case = resolve_case(load_case(schedule, args.case_id))
    if args.board_wait_ms < 10000 or args.post_match_ms < 10000:
        parser.error(
            "board wait and post-match hold must each be at least 10000 ms"
        )
    if args.board_ip not in profile.read_text(encoding="utf-8"):
        parser.error(
            "board IP does not match the Fast DDS initial-peer profile"
        )
    frozen_dir = (
        args.frozen_artifacts.resolve() if args.frozen_artifacts else None
    )
    frozen_manifest = (
        load_frozen_bundle(frozen_dir, case.case_id)
        if frozen_dir is not None
        else None
    )
    if args.dry_run:
        value = asdict(case)
        value["execution_mode"] = (
            "frozen_artifacts" if frozen_manifest else "build_from_source"
        )
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--output is required unless --dry-run is used")

    output = args.output.resolve()
    if output.exists():
        parser.error(f"output already exists: {output}")
    output.mkdir(parents=True)
    artifacts = output / "artifacts"
    artifacts.mkdir()
    started = utc_now()
    row = load_case(schedule, args.case_id)
    write_json_atomic(output / "schedule_row.json", row)
    shutil.copy2(profile, artifacts / profile.name)

    board_wait_ms = args.board_wait_ms
    host_wait_ms = board_wait_ms + 5000 if not case.expected_match else 50000
    build_arguments = [
        "-B",
        args.build_dir,
        f"-DMROS2_QOS_CASE_ID={case.case_id}",
        f"-DMROS2_QOS_BOARD_ROLE={case.board_role}",
        f"-DMROS2_QOS_RELIABILITY={case.board_qos.reliability}",
        f"-DMROS2_QOS_DURABILITY={case.board_qos.durability}",
        "-DMROS2_QOS_DEADLINE_MS="
        f"{cmake_duration(case.board_qos.deadline_ms)}",
        "-DMROS2_QOS_LIVELINESS_LEASE_MS="
        f"{cmake_duration(case.board_qos.liveliness_lease_ms)}",
        f"-DMROS2_QOS_EXPECTED_MATCH={int(case.expected_match)}",
        f"-DMROS2_QOS_WAIT_MS={board_wait_ms}",
        "-DMROS2_QOS_POST_MATCH_MS=5000",
        "-DMROS2_QOS_MESSAGE_COUNT=10",
        "-DMROS2_QOS_PERIOD_MS=100",
        "build",
    ]
    return_codes: dict[str, int] = {}
    failure = ""
    host_process: subprocess.Popen[bytes] | None = None
    capture_process: subprocess.Popen[bytes] | None = None
    pcap_process: subprocess.Popen[bytes] | None = None
    pcap_log = None
    host_log = None
    capture_log = None
    order_evidence: dict[str, object] = {}
    try:
        if frozen_manifest is None:
            return_codes["build"] = run_logged(
                idf_command(args.idf_export, WORKSPACE, build_arguments),
                output / "build.log",
            )
            if return_codes["build"] != 0:
                raise RuntimeError("firmware build failed")
            build_dir = WORKSPACE / args.build_dir
            firmware = build_dir / "seven_qos_compatibility.bin"
            shutil.copy2(firmware, artifacts / "firmware.bin")
            shutil.copy2(
                build_dir / "CMakeCache.txt", artifacts / "CMakeCache.txt"
            )
            flash_command = idf_command(
                args.idf_export,
                WORKSPACE,
                ["-p", args.serial_port, "-B", args.build_dir, "flash"],
            )
        else:
            (output / "build.log").write_text(
                "FROZEN_ARTIFACTS_NO_BUILD\n", encoding="ascii"
            )
            shutil.copy2(
                frozen_dir / "artifact_manifest.json",
                artifacts / "frozen_artifact_manifest.json",
            )
            app_relative = frozen_manifest["app_relative_path"]
            shutil.copy2(frozen_dir / app_relative, artifacts / "firmware.bin")
            flash_command = frozen_flash_command(
                args.idf_export,
                args.serial_port,
                frozen_dir,
                frozen_manifest,
            )

        return_codes["flash"] = run_logged(
            flash_command,
            output / "flash.log",
        )
        if return_codes["flash"] != 0:
            raise RuntimeError("firmware flash failed")

        pcap_log = (output / "dumpcap.log").open("wb")
        pcap_process = subprocess.Popen(
            [
                "dumpcap",
                "-q",
                "-i",
                args.interface,
                "-f",
                f"host {args.board_ip} and udp",
                "-w",
                str(output / "capture.pcapng"),
            ],
            cwd=REPO,
            stdout=pcap_log,
            stderr=subprocess.STDOUT,
        )

        gate = (
            output / "release_host_endpoint.gate"
            if case.endpoint_creation_order == "local_first"
            else None
        )
        host_log = (output / "host.log").open("wb")
        host_process = subprocess.Popen(
            host_command(
                case,
                host_probe,
                profile,
                args.ros_setup,
                gate,
                host_wait_ms,
                args.post_match_ms,
            ),
            cwd=REPO,
            stdout=host_log,
            stderr=subprocess.STDOUT,
        )
        host_marker = (
            b"QOS_HOST_PARTICIPANT_READY "
            if gate is not None
            else b"QOS_HOST_ENDPOINT_READY "
        )
        if not wait_for_marker(
            output / "host.log", host_marker, host_process, 15
        ):
            raise RuntimeError("host readiness marker was not observed")
        order_evidence["host_marker"] = host_marker.decode().strip()
        order_evidence["host_marker_observed_at_utc"] = utc_now()

        capture_command = [
            sys.executable,
            str(CAPTURE),
            "--port",
            args.serial_port,
            "--timeout",
            str(max(45, board_wait_ms / 1000 + 20)),
            "--terminal-prefix",
            "QOS_BOARD_FINAL",
            "--output",
            str(output / "serial.raw"),
        ]
        capture_log = (output / "capture.log").open("wb")
        capture_process = subprocess.Popen(
            capture_command,
            cwd=REPO,
            stdout=capture_log,
            stderr=subprocess.STDOUT,
        )
        if gate is not None:
            if not wait_for_marker(
                output / "serial.raw",
                b"QOS_BOARD_LOCAL_READY ",
                capture_process,
                max(30, board_wait_ms / 1000),
            ):
                raise RuntimeError(
                    "board local endpoint marker was not observed"
                )
            order_evidence["board_marker"] = "QOS_BOARD_LOCAL_READY"
            order_evidence["board_marker_observed_at_utc"] = utc_now()
            gate.write_text(
                f"released_at_utc={utc_now()}\n", encoding="ascii"
            )
            order_evidence["host_endpoint_gate_released_at_utc"] = utc_now()
        else:
            order_evidence["board_reset_started_at_utc"] = utc_now()

        return_codes["capture"] = capture_process.wait(
            timeout=max(60, board_wait_ms / 1000 + 30)
        )
        return_codes["host"] = host_process.wait(
            timeout=max(
                80, (host_wait_ms + args.post_match_ms) / 1000 + 30
            )
        )
        host_validation, board_validation = validator_commands(case, output)
        return_codes["host_validation"] = run_logged(
            host_validation, output / "host_validation.log"
        )
        return_codes["board_validation"] = run_logged(
            board_validation, output / "board_validation.log"
        )
        if any(return_codes.values()):
            raise RuntimeError(
                "one or more execution or validation stages failed"
            )
    except Exception as error:  # Evidence is retained for every failure mode.
        failure = str(error)
    finally:
        for process in (capture_process, host_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        if pcap_process is not None and pcap_process.poll() is None:
            pcap_process.send_signal(signal.SIGINT)
            try:
                pcap_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pcap_process.kill()
        for stream in (capture_log, host_log, pcap_log):
            if stream is not None:
                stream.close()

    hash_paths = [
        RUNNER,
        schedule,
        profile,
        host_probe,
        HOST_VALIDATOR,
        BOARD_VALIDATOR,
        REPO / "mros2/embeddedRTPS/src/discovery/SPDPAgent.cpp",
        REPO / "mros2/embeddedRTPS/src/discovery/TopicData.cpp",
        REPO / "mros2/embeddedRTPS/src/entities/Domain.cpp",
        REPO / "mros2/embeddedRTPS/include/rtps/discovery/TopicData.h",
        REPO
        / "mros2/embeddedRTPS/include/rtps/discovery/QoSCompatibility.h",
        REPO / "mros2/embeddedRTPS/include/rtps/entities/QosTime.h",
        REPO / "mros2/src/mros2.cpp",
        REPO / "workspace/seven_qos_compatibility/CMakeLists.txt",
        REPO / "workspace/seven_qos_compatibility/main/app.cpp",
    ]
    if (artifacts / "firmware.bin").exists():
        hash_paths.append(artifacts / "firmware.bin")
    if frozen_dir is not None and frozen_manifest is not None:
        hash_paths.append(frozen_dir / "artifact_manifest.json")
        hash_paths.extend(
            frozen_dir / name for name in frozen_manifest["files"]
        )
    manifest = {
        "schema_version": 1,
        "classification": "seven_qos_hardware_compatibility_case",
        "status": "PASS" if not failure else "FAIL",
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "case": asdict(case),
        "schedule_row": row,
        "schedule_sha256": sha256(schedule),
        "serial_port": args.serial_port,
        "board_ip": args.board_ip,
        "interface": args.interface,
        "build_dir": args.build_dir,
        "execution_mode": (
            "frozen_artifacts" if frozen_manifest else "build_from_source"
        ),
        "frozen_bundle_manifest_sha256": (
            sha256(frozen_dir / "artifact_manifest.json")
            if frozen_dir is not None
            else None
        ),
        "order_evidence": order_evidence,
        "return_codes": return_codes,
        "failure": failure,
        "artifacts": {
            (
                str(path.relative_to(REPO))
                if path.is_relative_to(REPO)
                else str(path)
            ): sha256(path)
            for path in hash_paths
            if path.exists()
        },
    }
    write_json_atomic(output / "manifest.json", manifest)
    print(
        f"{manifest['status']}: case_id={case.case_id} "
        f"direction={case.direction} order={case.endpoint_creation_order} "
        f"expected_match={int(case.expected_match)} output={output}"
    )
    if failure:
        print(f"failure={failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
