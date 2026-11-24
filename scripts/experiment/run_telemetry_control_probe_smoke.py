#!/usr/bin/env python3
"""Run one exact-binary telemetry control-probe hardware smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from seven_qos_evidence_identity import (
    EVIDENCE_MODES,
    validate_evidence_identity,
)


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
MICROROS_SNAP_COMMAND = Path("/snap/bin/micro-ros-agent")
MICROROS_SNAP_BINARY = Path(
    "/snap/micro-ros-agent/current/opt/ros/snap/lib/"
    "micro_ros_agent/micro_ros_agent"
)
MICROROS_SNAP_MANIFEST = Path(
    "/snap/micro-ros-agent/current/meta/snap.yaml"
)
IDF_PYTHON = Path(os.environ.get("IDF_PYTHON", sys.executable))
ESPTOOL = Path(
    os.environ.get("ESPTOOL", shutil.which("esptool.py") or "esptool.py")
)
RUN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
DURABILITY_PREJOIN_MARKER = "PERF_DURABILITY_PREJOIN_READY"

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


def validate_flash_reuse(
    manifest_path: Path,
    *,
    system: str,
    mode: str,
    serial_port: str,
    firmware_sha256: str,
) -> dict[str, object]:
    """Validate that a prior PASS attempt flashed this exact firmware."""
    manifest_path = manifest_path.expanduser().resolve()
    if not manifest_path.is_file():
        raise ValueError(f"flash-reuse manifest is unavailable: {manifest_path}")
    try:
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"flash-reuse manifest is unreadable: {manifest_path}"
        ) from exc
    firmware = prior.get("artifacts", {}).get("firmware", {})
    checks = {
        "status": prior.get("status") == "PASS",
        "system": prior.get("system") == system,
        "mode": prior.get("mode") == mode,
        "serial_port": prior.get("serial_port") == serial_port,
        "firmware_sha256": firmware.get("sha256") == firmware_sha256,
        "flash_return_code": prior.get("return_codes", {}).get("flash") == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(
            "flash-reuse source does not prove the requested exact firmware: "
            + ", ".join(failed)
        )
    return {
        "classification": "verified_exact_binary_flash_reuse",
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256(manifest_path),
        "source_attempt_started_at_utc": prior.get("started_at_utc"),
        "source_flash_started_at_utc": prior.get("flash_started_at_utc"),
        "source_flash_completed_at_utc": prior.get("flash_completed_at_utc"),
        "firmware_sha256": firmware_sha256,
        "checks": checks,
    }


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


def wait_for_serial_marker(
    raw_path: Path,
    marker: bytes,
    process: subprocess.Popen[bytes],
    timeout_seconds: float,
) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        if process.poll() is not None:
            raise RuntimeError("UART capture exited before host start marker")
        if raw_path.exists() and marker in raw_path.read_bytes():
            return time.monotonic() - started
        time.sleep(0.1)
    raise RuntimeError(
        f"host start marker not seen within {timeout_seconds:.1f} seconds"
    )


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


def validate_durability_probe(raw: bytes, expected_depth: int) -> dict[str, int]:
    """Strictly validate the retained suffix reported by the board probe."""
    text = raw.decode("utf-8", "replace")
    lines = [
        line for line in text.splitlines()
        if line.startswith("PERF_POLICY_FINAL ")
    ]
    if len(lines) != 1:
        raise ValueError(
            f"expected one PERF_POLICY_FINAL, found {len(lines)}"
        )
    fields: dict[str, str] = {}
    for token in lines[0].split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value

    def integer(key: str) -> int:
        if key not in fields:
            raise ValueError(f"PERF_POLICY_FINAL is missing {key}")
        return int(fields[key], 0)

    # Transient Local retains the newest min(depth, pre-join) samples; Volatile
    # is the control and must retain none. Both are valid probe configurations
    # and both are checked exactly - the Volatile branch is not a waiver, it
    # asserts 0 retained, 0 replies and an empty replay mask, which is the same
    # expectation app.cpp already encodes for durability_code != 1.
    probe_durability = fields.get("durability")
    if probe_durability not in ("transient_local", "volatile"):
        raise ValueError(
            "durability probe used an unsupported Durability: "
            f"{probe_durability!r}"
        )
    cache_depth = integer("durability_cache_depth")
    prejoin_samples = integer("durability_prejoin_samples")
    attempts = integer("durability_attempt_delta")
    accepted = integer("durability_accept_delta")
    rejected = integer("durability_reject_delta")
    allocation_failures = integer("durability_allocation_failure_delta")
    history_prejoin = integer("durability_history_prejoin")
    history_after_join = integer("durability_history_after_join")
    replies = integer("durability_probe_replies")
    reply_mask = integer("durability_probe_reply_mask")
    reader_matched = integer("durability_reader_matched")
    # The KEEP_LAST buffer fills the same way under both Durability kinds, so
    # the pre-join history count is identical; what Volatile changes is whether
    # those retained samples are REPLAYED to a reader that joins later. Keeping
    # `retained` common and branching only on the replay is what makes the
    # control isolate Durability: the data is demonstrably present either way.
    retained = min(cache_depth, prejoin_samples)
    transient_local = probe_durability == "transient_local"
    expected_replies = retained if transient_local else 0
    expected_mask = (
        (((1 << retained) - 1) << (prejoin_samples - retained))
        if transient_local
        else 0
    )
    if cache_depth != expected_depth:
        raise ValueError(
            f"durability depth mismatch: {cache_depth} != {expected_depth}"
        )
    if not 1 <= prejoin_samples <= 64:
        raise ValueError("durability pre-join sample count is outside 1..64")
    if attempts != prejoin_samples or accepted != attempts:
        raise ValueError("durability pre-join acceptance is inconsistent")
    if rejected != 0 or allocation_failures != 0:
        raise ValueError("durability pre-join cache reported a failure")
    # Transient Local must have retained exactly the suffix - that is the whole
    # claim. A Volatile writer makes no retention guarantee, so its history holds
    # only whatever has not yet drained: 10 and 4 were observed on consecutive
    # runs of the same build. Bound it rather than pin it. The control's evidence
    # is the replay count and the post-join history, both of which are exactly
    # zero and are asserted as such below.
    if transient_local:
        if history_prejoin != retained:
            raise ValueError(
                "durability pre-join retained history count is incomplete"
            )
    elif not 0 <= history_prejoin <= cache_depth:
        raise ValueError(
            "durability pre-join history count exceeds the configured cache depth"
        )
    # After the late reader joins, the firmware deliberately emits a live gate
    # sample and may emit warm-up samples before PERF_POLICY_FINAL is captured.
    # Those live samples legitimately grow a partially filled KEEP_LAST cache.
    # The replay mask below proves the pre-join suffix itself; this count only
    # needs to preserve that suffix without exceeding the configured depth.
    # Transient Local must still hold the suffix after the join; Volatile drops
    # it, which is the control's whole point, so its floor is zero.
    post_join_floor = retained if transient_local else 0
    if not post_join_floor <= history_after_join <= cache_depth:
        raise ValueError(
            "durability post-join history count is outside retained/depth bounds"
        )
    if reader_matched != 1:
        raise ValueError("durability writer has no matched host reader")
    if replies != expected_replies or reply_mask != expected_mask:
        raise ValueError(
            "durability replay suffix is incomplete: "
            f"replies={replies}/{retained} "
            f"mask=0x{reply_mask:016x} expected=0x{expected_mask:016x}"
        )
    return {
        "cache_depth": cache_depth,
        "prejoin_samples": prejoin_samples,
        "retained": retained,
        "history_prejoin": history_prejoin,
        "history_after_join": history_after_join,
        "replies": replies,
        "reply_mask": reply_mask,
    }


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
    parser.add_argument("--expected-reply-grace-ms", type=int, default=5000)
    parser.add_argument("--expected-rdh-depth", type=int, default=0)
    parser.add_argument(
        "--rdh-volatile-control",
        action="store_true",
        help="RDH run whose endpoint is Volatile: expect a volatile "
             "host rather than Transient Local. Opt-in and narrow - "
             "it only relaxes the host Durability requirement.",
    )
    parser.add_argument("--expected-impairment", default="clean")
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
    parser.add_argument("--allow-delivery-loss", action="store_true")
    parser.add_argument("--allow-publish-failures", action="store_true")
    parser.add_argument(
        "--host-durability", choices=("volatile", "transient_local"),
        default="volatile",
    )
    parser.add_argument("--host-history-depth", type=int, default=10)
    parser.add_argument(
        "--expected-endpoint-durability",
        choices=("volatile", "transient_local"),
        help=(
            "Firmware endpoint durability attested by COMPARE_CONFIG; "
            "defaults to --host-durability"
        ),
    )
    parser.add_argument(
        "--expected-endpoint-history",
        choices=("keep_last",),
        default="keep_last",
    )
    parser.add_argument(
        "--expected-endpoint-history-depth",
        type=int,
        help=(
            "Firmware endpoint Keep Last depth attested by COMPARE_CONFIG; "
            "defaults to --host-history-depth"
        ),
    )
    parser.add_argument(
        "--host-rdh-only",
        action="store_true",
        help="Disable non-Reliability/Durability/History QoS on the host echo.",
    )
    parser.add_argument("--host-start-delay-seconds", type=float, default=0.0)
    parser.add_argument(
        "--micro-host-restart-after-seconds",
        type=float,
        default=0.0,
        help=(
            "For micro-ROS only: restart the host echo once when COMPARE_READY "
            "has not appeared after this many seconds. This is a bounded "
            "discovery-recovery gate and is recorded in the attempt manifest."
        ),
    )
    parser.add_argument("--host-start-marker")
    parser.add_argument("--host-reply-liveliness-lease-ms", type=int, default=0)
    parser.add_argument("--agent-verbosity", type=int, choices=range(7), default=4)
    parser.add_argument(
        "--micro-agent-backend", choices=("local", "snap"), default="local",
        help="micro-ROS Agent provenance/launch backend",
    )
    parser.add_argument("--micro-dds-mtu-profile", action="store_true")
    parser.add_argument(
        "--micro-agent-refs",
        type=Path,
        help="Fast DDS entity-reference XML passed to the micro-ROS Agent",
    )
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--capture-timeout", type=float, default=180.0)
    parser.add_argument("--min-host-free-gib", type=float, default=5.0)
    parser.add_argument("--echo-node", type=Path, default=SEALED_TOOLS / "echo_node")
    parser.add_argument("--fastdds-profile", type=Path, default=FASTDDS_PROFILE)
    parser.add_argument("--idf-python", type=Path, default=IDF_PYTHON)
    parser.add_argument("--esptool", type=Path, default=ESPTOOL)
    parser.add_argument(
        "--reuse-flashed-from",
        type=Path,
        help=(
            "Do not flash; reuse the board image proven by a prior PASS "
            "attempt_manifest.json. Exact firmware SHA-256, system, mode, "
            "serial port, and successful prior flash are mandatory."
        ),
    )
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
    if args.host_start_delay_seconds < 0:
        parser.error("--host-start-delay-seconds must be nonnegative")
    if args.micro_host_restart_after_seconds < 0:
        parser.error("--micro-host-restart-after-seconds must be nonnegative")
    if args.system != "microros" and args.micro_host_restart_after_seconds > 0:
        parser.error("--micro-host-restart-after-seconds requires --system microros")
    if not 1 <= args.host_history_depth <= 1000:
        parser.error("--host-history-depth must be in 1..1000")
    endpoint_durability = (
        args.expected_endpoint_durability or args.host_durability
    )
    endpoint_history_depth = (
        args.expected_endpoint_history_depth
        if args.expected_endpoint_history_depth is not None
        else args.host_history_depth
    )
    if args.system != "upstream" and not 1 <= endpoint_history_depth <= 40:
        parser.error("--expected-endpoint-history-depth must be in 1..40")
    if args.system != "upstream" and (
        endpoint_durability != args.host_durability
        or endpoint_history_depth != args.host_history_depth
    ):
        parser.error(
            "matched endpoint durability and History depth must equal the "
            "host settings"
        )
    if not 0 <= args.host_reply_liveliness_lease_ms <= 10000:
        parser.error("--host-reply-liveliness-lease-ms must be in 0..10000")
    if args.host_start_marker is not None:
        try:
            marker_bytes = args.host_start_marker.encode("ascii")
        except UnicodeEncodeError:
            parser.error("--host-start-marker must be ASCII")
        if not marker_bytes or b"\n" in marker_bytes or b"\r" in marker_bytes:
            parser.error("--host-start-marker must be one nonempty line fragment")
    else:
        marker_bytes = None
    durability_probe_gate = args.host_start_marker == DURABILITY_PREJOIN_MARKER
    if (args.build_dir is None) != (args.app_name is None):
        parser.error("--build-dir and --app-name must be provided together")
    if args.expected_payload_bytes <= 0 or args.expected_target_tx <= 0:
        parser.error("expected payload and target TX must be positive")
    if not 1000 <= args.expected_reply_grace_ms <= 30000:
        parser.error("--expected-reply-grace-ms must be in 1000..30000")
    if not 0 <= args.expected_rdh_depth <= 40:
        parser.error("--expected-rdh-depth must be in 0..40")
    # The Volatile late-join control is the one legitimate case where an RDH
    # run must NOT have a Transient Local host. The board is the writer holding
    # the pre-join cache and the host is the late-joining reader, so a Volatile
    # board writer cannot satisfy a Transient Local host reader - offered vs
    # requested Durability makes them incompatible and the bidirectional match
    # times out. Requiring transient_local unconditionally therefore excludes
    # exactly the control that gives P2/P3 their meaning.
    #
    # This guard was added 2026-08-03 for the impaired campaign, after the
    # 2026-07-30 late-join runs; those ran before it existed, which is why the
    # control worked then and not now.
    required_host_durability = (
        "volatile" if args.rdh_volatile_control else "transient_local"
    )
    if args.expected_rdh_depth > 0 and (
        args.system == "upstream"
        or args.expected_qos != "RELIABLE"
        or args.host_durability != required_host_durability
        or args.host_history_depth != args.expected_rdh_depth
    ):
        parser.error(
            "RDH mode requires a non-upstream Reliable system and matching "
            "Transient Local host depth"
        )
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
    if args.expected_rate_hz <= 0 or 1000 % args.expected_rate_hz:
        parser.error("expected rate must be a positive divisor of 1000 Hz")
    if args.system != "microros" and args.agent_verbosity != 4:
        parser.error("--agent-verbosity only applies to micro-ROS")
    if args.system != "microros" and args.micro_agent_backend != "local":
        parser.error("--micro-agent-backend only applies to micro-ROS")
    if args.system != "microros" and args.micro_dds_mtu_profile:
        parser.error("--micro-dds-mtu-profile only applies to micro-ROS")
    if args.system != "microros" and args.micro_agent_refs is not None:
        parser.error("--micro-agent-refs only applies to micro-ROS")
    if args.system == "microros" and args.host_start_marker is not None:
        parser.error("serial-marker host start does not apply to micro-ROS")

    echo_node = args.echo_node.resolve()
    fastdds_profile = args.fastdds_profile.resolve()
    idf_python = args.idf_python.expanduser().absolute()
    esptool = args.esptool.resolve()

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
        "echo_node": echo_node,
    }
    use_fastdds_profile = args.system != "microros" or args.micro_dds_mtu_profile
    if use_fastdds_profile:
        source_artifacts["fastdds_profile"] = fastdds_profile
    if args.system == "microros":
        if args.micro_agent_refs is not None:
            source_artifacts["micro_ros_agent_refs"] = (
                args.micro_agent_refs.expanduser().resolve()
            )
        if args.micro_agent_backend == "snap":
            source_artifacts["micro_ros_agent_snap_binary"] = (
                MICROROS_SNAP_BINARY
            )
            source_artifacts["micro_ros_agent_snap_manifest"] = (
                MICROROS_SNAP_MANIFEST
            )
        else:
            source_artifacts["micro_ros_agent"] = MICROROS_AGENT
            source_artifacts["micro_ros_agent_library"] = (
                MICROROS_AGENT_LIBRARY
            )
            source_artifacts["micro_ros_agent_cmake_cache"] = (
                MICROROS_AGENT_CACHE
            )
    project_description_path = build_dir / "project_description.json"
    if not project_description_path.is_file():
        raise SystemExit(f"missing build description: {project_description_path}")
    project_description = json.loads(project_description_path.read_text())
    sdkconfig_path = Path(project_description["config_file"])
    source_artifacts["project_description"] = project_description_path
    source_artifacts["sdkconfig"] = sdkconfig_path
    required_paths = [
        *source_artifacts.values(),
        idf_python,
        esptool,
    ]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise SystemExit("missing required paths:\n" + "\n".join(missing))
    if not args.dry_run and not Path(args.port).exists():
        raise SystemExit(f"serial port does not exist: {args.port}")

    flash_reuse = None
    if args.reuse_flashed_from is not None:
        try:
            flash_reuse = validate_flash_reuse(
                args.reuse_flashed_from,
                system=args.system,
                mode=args.mode,
                serial_port=args.port,
                firmware_sha256=sha256(source_artifacts["firmware"]),
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

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
        "classification": (
            "seven_qos_performance_formal_attempt"
            if args.evidence_mode == "formal_candidate"
            else "telemetry_control_probe_engineering_smoke"
        ),
        "evidence_boundary": (
            "formal candidate only; acceptance ledger determines inclusion"
            if args.evidence_mode == "formal_candidate"
            else "diagnostic pilot gate; never a formal comparison run"
        ),
        "evidence_identity": evidence_identity.as_dict(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": args.system,
        "mode": args.mode,
        "serial_port": args.port,
        "agent_verbosity": args.agent_verbosity if args.system == "microros" else None,
        "micro_agent_backend": (
            args.micro_agent_backend if args.system == "microros" else None
        ),
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
            "reply_grace_ms": args.expected_reply_grace_ms,
            "rdh_depth": args.expected_rdh_depth,
            "impairment": args.expected_impairment,
            "delivery_policy": (
                "outcome" if args.allow_delivery_loss else "exact"
            ),
            "publish_failure_policy": (
                "outcome" if args.allow_publish_failures else "zero"
            ),
            "host_durability": args.host_durability,
            "host_history_depth": args.host_history_depth,
            "expected_endpoint_durability": (
                endpoint_durability if args.system != "upstream" else None
            ),
            "expected_endpoint_history": (
                args.expected_endpoint_history
                if args.system != "upstream"
                else None
            ),
            "expected_endpoint_history_depth": (
                endpoint_history_depth if args.system != "upstream" else None
            ),
            "host_rdh_only": args.host_rdh_only,
            "host_start_delay_seconds": args.host_start_delay_seconds,
            "micro_host_restart_after_seconds": (
                args.micro_host_restart_after_seconds
                if args.system == "microros"
                else None
            ),
            "host_start_marker": args.host_start_marker,
            "host_reply_liveliness_lease_ms": (
                args.host_reply_liveliness_lease_ms
            ),
            "durability_probe_gate": durability_probe_gate,
            "firmware_run_token": args.expected_firmware_token,
        },
        "build_dir": str(build_dir),
        "project_version": project_description.get("project_version"),
        "project_description_sha256": sha256(project_description_path),
        "sdkconfig_path": str(sdkconfig_path),
        "sdkconfig_sha256": sha256(sdkconfig_path),
        "idf_python": str(idf_python),
        "idf_python_sha256": sha256(idf_python),
        "esptool": str(esptool),
        "esptool_sha256": sha256(esptool),
        "artifacts": artifact_records,
        "flash_execution": {
            "policy": (
                "reuse_verified_exact_binary"
                if flash_reuse is not None
                else "execute_flash_this_attempt"
            ),
            "executed_this_attempt": flash_reuse is None,
            "reuse": flash_reuse,
            "status": "PLANNED",
        },
        "commands": {},
        "return_codes": {},
        "startup_order": (
            "capture_then_host_then_agent_board_entities_with_bounded_ready_restart"
            if args.system == "microros"
            and args.micro_host_restart_after_seconds > 0
            else "capture_then_delayed_host_then_agent_board_entities"
            if args.system == "microros" and args.host_start_delay_seconds > 0
            else "capture_then_host_then_agent_board_entities"
            if args.system == "microros"
            else (
                "board_reset_then_capture_then_marker_then_host"
                if args.host_start_marker is not None
                else "board_reset_then_capture_then_delayed_host"
                if args.host_start_delay_seconds > 0
                else "board_reset_then_capture_then_host"
            )
        ),
        "status": "RUNNING",
    }
    manifest_path = output / "attempt_manifest.json"

    flash_command = [
        str(idf_python),
        str(esptool),
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
    reset_command = [
        str(idf_python),
        str(esptool),
        "--chip",
        "esp32s3",
        "-p",
        args.port,
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "run",
    ]
    host_qos_flag = (
        "--best-effort" if args.expected_qos == "BEST_EFFORT" else "--reliable"
    )
    host_exports = "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
    if use_fastdds_profile:
        host_exports += (
            "export FASTRTPS_DEFAULT_PROFILES_FILE="
            + shlex.quote(str(artifact_dir / source_artifacts["fastdds_profile"].name))
            + " && "
        )
    host_shell = (
        "source /opt/ros/humble/setup.bash && "
        + host_exports
        + "exec "
        + shlex.quote(str(artifact_dir / source_artifacts["echo_node"].name))
        + " " + host_qos_flag
        + (" --transient-local" if args.host_durability == "transient_local" else "")
        + " --history-depth " + str(args.host_history_depth)
        + (" --rdh-only" if args.host_rdh_only else "")
        + (" --wait-for-reply-reader" if durability_probe_gate else "")
        + (" --buffer-durability-probe" if durability_probe_gate else "")
        + (" --defer-subscription-until-spin" if durability_probe_gate else "")
        + (
            " --reply-liveliness-lease-ms "
            + str(args.host_reply_liveliness_lease_ms)
            if args.host_reply_liveliness_lease_ms > 0
            else ""
        )
        + " --topic-base /system_compare"
    )
    host_command = ["bash", "-lc", host_shell]
    agent_executable = (
        MICROROS_SNAP_COMMAND
        if args.system == "microros" and args.micro_agent_backend == "snap"
        else artifact_dir / MICROROS_AGENT.name
    )
    agent_command = [
        str(agent_executable),
        "udp4",
        "--port",
        "7408",
        "--verbose",
        str(args.agent_verbosity),
    ]
    if args.system == "microros" and args.micro_agent_refs is not None:
        agent_command.extend(
            (
                "--refs",
                str(artifact_dir / source_artifacts["micro_ros_agent_refs"].name),
            )
        )
    agent_environment = os.environ.copy()
    if args.system == "microros":
        if args.micro_dds_mtu_profile:
            agent_environment["FASTRTPS_DEFAULT_PROFILES_FILE"] = str(
                artifact_dir / source_artifacts["fastdds_profile"].name
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
        "--failure-prefix",
        "BENCH_SMOKE_ERROR",
        "--failure-prefix",
        "COMPARE_FATAL",
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
            "--expected-reply-grace-ms",
            str(args.expected_reply_grace_ms),
            "--expected-impairment",
            args.expected_impairment,
        ]
        if args.system != "upstream":
            validator_command.extend(
                (
                    "--expected-endpoint-durability",
                    endpoint_durability.upper(),
                    "--expected-endpoint-history",
                    args.expected_endpoint_history.upper(),
                    "--expected-endpoint-history-depth",
                    str(endpoint_history_depth),
                )
            )
        if args.expected_firmware_token is not None:
            validator_command.extend(
                ("--expected-run-token", args.expected_firmware_token)
            )
        if args.allow_delivery_loss:
            validator_command.append("--allow-delivery-loss")
        if args.allow_publish_failures:
            validator_command.append("--allow-publish-failures")
    else:
        validator_command = [
            sys.executable,
            str(REPO / "scripts/experiment/validate_telemetry_off_smoke.py"),
            str(output / "serial.raw"),
            "--system",
            args.system,
            "--expected-qos",
            args.expected_qos,
            "--expected-payload-bytes",
            str(args.expected_payload_bytes),
            "--expected-rate-hz",
            str(args.expected_rate_hz),
            "--expected-target-tx",
            str(args.expected_target_tx),
            "--expected-reply-grace-ms",
            str(args.expected_reply_grace_ms),
            "--expected-rdh-depth",
            str(args.expected_rdh_depth),
        ]
        if args.system != "upstream":
            validator_command.append("--require-control-probe")
        if args.expected_impairment in {
            "tail_outage_h2b",
            "liveliness_outage_h2b",
            "resource_ack_suppression_h2b",
        }:
            nominal_window_us = (
                args.expected_target_tx * 1_000_000 // args.expected_rate_hz
            )
            validator_command.extend(
                (
                    "--expected-control-window-max-us",
                    str(
                        nominal_window_us
                        + args.expected_reply_grace_ms * 1000
                    ),
                )
            )
        if args.allow_delivery_loss:
            validator_command.append("--allow-delivery-loss")
        if args.allow_publish_failures:
            validator_command.append("--allow-publish-failures")
    manifest["commands"] = {
        "flash": command_record(flash_command),
        "reset_without_flash": (
            command_record(reset_command) if flash_reuse is not None else None
        ),
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
        manifest["flash_execution"]["status"] = "DRY_RUN_VALIDATED"
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
        if flash_reuse is None:
            manifest["flash_started_at_utc"] = (
                datetime.now(timezone.utc).isoformat()
            )
            with (output / "flash.log").open("wb") as flash_log:
                flash = subprocess.run(
                    flash_command,
                    cwd=REPO,
                    stdout=flash_log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            manifest["flash_completed_at_utc"] = (
                datetime.now(timezone.utc).isoformat()
            )
            manifest["return_codes"]["flash"] = flash.returncode
            manifest["flash_execution"]["status"] = (
                "PASS" if flash.returncode == 0 else "FAIL"
            )
            if flash.returncode != 0:
                raise RuntimeError("flash failed")
        else:
            with (output / "reset.log").open("wb") as reset_log:
                reset = subprocess.run(
                    reset_command,
                    cwd=REPO,
                    stdout=reset_log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            manifest["return_codes"]["reset_without_flash"] = reset.returncode
            manifest["flash_execution"]["status"] = (
                "REUSED_VERIFIED_AND_RESET"
                if reset.returncode == 0
                else "REUSE_RESET_FAIL"
            )
            if reset.returncode != 0:
                raise RuntimeError("exact-binary reuse board reset failed")
            manifest["flash_reuse_verified_at_utc"] = (
                datetime.now(timezone.utc).isoformat()
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
                if args.host_start_delay_seconds > 0:
                    time.sleep(args.host_start_delay_seconds)
                manifest["host_started_at_utc"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                host_process = subprocess.Popen(
                    host_command,
                    cwd=REPO,
                    stdout=host_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                agent_process = subprocess.Popen(
                    agent_command,
                    cwd=REPO,
                    env=agent_environment,
                    stdout=agent_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                entity_wait = wait_for_agent_entities(
                    output / "agent.log", agent_process
                )
                manifest["agent_entity_ready_wait_seconds"] = entity_wait
                manifest["micro_host_restart_performed"] = False
                if args.micro_host_restart_after_seconds > 0:
                    ready_marker = b"COMPARE_READY system=microros"
                    restart_deadline = (
                        time.monotonic()
                        + args.micro_host_restart_after_seconds
                    )
                    while time.monotonic() < restart_deadline:
                        if capture_process.poll() is not None:
                            break
                        if agent_process.poll() is not None:
                            raise RuntimeError(
                                "micro-ROS Agent exited while awaiting COMPARE_READY"
                            )
                        if host_process.poll() is not None:
                            raise RuntimeError(
                                "host exited while awaiting COMPARE_READY"
                            )
                        if (
                            (output / "serial.raw").exists()
                            and ready_marker
                            in (output / "serial.raw").read_bytes()
                        ):
                            break
                        time.sleep(0.1)
                    ready_seen = (
                        (output / "serial.raw").exists()
                        and ready_marker in (output / "serial.raw").read_bytes()
                    )
                    if not ready_seen and capture_process.poll() is None:
                        first_host_process = host_process
                        host_log.write(
                            b"\n--- managed overlapping host recovery: "
                            b"COMPARE_READY absent ---\n"
                        )
                        host_log.flush()
                        manifest["micro_host_restart_performed"] = True
                        manifest["micro_host_restarted_at_utc"] = (
                            datetime.now(timezone.utc).isoformat()
                        )
                        replacement_host_process = subprocess.Popen(
                            host_command,
                            cwd=REPO,
                            stdout=host_log,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        recovery_deadline = time.monotonic() + 10.0
                        recovery_ready_seen = False
                        while time.monotonic() < recovery_deadline:
                            if capture_process.poll() is not None:
                                break
                            if replacement_host_process.poll() is not None:
                                raise RuntimeError(
                                    "replacement host exited before COMPARE_READY"
                                )
                            recovery_ready_seen = (
                                (output / "serial.raw").exists()
                                and ready_marker
                                in (output / "serial.raw").read_bytes()
                            )
                            if recovery_ready_seen:
                                break
                            time.sleep(0.1)
                        manifest["micro_host_recovery_ready_seen"] = (
                            recovery_ready_seen
                        )
                        terminate_group(first_host_process, grace_seconds=0.2)
                        manifest["micro_first_host_return_code"] = (
                            first_host_process.returncode
                        )
                        host_process = replacement_host_process
                capture_returncode = capture_process.wait()
            else:
                capture_process = subprocess.Popen(
                    capture_command,
                    cwd=REPO,
                    stdout=capture_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                if marker_bytes is not None:
                    marker_wait = wait_for_serial_marker(
                        output / "serial.raw",
                        marker_bytes,
                        capture_process,
                        args.capture_timeout,
                    )
                    manifest["host_start_marker_wait_seconds"] = marker_wait
                if args.host_start_delay_seconds > 0:
                    time.sleep(args.host_start_delay_seconds)
                manifest["host_started_at_utc"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                host_process = subprocess.Popen(
                    host_command,
                    cwd=REPO,
                    stdout=host_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                time.sleep(1.0)
                if host_process.poll() is not None:
                    raise RuntimeError("host exited before capture completed")
                capture_returncode = capture_process.wait()
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
        if durability_probe_gate:
            try:
                manifest["durability_probe_validation"] = (
                    validate_durability_probe(
                        (output / "serial.raw").read_bytes(),
                        args.expected_rdh_depth,
                    )
                )
            except ValueError as exc:
                raise RuntimeError(
                    f"strict durability replay validator failed: {exc}"
                ) from exc
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
