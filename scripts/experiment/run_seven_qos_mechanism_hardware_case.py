#!/usr/bin/env python3
"""Build, execute, capture, and validate one deterministic hardware case."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

from seven_qos_mechanism_hardware_cases import get_case


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO / "workspace/seven_qos_mechanisms"
CAPTURE = REPO / "scripts/experiment/capture_benchmark_telemetry_smoke.py"
BOARD_VALIDATOR = (
    REPO / "scripts/experiment/validate_seven_qos_mechanism_board_log.py"
)
HOST_PROBE = REPO / "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/qos_compatibility_probe"
HOST_PROFILE = REPO / "tools/echo_cpp/config/seven_qos_esp32_initial_peer.xml"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CRASH_MARKERS = ("Guru Meditation", "abort()", "LoadProhibited", "StoreProhibited")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_logged(command: list[str], log: Path, *, cwd: Path | None = None) -> None:
    with log.open("wb") as handle:
        result = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {shlex.join(command)}")


def idf_shell(arguments: list[str]) -> list[str]:
    body = (
        "set -euo pipefail; "
        "source ${IDF_PATH:?Set_IDF_PATH}/export.sh >/dev/null 2>&1; "
        f"cd {shlex.quote(str(WORKSPACE))}; "
        f"exec idf.py {shlex.join(arguments)}"
    )
    return ["bash", "-lc", body]


def build_and_flash(
    config: dict[str, Any], output: Path, port: str, build_dir: str,
    host_probe: Path, host_profile: Path,
) -> None:
    cmake = [
        "-B", build_dir,
        f"-DMROS2_MECHANISM_CASE_ID={config['case_id']}",
        f"-DMROS2_MECHANISM_KIND={config['kind']}",
        f"-DMROS2_MECHANISM_PAYLOAD_BYTES={config['payload']}",
        f"-DMROS2_MECHANISM_TIMEOUT_MS={config['timeout_ms']}",
        f"-DMROS2_RTPS_HISTORY_CAPACITY={config['capacity']}",
        "-DMROS2_RTPS_HEARTBEAT_PERIOD_MS=100",
        "-DMROS2_QOS_MONITOR_PERIOD_MS=5",
        "-DCCACHE_ENABLE=0",
    ]
    run_logged(idf_shell(cmake + ["build"]), output / "build.log")
    build = WORKSPACE / build_dir
    artifacts = output / "artifacts"
    artifacts.mkdir()
    artifact_sources = {
        "firmware.bin": build / "seven_qos_mechanisms.bin",
        "firmware.elf": build / "seven_qos_mechanisms.elf",
        "firmware.map": build / "seven_qos_mechanisms.map",
        "sdkconfig": WORKSPACE / "sdkconfig",
        "app.cpp": WORKSPACE / "main/app.cpp",
        "host_probe": host_probe,
        "initial_peer.xml": host_profile,
    }
    manifest: dict[str, dict[str, Any]] = {}
    for name, source in artifact_sources.items():
        if not source.is_file():
            raise RuntimeError(f"missing build artifact: {source}")
        destination = artifacts / name
        shutil.copy2(source, destination)
        manifest[name] = {"bytes": destination.stat().st_size, "sha256": sha256(destination)}
    write_json(output / "artifact_manifest.json", manifest)
    run_logged(
        idf_shell(["-B", build_dir, "-p", port, "flash"]),
        output / "flash.log",
    )


def load_frozen_bundle(bundle_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    manifest_path = bundle_dir / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "seven_qos_mechanism_frozen_flash_bundle":
        raise ValueError("unexpected frozen bundle classification")
    if manifest.get("case_id") != config["case_id"]:
        raise ValueError("frozen bundle case ID mismatch")
    if manifest.get("case_config_sha256") != canonical_sha256(config):
        raise ValueError("frozen bundle case configuration mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("frozen bundle has no file inventory")
    for relative, record in files.items():
        path = (bundle_dir / relative).resolve()
        if not path.is_relative_to(bundle_dir.resolve()):
            raise ValueError("frozen bundle path escapes its root")
        if not path.is_file():
            raise ValueError(f"missing frozen bundle file: {relative}")
        if path.stat().st_size != record.get("bytes"):
            raise ValueError(f"frozen bundle size mismatch: {relative}")
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"frozen bundle SHA-256 mismatch: {relative}")
    return manifest


def frozen_flash_command(
    idf_export: Path, port: str, bundle_dir: Path, manifest: dict[str, Any]
) -> list[str]:
    flash = manifest["flash"]
    arguments = [
        "python", "-m", "esptool", "--chip", flash["chip"],
        "--port", port, "--baud", str(flash["baud"]),
        "--before", flash["before"], "--after", flash["after"],
        "write_flash", *flash["write_flash_args"],
    ]
    for item in flash["flash_files"]:
        path = (bundle_dir / item["relative_path"]).resolve()
        if not path.is_relative_to(bundle_dir.resolve()):
            raise ValueError("frozen flash path escapes its root")
        arguments.extend((item["offset"], str(path)))
    body = (
        f"source {shlex.quote(str(idf_export))} >/dev/null 2>&1 && "
        f"exec {shlex.join(arguments)}"
    )
    return ["bash", "-lc", body]


def flash_frozen_bundle(
    config: dict[str, Any], output: Path, port: str, bundle_dir: Path,
    manifest: dict[str, Any], idf_export: Path, host_probe: Path,
    host_profile: Path,
) -> None:
    artifacts = output / "artifacts"
    artifacts.mkdir()
    shutil.copy2(
        bundle_dir / "artifact_manifest.json",
        artifacts / "frozen_artifact_manifest.json",
    )
    app_relative = manifest["app_relative_path"]
    shutil.copy2(bundle_dir / app_relative, artifacts / "firmware.bin")
    shutil.copy2(host_probe, artifacts / "host_probe")
    shutil.copy2(host_profile, artifacts / "initial_peer.xml")
    inventory = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(artifacts.iterdir())
        if path.is_file()
    }
    write_json(output / "artifact_manifest.json", inventory)
    run_logged(
        frozen_flash_command(idf_export, port, bundle_dir, manifest),
        output / "flash.log",
    )


def capture_command(output: Path, port: str, timeout: int, terminal: str = "MECH_BOARD_FINAL") -> list[str]:
    return [
        sys.executable,
        str(CAPTURE),
        "--port", port,
        "--timeout", str(timeout),
        "--terminal-prefix", terminal,
        "--output", str(output),
    ]


def host_command(
    case_id: str,
    config: dict[str, Any],
    host_probe: Path,
    host_profile: Path,
    *,
    publish_gate: Path | None = None,
) -> list[str]:
    options = [
        str(host_probe),
        "--case-id", case_id,
        "--role", config["role"],
        "--topic", "/seven_qos_mechanism",
        "--reliability", config["reliability"],
        "--durability", config["durability"],
        "--deadline-ms", config["deadline_ms"],
        "--liveliness-lease-ms", config["liveliness_lease_ms"],
        "--expected-match", "1",
        "--wait-ms", "60000",
        "--pre-publish-ms", str(config["pre_publish_ms"]),
        "--post-match-ms", str(config["post_match_ms"]),
        "--message-count", str(config["message_count"]),
        "--period-ms", str(config["period_ms"]),
    ]
    if config["expected_rx"] is not None:
        options += ["--expected-rx-count", str(config["expected_rx"])]
    if publish_gate is not None:
        options += ["--publish-gate", str(publish_gate)]
    timeout = max(70, (config["post_match_ms"] + config["pre_publish_ms"]) // 1000 + 30)
    body = (
        "set +u; source /opt/ros/humble/setup.bash; "
        "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp; "
        f"export FASTRTPS_DEFAULT_PROFILES_FILE={shlex.quote(str(host_profile))}; "
        f"exec timeout {timeout} {shlex.join(options)}"
    )
    return ["bash", "-lc", body]


def start_logged(command: list[str], log: Path) -> tuple[subprocess.Popen[bytes], Any]:
    handle = log.open("wb")
    process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
    return process, handle


def wait_process(process: subprocess.Popen[bytes], handle: Any, name: str) -> int:
    rc = process.wait()
    handle.close()
    if rc != 0:
        raise RuntimeError(f"{name} failed rc={rc}")
    return rc


def wait_for_text(path: Path, text: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and text in path.read_text(encoding="utf-8", errors="replace"):
            return
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {text!r} in {path}")


def start_pcap(path: Path, interface: str) -> tuple[subprocess.Popen[bytes], Any]:
    handle = (path.parent / "dumpcap.log").open("wb")
    process = subprocess.Popen(
        ["dumpcap", "-q", "-i", interface, "-f", "udp", "-w", str(path)],
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    time.sleep(0.5)
    if process.poll() is not None:
        handle.close()
        raise RuntimeError("dumpcap failed to start")
    return process, handle


def stop_pcap(process: subprocess.Popen[bytes], handle: Any) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
    handle.close()


def qdisc_state(interface: str) -> str:
    result = subprocess.run(
        ["sudo", "-n", "tc", "qdisc", "show", "dev", interface],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def set_netem(interface: str, mode: str) -> None:
    subprocess.run(
        ["sudo", "-n", "tc", "qdisc", "replace", "dev", interface, "root", "netem"]
        + mode.split(),
        check=True,
    )


def change_netem(interface: str, mode: str) -> None:
    subprocess.run(
        ["sudo", "-n", "tc", "qdisc", "change", "dev", interface, "root", "netem"]
        + mode.split(),
        check=True,
    )


def clear_netem(interface: str) -> None:
    subprocess.run(
        ["sudo", "-n", "tc", "qdisc", "del", "dev", interface, "root"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def validate_qdisc_restoration(before: str, after: str) -> dict[str, Any]:
    errors: list[str] = []
    if after != before:
        errors.append("qdisc state differs after impairment cleanup")
    if "netem" in after or "ingress" in after or "clsact" in after:
        errors.append("impairment qdisc remains after cleanup")
    return {
        "schema_version": 1,
        "classification": "qdisc_restoration_validation",
        "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }


def parse_marker(line: str, prefix: str) -> dict[str, str] | None:
    if not line.startswith(prefix + " "):
        return None
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    return fields


def validate_host_log(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    finals = [
        marker for line in text.splitlines()
        if (marker := parse_marker(line, "QOS_HOST_FINAL")) is not None
    ]
    receives = [
        marker for line in text.splitlines()
        if (marker := parse_marker(line, "QOS_HOST_RX")) is not None
    ]
    errors: list[str] = []
    if len(finals) != 1 or finals[0].get("status") != "PASS":
        errors.append(f"expected one passing host final, found={finals}")
    expected_rx = config["expected_rx"]
    if expected_rx is not None and len(receives) != expected_rx:
        errors.append(f"host rx markers={len(receives)}, expected={expected_rx}")
    expected_first = config["expected_first_bytes"]
    if expected_first is not None:
        observed = [int(marker.get("first", "-1")) for marker in receives]
        if observed != expected_first:
            errors.append(f"host first bytes={observed}, expected={expected_first}")
    expected_bytes = config["expected_message_bytes"]
    if expected_bytes is not None:
        observed = [int(marker.get("bytes", "-1")) for marker in receives]
        if observed != [expected_bytes] * len(receives):
            errors.append(f"host message bytes={observed}, expected={expected_bytes}")
    return {
        "final": finals[0] if len(finals) == 1 else {},
        "receives": receives,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }


def run_attempt(
    config: dict[str, Any], output: Path, port: str, interface: str,
    host_probe: Path, host_profile: Path,
) -> dict[str, Any]:
    pcap_process: subprocess.Popen[bytes] | None = None
    pcap_handle: Any = None
    capture_process: subprocess.Popen[bytes] | None = None
    capture_handle: Any = None
    host_processes: list[tuple[subprocess.Popen[bytes], Any, str]] = []
    netem_active = False
    process_status: dict[str, int] = {}
    host_reports: list[dict[str, Any]] = []
    baseline: str | None = None
    phase1_epoch: int | None = None
    try:
        baseline = qdisc_state(interface)
        (output / "qdisc_before.txt").write_text(baseline + "\n", encoding="utf-8")
        if "netem" in baseline or "ingress" in baseline or "clsact" in baseline:
            raise RuntimeError(f"unexpected pre-existing impairment: {baseline}")
        pcap_process, pcap_handle = start_pcap(output / "capture.pcapng", interface)

        if config["orchestration"] == "reset_board_then_late_join":
            phase, phase_handle = start_logged(
                capture_command(output / "phase1_serial.raw", port, 20, "MECH_BOARD_PHASE"),
                output / "phase1_capture.log",
            )
            wait_process(phase, phase_handle, "phase1 capture")
            phase1_text = ANSI.sub(
                "", (output / "phase1_serial.raw").read_bytes().decode(
                    "utf-8", errors="replace"
                )
            )
            phase1_configs = [
                marker for line in phase1_text.splitlines()
                if (marker := parse_marker(line, "MECH_BOARD_CONFIG")) is not None
            ]
            if len(phase1_configs) != 1:
                raise RuntimeError(
                    f"expected one phase1 config marker, found={phase1_configs}"
                )
            phase1_epoch = int(phase1_configs[0]["boot_epoch"])

        capture_timeout = 80 if config["timeout_ms"] > 20000 else 45
        capture_process, capture_handle = start_logged(
            capture_command(output / "serial.raw", port, capture_timeout),
            output / "capture.log",
        )
        host_config = config["host"]
        if host_config is not None:
            time.sleep(host_config["start_delay_ms"] / 1000)
            gate = None
            if config["orchestration"] in {
                "duplicate_user_data", "delay_first_user_data"
            }:
                gate = output / "publish.gate"
            host1_log = output / "host.log"
            host1, host1_handle = start_logged(
                host_command(
                    config["case_id"], host_config, host_probe, host_profile,
                    publish_gate=gate,
                ),
                host1_log,
            )
            host_processes.append((host1, host1_handle, "host"))

            if gate is not None:
                wait_for_text(host1_log, "QOS_HOST_MATCHED ", 30)
                time.sleep(host_config["pre_publish_ms"] / 1000 + 0.2)
                mode = (
                    "duplicate 100%"
                    if config["orchestration"] == "duplicate_user_data"
                    else "delay 300ms limit 1000"
                )
                set_netem(interface, mode)
                netem_active = True
                (output / "qdisc_active.txt").write_text(qdisc_state(interface) + "\n", encoding="utf-8")
                gate.touch()
                if config["orchestration"] == "delay_first_user_data":
                    time.sleep(0.05)
                    change_netem(interface, "delay 0ms limit 1000")
                    (output / "qdisc_release.txt").write_text(
                        qdisc_state(interface) + "\n", encoding="utf-8"
                    )
                    time.sleep(0.35)
                else:
                    time.sleep(0.30)
                clear_netem(interface)
                netem_active = False

            if config["orchestration"] in {"restart_host_writer", "restart_host_after_loss"}:
                process_status["host1"] = wait_process(host1, host1_handle, "host1")
                host_processes.clear()
                second_log = output / "host2.log"
                second, second_handle = start_logged(
                    host_command(
                        config["case_id"] + "-SECOND", host_config,
                        host_probe, host_profile,
                    ),
                    second_log,
                )
                host_processes.append((second, second_handle, "host2"))

        if capture_process is None or capture_handle is None:
            raise RuntimeError("capture was not started")
        process_status["capture"] = wait_process(capture_process, capture_handle, "capture")
        capture_process = None
        capture_handle = None
        for process, handle, name in host_processes:
            process_status[name] = wait_process(process, handle, name)
        host_processes.clear()
    finally:
        if netem_active:
            clear_netem(interface)
        if capture_process is not None and capture_process.poll() is None:
            capture_process.terminate()
            capture_process.wait(timeout=5)
        if capture_handle is not None:
            capture_handle.close()
        for process, handle, _ in host_processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            handle.close()
        if pcap_process is not None:
            stop_pcap(pcap_process, pcap_handle)
        after = qdisc_state(interface)
        (output / "qdisc_after.txt").write_text(after + "\n", encoding="utf-8")
        if baseline is not None:
            qdisc_report = validate_qdisc_restoration(baseline, after)
            write_json(output / "qdisc_validation.json", qdisc_report)
            if qdisc_report["status"] != "PASS":
                raise RuntimeError(f"qdisc restoration failed: {qdisc_report['errors']}")

    raw = (output / "serial.raw").read_bytes().decode("utf-8", errors="replace")
    serial = ANSI.sub("", raw)
    (output / "serial.log").write_text(serial, encoding="utf-8")
    markers = "\n".join(line for line in serial.splitlines() if line.startswith("MECH_BOARD_")) + "\n"
    (output / "markers.log").write_text(markers, encoding="utf-8")
    for marker in CRASH_MARKERS:
        if marker.lower() in serial.lower():
            raise RuntimeError(f"crash marker present: {marker}")

    board_validation = output / "board_validation.json"
    run_logged(
        [
            sys.executable, str(BOARD_VALIDATOR),
            "--serial-log", str(output / "serial.log"),
            "--case-id", config["case_id"],
            "--kind", config["kind"],
            "--sample-limit", "5",
            "--output", str(board_validation),
        ],
        output / "board_validation.log",
    )

    if config["host"] is not None:
        for name in ("host.log", "host2.log"):
            path = output / name
            if path.exists():
                host_reports.append(validate_host_log(path, config["host"]))
        for report in host_reports:
            if report["status"] != "PASS":
                raise RuntimeError(f"host validation failed: {report['errors']}")

    if config["orchestration"] == "reset_board_then_late_join":
        board_config = next(
            parse_marker(line, "MECH_BOARD_CONFIG")
            for line in markers.splitlines()
            if line.startswith("MECH_BOARD_CONFIG ")
        )
        epoch = int(board_config["boot_epoch"])
        epoch_errors: list[str] = []
        if phase1_epoch is None or epoch != phase1_epoch + 1:
            epoch_errors.append(
                f"boot epoch transition phase1={phase1_epoch}, phase2={epoch}"
            )
        epoch_report = {
            "schema_version": 1,
            "classification": "mechanism_boot_epoch_validation",
            "phase1_epoch": phase1_epoch,
            "phase2_epoch": epoch,
            "errors": epoch_errors,
            "status": "PASS" if not epoch_errors else "FAIL",
        }
        write_json(output / "epoch_validation.json", epoch_report)
        if epoch_errors:
            raise RuntimeError(f"boot epoch validation failed: {epoch_errors}")
        expected = [65 + ((epoch * 5 + index) % 26) for index in (2, 3, 4)]
        observed = [int(item["first"]) for item in host_reports[0]["receives"]]
        if observed != expected:
            raise RuntimeError(f"epoch replay bytes={observed}, expected={expected}")

    if not (output / "capture.pcapng").is_file() or (output / "capture.pcapng").stat().st_size <= 24:
        raise RuntimeError("PCAP is missing or empty")
    write_json(output / "process_status.json", process_status)
    write_json(output / "host_validation.json", host_reports)
    return {"process_status": process_status, "host_validation": host_reports}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--build-dir", default="build_mechanism_case_runner_s3")
    parser.add_argument("--host-probe", type=Path, default=HOST_PROBE)
    parser.add_argument("--profile", type=Path, default=HOST_PROFILE)
    parser.add_argument("--frozen-artifacts", type=Path)
    parser.add_argument(
        "--idf-export", type=Path,
        default=Path.home() / "esp-idf/export.sh",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = get_case(args.case_id)
    host_probe = args.host_probe.resolve()
    host_profile = args.profile.resolve()
    frozen_dir = args.frozen_artifacts.resolve() if args.frozen_artifacts else None
    frozen_manifest = (
        load_frozen_bundle(frozen_dir, config) if frozen_dir is not None else None
    )
    if args.dry_run:
        print(json.dumps({
            **config,
            "execution_mode": (
                "frozen_artifacts" if frozen_manifest else "build_from_source"
            ),
        }, indent=2, sort_keys=True))
        return 0
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output already exists: {output}")
    output.mkdir(parents=True)
    write_json(output / "case_config.json", config)
    started = utc_now()
    status = "FAIL"
    error = None
    try:
        if frozen_manifest is None:
            build_and_flash(
                config, output, args.serial_port, args.build_dir,
                host_probe, host_profile,
            )
        else:
            flash_frozen_bundle(
                config, output, args.serial_port, frozen_dir,
                frozen_manifest, args.idf_export.resolve(), host_probe,
                host_profile,
            )
        run_attempt(
            config, output, args.serial_port, args.interface,
            host_probe, host_profile,
        )
        status = "PASS"
        return_code = 0
    except Exception as exception:
        error = str(exception)
        print(f"MECHANISM_CASE_ERROR case_id={args.case_id} error={error}", file=sys.stderr)
        return_code = 1
    finally:
        write_json(
            output / "run_metadata.json",
            {
                "schema_version": 1,
                "classification": "seven_qos_mechanism_hardware_attempt",
                "case_id": args.case_id,
                "started_utc": started,
                "finished_utc": utc_now(),
                "status": status,
                "error": error,
                "execution_mode": (
                    "frozen_artifacts" if frozen_manifest else "build_from_source"
                ),
                "frozen_bundle_manifest_sha256": (
                    sha256(frozen_dir / "artifact_manifest.json")
                    if frozen_manifest else None
                ),
                "runner_sha256": sha256(Path(__file__)),
            },
        )
    print(f"MECHANISM_CASE case_id={args.case_id} status={status}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
