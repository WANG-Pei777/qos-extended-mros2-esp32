#!/usr/bin/env python3
"""Audit whether sealed formal firmware contains the QoS monitor timing defect."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

ARTIFACTS = (
    {
        "evidence": "P4 best-effort formal firmware",
        "path": "results/experiments/20260715_p4_firmware_set_amended/artifacts/"
        "p4_best_effort_elf_78c248ff480538cec4a7a2e97a710091dad695522618b2a199aa969fe795c6d9.elf",
        "sha256": "78c248ff480538cec4a7a2e97a710091dad695522618b2a199aa969fe795c6d9",
    },
    {
        "evidence": "P4 reliable formal firmware",
        "path": "results/experiments/20260715_p4_firmware_set_amended/artifacts/"
        "p4_reliable_elf_67d1aca4be3d9ce2fc6e41b0ab8ccac2a3d7ead6bd6e6cf08cec63f9c4a07d24.elf",
        "sha256": "67d1aca4be3d9ce2fc6e41b0ab8ccac2a3d7ead6bd6e6cf08cec63f9c4a07d24",
    },
    {
        "evidence": "three-system mROS2-QoS formal firmware",
        "path": "results/experiments/20260715_three_system_firmware_set/systems/"
        "mros2qos/system_compare.elf",
        "sha256": "ec77dbf731b39b92c8f2dabb608f90f91caf6ddf3496e80e0bec68efe15a6f0e",
    },
)

SOURCE_COMMITS = (
    {
        "evidence": "P4 formal firmware source",
        "commit": "43ab8a86233f3a00d86160c296e4bef0486a2375",
    },
    {
        "evidence": "three-system mROS2-QoS formal firmware source",
        "commit": "b8c8d84c2e3e37488af64bac0ea20436a8838661",
    },
)

FORBIDDEN_SYMBOLS = ("qosMonitorLoop", "qosMonitorJumppad", "QoSMonitor")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(*command: str) -> str:
    return subprocess.run(
        command,
        cwd=REPO,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    nm = shutil.which("xtensa-esp32s3-elf-nm") or shutil.which("nm")
    if nm is None:
        raise SystemExit("neither xtensa-esp32s3-elf-nm nor nm is available")

    failures: list[str] = []
    artifact_checks = []
    for item in ARTIFACTS:
        path = REPO / item["path"]
        actual_hash = sha256(path)
        symbols = run(nm, "-C", str(path))
        matches = actual_hash == item["sha256"]
        forbidden_found = [name for name in FORBIDDEN_SYMBOLS if name in symbols]
        if not matches:
            failures.append(f"hash mismatch: {item['path']}")
        if forbidden_found:
            failures.append(f"monitor symbol found: {item['path']}")
        artifact_checks.append(
            {
                **item,
                "actual_sha256": actual_hash,
                "hash_matches": matches,
                "forbidden_monitor_symbols_found": forbidden_found,
                "check_deadline_symbol_present": "checkDeadlineMissed" in symbols,
            }
        )

    source_checks = []
    source_path = "mros2/embeddedRTPS/src/entities/Domain.cpp"
    for item in SOURCE_COMMITS:
        source = run("git", "show", f"{item['commit']}:{source_path}")
        forbidden_found = [name for name in FORBIDDEN_SYMBOLS if name in source]
        if forbidden_found:
            failures.append(f"monitor source found: {item['commit']}")
        source_checks.append(
            {
                **item,
                "path": source_path,
                "forbidden_monitor_identifiers_found": forbidden_found,
            }
        )

    report = {
        "schema_version": 1,
        "classification": "qos_monitor_timing_defect_legacy_evidence_impact_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "decision": {
            "p4_formal": "UNAFFECTED",
            "three_system_formal": "UNAFFECTED",
            "pre_fix_mros2qos_telemetry_cpu": "SUPERSEDED_DO_NOT_CITE",
        },
        "interpretation": (
            "checkDeadlineMissed may exist in an ELF without the later Domain monitor. "
            "The defect requires qosMonitorLoop to call it from a zero-tick polling loop."
        ),
        "artifact_checks": artifact_checks,
        "source_checks": source_checks,
        "failures": failures,
    }

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else REPO / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
