#!/usr/bin/env python3
"""Validate a frozen deterministic Seven-QoS mechanism protocol."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from run_seven_qos_mechanism_hardware_case import (
    canonical_sha256,
    load_frozen_bundle,
    sha256,
)
from seven_qos_mechanism_hardware_cases import HARDWARE_CASES, get_case
from seven_qos_mechanism_oracles import UNIT_ORACLES


REPO = Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"protocol path escapes root: {relative}")
    return path


def verify_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"frozen hash mismatch: {label}")


def validate_protocol(
    protocol: Path, *, verify_bound_repo: bool = True
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    protocol = protocol.resolve()
    design = json.loads(
        (protocol / "design_manifest.json").read_text(encoding="utf-8")
    )
    if design.get("classification") != "seven_qos_mechanism_formal_preregistration":
        raise ValueError("unexpected mechanism protocol classification")
    if design.get("status") != "FROZEN_NO_DATA":
        raise ValueError("mechanism protocol is not frozen before data")

    paths = {
        "claims": protocol / "claims.csv",
        "unit": protocol / "unit_schedule.csv",
        "hardware": protocol / "hardware_schedule.csv",
    }
    verify_hash(paths["claims"], design["claims_sha256"], "claims.csv")
    verify_hash(paths["unit"], design["unit_schedule_sha256"], "unit_schedule.csv")
    verify_hash(
        paths["hardware"], design["hardware_schedule_sha256"],
        "hardware_schedule.csv",
    )
    claims = read_csv(paths["claims"])
    units = read_csv(paths["unit"])
    hardware = read_csv(paths["hardware"])
    if (len(claims), len(units), len(hardware)) != (36, 27, 32):
        raise ValueError("frozen schedule counts are not 36/27/32")
    if [int(row["claim_ordinal"]) for row in claims] != list(range(1, 37)):
        raise ValueError("claim ordinals are not contiguous")
    if [int(row["ordinal"]) for row in units] != list(range(1, 28)):
        raise ValueError("unit ordinals are not contiguous")
    if [int(row["ordinal"]) for row in hardware] != list(range(1, 33)):
        raise ValueError("hardware ordinals are not contiguous")
    claim_by_id = {row["case_id"]: row for row in claims}
    if len(claim_by_id) != 36:
        raise ValueError("claim IDs are not unique")
    if set(UNIT_ORACLES) != {row["case_id"] for row in units}:
        raise ValueError("unit schedule does not match unit registry")
    if set(HARDWARE_CASES) != {row["case_id"] for row in hardware}:
        raise ValueError("hardware schedule does not match hardware registry")

    unit_design = design["unit_artifacts"]
    binary_root = contained(protocol, unit_design["binary_root"])
    for name, expected in unit_design["binary_hashes"].items():
        verify_hash(binary_root / name, expected, f"unit binary {name}")
    source_root = contained(protocol, unit_design["source_root"])
    for relative, expected in unit_design["source_hashes"].items():
        verify_hash(source_root / relative, expected, f"unit source {relative}")
    for row in units:
        case_id = row["case_id"]
        oracle = UNIT_ORACLES[case_id]
        claim = claim_by_id[case_id]
        if int(row["claim_ordinal"]) != int(claim["claim_ordinal"]):
            raise ValueError(f"unit claim binding mismatch: {case_id}")
        if row["binary"] != oracle["binary"]:
            raise ValueError(f"unit binary binding mismatch: {case_id}")
        verify_hash(
            binary_root / row["binary"], row["binary_sha256"],
            f"unit row binary {case_id}",
        )
        if row["oracle_sha256"] != canonical_sha256(oracle):
            raise ValueError(f"unit oracle drift: {case_id}")

    for row in hardware:
        case_id = row["case_id"]
        config = get_case(case_id)
        claim = claim_by_id[case_id]
        if int(row["claim_ordinal"]) != int(claim["claim_ordinal"]):
            raise ValueError(f"hardware claim binding mismatch: {case_id}")
        if json.loads(row["case_config_json"]) != config:
            raise ValueError(f"hardware config drift: {case_id}")
        if row["case_config_sha256"] != canonical_sha256(config):
            raise ValueError(f"hardware config hash drift: {case_id}")
        bundle = contained(protocol, row["bundle_relative_path"])
        manifest = load_frozen_bundle(bundle, config)
        verify_hash(
            bundle / "artifact_manifest.json",
            row["artifact_manifest_sha256"],
            f"bundle manifest {case_id}",
        )
        if row["firmware_sha256"] != manifest["app_sha256"]:
            raise ValueError(f"firmware schedule drift: {case_id}")

    host = design["host_artifacts"]
    verify_hash(
        contained(protocol, host["probe_relative_path"]),
        host["probe_sha256"], "host probe",
    )
    verify_hash(
        contained(protocol, host["profile_relative_path"]),
        host["profile_sha256"], "host profile",
    )
    verify_hash(
        protocol / "artifacts/host/ldd.txt", host["ldd_sha256"], "host ldd",
    )
    environment_root = protocol / "artifacts/environment"
    for relative, expected in design["hardware_and_network_gate"]["files"].items():
        verify_hash(environment_root / relative, expected, f"environment {relative}")
    smoke = design["excluded_prefreeze_evidence"]
    if len(smoke.get("releases", [])) != 8:
        raise ValueError("replacement protocol does not bind all amendment evidence")
    for release in smoke["releases"]:
        release_path = REPO / release["verification_path"]
        verify_hash(
            release_path, release["verification_sha256"],
            f"prefreeze release {release['label']}",
        )
        release_report = json.loads(release_path.read_text(encoding="utf-8"))
        if (
            release_report.get("status") != "PASS"
            or release_report.get("tree_sha256") != release["tree_sha256"]
            or release_report.get("file_manifest_sha256")
            != release["file_manifest_sha256"]
        ):
            raise ValueError(f"prefreeze release drift: {release['label']}")
    amendment = design["amendment"]
    verify_hash(
        REPO / amendment["relative_path"], amendment["sha256"],
        "protocol amendment",
    )
    if amendment.get("claim_schedule_changed") or amendment.get("oracle_changed"):
        raise ValueError("replacement protocol unexpectedly changes claims or oracles")
    if verify_bound_repo:
        for relative, expected in design["bound_source_files"].items():
            verify_hash(REPO / relative, expected, f"bound source {relative}")
    return design, claims, units, hardware


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--skip-bound-repo", action="store_true")
    args = parser.parse_args()
    design, claims, units, hardware = validate_protocol(
        args.protocol, verify_bound_repo=not args.skip_bound_repo
    )
    print(
        f"PASS: claims={len(claims)} unit={len(units)} hardware={len(hardware)} "
        f"hardware_schedule_sha256={design['hardware_schedule_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
