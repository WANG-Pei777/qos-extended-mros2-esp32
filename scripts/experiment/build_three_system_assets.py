#!/usr/bin/env python3
"""Build, reproducibility-check, and seal the three-system executable set."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
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

from three_system_common import (
    file_record,
    generate_schedule,
    git_output,
    require_clean_repo,
    sha256_file,
    write_schedule,
)


SYSTEM_BUILD_SPECS = {
    "mros2qos": {
        "project": "workspace/system_compare",
        "app": "system_compare",
    },
    "upstream": {
        "project": "workspace/echoreply_string",
        "app": "echoreply_string",
    },
    "microros": {
        "project": "examples/int32_publisher",
        "app": "int32_publisher",
        "sdkconfig_defaults": "sdkconfig.defaults;sdkconfig.defaults.local",
    },
}


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument(
        "--upstream-root",
        type=Path,
        default=project_root / "upstream_bench/mros2-esp32",
    )
    parser.add_argument(
        "--microros-root",
        type=Path,
        default=project_root / "microros_bench/micro_ros_espidf_component",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--host-ip",
        required=True,
        help="Frozen ROS 2/WSL IPv4 encoded in the direct-RTPS peer config",
    )
    parser.add_argument(
        "--build-root", type=Path, default=Path("/tmp/three-system-build")
    )
    parser.add_argument("--repro-builds", type=int, default=2)
    parser.add_argument(
        "--agent-binary",
        type=Path,
        default=Path(
            "/snap/micro-ros-agent/current/opt/ros/snap/lib/"
            "micro_ros_agent/micro_ros_agent"
        ),
    )
    parser.add_argument(
        "--agent-launcher", type=Path, default=Path("/usr/bin/snap")
    )
    return parser.parse_args()


def run_logged(command, cwd, environment, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [str(item) for item in command],
            cwd=cwd,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if completed.returncode != 0:
        raise SystemExit(f"build failed ({completed.returncode}): {log_path}")


def safe_fresh_directory(path):
    path = Path(path).resolve()
    try:
        path.relative_to("/tmp")
    except ValueError as exc:
        raise ValueError(f"build directory must remain under /tmp: {path}") from exc
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def sanitized_sdkconfig(source, destination):
    text = Path(source).read_text(encoding="utf-8", errors="replace")
    lines = []
    for line in text.splitlines():
        if re.match(r"CONFIG_ESP_WIFI_(SSID|PASSWORD)=", line):
            key = line.split("=", 1)[0]
            lines.append(f'{key}="<redacted>"')
        else:
            lines.append(line)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def require_ignored_file(repo, path):
    if not path.is_file():
        raise ValueError(f"required local configuration is missing: {path}")
    completed = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "-q", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise ValueError(f"local configuration is not ignored by Git: {path}")


def validate_rtps_peer_config(path, expected_ip):
    address = ipaddress.IPv4Address(expected_ip)
    octets = ", ".join(str(item) for item in address.packed)
    expected = f"REMOTE_PARTICIPANT_IP{{{octets}}}"
    text = Path(path).read_text(encoding="utf-8")
    if expected not in text:
        raise ValueError(
            f"RTPS peer config does not encode frozen host IP {address}: {path}"
        )
    return str(address)


def validate_microros_agent_config(path, expected_ip):
    expected = f'CONFIG_MICRO_ROS_AGENT_IP="{expected_ip}"'
    text = Path(path).read_text(encoding="utf-8")
    if expected not in text:
        raise ValueError(
            f"micro-ROS sdkconfig does not encode frozen Agent IP {expected_ip}"
        )


def build_firmware(system, repo, output, build_root, build_count, base_env):
    spec = SYSTEM_BUILD_SPECS[system]
    project = repo / spec["project"]
    app = spec["app"]
    system_output = output / "systems" / system
    system_output.mkdir(parents=True, exist_ok=True)
    commit = git_output(repo, "rev-parse", "HEAD")
    source_epoch = git_output(repo, "show", "-s", "--format=%ct", commit)
    hashes = []
    build_records = []
    canonical_root = build_root / f"{system}_repro"
    primary_root = safe_fresh_directory(build_root / f"{system}_primary")
    for ordinal in range(1, build_count + 1):
        # Reuse one absolute path after a full deletion. ESP-IDF embeds the ELF
        # digest in the app descriptor, and debug paths otherwise change it.
        root = safe_fresh_directory(canonical_root)
        sdkconfig = root / "sdkconfig"
        command = [
            "idf.py",
            "-B",
            root,
            "-D",
            f"SDKCONFIG={sdkconfig}",
            "-D",
            "CCACHE_ENABLE=0",
        ]
        defaults = spec.get("sdkconfig_defaults")
        if defaults:
            command.extend(["-D", f"SDKCONFIG_DEFAULTS={defaults}"])
        command.append("build")
        environment = base_env.copy()
        environment["SOURCE_DATE_EPOCH"] = source_epoch
        log_path = system_output / f"build_{ordinal}.log"
        run_logged(command, project, environment, log_path)
        current = {
            "firmware": sha256_file(root / f"{app}.bin"),
            "bootloader": sha256_file(root / "bootloader/bootloader.bin"),
            "partition_table": sha256_file(
                root / "partition_table/partition-table.bin"
            ),
        }
        hashes.append(current)
        build_records.append(
            {
                "ordinal": ordinal,
                "command": [str(item) for item in command],
                "log": file_record(log_path, output),
                "hashes": current,
            }
        )
        if ordinal == 1:
            for relative in (
                f"{app}.bin",
                f"{app}.elf",
                f"{app}.map",
                "bootloader/bootloader.bin",
                "partition_table/partition-table.bin",
                "sdkconfig",
            ):
                source = root / relative
                destination = primary_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    if any(item != hashes[0] for item in hashes[1:]):
        raise SystemExit(f"non-reproducible firmware build: {system}")

    copies = {
        "firmware": (primary_root / f"{app}.bin", f"{app}.bin"),
        "bootloader": (
            primary_root / "bootloader/bootloader.bin",
            "bootloader.bin",
        ),
        "partition_table": (
            primary_root / "partition_table/partition-table.bin",
            "partition-table.bin",
        ),
        "elf": (primary_root / f"{app}.elf", f"{app}.elf"),
        "map": (primary_root / f"{app}.map", f"{app}.map"),
    }
    artifacts = {}
    for name, (source, filename) in copies.items():
        destination = system_output / filename
        shutil.copy2(source, destination)
        artifacts[name] = file_record(destination, output)
    sanitized = system_output / "sdkconfig.redacted"
    sanitized_sdkconfig(primary_root / "sdkconfig", sanitized)
    artifacts["sdkconfig_redacted"] = file_record(sanitized, output)
    return {
        "source_repo": str(repo),
        "source_commit": commit,
        "source_tree": git_output(repo, "rev-parse", "HEAD^{tree}"),
        "app": app,
        "reproducibility": {
            "builds": build_count,
            "status": "PASS",
            "hashes_identical": True,
        },
        "builds": build_records,
        "artifacts": artifacts,
        "flash_offsets": {
            "bootloader": "0x0",
            "partition_table": "0x8000",
            "firmware": "0x10000",
        },
    }


def build_host(project_root, output, build_root, build_count, base_env):
    source = project_root / "tools/echo_cpp"
    host_output = output / "host"
    host_output.mkdir(parents=True, exist_ok=True)
    hashes = []
    records = []
    canonical_root = build_root / "host_repro"
    primary_root = safe_fresh_directory(build_root / "host_primary")
    primary_binary = primary_root / "echo_node"
    for ordinal in range(1, build_count + 1):
        root = safe_fresh_directory(canonical_root)
        command = [
            "colcon",
            "--log-base",
            root / "log",
            "build",
            "--base-paths",
            source,
            "--packages-select",
            "echo_cpp",
            "--build-base",
            root / "build",
            "--install-base",
            root / "install",
        ]
        log_path = host_output / f"build_{ordinal}.log"
        run_logged(command, project_root, base_env, log_path)
        binary = root / "install/echo_cpp/lib/echo_cpp/echo_node"
        digest = sha256_file(binary)
        hashes.append(digest)
        records.append(
            {
                "ordinal": ordinal,
                "command": [str(item) for item in command],
                "log": file_record(log_path, output),
                "sha256": digest,
            }
        )
        if ordinal == 1:
            shutil.copy2(binary, primary_binary)
    if any(item != hashes[0] for item in hashes[1:]):
        raise SystemExit("non-reproducible host echo build")
    destination = host_output / "echo_node"
    shutil.copy2(primary_binary, destination)
    destination.chmod(0o755)
    return {
        "source_commit": git_output(project_root, "rev-parse", "HEAD"),
        "reproducibility": {
            "builds": build_count,
            "status": "PASS",
            "hashes_identical": True,
        },
        "builds": records,
        "artifact": file_record(destination, output),
    }


def main():
    args = parse_args()
    if args.repro_builds < 2:
        raise SystemExit("at least two builds are required for reproducibility")
    project_root = args.project_root.resolve()
    repos = {
        "mros2qos": project_root,
        "upstream": args.upstream_root.resolve(),
        "microros": args.microros_root.resolve(),
    }
    commits = {system: require_clean_repo(repo) for system, repo in repos.items()}
    require_ignored_file(
        project_root, project_root / "platform/wifi/wifi_secrets.h"
    )
    peer_config = project_root / "platform/rtps/config_local.h"
    require_ignored_file(project_root, peer_config)
    host_ip = validate_rtps_peer_config(peer_config, args.host_ip)
    require_ignored_file(
        repos["upstream"], repos["upstream"] / "platform/wifi/wifi_secrets.h"
    )
    require_ignored_file(
        repos["microros"],
        repos["microros"]
        / "examples/int32_publisher/sdkconfig.defaults.local",
    )
    if not os.environ.get("IDF_PATH") or not shutil.which("idf.py"):
        raise SystemExit("source the ESP-IDF environment before building")
    if not os.environ.get("AMENT_PREFIX_PATH") or not shutil.which("colcon"):
        raise SystemExit("source ROS 2 Humble before building the host echo")

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    build_root = args.build_root.resolve()
    base_env = os.environ.copy()
    systems = {
        system: build_firmware(
            system,
            repo,
            output,
            build_root,
            args.repro_builds,
            base_env,
        )
        for system, repo in repos.items()
    }
    peer_copy = output / "systems/mros2qos/rtps_peer_config.h"
    shutil.copy2(peer_config, peer_copy)
    systems["mros2qos"]["artifacts"]["rtps_peer_config"] = file_record(
        peer_copy, output
    )
    systems["mros2qos"]["runtime_peer_ipv4"] = host_ip
    microros_config = output / systems["microros"]["artifacts"][
        "sdkconfig_redacted"
    ]["path"]
    validate_microros_agent_config(microros_config, host_ip)
    systems["microros"]["runtime_agent_ipv4"] = host_ip
    host = build_host(
        project_root,
        output,
        build_root,
        args.repro_builds,
        base_env,
    )

    agent_binary = args.agent_binary.resolve()
    if not agent_binary.is_file():
        raise SystemExit(f"micro-ROS Agent is unavailable: {agent_binary}")
    agent_launcher = args.agent_launcher.resolve()
    if not agent_launcher.is_file():
        raise SystemExit(
            f"micro-ROS Agent launcher is unavailable: {agent_launcher}"
        )
    package_query_command = [str(agent_launcher), "list", "micro-ros-agent"]
    package_query_output = subprocess.check_output(
        package_query_command, text=True, stderr=subprocess.STDOUT
    ).strip()
    launch_command = [str(agent_launcher), "run", "micro-ros-agent"]
    schedule_path = output / "randomized_schedule.csv"
    write_schedule(schedule_path, generate_schedule())
    manifest = {
        "schema_version": 1,
        "classification": "three_system_matched_workload_executable_set",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SEALED",
        "source_commits": commits,
        "runtime_peer_ipv4": host_ip,
        "idf": {
            "path": os.environ["IDF_PATH"],
            "version": subprocess.check_output(
                ["idf.py", "--version"], text=True
            ).strip(),
        },
        "systems": systems,
        "host_echo": host,
        "micro_ros_agent": {
            "artifact": file_record(agent_binary),
            "launcher": file_record(agent_launcher),
            "launch_command": launch_command,
            "package_query_command": package_query_command,
            "package_query_output": package_query_output,
            "transport": "udp4",
            "port": 7408,
        },
        "schedule": {
            **file_record(schedule_path, output),
            "seed": 202607153,
            "superblocks": 10,
            "accepted_runs_per_visit": 10,
            "total_accepted_runs": 300,
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[sealed] {manifest_path}")
    for system, record in systems.items():
        print(
            f"[hash] {system} firmware="
            f"{record['artifacts']['firmware']['sha256']}"
        )
    print(f"[hash] host={host['artifact']['sha256']}")


if __name__ == "__main__":
    main()
