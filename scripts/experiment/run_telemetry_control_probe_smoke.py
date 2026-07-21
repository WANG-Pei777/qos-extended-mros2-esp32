#!/usr/bin/env python3
"""Run one exact-binary telemetry control-probe hardware smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO.parent
SEALED_TOOLS = (
    REPO
    / "results/diagnostics/20260716_three_system_telemetry_static_overhead"
    / "provenance/tools"
)
FASTDDS_PROFILE = REPO / "scripts/experiment/fastdds_udp_mtu_1200.xml"
MICROROS_AGENT = (
    PROJECT_ROOT / "microros_bench/agent_toolchain/build/MicroXRCEAgent"
)
MICROROS_AGENT_LIBRARY = (
    PROJECT_ROOT
    / "microros_bench/agent_toolchain/build/libmicroxrcedds_agent.so.2.4"
)
MICROROS_AGENT_CACHE = (
    PROJECT_ROOT / "microros_bench/agent_toolchain/build/CMakeCache.txt"
)
IDF_PYTHON = Path(os.environ.get("IDF_PYTHON", sys.executable))
ESPTOOL = Path(
    os.environ.get("ESPTOOL", shutil.which("esptool.py") or "esptool.py")
)

BUILD_SPECS = {
    ("mros2qos", "on"): (
        REPO / "workspace/telemetry_compare/build_overhead_tickfix_on",
        "mros2qos_telemetry_compare",
    ),
    ("mros2qos", "off"): (
        REPO / "workspace/telemetry_compare/build_overhead_tickfix_off",
        "mros2qos_telemetry_compare",
    ),
    ("upstream", "on"): (
        PROJECT_ROOT
        / "upstream_bench/mros2-esp32/workspace/telemetry_compare/build_overhead_on",
        "upstream_telemetry_compare",
    ),
    ("upstream", "off"): (
        PROJECT_ROOT
        / "upstream_bench/mros2-esp32/workspace/telemetry_compare/build_overhead_off",
        "upstream_telemetry_compare",
    ),
    ("microros", "on"): (
        PROJECT_ROOT / "microros_bench/telemetry_compare/build_overhead_on",
        "microros_telemetry_compare",
    ),
    ("microros", "off"): (
        PROJECT_ROOT / "microros_bench/telemetry_compare/build_overhead_off",
        "microros_telemetry_compare",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def terminate_group(process: subprocess.Popen[bytes], grace_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    for sig, grace in ((signal.SIGINT, grace_seconds), (signal.SIGTERM, 2.0)):
        try:
            os.killpg(process.pid, sig)
            process.wait(timeout=grace)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2.0)


def command_record(command: list[str]) -> list[str]:
    return [str(item) for item in command]


def wait_for_agent_entities(
    log_path: Path,
    process: subprocess.Popen[bytes],
    timeout_seconds: float = 30.0,
) -> float:
    started = time.monotonic()
    required = (b"datawriter created", b"datareader created")
    while time.monotonic() - started < timeout_seconds:
        if process.poll() is not None:
            raise RuntimeError("micro-ROS Agent exited before entity readiness")
        if log_path.exists():
            contents = log_path.read_bytes()
            if all(marker in contents for marker in required):
                return time.monotonic() - started
        time.sleep(0.1)
    raise RuntimeError("micro-ROS Agent entities not ready within 30 seconds")


def normalize_expected_qos(value: str) -> str:
    normalized = value.strip().upper().replace("-", "_")
    aliases = {
        "BE": "BEST_EFFORT",
        "BEST_EFFORT": "BEST_EFFORT",
        "REL": "RELIABLE",
        "RELIABLE": "RELIABLE",
    }
    if normalized not in aliases:
        raise ValueError(f"unsupported expected QoS: {value}")
    return aliases[normalized]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=("mros2qos", "upstream", "microros"), required=True)
    parser.add_argument("--mode", choices=("on", "off"), required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--app-name")
    parser.add_argument("--expected-qos", default="BEST_EFFORT")
    parser.add_argument("--expected-payload-bytes", type=int, default=64)
    parser.add_argument("--expected-rate-hz", type=int, default=10)
    parser.add_argument("--expected-target-tx", type=int, default=200)
    parser.add_argument("--expected-impairment", default="clean")
    parser.add_argument("--allow-delivery-loss", action="store_true")
    parser.add_argument("--agent-verbosity", type=int, choices=range(7), default=4)
    parser.add_argument("--micro-dds-mtu-profile", action="store_true")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--capture-timeout", type=float, default=180.0)
    parser.add_argument("--min-host-free-gib", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        args.expected_qos = normalize_expected_qos(args.expected_qos)
    except ValueError as exc:
        parser.error(str(exc))
    if args.capture_timeout <= 0:
        parser.error("--capture-timeout must be positive")
    if args.min_host_free_gib < 0:
        parser.error("--min-host-free-gib must be nonnegative")
    if (args.build_dir is None) != (args.app_name is None):
        parser.error("--build-dir and --app-name must be provided together")
    if args.expected_payload_bytes <= 0 or args.expected_target_tx <= 0:
        parser.error("expected payload and target TX must be positive")
    if args.expected_rate_hz <= 0 or 1000 % args.expected_rate_hz:
        parser.error("expected rate must be a positive divisor of 1000 Hz")
    if args.mode == "off" and (
        args.expected_qos != "BEST_EFFORT"
        or args.expected_payload_bytes != 64
        or args.expected_rate_hz != 10
        or args.expected_target_tx != 200
        or args.expected_impairment != "clean"
    ):
        parser.error("custom workload validation currently requires telemetry mode on")
    if args.mode == "off" and args.allow_delivery_loss:
        parser.error("--allow-delivery-loss requires telemetry mode on")
    if args.system != "microros" and args.agent_verbosity != 4:
        parser.error("--agent-verbosity only applies to micro-ROS")
    if args.system != "microros" and args.micro_dds_mtu_profile:
        parser.error("--micro-dds-mtu-profile only applies to micro-ROS")

    output = args.output if args.output.is_absolute() else REPO / args.output
    if output.exists():
        parser.error(f"output already exists: {output}")

    host_storage = Path("/mnt/c")
    if not host_storage.is_dir():
        raise SystemExit("missing /mnt/c host-storage mount")
    host_storage_usage = shutil.disk_usage(host_storage)
    min_host_free_bytes = int(args.min_host_free_gib * 1024**3)
    if host_storage_usage.free < min_host_free_bytes:
        raise SystemExit(
            "host storage gate failed: "
            f"free={host_storage_usage.free} required={min_host_free_bytes}"
        )

    if args.build_dir is None:
        build_dir, app_name = BUILD_SPECS[(args.system, args.mode)]
    else:
        build_dir = args.build_dir.resolve()
        app_name = args.app_name
    source_artifacts = {
        "bootloader": build_dir / "bootloader/bootloader.bin",
        "partition_table": build_dir / "partition_table/partition-table.bin",
        "firmware": build_dir / f"{app_name}.bin",
        "elf": build_dir / f"{app_name}.elf",
        "map": build_dir / f"{app_name}.map",
        "cmake_cache": build_dir / "CMakeCache.txt",
    }
    use_fastdds_profile = args.system != "microros" or args.micro_dds_mtu_profile
    if use_fastdds_profile:
        source_artifacts["fastdds_profile"] = FASTDDS_PROFILE
    if args.system == "microros":
        source_artifacts["micro_ros_agent"] = MICROROS_AGENT
        source_artifacts["micro_ros_agent_library"] = MICROROS_AGENT_LIBRARY
        source_artifacts["micro_ros_agent_cmake_cache"] = MICROROS_AGENT_CACHE
    project_description_path = build_dir / "project_description.json"
    if not project_description_path.is_file():
        raise SystemExit(f"missing build description: {project_description_path}")
    project_description = json.loads(project_description_path.read_text())
    sdkconfig_path = Path(project_description["config_file"])
    required_paths = [
        *source_artifacts.values(),
        sdkconfig_path,
        SEALED_TOOLS / "echo_node",
        IDF_PYTHON,
        ESPTOOL,
    ]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise SystemExit("missing required paths:\n" + "\n".join(missing))
    if not args.dry_run and not Path(args.port).exists():
        raise SystemExit(f"serial port does not exist: {args.port}")

    output.mkdir(parents=True)
    artifact_dir = output / "artifacts"
    artifact_dir.mkdir()
    artifact_records = {}
    for name, source in source_artifacts.items():
        destination = artifact_dir / source.name
        shutil.copy2(source, destination)
        artifact_records[name] = {
            "path": str(destination.relative_to(output)),
            "bytes": destination.stat().st_size,
            "sha256": sha256(destination),
            "source_path": str(source),
        }

    manifest = {
        "schema_version": 1,
        "classification": "telemetry_control_probe_engineering_smoke",
        "evidence_boundary": "diagnostic pilot gate; never a formal comparison run",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": args.system,
        "mode": args.mode,
        "serial_port": args.port,
        "agent_verbosity": args.agent_verbosity if args.system == "microros" else None,
        "micro_dds_mtu_profile": (
            args.micro_dds_mtu_profile if args.system == "microros" else None
        ),
        "capture_timeout_seconds": args.capture_timeout,
        "host_storage_gate": {
            "path": str(host_storage),
            "free_bytes_at_start": host_storage_usage.free,
            "required_free_bytes": min_host_free_bytes,
            "status": "PASS",
        },
        "workload": {
            "qos": args.expected_qos,
            "payload_bytes": args.expected_payload_bytes,
            "rate_hz": args.expected_rate_hz,
            "target_tx": args.expected_target_tx,
            "impairment": args.expected_impairment,
            "delivery_policy": (
                "outcome" if args.allow_delivery_loss else "exact"
            ),
        },
        "build_dir": str(build_dir),
        "project_description_sha256": sha256(project_description_path),
        "sdkconfig_path": str(sdkconfig_path),
        "sdkconfig_sha256": sha256(sdkconfig_path),
        "artifacts": artifact_records,
        "commands": {},
        "return_codes": {},
        "startup_order": (
            "agent_board_entities_then_host"
            if args.system == "microros"
            else "host_then_board_reset"
        ),
        "status": "RUNNING",
    }
    manifest_path = output / "attempt_manifest.json"

    flash_command = [
        str(IDF_PYTHON),
        str(ESPTOOL),
        "--chip",
        "esp32s3",
        "-p",
        args.port,
        "-b",
        "460800",
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
        "--flash_mode",
        "dio",
        "--flash_freq",
        "80m",
        "--flash_size",
        "2MB",
        "0x0",
        str(artifact_dir / source_artifacts["bootloader"].name),
        "0x10000",
        str(artifact_dir / source_artifacts["firmware"].name),
        "0x8000",
        str(artifact_dir / source_artifacts["partition_table"].name),
    ]
    host_qos_flag = (
        "--best-effort" if args.expected_qos == "BEST_EFFORT" else "--reliable"
    )
    host_exports = "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
    if use_fastdds_profile:
        host_exports += (
            "export FASTRTPS_DEFAULT_PROFILES_FILE="
            + shlex.quote(str(artifact_dir / FASTDDS_PROFILE.name))
            + " && "
        )
    host_shell = (
        "source /opt/ros/humble/setup.bash && "
        + host_exports
        + "exec "
        + shlex.quote(str(SEALED_TOOLS / "echo_node"))
        + " " + host_qos_flag + " --topic-base /system_compare"
    )
    host_command = ["bash", "-lc", host_shell]
    agent_command = [
        str(artifact_dir / MICROROS_AGENT.name),
        "udp4",
        "--port",
        "7408",
        "--verbose",
        str(args.agent_verbosity),
    ]
    agent_environment = os.environ.copy()
    if args.system == "microros":
        if args.micro_dds_mtu_profile:
            agent_environment["FASTRTPS_DEFAULT_PROFILES_FILE"] = str(
                artifact_dir / FASTDDS_PROFILE.name
            )
            agent_environment.pop("FASTDDS_DEFAULT_PROFILES_FILE", None)
        else:
            # The Wi-Fi hop is bounded by the XRCE transport MTU. The Agent
            # and echo node otherwise use the default local DDS transport.
            agent_environment.pop("FASTRTPS_DEFAULT_PROFILES_FILE", None)
            agent_environment.pop("FASTDDS_DEFAULT_PROFILES_FILE", None)
    terminal_prefix = "BENCH_DUMP_END" if args.mode == "on" else "COMPARE_FINAL"
    capture_command = [
        sys.executable,
        str(REPO / "scripts/experiment/capture_benchmark_telemetry_smoke.py"),
        "--port",
        args.port,
        "--timeout",
        str(args.capture_timeout),
        "--terminal-prefix",
        terminal_prefix,
        "--post-terminal-seconds",
        "6",
        "--output",
        str(output / "serial.raw"),
    ]
    if args.mode == "on":
        validator_command = [
            sys.executable,
            str(REPO / "scripts/experiment/validate_benchmark_telemetry_smoke.py"),
            str(output / "serial.raw"),
            "--require-control-probe",
            "--expected-qos",
            args.expected_qos,
            "--expected-payload-bytes",
            str(args.expected_payload_bytes),
            "--expected-rate-hz",
            str(args.expected_rate_hz),
            "--expected-target-tx",
            str(args.expected_target_tx),
            "--expected-impairment",
            args.expected_impairment,
        ]
        if args.allow_delivery_loss:
            validator_command.append("--allow-delivery-loss")
    else:
        validator_command = [
            sys.executable,
            str(REPO / "scripts/experiment/validate_telemetry_off_smoke.py"),
            str(output / "serial.raw"),
            "--system",
            args.system,
            "--require-control-probe",
        ]
    manifest["commands"] = {
        "flash": command_record(flash_command),
        "host": command_record(host_command),
        "agent": command_record(agent_command) if args.system == "microros" else None,
        "agent_environment": (
            (
                {
                    "FASTRTPS_DEFAULT_PROFILES_FILE": str(
                        artifact_dir / FASTDDS_PROFILE.name
                    ),
                    "FASTDDS_DEFAULT_PROFILES_FILE": "unset",
                    "scope": "local Agent-to-host DDS; XRCE Wi-Fi MTU remains firmware-controlled",
                }
                if args.micro_dds_mtu_profile
                else {
                    "FASTRTPS_DEFAULT_PROFILES_FILE": "unset",
                    "FASTDDS_DEFAULT_PROFILES_FILE": "unset",
                    "scope": "default local DDS; XRCE Wi-Fi MTU is firmware-controlled",
                }
            )
            if args.system == "microros"
            else None
        ),
        "capture": command_record(capture_command),
        "validator": command_record(validator_command),
    }

    if args.dry_run:
        manifest["status"] = "DRY_RUN_PASS"
        manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"PASS: dry-run manifest written to {manifest_path}")
        return 0

    host_process: subprocess.Popen[bytes] | None = None
    agent_process: subprocess.Popen[bytes] | None = None
    capture_process: subprocess.Popen[bytes] | None = None
    host_log = (output / "host.log").open("wb")
    agent_log = (output / "agent.log").open("wb")
    try:
        with (output / "flash.log").open("wb") as flash_log:
            flash = subprocess.run(
                flash_command,
                cwd=REPO,
                stdout=flash_log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        manifest["return_codes"]["flash"] = flash.returncode
        if flash.returncode != 0:
            raise RuntimeError("flash failed")

        if args.system == "microros":
            agent_process = subprocess.Popen(
                agent_command,
                cwd=REPO,
                env=agent_environment,
                stdout=agent_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        with (output / "capture.log").open("wb") as capture_log:
            if args.system == "microros":
                capture_process = subprocess.Popen(
                    capture_command,
                    cwd=REPO,
                    stdout=capture_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                entity_wait = wait_for_agent_entities(
                    output / "agent.log", agent_process
                )
                manifest["agent_entity_ready_wait_seconds"] = entity_wait
                host_process = subprocess.Popen(
                    host_command,
                    cwd=REPO,
                    stdout=host_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                capture_returncode = capture_process.wait()
            else:
                host_process = subprocess.Popen(
                    host_command,
                    cwd=REPO,
                    stdout=host_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                time.sleep(1.0)
                capture = subprocess.run(
                    capture_command,
                    cwd=REPO,
                    stdout=capture_log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                capture_returncode = capture.returncode
        manifest["return_codes"]["capture"] = capture_returncode
        if capture_returncode != 0:
            raise RuntimeError("UART capture failed")

        with (output / "validation.txt").open("wb") as validation_log:
            validation = subprocess.run(
                validator_command,
                cwd=REPO,
                stdout=validation_log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        manifest["return_codes"]["validator"] = validation.returncode
        if validation.returncode != 0:
            raise RuntimeError("strict validator failed")
        manifest["status"] = "PASS"
    except Exception as exc:
        manifest["status"] = "FAIL"
        manifest["failure"] = str(exc)
    finally:
        if capture_process is not None:
            terminate_group(capture_process, grace_seconds=1.0)
        if host_process is not None:
            terminate_group(host_process)
            manifest["return_codes"]["host"] = host_process.returncode
        if agent_process is not None:
            terminate_group(agent_process)
            manifest["return_codes"]["agent"] = agent_process.returncode
        host_log.close()
        agent_log.close()
        manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    if manifest["status"] != "PASS":
        print(f"FAIL: {manifest.get('failure', 'unknown failure')}", file=sys.stderr)
        return 1
    validation_text = (output / "validation.txt").read_text(errors="replace").strip()
    print(f"PASS: {args.system}/{args.mode} {validation_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
