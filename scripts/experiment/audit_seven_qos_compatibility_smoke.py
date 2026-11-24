#!/usr/bin/env python3
"""Audit and curate the accepted Seven-QoS compatibility smoke evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from validate_qos_compatibility_board_probe import validate as validate_board
from validate_qos_compatibility_host_probe import validate as validate_host


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PREP = (
    REPO
    / "results/diagnostics/20260717_seven_qos_compatibility_smoke_prep"
)
DEFAULT_OUTPUT = (
    REPO
    / "results/diagnostics/20260717_seven_qos_compatibility_smoke_release"
)
RUNNER_VALIDATION = "RUNNER-CMP-REL-b2h-remote-first-p3_attempt18_exact"


@dataclass(frozen=True)
class AcceptedCase:
    label: str
    source_directory: str
    case_id: str
    direction: str
    endpoint_creation_order: str
    expected_match: bool
    board_role: str
    board_reliability: str
    board_durability: str
    host_role: str


ACCEPTED_CASES = (
    AcceptedCase(
        "01_b2h_match_remote_first",
        "SELF-BOARD-B2H_remote_first_attempt11_initial_peer_long_hold",
        "SELF-BOARD-B2H",
        "b2h",
        "remote_first",
        True,
        "publisher",
        "reliable",
        "volatile",
        "subscriber",
    ),
    AcceptedCase(
        "02_b2h_match_local_first",
        "SELF-BOARD-B2H_local_first_attempt12_gate_latest",
        "SELF-BOARD-B2H",
        "b2h",
        "local_first",
        True,
        "publisher",
        "reliable",
        "volatile",
        "subscriber",
    ),
    AcceptedCase(
        "03_b2h_mismatch_remote_first",
        "SELF-BOARD-B2H-MISMATCH_remote_first_attempt13",
        "SELF-BOARD-B2H-MISMATCH",
        "b2h",
        "remote_first",
        False,
        "publisher",
        "best_effort",
        "volatile",
        "subscriber",
    ),
    AcceptedCase(
        "04_b2h_mismatch_local_first",
        "SELF-BOARD-B2H-MISMATCH_local_first_attempt14_gate",
        "SELF-BOARD-B2H-MISMATCH",
        "b2h",
        "local_first",
        False,
        "publisher",
        "best_effort",
        "volatile",
        "subscriber",
    ),
    AcceptedCase(
        "05_h2b_match_remote_first",
        "SELF-BOARD-H2B_remote_first_attempt15",
        "SELF-BOARD-H2B",
        "h2b",
        "remote_first",
        True,
        "subscriber",
        "reliable",
        "volatile",
        "publisher",
    ),
    AcceptedCase(
        "06_h2b_match_local_first",
        "SELF-BOARD-H2B_local_first_attempt16_gate",
        "SELF-BOARD-H2B",
        "h2b",
        "local_first",
        True,
        "subscriber",
        "reliable",
        "volatile",
        "publisher",
    ),
)


PROVENANCE = (
    "mros2/embeddedRTPS/src/discovery/SPDPAgent.cpp",
    "tools/echo_cpp/src/qos_compatibility_probe.cpp",
    "tools/echo_cpp/config/seven_qos_esp32_initial_peer.xml",
    "tools/echo_cpp/CMakeLists.txt",
    "scripts/experiment/run_seven_qos_compatibility_case.py",
    "scripts/experiment/audit_seven_qos_compatibility_smoke.py",
    "scripts/experiment/validate_qos_compatibility_host_probe.py",
    "scripts/experiment/validate_qos_compatibility_board_probe.py",
    "scripts/experiment/test_seven_qos_compatibility_case_runner.py",
    "scripts/experiment/test_qos_compatibility_host_probe.py",
    "scripts/experiment/test_qos_compatibility_board_probe.py",
    "workspace/seven_qos_compatibility/CMakeLists.txt",
    "workspace/seven_qos_compatibility/main/CMakeLists.txt",
    "workspace/seven_qos_compatibility/main/app.cpp",
    "results/protocols/20260717_seven_qos_deterministic_expanded_draft/"
    "schedule.csv",
    "results/protocols/20260717_seven_qos_deterministic_expanded_draft/"
    "design_manifest.json",
)


FIRMWARE = {
    "b2h_match.bin": (
        "workspace/seven_qos_compatibility/build_self_board_b2h/"
        "seven_qos_compatibility.bin"
    ),
    "b2h_mismatch.bin": (
        "workspace/seven_qos_compatibility/build_self_board_b2h_mismatch/"
        "seven_qos_compatibility.bin"
    ),
    "h2b_match.bin": (
        "workspace/seven_qos_compatibility/build_self_board_h2b/"
        "seven_qos_compatibility.bin"
    ),
    "host_probe": (
        "tools/echo_cpp/install/echo_cpp/lib/echo_cpp/"
        "qos_compatibility_probe"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact_list(path: Path) -> int:
    checked = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, source = line.split(maxsplit=1)
        source_path = Path(source.strip())
        if sha256(source_path) != expected:
            raise ValueError(f"artifact hash mismatch: {source_path}")
        checked += 1
    if checked == 0:
        raise ValueError(f"empty artifact hash list: {path}")
    return checked


def pcap_packet_count(path: Path) -> int:
    completed = subprocess.run(
        ["tshark", "-r", str(path), "-T", "fields", "-e", "frame.number"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(f"unreadable PCAP: {path}")
    return sum(bool(line.strip()) for line in completed.stdout.splitlines())


def audit_case(prep: Path, case: AcceptedCase) -> dict[str, object]:
    source = prep / case.source_directory
    required = (
        "serial.raw",
        "host.log",
        "capture.pcapng",
        "orchestration.log",
        "artifact_sha256.txt",
    )
    missing = [name for name in required if not (source / name).is_file()]
    if missing:
        raise ValueError(f"{case.label} missing files: {missing}")

    board = validate_board(
        (source / "serial.raw")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines(),
        case_id=case.case_id,
        role=case.board_role,
        reliability=case.board_reliability,
        durability=case.board_durability,
        deadline_ms="infinite",
        liveliness_lease_ms="infinite",
        expected_match=case.expected_match,
    )
    host = validate_host(
        (source / "host.log")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines(),
        case.case_id,
        case.host_role,
        case.expected_match,
    )
    orchestration = (source / "orchestration.log").read_text(
        encoding="utf-8", errors="replace"
    )
    if case.endpoint_creation_order == "remote_first":
        if "before controlled board reset" not in orchestration:
            raise ValueError(f"{case.label} lacks remote-first order evidence")
    else:
        if "before" not in orchestration or not (
            source / "release_host_endpoint.gate"
        ).is_file():
            raise ValueError(f"{case.label} lacks local-first gate evidence")
    packets = pcap_packet_count(source / "capture.pcapng")
    if packets == 0:
        raise ValueError(f"{case.label} has an empty PCAP")
    return {
        "case": asdict(case),
        "status": "PASS",
        "board": board,
        "host": host,
        "pcap_packets": packets,
        "artifact_hashes_reverified": verify_artifact_list(
            source / "artifact_sha256.txt"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prep", type=Path, default=DEFAULT_PREP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    prep = args.prep.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output already exists: {output}")

    audited = [audit_case(prep, case) for case in ACCEPTED_CASES]
    runner_source = prep / RUNNER_VALIDATION
    runner_manifest = json.loads(
        (runner_source / "manifest.json").read_text(encoding="utf-8")
    )
    if runner_manifest.get("status") != "PASS" or any(
        runner_manifest.get("return_codes", {}).values()
    ):
        raise ValueError("exact runner validation did not pass")
    runner_key = "scripts/experiment/run_seven_qos_compatibility_case.py"
    if runner_manifest["artifacts"].get(runner_key) != sha256(
        REPO / runner_key
    ):
        raise ValueError("runner validation did not bind the current runner")

    output.mkdir(parents=True)
    cases_output = output / "accepted_cases"
    cases_output.mkdir()
    for case in ACCEPTED_CASES:
        shutil.copytree(
            prep / case.source_directory,
            cases_output / case.label,
            copy_function=shutil.copy2,
        )
    shutil.copytree(
        runner_source,
        output / "runner_exact_validation",
        copy_function=shutil.copy2,
    )

    provenance_output = output / "provenance"
    for relative in PROVENANCE:
        source = REPO / relative
        destination = provenance_output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    firmware_output = output / "artifacts"
    firmware_output.mkdir()
    for name, relative in FIRMWARE.items():
        shutil.copy2(REPO / relative, firmware_output / name)

    selected = {case.source_directory for case in ACCEPTED_CASES}
    selected.add(RUNNER_VALIDATION)
    inventory = [
        {
            "directory": path.name,
            "selected_for_release": path.name in selected,
            "classification": (
                "accepted_smoke_or_exact_runner_validation"
                if path.name in selected
                else "retained_engineering_attempt_not_in_acceptance_set"
            ),
        }
        for path in sorted(prep.iterdir())
        if path.is_dir()
    ]
    report = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_smoke_release",
        "status": "COMPLETE_SMOKE_PASS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "accepted_smoke_units": 6,
            "directions": ["b2h", "h2b"],
            "endpoint_creation_orders": ["local_first", "remote_first"],
            "contains_expected_mismatch": True,
            "formal_schedule_compatibility_rows": 48,
            "formal_schedule_rows_executed_by_this_release": 0,
            "claim_boundary": (
                "Harness smoke closure only; this is not the formal "
                "48-case compatibility result set."
            ),
        },
        "accepted_cases": audited,
        "runner_exact_validation_manifest": (
            "runner_exact_validation/manifest.json"
        ),
        "attempt_inventory": inventory,
        "provenance_sha256": {
            relative: sha256(REPO / relative) for relative in PROVENANCE
        },
        "artifact_sha256": {
            name: sha256(firmware_output / name) for name in FIRMWARE
        },
    }
    (output / "audit_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# Seven-QoS compatibility smoke release\n\n"
        "Status: `COMPLETE_SMOKE_PASS`.\n\n"
        "This release closes the minimum hardware harness smoke gate across "
        "both traffic directions, both endpoint creation orders, and one "
        "explicit QoS mismatch. It does not claim completion of the 48-case "
        "formal compatibility schedule.\n",
        encoding="ascii",
    )
    print(
        f"PASS: accepted_cases={len(audited)} "
        f"inventory={len(inventory)} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
