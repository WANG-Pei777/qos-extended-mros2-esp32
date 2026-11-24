#!/usr/bin/env python3
"""Prepare a no-data execution plan for the frozen Seven-QoS schedule."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from generate_seven_qos_performance_protocol import FAMILY_ORDER, sha256
from validate_seven_qos_performance_expanded import validate


REPO = Path(__file__).resolve().parents[2]
RUNNER_BY_FAMILY = {
    "history_depth": "workload_ingress",
    "durability": "workload_egress",
    "deadline": "workload_egress",
    "lifespan": "workload_egress",
    "liveliness": "workload_egress",
    "resource_limits": "workload_egress",
}
ENTRYPOINT_BY_RUNNER = {
    "telemetry_control_probe": "scripts/experiment/run_telemetry_control_probe_smoke.py",
    "workload_egress": "scripts/experiment/run_workload_impairment_smoke.py",
    "workload_ingress": "scripts/experiment/run_workload_ingress_impairment_smoke.py",
}
CELL_REQUIREMENT_FIELDS = (
    "family",
    "cell_id",
    "direction",
    "runner_kind",
    "runner_entrypoint",
    "network_profile",
    "fixed_json",
    "configuration_json",
    "configuration_sha256",
    "firmware_run_token",
    "source_commit",
    "build_dir",
    "app_name",
    "firmware_sha256",
    "elf_sha256",
    "sdkconfig_sha256",
    "project_description_sha256",
    "runtime_arguments_json",
    "artifact_bundle_status",
    "runtime_binding_status",
    "acceptance_oracle_status",
    "blocking_reasons_json",
)
EXECUTION_PLAN_FIELDS = (
    "ordinal",
    "run_token",
    "family",
    "cell_id",
    "visit",
    "replicate_within_visit",
    "direction",
    "runner_kind",
    "network_profile",
    "candidate_relative_path",
    "artifact_bundle_status",
    "launch_status",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def configuration_sha256(fixed_json: str, configuration_json: str) -> str:
    material = canonical_json({
        "fixed": json.loads(fixed_json),
        "configuration": json.loads(configuration_json),
    }).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def firmware_run_token(family: str, cell_id: str, configuration_hash: str) -> str:
    return f"sqc-{family}-{cell_id}-{configuration_hash[:12]}"


def network_profile(family: str, configuration: dict[str, Any]) -> str:
    if family == "history_depth":
        profiles = {
            0: "clean",
            5: "loss5_independent_b2h",
            15: "loss15_independent_b2h",
        }
        try:
            return profiles[int(configuration["loss_pct"])]
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{family}: unsupported loss configuration")
    if family == "deadline":
        profiles = {0: "clean", 50: "delay50ms_h2b"}
        try:
            return profiles[int(configuration["delay_ms"])]
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{family}: unsupported delay configuration")
    if family == "liveliness":
        return "liveliness_outage_h2b"
    if family == "resource_limits":
        return "resource_ack_suppression_h2b"
    if family in {"durability", "lifespan"}:
        return "clean"
    raise ValueError(f"unsupported family: {family}")


def blocking_reasons(family: str) -> list[str]:
    reasons = [
        "exact_cell_firmware_bundle_unfrozen",
        "exact_runtime_arguments_unfrozen",
        "formal_acceptance_oracle_unverified",
    ]
    if family == "resource_limits":
        reasons.append("ack_suppression_duration_not_bound_per_cell")
    return reasons


def build_tables(
    schedule: list[dict[str, str]], cells: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    requirements: list[dict[str, str]] = []
    requirement_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for cell in cells:
        family = cell["family"]
        runner_kind = RUNNER_BY_FAMILY[family]
        configuration = json.loads(cell["configuration_json"])
        configuration_hash = configuration_sha256(
            cell["fixed_json"], cell["configuration_json"]
        )
        row = {
            "family": family,
            "cell_id": cell["cell_id"],
            "direction": cell["direction"],
            "runner_kind": runner_kind,
            "runner_entrypoint": ENTRYPOINT_BY_RUNNER[runner_kind],
            "network_profile": network_profile(family, configuration),
            "fixed_json": cell["fixed_json"],
            "configuration_json": cell["configuration_json"],
            "configuration_sha256": configuration_hash,
            "firmware_run_token": firmware_run_token(
                family, cell["cell_id"], configuration_hash
            ),
            "source_commit": "",
            "build_dir": "",
            "app_name": "",
            "firmware_sha256": "",
            "elf_sha256": "",
            "sdkconfig_sha256": "",
            "project_description_sha256": "",
            "runtime_arguments_json": "",
            "artifact_bundle_status": "UNBOUND",
            "runtime_binding_status": "UNBOUND",
            "acceptance_oracle_status": "UNVERIFIED",
            "blocking_reasons_json": canonical_json(blocking_reasons(family)),
        }
        key = (family, cell["cell_id"])
        if key in requirement_by_key:
            raise ValueError(f"duplicate cell requirement: {key}")
        requirement_by_key[key] = row
        requirements.append(row)

    plan: list[dict[str, str]] = []
    for scheduled in schedule:
        key = (scheduled["family"], scheduled["cell_id"])
        requirement = requirement_by_key.get(key)
        if requirement is None:
            raise ValueError(f"scheduled cell has no artifact requirement: {key}")
        ordinal = int(scheduled["ordinal"])
        token = scheduled["run_token"]
        plan.append({
            "ordinal": str(ordinal),
            "run_token": token,
            "family": scheduled["family"],
            "cell_id": scheduled["cell_id"],
            "visit": scheduled["visit"],
            "replicate_within_visit": scheduled["replicate_within_visit"],
            "direction": scheduled["direction"],
            "runner_kind": requirement["runner_kind"],
            "network_profile": requirement["network_profile"],
            "candidate_relative_path": (
                f"runs/{ordinal:04d}_{token}_{scheduled['family']}_"
                f"{scheduled['cell_id']}/attempt_01"
            ),
            "artifact_bundle_status": requirement["artifact_bundle_status"],
            "launch_status": "BLOCKED_UNFROZEN_CELL_BINDING",
        })

    if len(requirements) != 51 or len(plan) != 1530:
        raise ValueError(
            f"unexpected table sizes: cells={len(requirements)} runs={len(plan)}"
        )
    if len({row["candidate_relative_path"] for row in plan}) != len(plan):
        raise ValueError("candidate paths are not unique")
    return requirements, plan


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prepare(protocol: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    design, schedule, cells = validate(protocol)
    requirements, plan = build_tables(schedule, cells)
    output.mkdir(parents=True)
    inputs = output / "inputs"
    inputs.mkdir()
    for name in ("design_manifest.json", "schedule.csv", "cell_manifest.csv"):
        shutil.copy2(protocol / name, inputs / name)
    write_csv(output / "cell_artifact_requirements.csv", CELL_REQUIREMENT_FIELDS, requirements)
    write_csv(output / "execution_plan.csv", EXECUTION_PLAN_FIELDS, plan)
    manifest = {
        "schema_version": 1,
        "classification": "seven_qos_performance_no_data_execution_plan",
        "status": "BLOCKED_UNFROZEN_CELL_BINDINGS",
        "formal_launch_allowed": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": git_commit(),
        "protocol_path": str(protocol.resolve()),
        "protocol_design_sha256": sha256(protocol / "design_manifest.json"),
        "protocol_schedule_sha256": design["schedule_sha256"],
        "copied_schedule_sha256": sha256(inputs / "schedule.csv"),
        "cell_count": len(requirements),
        "scheduled_accepted_run_count": len(plan),
        "bound_cell_artifact_count": 0,
        "bound_runtime_count": 0,
        "verified_acceptance_oracle_count": 0,
        "cell_artifact_requirements_sha256": sha256(
            output / "cell_artifact_requirements.csv"
        ),
        "execution_plan_sha256": sha256(output / "execution_plan.csv"),
        "evidence_boundary": (
            "no-data preparation artifact; cannot launch or accept formal attempts"
        ),
    }
    (output / "preparation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    output = args.output if args.output.is_absolute() else REPO / args.output
    protocols_root = (REPO / "results/protocols").resolve()
    output = output.resolve()
    if protocols_root not in output.parents:
        parser.error(f"output must be below {protocols_root}")
    try:
        manifest = prepare(protocol.resolve(), output)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(
        "PASS: no-data plan "
        f"cells={manifest['cell_count']} runs={manifest['scheduled_accepted_run_count']} "
        f"gate={manifest['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
