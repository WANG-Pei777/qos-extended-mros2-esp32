#!/usr/bin/env python3
"""Run the complete P4 collection, analysis, and release pipeline."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


def git_output(project_root, *args):
    return subprocess.check_output(
        ["git", "-C", str(project_root), *args], text=True
    ).strip()


def load_idf_environment(export_script):
    export_script = Path(export_script).resolve()
    if not export_script.is_file():
        raise ValueError(f"ESP-IDF export script unavailable: {export_script}")
    completed = subprocess.run(
        [
            "bash",
            "-lc",
            f"source {shlex.quote(str(export_script))} >/dev/null && env -0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    environment = os.environ.copy()
    for entry in completed.stdout.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        environment[key.decode()] = value.decode(errors="surrogateescape")
    if not environment.get("IDF_PATH"):
        raise ValueError("ESP-IDF environment did not define IDF_PATH")
    return environment


def pipeline_commands(
    project_root,
    firmware_set,
    results_id,
    serial_port,
    board_ip,
    interface,
    analysis_tag,
):
    python = sys.executable
    scripts = project_root / "scripts/experiment"
    results = project_root / "results/experiments" / results_id
    audit = results / "analysis/formal_audit_report.json"
    window = results / "window_manifest.json"
    return [
        (
            "verify_firmware_set_seal",
            [python, str(scripts / "verify_result_tree_seal.py"), str(firmware_set)],
        ),
        (
            "independent_window_smoke",
            [
                python,
                str(scripts / "run_p4_smoke_gates.py"),
                "--firmware-set",
                str(firmware_set),
                "--results-id",
                results_id,
                "--serial-port",
                serial_port,
                "--board-ip",
                board_ip,
                "--interface",
                interface,
                "--new-window-ack",
                "--network-reassociated-ack",
            ],
        ),
        (
            "formal_collection",
            [
                python,
                str(scripts / "run_p4_formal.py"),
                "--firmware-set",
                str(firmware_set),
                "--results-id",
                results_id,
                "--window-manifest",
                str(window),
                "--serial-port",
                serial_port,
                "--board-ip",
                board_ip,
                "--interface",
                interface,
            ],
        ),
        (
            "formal_audit",
            [
                python,
                str(scripts / "audit_p4_formal.py"),
                str(results),
                "--output",
                str(audit),
            ],
        ),
        (
            "confirmatory_analysis",
            [
                python,
                str(scripts / "analyze_p4_complete.py"),
                str(results),
                "--audit-report",
                str(audit),
                "--output-dir",
                str(results / f"analysis/confirmatory_{analysis_tag}"),
                "--bootstrap-samples",
                "10000",
                "--seed",
                "20260715",
            ],
        ),
        (
            "wire_analysis",
            [
                python,
                str(scripts / "analyze_p4_wire.py"),
                str(results),
                "--audit-report",
                str(audit),
                "--window-manifest",
                str(window),
                "--board-ip",
                board_ip,
                "--output-dir",
                str(results / f"analysis/wire_{analysis_tag}"),
            ],
        ),
        (
            "seal_result_tree",
            [python, str(scripts / "seal_result_tree.py"), str(results)],
        ),
        (
            "verify_result_tree_seal",
            [python, str(scripts / "verify_result_tree_seal.py"), str(results)],
        ),
    ]


def command_record(name, command, returncode, started, completed):
    return {
        "name": name,
        "command": command,
        "returncode": returncode,
        "started_at_utc": started,
        "completed_at_utc": completed,
    }


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--firmware-set", type=Path, required=True)
    parser.add_argument("--results-id", required=True)
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--board-ip", default="10.219.224.107")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument(
        "--idf-export",
        type=Path,
        default=Path.home() / "esp-idf/export.sh",
    )
    parser.add_argument("--new-window-ack", action="store_true")
    parser.add_argument("--network-reassociated-ack", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.results_id):
        raise SystemExit("results-id contains unsupported characters")
    if not args.new_window_ack or not args.network_reassociated_ack:
        raise SystemExit(
            "pipeline requires explicit new-window and network-reassociation acknowledgements"
        )
    project_root = args.project_root.resolve()
    firmware_set = args.firmware_set.resolve()
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("P4 pipeline requires a clean harness worktree")
    harness_commit = git_output(project_root, "rev-parse", "HEAD")
    analysis_tag = harness_commit[:7]
    try:
        environment = load_idf_environment(args.idf_export)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    commands = pipeline_commands(
        project_root,
        firmware_set,
        args.results_id,
        args.serial_port,
        args.board_ip,
        args.interface,
        analysis_tag,
    )
    results = project_root / "results/experiments" / args.results_id
    records = []
    for index, (name, command) in enumerate(commands, start=1):
        print(f"[pipeline] step {index}/{len(commands)}: {name}", flush=True)
        started = datetime.now(timezone.utc).isoformat()
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=environment,
            check=False,
        )
        finished = datetime.now(timezone.utc).isoformat()
        records.append(
            command_record(name, command, completed.returncode, started, finished)
        )
        if completed.returncode != 0:
            raise SystemExit(
                f"P4 pipeline stopped at {name} with exit code "
                f"{completed.returncode}"
            )
        if name == "wire_analysis":
            pipeline_manifest = {
                "schema_version": 1,
                "classification": "p4_end_to_end_pipeline_execution",
                "status_before_release_seal": "ALL_COLLECTION_AND_ANALYSIS_STEPS_PASS",
                "harness_commit": harness_commit,
                "firmware_set": str(firmware_set),
                "results_id": args.results_id,
                "steps": records,
            }
            results.mkdir(parents=True, exist_ok=True)
            (results / "pipeline_manifest.json").write_text(
                json.dumps(pipeline_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    print(f"[pipeline] COMPLETE and independently verified: {results}")


if __name__ == "__main__":
    main()
