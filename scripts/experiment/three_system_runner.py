#!/usr/bin/env python3
"""Hardware execution primitives shared by three-system smoke and formal runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

import serial

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from three_system_common import (
    file_record,
    parse_compare_serial,
    resolve_record,
    sha256_file,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def command_output(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def network_snapshot(interface: str, board_ip: str) -> dict[str, Any]:
    ping = subprocess.run(
        ["ping", "-c", "3", "-W", "1", board_ip],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    qdisc = command_output(
        ["sudo", "-n", "tc", "qdisc", "show", "dev", interface]
    )
    filters = command_output(
        ["sudo", "-n", "tc", "filter", "show", "dev", interface, "ingress"]
    )
    return {
        "captured_at_utc": utc_now(),
        "interface": interface,
        "board_ip": board_ip,
        "ping_returncode": ping.returncode,
        "ping_output": ping.stdout,
        "qdisc": qdisc,
        "ingress_filters": filters,
        "neighbor": command_output(["ip", "neigh", "show", board_ip]),
    }


def impairment_reasons(snapshot: dict[str, Any]) -> list[str]:
    reasons = []
    qdisc = snapshot["qdisc"]
    if "netem" in qdisc or "clsact" in qdisc:
        reasons.append("stale_qdisc")
    if snapshot["ingress_filters"].strip():
        reasons.append("stale_ingress_filter")
    return reasons


def wait_for_board(board_ip: str, timeout_seconds: int = 210) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        completed = subprocess.run(
            ["ping", "-c", "1", "-W", "1", board_ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError(
        f"board {board_ip} did not become reachable within {timeout_seconds}s"
    )


def flash_system(
    project_root: Path,
    set_root: Path,
    system_record: dict[str, Any],
    serial_port: str,
    baud: int,
    output_dir: Path,
) -> dict[str, Any]:
    artifacts = system_record["artifacts"]
    firmware = resolve_record(set_root, artifacts["firmware"])
    bootloader = resolve_record(set_root, artifacts["bootloader"])
    partition = resolve_record(set_root, artifacts["partition_table"])
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        raise RuntimeError("IDF_PATH is unavailable")
    esptool = Path(idf_path) / "components/esptool_py/esptool/esptool.py"
    command = [
        sys.executable,
        str(esptool),
        "--chip",
        "esp32s3",
        "-p",
        serial_port,
        "-b",
        str(baud),
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
        str(bootloader),
        "0x8000",
        str(partition),
        "0x10000",
        str(firmware),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "flash.log"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if completed.returncode != 0 or text.count("Hash of data verified.") < 3:
        raise RuntimeError(f"flash verification failed: {log_path}")
    return {
        "created_at_utc": utc_now(),
        "command": command,
        "log": file_record(log_path),
        "firmware_sha256": artifacts["firmware"]["sha256"],
        "bootloader_sha256": artifacts["bootloader"]["sha256"],
        "partition_table_sha256": artifacts["partition_table"]["sha256"],
    }


class VisitProcesses:
    def __init__(
        self,
        system: str,
        host_binary: Path,
        agent_command: list[str],
        visit_dir: Path,
    ):
        self.system = system
        self.host_binary = host_binary
        self.agent_command = list(agent_command)
        self.visit_dir = visit_dir
        self.processes: dict[str, subprocess.Popen] = {}
        self.logs = {}

    def _start(self, name: str, command: list[str]):
        path = self.visit_dir / f"{name}.log"
        handle = path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
            start_new_session=True,
        )
        self.processes[name] = process
        self.logs[name] = (path, handle, command)

    def __enter__(self):
        if self.system == "microros":
            self._start(
                "agent",
                [*self.agent_command, "udp4", "--port", "7408", "-v", "4"],
            )
        self._start(
            "host",
            [
                str(self.host_binary),
                "--best-effort",
                "--topic-base",
                "/system_compare",
            ],
        )
        time.sleep(5)
        dead = [name for name, process in self.processes.items() if process.poll() is not None]
        if dead:
            self.stop()
            raise RuntimeError(f"visit process failed during startup: {dead}")
        return self

    def alive_reasons(self) -> list[str]:
        return [
            f"process_exited:{name}:{process.returncode}"
            for name, process in self.processes.items()
            if process.poll() is not None
        ]

    def stop(self):
        cleanup_errors = []
        for process in self.processes.values():
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        for name, process in self.processes.items():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cleanup_errors.append(f"{name}:did_not_exit_after_sigkill")
        for _, handle, _ in self.logs.values():
            handle.close()
        if cleanup_errors:
            raise RuntimeError("process cleanup failed: " + ",".join(cleanup_errors))

    def evidence(self) -> dict[str, Any]:
        evidence = {}
        for name, (path, _, command) in self.logs.items():
            if path.is_file():
                evidence[name] = {
                    "command": command,
                    "exit_code": self.processes[name].returncode,
                    "log": file_record(path),
                }
        return evidence

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()


def pcap_stats(pcap_path: Path, board_ip: str) -> dict[str, int]:
    completed = subprocess.run(
        [
            "tshark",
            "-n",
            "-r",
            str(pcap_path),
            "-Y",
            f"udp && ip.src == {board_ip}",
            "-T",
            "fields",
            "-e",
            "frame.len",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return {"board_udp_packets": 0, "board_udp_bytes": 0, "tshark_rc": completed.returncode}
    lengths = [
        int(line)
        for line in completed.stdout.splitlines()
        if line.strip().isdigit()
    ]
    return {
        "board_udp_packets": len(lengths),
        "board_udp_bytes": sum(lengths),
        "tshark_rc": 0,
    }


def capture_serial_run(
    system: str,
    serial_port: str,
    board_ip: str,
    interface: str,
    attempt_dir: Path,
    timeout_seconds: int = 220,
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    serial_path = attempt_dir / "serial.log"
    pcap_path = attempt_dir / "capture.pcapng"
    capture_log_path = attempt_dir / "capture.log"
    capture_handle = capture_log_path.open("w", encoding="utf-8")
    capture = subprocess.Popen(
        [
            "tshark",
            "-i",
            interface,
            "-a",
            f"duration:{timeout_seconds + 20}",
            "-w",
            str(pcap_path),
        ],
        stdout=capture_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(0.5)
    chunks: list[bytes] = []
    line_buffer = ""
    reset_to_ready_ms = None
    final_seen = False
    reset_monotonic = None
    serial_error = None
    started_at_utc = utc_now()
    try:
        with serial.Serial(serial_port, 115200, timeout=0.2) as handle:
            handle.reset_input_buffer()
            handle.dtr = False
            handle.rts = True
            time.sleep(0.15)
            handle.rts = False
            reset_monotonic = time.monotonic()
            deadline = reset_monotonic + timeout_seconds
            final_deadline = None
            while time.monotonic() < deadline:
                data = handle.read(4096)
                now = time.monotonic()
                if data:
                    chunks.append(data)
                    line_buffer += data.decode("utf-8", "replace")
                    lines = line_buffer.split("\n")
                    line_buffer = lines.pop()
                    for line in lines:
                        if (
                            reset_to_ready_ms is None
                            and f"COMPARE_READY system={system}" in line
                        ):
                            reset_to_ready_ms = int((now - reset_monotonic) * 1000)
                        if f"COMPARE_FINAL system={system}" in line:
                            final_seen = True
                            final_deadline = now + 1.0
                if final_deadline is not None and now >= final_deadline:
                    break
    except Exception as exc:  # Preserve failed hardware attempts for audit.
        serial_error = f"{type(exc).__name__}: {exc}"
    finally:
        if capture.poll() is None:
            capture.send_signal(signal.SIGINT)
        try:
            capture.wait(timeout=15)
        except subprocess.TimeoutExpired:
            capture.kill()
            capture.wait()
        capture_handle.close()

    serial_text = b"".join(chunks).decode("utf-8", "replace")
    serial_path.write_text(serial_text, encoding="utf-8", errors="replace")
    parsed = parse_compare_serial(serial_text, system)
    stats = (
        pcap_stats(pcap_path, board_ip)
        if pcap_path.is_file() and pcap_path.stat().st_size > 0
        else {"board_udp_packets": 0, "board_udp_bytes": 0, "tshark_rc": -1}
    )
    return {
        "started_at_utc": started_at_utc,
        "completed_at_utc": utc_now(),
        "reset_method": "serial_rts_hardware_reset",
        "serial_error": serial_error,
        "final_seen": final_seen,
        "reset_to_ready_ms": reset_to_ready_ms,
        "serial": file_record(serial_path),
        "pcap": file_record(pcap_path) if pcap_path.is_file() else None,
        "capture_log": file_record(capture_log_path),
        "pcap_stats": stats,
        "protocol": parsed,
    }


def evaluate_attempt(
    run: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    process_reasons: list[str],
) -> list[str]:
    reasons = list(run["protocol"]["errors"])
    reasons.extend(impairment_reasons(before))
    reasons.extend(impairment_reasons(after))
    reasons.extend(process_reasons)
    if not run["final_seen"]:
        reasons.append("final_not_observed")
    if run["serial_error"]:
        reasons.append("serial_capture_error")
    if run["reset_to_ready_ms"] is None:
        reasons.append("runner_ready_timestamp_missing")
    if not run["pcap"]:
        reasons.append("pcap_missing")
    elif run["pcap_stats"]["board_udp_packets"] <= 0:
        reasons.append("pcap_no_board_udp")
    if run["pcap_stats"]["tshark_rc"] != 0:
        reasons.append("pcap_parse_failed")
    return sorted(set(reasons))
