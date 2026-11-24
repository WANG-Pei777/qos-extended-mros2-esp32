#!/usr/bin/env python3
"""Run an excluded single-host UDP native ROS 2 RTT baseline pilot."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_BIN_DIR = REPO / "tools/echo_cpp/build/echo_cpp"
DEFAULT_PROFILE = REPO / "scripts/experiment/fastdds_udp_mtu_1200.xml"
RUN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
FINAL_PREFIX = "NATIVE_FINAL "
SAMPLE_PREFIX = "NATIVE_RTT_SAMPLE "


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stop_process(process: subprocess.Popen[Any] | None) -> None:
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


def parse_record(line: str, prefix: str) -> dict[str, str]:
    if not line.startswith(prefix):
        raise ValueError(f"record does not start with {prefix.strip()}")
    fields: dict[str, str] = {}
    for token in line[len(prefix):].split():
        if "=" not in token:
            raise ValueError(f"malformed token in {prefix.strip()}: {token}")
        key, value = token.split("=", 1)
        if not key or key in fields:
            raise ValueError(f"invalid or duplicate field: {key}")
        fields[key] = value
    return fields


def validate_probe_output(
    text: str,
    *,
    run_token: str,
    qos: str,
    durability: str,
    history_depth: int,
    payload_bytes: int,
    rate_hz: int,
    target_tx: int,
) -> dict[str, Any]:
    final_lines = [
        line.strip() for line in text.splitlines()
        if line.startswith(FINAL_PREFIX)
    ]
    if len(final_lines) != 1:
        raise ValueError(f"expected one NATIVE_FINAL record, found {len(final_lines)}")
    final = parse_record(final_lines[0], FINAL_PREFIX)
    expected = {
        "schema": "1",
        "run_token": run_token,
        "qos": qos,
        "durability": durability.upper(),
        "history": "KEEP_LAST",
        "depth": str(history_depth),
        "payload_bytes": str(payload_bytes),
        "rate_hz": str(rate_hz),
        "target_tx": str(target_tx),
        "tx": str(target_tx),
    }
    for key, value in expected.items():
        if final.get(key) != value:
            raise ValueError(f"NATIVE_FINAL {key}={final.get(key)!r}, expected {value!r}")

    numeric = {
        key: int(final[key])
        for key in (
            "rx", "missing", "duplicates", "malformed", "arrival_inversions",
            "min_us", "avg_us", "p95_us", "max_us", "rtt_sum_us", "ready_ms",
        )
    }
    if numeric["rx"] < 0 or numeric["rx"] > target_tx:
        raise ValueError("RX is outside 0..target_tx")
    if numeric["missing"] != target_tx - numeric["rx"]:
        raise ValueError("missing count does not reconcile with RX")
    if numeric["malformed"] != 0:
        raise ValueError("native probe reported malformed replies")
    if numeric["rx"] > 0:
        if not 0 < numeric["min_us"] <= numeric["avg_us"] <= numeric["max_us"]:
            raise ValueError("RTT min/average/max are inconsistent")
        if not numeric["min_us"] <= numeric["p95_us"] <= numeric["max_us"]:
            raise ValueError("RTT p95 is outside min/max")
    samples = [
        parse_record(line.strip(), SAMPLE_PREFIX)
        for line in text.splitlines() if line.startswith(SAMPLE_PREFIX)
    ]
    if len(samples) != numeric["rx"]:
        raise ValueError("per-message RTT count does not match RX")
    sequences = [int(row["seq"]) for row in samples]
    if len(sequences) != len(set(sequences)):
        raise ValueError("duplicate sequence in RTT sidecar")
    if any(row.get("run_token") != run_token for row in samples):
        raise ValueError("RTT sidecar run token mismatch")
    if sum(int(row["rtt_us"]) for row in samples) != numeric["rtt_sum_us"]:
        raise ValueError("RTT sidecar sum does not match NATIVE_FINAL")
    return {"final": final, "numeric": numeric, "sample_count": len(samples)}


def extract_pcap(
    pcap: Path, output: Path, port_min: int, port_max: int
) -> dict[str, Any]:
    fields = (
        "frame.number", "frame.time_relative", "frame.len", "ip.src", "ip.dst",
        "ip.dsfield.dscp", "udp.srcport", "udp.dstport", "rtps.sm.id",
    )
    command = [
        "tshark", "-r", str(pcap),
        "-Y", f"ip && udp.port >= {port_min} && udp.port <= {port_max}",
        "-T", "fields",
        "-E", "header=y", "-E", "separator=/t", "-E", "occurrence=a",
        "-E", "aggregator=|",
    ]
    for field in fields:
        command.extend(("-e", field))
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    output.write_text(result.stdout, encoding="utf-8")

    rows = [line.split("\t") for line in result.stdout.splitlines()[1:] if line]
    packet_count = len(rows)
    total_bytes = sum(int(row[2]) for row in rows if len(row) > 2 and row[2])
    dscp = Counter(
        value for row in rows if len(row) > 5
        for value in row[5].split("|") if value
    )
    flows = Counter(
        f"{row[3]}:{row[6]}->{row[4]}:{row[7]}"
        for row in rows if len(row) > 7 and all(row[index] for index in (3, 4, 6, 7))
    )
    submessages = Counter(
        value for row in rows if len(row) > 8
        for value in row[8].split("|") if value
    )
    return {
        "packet_count": packet_count,
        "total_frame_bytes": total_bytes,
        "dscp_counts": dict(sorted(dscp.items())),
        "flow_packet_counts": dict(sorted(flows.items())),
        "rtps_submessage_counts": dict(sorted(submessages.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qos", choices=("BEST_EFFORT", "RELIABLE"), required=True)
    parser.add_argument(
        "--durability",
        choices=("volatile", "transient_local"),
        default="volatile",
    )
    parser.add_argument("--history-depth", type=int, default=10)
    parser.add_argument("--payload-bytes", type=int, default=512)
    parser.add_argument("--rate-hz", type=int, default=50)
    parser.add_argument("--target-tx", type=int, default=1000)
    parser.add_argument("--grace-ms", type=int, default=5000)
    parser.add_argument("--run-token", required=True)
    parser.add_argument("--topic-base", default="/native_baseline")
    parser.add_argument("--ros-domain-id", type=int, default=83)
    parser.add_argument("--capture-interface", default="any")
    parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    parser.add_argument("--fastdds-profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not RUN_TOKEN_RE.fullmatch(args.run_token):
        parser.error("--run-token must contain only letters, numbers, dot, underscore, or dash")
    if not 32 <= args.payload_bytes <= 2048:
        parser.error("--payload-bytes must be in 32..2048")
    if args.rate_hz <= 0 or 1000 % args.rate_hz:
        parser.error("--rate-hz must be a positive divisor of 1000")
    if args.target_tx <= 0:
        parser.error("--target-tx must be positive")
    if not 1 <= args.history_depth <= 1000:
        parser.error("--history-depth must be in 1..1000")
    if not 0 <= args.ros_domain_id <= 232:
        parser.error("--ros-domain-id must be in 0..232")
    for command in ("git", "tshark"):
        if shutil.which(command) is None:
            parser.error(f"required command unavailable: {command}")

    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    allowed_root = (REPO / "results/diagnostics").resolve()
    if allowed_root not in output.parents:
        parser.error(f"output must be below {allowed_root}")
    if output.exists():
        parser.error(f"output already exists: {output}")

    echo_binary = (args.bin_dir / "echo_node").resolve()
    probe_binary = (args.bin_dir / "native_rtt_probe").resolve()
    profile = args.fastdds_profile.resolve()
    for path in (echo_binary, probe_binary, profile):
        if not path.is_file():
            parser.error(f"required artifact missing: {path}")

    output.mkdir(parents=True)
    artifacts = output / "artifacts"
    artifacts.mkdir()
    copied = {}
    for source in (echo_binary, probe_binary, profile):
        target = artifacts / source.name
        shutil.copy2(source, target)
        copied[source.name] = {"path": str(target.relative_to(output)), "sha256": sha256(target)}

    qos_flag = "--reliable" if args.qos == "RELIABLE" else "--best-effort"
    durability_flag = (
        "--transient-local"
        if args.durability == "transient_local"
        else "--volatile"
    )
    echo_command = [
        str(artifacts / echo_binary.name),
        qos_flag,
        durability_flag,
        "--history-depth",
        str(args.history_depth),
        "--topic-base",
        args.topic_base,
    ]
    probe_command = [
        str(artifacts / probe_binary.name),
        qos_flag,
        durability_flag,
        "--history-depth",
        str(args.history_depth),
        "--payload-bytes", str(args.payload_bytes),
        "--rate-hz", str(args.rate_hz),
        "--target-tx", str(args.target_tx),
        "--grace-ms", str(args.grace_ms),
        "--run-token", args.run_token,
        "--topic-base", args.topic_base,
    ]
    environment = os.environ.copy()
    environment.update({
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "FASTRTPS_DEFAULT_PROFILES_FILE": str(artifacts / profile.name),
        "ROS_DOMAIN_ID": str(args.ros_domain_id),
    })
    domain_port_min = 7400 + 250 * args.ros_domain_id
    domain_port_max = domain_port_min + 249
    capture_filter = f"udp portrange {domain_port_min}-{domain_port_max}"

    echo_process: subprocess.Popen[str] | None = None
    capture_process: subprocess.Popen[bytes] | None = None
    probe_result: subprocess.CompletedProcess[str] | None = None
    errors: list[str] = []
    started_at = datetime.now(timezone.utc).isoformat()
    pcap = output / "traffic.pcapng"
    capture_fd, capture_name = tempfile.mkstemp(
        prefix="mros2_native_rtt_",
        suffix=".pcapng",
        dir="/tmp",
    )
    os.close(capture_fd)
    capture_temp = Path(capture_name)
    capture_temp.chmod(0o666)
    with (output / "echo_stdout.log").open("w", encoding="utf-8") as echo_stdout, (
        output / "echo_stderr.log"
    ).open("w", encoding="utf-8") as echo_stderr, (
        output / "tshark.log"
    ).open("wb") as capture_log:
        try:
            capture_process = subprocess.Popen(
                [
                    "tshark", "-i", args.capture_interface, "-f", capture_filter,
                    "-w", str(capture_temp),
                ],
                stdout=capture_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            echo_process = subprocess.Popen(
                echo_command,
                stdout=echo_stdout,
                stderr=echo_stderr,
                text=True,
                env=environment,
                start_new_session=True,
            )
            time.sleep(1.0)
            probe_result = subprocess.run(
                probe_command,
                capture_output=True,
                text=True,
                env=environment,
                timeout=120,
                check=False,
            )
        except Exception as exception:
            errors.append(str(exception))
        finally:
            stop_process(echo_process)
            stop_process(capture_process)
            if capture_temp.is_file():
                shutil.copy2(capture_temp, pcap)
                capture_temp.unlink()

    probe_stdout = probe_result.stdout if probe_result is not None else ""
    probe_stderr = probe_result.stderr if probe_result is not None else ""
    (output / "probe_stdout.log").write_text(probe_stdout, encoding="utf-8")
    (output / "probe_stderr.log").write_text(probe_stderr, encoding="utf-8")

    validation: dict[str, Any] | None = None
    if probe_result is None:
        errors.append("probe did not run")
    elif probe_result.returncode != 0:
        errors.append(f"probe exited with {probe_result.returncode}")
    else:
        try:
            validation = validate_probe_output(
                probe_stdout,
                run_token=args.run_token,
                qos=args.qos,
                durability=args.durability,
                history_depth=args.history_depth,
                payload_bytes=args.payload_bytes,
                rate_hz=args.rate_hz,
                target_tx=args.target_tx,
            )
        except ValueError as exception:
            errors.append(str(exception))

    pcap_summary: dict[str, Any] | None = None
    if not pcap.is_file() or pcap.stat().st_size == 0:
        errors.append("capture is missing or empty")
    else:
        try:
            pcap_summary = extract_pcap(
                pcap, output / "pcap_packets.tsv",
                domain_port_min, domain_port_max,
            )
        except (OSError, subprocess.CalledProcessError, ValueError) as exception:
            errors.append(f"PCAP extraction failed: {exception}")

    git_read_only = ["git", "-c", f"safe.directory={REPO}"]
    source_commit = subprocess.run(
        [*git_read_only, "rev-parse", "HEAD"], cwd=REPO, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    worktree_status = subprocess.run(
        [*git_read_only, "status", "--short"], cwd=REPO, check=True,
        capture_output=True, text=True,
    ).stdout
    manifest = {
        "schema_version": 1,
        "classification": "native_ros2_single_host_udp_engineering_pilot",
        "evidence_boundary": (
            "excluded engineering pilot; two native processes share one WSL host; "
            "not a two-physical-host network baseline and never formal comparison data"
        ),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "worktree_clean": not bool(worktree_status.strip()),
        "worktree_status": worktree_status.splitlines(),
        "transport": {
            "rmw": environment["RMW_IMPLEMENTATION"],
            "profile": copied[profile.name],
            "builtin_transports_disabled": True,
            "capture_interface": args.capture_interface,
            "capture_filter": capture_filter,
            "domain_port_min": domain_port_min,
            "domain_port_max": domain_port_max,
            "ros_domain_id": args.ros_domain_id,
            "host_topology": "single_wsl_host_two_processes",
            "impairment": "clean",
        },
        "workload": {
            "qos": args.qos,
            "durability": args.durability,
            "history": "keep_last",
            "history_depth": args.history_depth,
            "payload_bytes": args.payload_bytes,
            "rate_hz": args.rate_hz,
            "target_tx": args.target_tx,
            "grace_ms": args.grace_ms,
            "run_token": args.run_token,
            "topic_base": args.topic_base,
        },
        "commands": {"echo": echo_command, "probe": probe_command},
        "return_codes": {
            "probe": probe_result.returncode if probe_result is not None else None,
            "echo": echo_process.returncode if echo_process is not None else None,
            "capture": capture_process.returncode if capture_process is not None else None,
        },
        "artifacts": copied,
        "probe_validation": validation,
        "pcap": {
            "path": "traffic.pcapng" if pcap.is_file() else None,
            "bytes": pcap.stat().st_size if pcap.is_file() else None,
            "sha256": sha256(pcap) if pcap.is_file() else None,
            "packet_table": "pcap_packets.tsv" if (output / "pcap_packets.tsv").is_file() else None,
            "summary": pcap_summary,
        },
    }
    (output / "pilot_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": manifest["status"], "output": str(output), "errors": errors}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
