#!/usr/bin/env python3
"""Build and bind the 51 frozen Seven-QoS cell firmware bundles."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from generate_seven_qos_performance_protocol import sha256
from prepare_seven_qos_performance_campaign import (
    CELL_REQUIREMENT_FIELDS,
    EXECUTION_PLAN_FIELDS,
    canonical_json,
    write_csv,
)


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO / "workspace/seven_qos_performance_pilot"
APP_NAME = "seven_qos_performance_pilot"
NETWORK_ACK = "I_ACKNOWLEDGE_DEDICATED_ETH1"
DURABILITY_MARKER = "PERF_DURABILITY_PREJOIN_READY"
LIVELINESS_MARKER = "PERF_LIVELINESS_OUTAGE_READY"
RESOURCE_MARKER = "PERF_RESOURCE_ACK_SUPPRESSION_READY"
def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def git_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def tracked_worktree_dirty() -> bool:
    status = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "status",
            "--short",
            "--untracked-files=no",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return bool(status)


def milliseconds(seconds: int | float) -> int:
    value = float(seconds) * 1000.0
    rounded = round(value)
    if abs(value - rounded) > 1e-9 or rounded < 0:
        raise ValueError(f"seconds value is not an exact nonnegative ms value: {seconds}")
    return int(rounded)


def cell_binding(
    requirement: dict[str, str],
    *,
    interface: str,
    board_ip: str,
    serial_port: str,
    run_user: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    family = requirement["family"]
    fixed = json.loads(requirement["fixed_json"])
    configuration = json.loads(requirement["configuration_json"])
    payload = int(
        configuration["payload_bytes"]
        if "payload_bytes" in configuration
        else fixed["payload_bytes"]
    )
    window_ms = int(fixed["measurement_window_ms"])
    if family == "deadline":
        period_ms = int(configuration["publish_period_ms"])
        if 1000 % period_ms:
            raise ValueError(f"{family}/{requirement['cell_id']}: invalid period")
        rate_hz = 1000 // period_ms
    else:
        rate_hz = int(
            configuration["publish_rate_hz"]
            if "publish_rate_hz" in configuration
            else fixed["publish_rate_hz"]
        )
    if rate_hz <= 0 or 1000 % rate_hz or rate_hz * window_ms % 1000:
        raise ValueError(f"{family}/{requirement['cell_id']}: invalid rate/window")

    cmake = {
        "MATCHED_BENCH_TELEMETRY_ENABLED": "ON",
        "MATCHED_BENCH_RELIABLE": "ON",
        "MATCHED_BENCH_PAYLOAD_BYTES": str(payload),
        "MATCHED_BENCH_PUBLISH_RATE_HZ": str(rate_hz),
        "MATCHED_BENCH_WINDOW_MS": str(window_ms),
        "MATCHED_BENCH_IMPAIRMENT": requirement["network_profile"],
        "MROS2_RTPS_HISTORY_CAPACITY": str(
            int(fixed.get("compile_time_capacity", 40))
        ),
        "SEVEN_QOS_PERFORMANCE_FAMILY": family,
        "SEVEN_QOS_PERFORMANCE_CELL_ID": requirement["cell_id"],
        "SEVEN_QOS_PERFORMANCE_RUN_TOKEN": requirement["firmware_run_token"],
        "SEVEN_QOS_PERFORMANCE_DEADLINE_MS": "0",
        "SEVEN_QOS_PERFORMANCE_LIFESPAN_MS": "0",
        "SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS": "0",
        "SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES": "0",
        "SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA": "0",
        "SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS": "0",
        "SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH": "0",
        "SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE": "0",
        "SEVEN_QOS_PERFORMANCE_DURABILITY": "none",
        "SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH": "0",
        "SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES": "0",
        "SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS": "0",
        "SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS": "0",
    }
    runtime: dict[str, Any] = {
        "system": "mros2qos",
        "mode": "on",
        "qos": "RELIABLE",
        "payload_bytes": payload,
        "rate_hz": rate_hz,
        "target_tx": rate_hz * window_ms // 1000,
        "profile": requirement["network_profile"],
        "expected_impairment": requirement["network_profile"],
        "expected_firmware_token": requirement["firmware_run_token"],
        "interface": interface,
        "board_ip": board_ip,
        "serial_port": serial_port,
        "run_user": run_user,
        "network_change_ack": NETWORK_ACK,
    }

    if family == "history_depth":
        cmake["SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH"] = str(
            int(configuration["depth"])
        )
        cmake["SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE"] = str(
            int(configuration["burst_size"])
        )
    elif family == "durability":
        cmake["SEVEN_QOS_PERFORMANCE_DURABILITY"] = str(
            configuration["durability"]
        )
        cmake["SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH"] = str(
            int(configuration["cache_depth"])
        )
        cmake["SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES"] = str(
            int(fixed["prejoin_sample_attempts"])
        )
        runtime["host_durability"] = str(configuration["durability"])
        runtime["host_start_marker"] = DURABILITY_MARKER
        runtime["host_start_delay_seconds"] = float(configuration["late_join_s"])
    elif family == "deadline":
        deadline = configuration["deadline_ms"]
        cmake["SEVEN_QOS_PERFORMANCE_DEADLINE_MS"] = str(
            0 if deadline is None else int(deadline)
        )
    elif family == "lifespan":
        lifespan = configuration["lifespan_ms"]
        cmake["SEVEN_QOS_PERFORMANCE_LIFESPAN_MS"] = str(
            0 if lifespan is None else int(lifespan)
        )
        cmake["SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS"] = str(
            int(configuration["release_delay_ms"])
        )
    elif family == "liveliness":
        lease_ms = milliseconds(configuration["lease_s"])
        outage_ms = milliseconds(configuration["outage_s"])
        cmake["SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS"] = str(lease_ms)
        cmake["SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS"] = str(outage_ms)
        runtime["host_reply_liveliness_lease_ms"] = lease_ms
        runtime["dynamic_outage_marker"] = LIVELINESS_MARKER
        runtime["dynamic_outage_seconds"] = outage_ms / 1000.0
    elif family == "resource_limits":
        ack_ms = int(fixed["ack_suppression_ms"])
        cmake["SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES"] = str(
            int(configuration["max_samples"])
        )
        cmake["SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA"] = "1"
        cmake["SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS"] = str(ack_ms)
        runtime["allow_publish_failures"] = True
        runtime["dynamic_outage_marker"] = RESOURCE_MARKER
        runtime["dynamic_outage_seconds"] = ack_ms / 1000.0
    else:
        raise ValueError(f"unsupported family: {family}")
    return cmake, runtime


def parse_cmake_cache(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("//", "#")) or "=" not in line:
            continue
        key_type, value = line.split("=", 1)
        key = key_type.split(":", 1)[0]
        values[key] = value
    return values


def build_command(build_dir: Path, cmake: dict[str, str]) -> list[str]:
    command = ["idf.py", "-B", str(build_dir)]
    for key in sorted(cmake):
        command.extend(("-D", f"{key}={cmake[key]}"))
    command.append("build")
    return command


def artifact_paths(build_dir: Path) -> dict[str, Path]:
    project_description = build_dir / "project_description.json"
    if not project_description.is_file():
        raise ValueError(f"missing project description: {project_description}")
    description = json.loads(project_description.read_text(encoding="utf-8"))
    return {
        "firmware_sha256": build_dir / f"{APP_NAME}.bin",
        "elf_sha256": build_dir / f"{APP_NAME}.elf",
        "sdkconfig_sha256": Path(description["config_file"]),
        "project_description_sha256": project_description,
    }


def verify_build(
    build_dir: Path,
    cmake: dict[str, str],
    source_commit: str,
) -> dict[str, str]:
    cache = parse_cmake_cache(build_dir / "CMakeCache.txt")
    observed = {key: cache.get(key) for key in cmake}
    if observed != cmake:
        raise ValueError(f"CMake cache mismatch in {build_dir}")
    paths = artifact_paths(build_dir)
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError("missing build artifacts: " + ", ".join(missing))
    description = json.loads(
        paths["project_description_sha256"].read_text(encoding="utf-8")
    )
    project_version = str(description.get("project_version", ""))
    if not project_version or not source_commit.startswith(project_version):
        raise ValueError(
            f"project version {project_version!r} does not bind {source_commit}"
        )
    return {field: sha256(path) for field, path in paths.items()}


def update_tables(
    prepared: Path,
    requirements: list[dict[str, str]],
    plan: list[dict[str, str]],
) -> None:
    by_key = {(row["family"], row["cell_id"]): row for row in requirements}
    for row in plan:
        requirement = by_key[(row["family"], row["cell_id"])]
        row["artifact_bundle_status"] = requirement["artifact_bundle_status"]
        row["launch_status"] = (
            "BLOCKED_UNVERIFIED_ACCEPTANCE_ORACLE"
            if requirement["artifact_bundle_status"] == "FROZEN"
            and requirement["runtime_binding_status"] == "BOUND"
            else "BLOCKED_UNFROZEN_CELL_BINDING"
        )
    write_csv(
        prepared / "cell_artifact_requirements.csv",
        CELL_REQUIREMENT_FIELDS,
        requirements,
    )
    write_csv(prepared / "execution_plan.csv", EXECUTION_PLAN_FIELDS, plan)
    manifest_path = prepared / "preparation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "BLOCKED_UNVERIFIED_ACCEPTANCE_ORACLE"
    manifest["formal_launch_allowed"] = False
    manifest["bound_cell_artifact_count"] = sum(
        row["artifact_bundle_status"] == "FROZEN" for row in requirements
    )
    manifest["bound_runtime_count"] = sum(
        row["runtime_binding_status"] == "BOUND" for row in requirements
    )
    manifest["verified_acceptance_oracle_count"] = sum(
        row["acceptance_oracle_status"] == "VERIFIED" for row in requirements
    )
    manifest["cell_artifact_requirements_sha256"] = sha256(
        prepared / "cell_artifact_requirements.csv"
    )
    manifest["execution_plan_sha256"] = sha256(prepared / "execution_plan.csv")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def bind(
    prepared: Path,
    build_root: Path,
    *,
    interface: str,
    board_ip: str,
    serial_port: str,
    run_user: str,
) -> None:
    if tracked_worktree_dirty():
        raise ValueError("tracked worktree must be clean before artifact binding")
    if not shutil.which("idf.py"):
        raise ValueError("idf.py is unavailable; source the ESP-IDF environment")
    requirements = read_csv(prepared / "cell_artifact_requirements.csv")
    plan = read_csv(prepared / "execution_plan.csv")
    source_commit = git_commit()
    source_epoch = subprocess.run(
        ["git", "-C", str(REPO), "show", "-s", "--format=%ct", source_commit],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    build_root.mkdir(parents=True, exist_ok=True)
    logs = prepared / "build_logs"
    logs.mkdir(exist_ok=True)

    for index, row in enumerate(requirements, start=1):
        cmake, runtime = cell_binding(
            row,
            interface=interface,
            board_ip=board_ip,
            serial_port=serial_port,
            run_user=run_user,
        )
        build_dir = (
            build_root
            / f"{row['family']}_{row['cell_id']}_{row['configuration_sha256'][:12]}"
        )
        try:
            hashes = verify_build(build_dir, cmake, source_commit)
            print(f"[resume {index:02d}/51] {row['family']}/{row['cell_id']}")
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            log_path = logs / f"{row['family']}_{row['cell_id']}.log"
            environment = os.environ.copy()
            environment["SOURCE_DATE_EPOCH"] = source_epoch
            print(f"[build {index:02d}/51] {row['family']}/{row['cell_id']}")
            with log_path.open("w", encoding="utf-8") as log:
                subprocess.run(
                    build_command(build_dir, cmake),
                    cwd=WORKSPACE,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True,
                )
            hashes = verify_build(build_dir, cmake, source_commit)

        row["source_commit"] = source_commit
        row["build_dir"] = str(build_dir)
        row["app_name"] = APP_NAME
        row.update(hashes)
        row["runtime_arguments_json"] = canonical_json(runtime)
        row["artifact_bundle_status"] = "FROZEN"
        row["runtime_binding_status"] = "BOUND"
        row["acceptance_oracle_status"] = "UNVERIFIED"
        row["blocking_reasons_json"] = canonical_json(
            ["exact_committed_cell_hardware_gate_unverified"]
        )
        update_tables(prepared, requirements, plan)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--board-ip", required=True)
    parser.add_argument(
        "--serial-port",
        default="/dev/ttyUSB0",
    )
    parser.add_argument("--run-user", default=os.environ.get("SUDO_USER") or os.environ.get("USER", ""))
    args = parser.parse_args()
    prepared = args.prepared.resolve()
    protocols_root = (REPO / "results/protocols").resolve()
    if protocols_root not in prepared.parents:
        parser.error(f"--prepared must be below {protocols_root}")
    try:
        bind(
            prepared,
            args.build_root.resolve(),
            interface=args.interface,
            board_ip=args.board_ip,
            serial_port=args.serial_port,
            run_user=args.run_user,
        )
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: 51 cell bundles frozen; exact hardware oracle remains blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
