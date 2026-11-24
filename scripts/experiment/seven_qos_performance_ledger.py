#!/usr/bin/env python3
"""Acceptance checks and receipts for Seven-QoS performance attempts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FIRMWARE_TOKEN_RE = re.compile(r"^sqc-[A-Za-z0-9][A-Za-z0-9_.-]*$")
FATAL_MARKERS = (
    "guru meditation",
    "watchdog",
    "backtrace:",
    "stack smashing",
    "heap corruption",
    "assert failed",
    "qos_board_error",
)
WRAPPER_SPECS = {
    "workload_egress": (
        "impairment_manifest.json",
        "seven_qos_performance_formal_network_attempt",
    ),
    "workload_ingress": (
        "ingress_impairment_manifest.json",
        "seven_qos_performance_formal_ingress_attempt",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_identity(
    plan_row: dict[str, str], schedule_sha256: str
) -> dict[str, str | int]:
    return {
        "mode": "formal_candidate",
        "campaign_run_token": plan_row["run_token"],
        "protocol_schedule_sha256": schedule_sha256,
        "schedule_ordinal": int(plan_row["ordinal"]),
        "cell_id": plan_row["cell_id"],
    }


def binding_errors(requirement: dict[str, str]) -> list[str]:
    errors: list[str] = []
    expected_statuses = {
        "artifact_bundle_status": "FROZEN",
        "runtime_binding_status": "BOUND",
        "acceptance_oracle_status": "VERIFIED",
    }
    for field, expected in expected_statuses.items():
        if requirement.get(field) != expected:
            errors.append(f"{field} is not {expected}")
    for field in (
        "source_commit",
        "build_dir",
        "app_name",
        "runtime_arguments_json",
    ):
        if not requirement.get(field):
            errors.append(f"missing {field}")
    if not FIRMWARE_TOKEN_RE.fullmatch(requirement.get("firmware_run_token", "")):
        errors.append("invalid firmware_run_token")
    for field in (
        "firmware_sha256",
        "elf_sha256",
        "sdkconfig_sha256",
        "project_description_sha256",
    ):
        if not SHA256_RE.fullmatch(requirement.get(field, "")):
            errors.append(f"invalid {field}")
    try:
        runtime = json.loads(requirement.get("runtime_arguments_json", ""))
        if not isinstance(runtime, dict) or not runtime:
            errors.append("runtime_arguments_json must be a nonempty object")
    except json.JSONDecodeError:
        errors.append("runtime_arguments_json is invalid JSON")
    return errors


def fatal_markers(attempt_dir: Path) -> list[str]:
    text = ""
    for name in (
        "serial.raw",
        "capture.log",
        "host.log",
        "flash.log",
        "wrapper_runner_stderr.txt",
    ):
        path = attempt_dir / name
        if path.is_file():
            text += path.read_bytes().decode("utf-8", errors="replace").lower()
    return sorted({marker for marker in FATAL_MARKERS if marker in text})


def artifact_record_errors(
    attempt_dir: Path,
    manifest: dict[str, Any],
    requirement: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    expected = {
        "firmware": "firmware_sha256",
        "elf": "elf_sha256",
        "sdkconfig": "sdkconfig_sha256",
        "project_description": "project_description_sha256",
    }
    root = attempt_dir.resolve()
    for artifact_key, requirement_key in expected.items():
        record = manifest.get("artifacts", {}).get(artifact_key, {})
        relative = record.get("path")
        if not isinstance(relative, str) or not relative:
            errors.append(f"missing {artifact_key} artifact path")
            continue
        artifact = (attempt_dir / relative).resolve()
        if root not in artifact.parents or not artifact.is_file():
            errors.append(f"missing or unsafe {artifact_key} artifact")
            continue
        actual = sha256(artifact)
        if record.get("sha256") != actual:
            errors.append(f"{artifact_key} manifest SHA-256 mismatch")
        if requirement.get(requirement_key) != actual:
            errors.append(f"{artifact_key} frozen SHA-256 mismatch")
    project_version = manifest.get("project_version")
    source_commit = requirement.get("source_commit", "")
    if not isinstance(project_version, str) or not project_version:
        errors.append("missing build-time project version")
    elif not source_commit.startswith(project_version):
        errors.append("build-time project version differs from frozen source commit")
    return errors


def validate_attempt(
    attempt_dir: Path,
    plan_row: dict[str, str],
    requirement: dict[str, str],
    schedule_sha256: str,
) -> dict[str, Any]:
    reasons = binding_errors(requirement)
    if plan_row.get("launch_status") != "READY":
        reasons.append("plan row is not READY")
    if plan_row.get("artifact_bundle_status") != "FROZEN":
        reasons.append("plan artifact bundle is not FROZEN")

    identity = expected_identity(plan_row, schedule_sha256)
    manifest_path = attempt_dir / "attempt_manifest.json"
    manifest: dict[str, Any] = {}
    if not manifest_path.is_file():
        reasons.append("missing attempt_manifest.json")
    else:
        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            reasons.append("unreadable attempt_manifest.json")
        if manifest.get("status") != "PASS":
            reasons.append("collector status is not PASS")
        if manifest.get("classification") != "seven_qos_performance_formal_attempt":
            reasons.append("collector classification is not formal")
        if manifest.get("evidence_identity") != identity:
            reasons.append("collector evidence identity mismatch")
        if (
            manifest.get("workload", {}).get("firmware_run_token")
            != requirement.get("firmware_run_token")
        ):
            reasons.append("firmware run token mismatch")
        reasons.extend(artifact_record_errors(attempt_dir, manifest, requirement))

    wrapper_path: Path | None = None
    runner_kind = plan_row.get("runner_kind", "")
    if runner_kind in WRAPPER_SPECS:
        wrapper_name, classification = WRAPPER_SPECS[runner_kind]
        wrapper_path = attempt_dir / wrapper_name
        if not wrapper_path.is_file():
            reasons.append(f"missing {wrapper_name}")
        else:
            try:
                wrapper = load_json(wrapper_path)
            except (OSError, json.JSONDecodeError):
                wrapper = {}
                reasons.append(f"unreadable {wrapper_name}")
            if wrapper.get("status") != "PASS":
                reasons.append("network wrapper status is not PASS")
            if wrapper.get("classification") != classification:
                reasons.append("network wrapper classification mismatch")
            if wrapper.get("evidence_identity") != identity:
                reasons.append("network wrapper evidence identity mismatch")
            if (
                wrapper.get("firmware_run_token")
                != requirement.get("firmware_run_token")
            ):
                reasons.append("network wrapper firmware run token mismatch")
            if wrapper.get("cleanup_ok") is not True:
                reasons.append("network cleanup did not pass")
            pcap = attempt_dir / "traffic.pcapng"
            if not pcap.is_file():
                reasons.append("missing traffic.pcapng")
            elif wrapper.get("pcap_sha256") != sha256(pcap):
                reasons.append("PCAP SHA-256 mismatch")
    elif runner_kind != "telemetry_control_probe":
        reasons.append(f"unknown runner kind: {runner_kind}")

    for required in ("serial.raw", "validation.txt"):
        if not (attempt_dir / required).is_file():
            reasons.append(f"missing {required}")
    fatals = fatal_markers(attempt_dir)
    status = "ACCEPTABLE" if not reasons and not fatals else "REJECTED"
    if fatals:
        status = "FATAL_REJECTED"
        reasons.append("fatal marker retained")
    return {
        "status": status,
        "reasons": reasons,
        "fatal_markers": fatals,
        "evidence_identity": identity,
        "collector_manifest_sha256": (
            sha256(manifest_path) if manifest_path.is_file() else None
        ),
        "wrapper_manifest_sha256": (
            sha256(wrapper_path) if wrapper_path and wrapper_path.is_file() else None
        ),
    }


def acceptance_artifacts(attempt_dir: Path, runner_kind: str) -> dict[str, str]:
    names = ["attempt_manifest.json", "serial.raw", "validation.txt"]
    if runner_kind in WRAPPER_SPECS:
        names.extend((WRAPPER_SPECS[runner_kind][0], "traffic.pcapng"))
    manifest = load_json(attempt_dir / "attempt_manifest.json")
    for key in ("firmware", "elf", "sdkconfig", "project_description"):
        relative = manifest.get("artifacts", {}).get(key, {}).get("path")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"missing acceptance artifact record: {key}")
        names.append(relative)
    artifacts: dict[str, str] = {}
    for name in names:
        path = attempt_dir / name
        if not path.is_file():
            raise ValueError(f"missing acceptance artifact: {name}")
        artifacts[name] = sha256(path)
    return artifacts


def build_acceptance_receipt(
    attempt_dir: Path,
    plan_row: dict[str, str],
    requirement: dict[str, str],
    schedule_sha256: str,
) -> dict[str, Any]:
    assessment = validate_attempt(
        attempt_dir, plan_row, requirement, schedule_sha256
    )
    if assessment["status"] != "ACCEPTABLE":
        raise ValueError("cannot receipt a rejected formal candidate")
    return {
        "schema_version": 1,
        "classification": "seven_qos_performance_acceptance_receipt",
        "ordinal": int(plan_row["ordinal"]),
        "run_token": plan_row["run_token"],
        "family": plan_row["family"],
        "cell_id": plan_row["cell_id"],
        "configuration_sha256": requirement["configuration_sha256"],
        "firmware_sha256": requirement["firmware_sha256"],
        "evidence_identity": assessment["evidence_identity"],
        "attempt_relative_path": plan_row["candidate_relative_path"],
        "artifacts": acceptance_artifacts(attempt_dir, plan_row["runner_kind"]),
    }
