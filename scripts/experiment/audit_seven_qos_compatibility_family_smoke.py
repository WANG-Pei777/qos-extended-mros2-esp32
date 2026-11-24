#!/usr/bin/env python3
"""Audit representative hardware smokes for all compatibility families."""

from __future__ import annotations

import argparse
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
    / "results/diagnostics/20260717_seven_qos_compatibility_family_smoke_prep"
)
DEFAULT_OUTPUT = (
    REPO
    / "results/diagnostics"
    / "20260717_seven_qos_compatibility_family_smoke_release"
)
ACCEPTED = (
    "CMP-DUR-h2b-local-first-p2_attempt02_exact",
    "CMP-DUR-b2h-remote-first-p3_attempt02_exact",
    "CMP-DL-h2b-local-first-p1_attempt02_fraction_fix",
    "CMP-DL-b2h-remote-first-p2",
    "CMP-LV-h2b-local-first-p1",
    "CMP-LV-b2h-remote-first-p2",
)
REJECTED_BEFORE_FIX = "CMP-DL-h2b-local-first-p1"
SUPERSEDED = {
    "CMP-DUR-h2b-local-first-p2",
    "CMP-DUR-b2h-remote-first-p3",
}
PROVENANCE = (
    "mros2/embeddedRTPS/include/rtps/discovery/QoSCompatibility.h",
    "mros2/embeddedRTPS/include/rtps/discovery/TopicData.h",
    "mros2/embeddedRTPS/include/rtps/entities/Domain.h",
    "mros2/embeddedRTPS/include/rtps/entities/QosTime.h",
    "mros2/embeddedRTPS/src/discovery/SPDPAgent.cpp",
    "mros2/embeddedRTPS/src/discovery/TopicData.cpp",
    "mros2/embeddedRTPS/src/entities/Domain.cpp",
    "mros2/src/mros2.cpp",
    "tests/test_qos_compatibility.cpp",
    "tests/test_qos_time.cpp",
    "scripts/test/qos_static_checks.sh",
    "scripts/experiment/run_seven_qos_compatibility_case.py",
    "scripts/experiment/audit_seven_qos_compatibility_family_smoke.py",
    "scripts/experiment/validate_qos_compatibility_host_probe.py",
    "scripts/experiment/validate_qos_compatibility_board_probe.py",
    "workspace/seven_qos_compatibility/CMakeLists.txt",
    "workspace/seven_qos_compatibility/main/CMakeLists.txt",
    "workspace/seven_qos_compatibility/main/app.cpp",
    "results/protocols/20260717_seven_qos_deterministic_expanded_draft/"
    "schedule.csv",
    "results/protocols/20260717_seven_qos_deterministic_expanded_draft/"
    "design_manifest.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tshark_output(path: Path, verbose: bool = False) -> str:
    command = ["tshark", "-r", str(path)]
    if verbose:
        command += [
            "-Y",
            "ip.src == 192.0.2.1 && "
            'rtps.param.topicName contains "seven_qos"',
            "-V",
        ]
    else:
        command += ["-T", "fields", "-e", "frame.number"]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(f"tshark failed for {path}")
    return completed.stdout


def audit_attempt(directory: Path) -> dict[str, object]:
    manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("status") != "PASS" or any(
        manifest.get("return_codes", {}).values()
    ):
        raise ValueError(f"attempt is not PASS: {directory.name}")
    case = manifest["case"]
    board_qos = case["board_qos"]
    expected = bool(case["expected_match"])
    board = validate_board(
        (directory / "serial.raw")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines(),
        case_id=case["case_id"],
        role=case["board_role"],
        reliability=board_qos["reliability"],
        durability=board_qos["durability"],
        deadline_ms=board_qos["deadline_ms"],
        liveliness_lease_ms=board_qos["liveliness_lease_ms"],
        expected_match=expected,
    )
    host = validate_host(
        (directory / "host.log")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines(),
        case["case_id"],
        case["host_role"],
        expected,
    )
    checked_hashes = 0
    for relative, expected_hash in manifest["artifacts"].items():
        artifact = REPO / relative
        if not artifact.is_file() or sha256(artifact) != expected_hash:
            raise ValueError(
                f"artifact hash mismatch in {directory.name}: {relative}"
            )
        checked_hashes += 1
    packets = sum(
        bool(line.strip())
        for line in tshark_output(directory / "capture.pcapng").splitlines()
    )
    if packets == 0:
        raise ValueError(f"empty PCAP: {directory.name}")
    return {
        "source_directory": directory.name,
        "status": "PASS",
        "case": case,
        "board": board,
        "host": host,
        "pcap_packets": packets,
        "artifact_hashes_reverified": checked_hashes,
        "manifest_sha256": sha256(directory / "manifest.json"),
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

    accepted = [audit_attempt(prep / name) for name in ACCEPTED]
    protocol_hashes: dict[str, str] | None = None
    for item in accepted:
        manifest = json.loads(
            (prep / item["source_directory"] / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        current = {
            key: value
            for key, value in manifest["artifacts"].items()
            if "/artifacts/firmware.bin" not in key
        }
        if protocol_hashes is None:
            protocol_hashes = current
        elif current != protocol_hashes:
            raise ValueError(
                "accepted cases do not bind one protocol source set"
            )

    deadline_verbose = tshark_output(
        prep
        / "CMP-DL-h2b-local-first-p1_attempt02_fraction_fix"
        / "capture.pcapng",
        verbose=True,
    )
    if "0.100000 sec (0s + 0x1999999a)" not in deadline_verbose:
        raise ValueError("Deadline PCAP lacks the exact 100 ms RTPS fraction")
    liveliness_verbose = tshark_output(
        prep / "CMP-LV-h2b-local-first-p1" / "capture.pcapng",
        verbose=True,
    )
    if "lease_duration: 2.000000 sec" not in liveliness_verbose:
        raise ValueError(
            "Liveliness PCAP lacks the requested two-second lease"
        )

    output.mkdir(parents=True)
    attempts_output = output / "attempts"
    attempts_output.mkdir()
    for source in sorted(path for path in prep.iterdir() if path.is_dir()):
        shutil.copytree(
            source,
            attempts_output / source.name,
            copy_function=shutil.copy2,
        )
    provenance_output = output / "provenance"
    for relative in PROVENANCE:
        source = REPO / relative
        destination = provenance_output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    inventory = []
    for source in sorted(path for path in prep.iterdir() if path.is_dir()):
        if source.name in ACCEPTED:
            classification = "accepted_current_source_family_smoke"
        elif source.name == REJECTED_BEFORE_FIX:
            classification = "rejected_pre_fix_deadline_wire_encoding"
        elif source.name in SUPERSEDED:
            classification = "superseded_pass_pre_duration_fix"
        else:
            classification = "retained_unclassified_engineering_attempt"
        inventory.append(
            {"directory": source.name, "classification": classification}
        )

    report = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_family_smoke_release",
        "status": "COMPLETE_FAMILY_SMOKE_PASS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "accepted_case_count": len(accepted),
        "accepted_cases": accepted,
        "attempt_inventory": inventory,
        "wire_encoding_evidence": {
            "deadline_requested_100_ms": "0.100000 sec (0x1999999a)",
            "liveliness_requested_2000_ms": "2.000000 sec",
        },
        "protocol_artifact_sha256": protocol_hashes,
        "provenance_sha256": {
            relative: sha256(REPO / relative) for relative in PROVENANCE
        },
        "claim_boundary": (
            "Representative engineering family smokes only; no row is "
            "accepted as part of the formal 48-case compatibility campaign."
        ),
    }
    (output / "audit_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# Seven-QoS compatibility family smoke release\n\n"
        "This engineering release contains compatible and incompatible "
        "representative hardware smokes for Durability, Deadline, and "
        "Liveliness. It retains the pre-fix Deadline rejection and does not "
        "claim formal 48-case completion.\n",
        encoding="ascii",
    )
    print(
        f"PASS: accepted={len(accepted)} inventory={len(inventory)} "
        f"output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
