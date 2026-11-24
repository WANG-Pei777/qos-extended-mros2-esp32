#!/usr/bin/env python3
"""Audit the frozen telemetry runtime-overhead pilot end to end."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    campaign_dir = args.campaign if args.campaign.is_absolute() else REPO / args.campaign
    protocol_dir = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    output = args.output or campaign_dir / "audit" / "audit_report.json"
    output = output if output.is_absolute() else REPO / output
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    design_path = protocol_dir / "design_manifest.json"
    schedule_path = protocol_dir / "schedule.csv"
    campaign_path = campaign_dir / "campaign_manifest.json"
    design = json.loads(design_path.read_text())
    campaign = json.loads(campaign_path.read_text())
    schedule = load_csv(schedule_path)
    accepted = load_csv(campaign_dir / "accepted_runs.csv")
    attempts = load_csv(campaign_dir / "attempt_ledger.csv")
    analysis = json.loads((campaign_dir / "analysis/analysis_report.json").read_text())
    exclusions_path = campaign_dir / "protocol_exclusions.json"
    exclusions = json.loads(exclusions_path.read_text()).get("exclusions", [])

    require(design.get("status") == "FROZEN_NO_DATA", "protocol status changed")
    require(
        sha256(schedule_path) == design.get("schedule_sha256"),
        "protocol schedule SHA-256 mismatch",
    )
    require(
        campaign.get("protocol_schedule_sha256") == design.get("schedule_sha256"),
        "campaign schedule SHA-256 mismatch",
    )
    require(
        campaign.get("protocol_design_sha256") == sha256(design_path),
        "campaign design SHA-256 mismatch",
    )
    expected_runs = int(design.get("total_scheduled_runs", 0))
    require(len(schedule) == expected_runs, "schedule row count mismatch")
    require(len(accepted) == expected_runs, "accepted row count mismatch")

    accepted_by_run: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in accepted:
        accepted_by_run[row["run_id"]].append(row)
    schedule_by_run = {row["run_id"]: row for row in schedule}
    require(
        len(schedule_by_run) == len(schedule), "schedule contains duplicate run IDs"
    )

    validator_failures: list[dict[str, object]] = []
    firmware_counts: Counter[str] = Counter()
    cell_counts: Counter[str] = Counter()
    pair_modes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for scheduled in schedule:
        run_id = scheduled["run_id"]
        rows = accepted_by_run.get(run_id, [])
        require(len(rows) == 1, f"{run_id}: expected one accepted attempt")
        if len(rows) != 1:
            continue
        row = rows[0]
        for field in (
            "ordinal",
            "superblock",
            "pair_id",
            "pair_position",
            "system",
            "telemetry",
            "firmware_sha256",
        ):
            require(
                row.get(field) == scheduled.get(field),
                f"{run_id}: accepted {field} differs from schedule",
            )

        attempt_dir = campaign_dir / row["relative_path"]
        manifest_path = attempt_dir / "attempt_manifest.json"
        serial_path = attempt_dir / "serial.raw"
        require(manifest_path.is_file(), f"{run_id}: missing attempt manifest")
        require(serial_path.is_file(), f"{run_id}: missing serial log")
        if not manifest_path.is_file() or not serial_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        firmware = manifest.get("artifacts", {}).get("firmware", {})
        require(manifest.get("status") == "PASS", f"{run_id}: manifest is not PASS")
        require(
            firmware.get("sha256") == scheduled["firmware_sha256"],
            f"{run_id}: manifest firmware SHA-256 mismatch",
        )
        require(
            manifest.get("return_codes", {}).get("validator") == 0,
            f"{run_id}: recorded validator return code is not zero",
        )

        system = scheduled["system"]
        telemetry = scheduled["telemetry"]
        if telemetry == "on":
            command = [
                sys.executable,
                str(REPO / "scripts/experiment/validate_benchmark_telemetry_smoke.py"),
                str(serial_path),
                "--require-control-probe",
            ]
        else:
            command = [
                sys.executable,
                str(REPO / "scripts/experiment/validate_telemetry_off_smoke.py"),
                str(serial_path),
                "--system",
                system,
                "--require-control-probe",
            ]
        validation = subprocess.run(command, capture_output=True, text=True)
        if validation.returncode != 0:
            validator_failures.append(
                {
                    "run_id": run_id,
                    "relative_path": row["relative_path"],
                    "output": (validation.stdout + validation.stderr).strip(),
                }
            )
        firmware_counts[scheduled["firmware_sha256"]] += 1
        cell_counts[f"{system}_{telemetry}"] += 1
        pair_modes[(system, scheduled["pair_id"])].add(telemetry)

    require(not validator_failures, "one or more accepted logs failed revalidation")
    require(
        dict(cell_counts) == design.get("counts"),
        "accepted system/mode counts differ from design",
    )
    for system in ("mros2qos", "upstream", "microros"):
        system_pairs = [
            modes for (pair_system, _), modes in pair_modes.items() if pair_system == system
        ]
        require(
            len(system_pairs) == design.get("pairs_per_system"),
            f"{system}: pair count mismatch",
        )
        require(
            all(modes == {"on", "off"} for modes in system_pairs),
            f"{system}: one or more pairs lack on/off",
        )
        for mode in ("on", "off"):
            expected_sha = design["artifacts"][system][mode]["firmware_sha256"]
            require(
                firmware_counts[expected_sha] == design["counts"][f"{system}_{mode}"],
                f"{system}/{mode}: firmware use count mismatch",
            )

    attempt_status_counts = Counter(row["status"] for row in attempts)
    fatal_attempts = [row for row in attempts if row["fatal_gate_failure"] != "0"]
    require(not fatal_attempts, "attempt ledger contains fatal gate failures")
    attempts_by_path = {row["relative_path"]: row for row in attempts}
    for exclusion in exclusions:
        relative_path = exclusion["relative_path"]
        require(relative_path in attempts_by_path, f"missing excluded attempt {relative_path}")
        if relative_path in attempts_by_path:
            require(
                attempts_by_path[relative_path]["status"]
                == exclusion["classification"],
                f"excluded attempt classification mismatch: {relative_path}",
            )

    require(analysis.get("status") == "COMPLETE", "analysis is not COMPLETE")
    require(analysis.get("accepted_runs") == expected_runs, "analysis run count mismatch")
    require(analysis.get("overall_cpu_gate_pass") is True, "overall CPU gate failed")
    for system, metrics in analysis.get("systems", {}).items():
        require(metrics.get("accepted_on") == 10, f"{system}: analysis on count mismatch")
        require(metrics.get("accepted_off") == 10, f"{system}: analysis off count mismatch")
        require(metrics.get("complete_pairs") == 10, f"{system}: analysis pair count mismatch")
        require(
            metrics.get("all_delivery_200_of_200") is True,
            f"{system}: analysis delivery gate failed",
        )
        require(metrics.get("cpu_gate_pass") is True, f"{system}: CPU gate failed")
        require(
            metrics.get("maximum_sample_control_agreement_pp", 1.0) <= 0.5,
            f"{system}: sample/control agreement exceeds 0.5 pp",
        )

    amendment_checks = []
    for amendment in campaign.get("protocol_amendments", []):
        path = REPO / amendment["path"]
        matches = path.is_file() and sha256(path) == amendment.get("sha256")
        require(matches, f"amendment SHA-256 mismatch: {amendment['id']}")
        amendment_checks.append({"id": amendment["id"], "sha256_match": matches})
        for key in ("validator", "regression_test"):
            record = amendment.get(key)
            if record:
                artifact = REPO / record["path"]
                artifact_matches = artifact.is_file() and sha256(artifact) == record.get("sha256")
                require(
                    artifact_matches,
                    f"{amendment['id']} {key} SHA-256 mismatch",
                )

    report = {
        "schema_version": 1,
        "classification": "telemetry_runtime_overhead_pilot_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "campaign": str(campaign_dir.relative_to(REPO)),
        "protocol": str(protocol_dir.relative_to(REPO)),
        "scheduled_runs": len(schedule),
        "accepted_runs": len(accepted),
        "accepted_cell_counts": dict(sorted(cell_counts.items())),
        "revalidated_logs": len(accepted) - len(validator_failures),
        "validator_failures": validator_failures,
        "attempt_rows": len(attempts),
        "attempt_status_counts": dict(sorted(attempt_status_counts.items())),
        "fatal_attempts": len(fatal_attempts),
        "protocol_exclusions": len(exclusions),
        "amendment_checks": amendment_checks,
        "analysis_status": analysis.get("status"),
        "overall_cpu_gate_pass": analysis.get("overall_cpu_gate_pass"),
        "errors": errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"{report['status']}: accepted={len(accepted)}/{len(schedule)} "
        f"revalidated={report['revalidated_logs']} attempts={len(attempts)} "
        f"exclusions={len(exclusions)}"
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
