#!/usr/bin/env python3
"""Validate a no-data expanded Seven-QoS performance schedule."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from typing import Any

from generate_seven_qos_performance_protocol import (
    CELL_FIELDS,
    FAMILY_ORDER,
    SCHEDULE_FIELDS,
    canonical_json,
    load_json,
    sha256,
    split_cell,
)
from validate_seven_qos_execution_contracts import validate_contracts


REPO = Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def validate(protocol: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    design = load_json(protocol / "design_manifest.json")
    schedule = read_csv(protocol / "schedule.csv")
    cells = read_csv(protocol / "cell_manifest.csv")
    source_path = protocol / str(design.get("source_manifest", ""))
    amendment_path = protocol / str(design.get("amendment", ""))
    execution_contracts_path = protocol / str(
        design.get("execution_contracts", "")
    )
    source = load_json(source_path)

    require(design.get("status") == "DRAFT_NO_DATA", "status is not DRAFT_NO_DATA")
    require(
        design.get("execution_gate") == "BLOCKED_FORMAL_PROTOCOL_FINALIZATION",
        "execution gate is not blocked",
    )
    require(source.get("status") == "draft_no_data", "source status is not draft_no_data")
    require(sha256(source_path) == design.get("source_manifest_sha256"), "source SHA-256 mismatch")
    require(sha256(amendment_path) == design.get("amendment_sha256"), "amendment SHA-256 mismatch")
    require(
        sha256(execution_contracts_path)
        == design.get("execution_contracts_sha256"),
        "execution contracts SHA-256 mismatch",
    )
    execution_contracts = load_json(execution_contracts_path)
    try:
        contract_summary = validate_contracts(
            execution_contracts, source
        )
    except (KeyError, ValueError) as error:
        errors.append(f"execution contracts failed validation: {error}")
        contract_summary = {"cells": 0}
    require(
        contract_summary.get("cells") == 51,
        "execution contracts do not cover 51 cells",
    )
    require(
        execution_contracts.get("frozen_schedule_sha256")
        == design.get("schedule_sha256"),
        "execution contracts are not bound to this schedule",
    )
    require(sha256(protocol / "schedule.csv") == design.get("schedule_sha256"), "schedule SHA-256 mismatch")
    require(sha256(protocol / "cell_manifest.csv") == design.get("cell_manifest_sha256"), "cell manifest SHA-256 mismatch")
    require(tuple(schedule[0]) == SCHEDULE_FIELDS if schedule else False, "schedule header mismatch")
    require(tuple(cells[0]) == CELL_FIELDS if cells else False, "cell header mismatch")
    require(len(cells) == 51, f"cell count is {len(cells)}, expected 51")
    require(len(schedule) == 1530, f"run count is {len(schedule)}, expected 1530")
    require(len({row["run_token"] for row in schedule}) == len(schedule), "run tokens are not unique")
    require(
        [int(row["ordinal"]) for row in schedule] == list(range(1, len(schedule) + 1)),
        "ordinals are not gapless",
    )
    require(
        all(row["energy_status"] == "deferred_not_collected" for row in schedule),
        "schedule contains a non-deferred energy status",
    )
    energy = source.get("energy_policy", {})
    require(energy.get("mode") == "deferred_supplemental_metric", "energy mode is not deferred")
    require(energy.get("collected_in_current_campaign") is False, "energy collection is enabled")
    require(energy.get("energy_claims_allowed") is False, "energy claims are enabled")

    expected_cells: dict[tuple[str, str], dict[str, str]] = {}
    for family in FAMILY_ORDER:
        spec = source["new_families"][family]
        fixed_json = canonical_json(spec["fixed"])
        for cell in spec["cells"]:
            cell_id, role, configuration = split_cell(cell)
            expected_cells[(family, cell_id)] = {
                "family": family,
                "cell_id": cell_id,
                "role": role,
                "direction": str(spec["direction"]),
                "fixed_json": fixed_json,
                "configuration_json": canonical_json(configuration),
            }
    require(
        {(row["family"], row["cell_id"]): row for row in cells} == expected_cells,
        "cell manifest differs from source cells",
    )

    visits = int(source["visits_per_family"])
    replicates = int(source["accepted_runs_per_cell_per_visit"])
    by_family_visit: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    counts = Counter((row["family"], row["cell_id"]) for row in schedule)
    for row in schedule:
        key = (row["family"], row["cell_id"])
        require(key in expected_cells, f"unknown scheduled cell: {key}")
        if key in expected_cells:
            for field in ("role", "direction", "fixed_json", "configuration_json"):
                require(row[field] == expected_cells[key][field], f"{key}: {field} drift")
        by_family_visit[(row["family"], int(row["visit"]))].append(row)

    for key in expected_cells:
        require(counts[key] == int(source["accepted_runs_per_cell"]), f"{key}: scheduled {counts[key]} times")
    for family in FAMILY_ORDER:
        family_cells = {key[1] for key in expected_cells if key[0] == family}
        for visit in range(1, visits + 1):
            rows = by_family_visit[(family, visit)]
            per_cell = Counter(row["cell_id"] for row in rows)
            require(set(per_cell) == family_cells, f"{family} visit {visit}: incomplete block")
            require(all(value == replicates for value in per_cell.values()), f"{family} visit {visit}: replicate count mismatch")
            positions: dict[str, set[int]] = defaultdict(set)
            replicate_ids: dict[str, set[int]] = defaultdict(set)
            for row in rows:
                positions[row["cell_id"]].add(int(row["visit_position"]))
                replicate_ids[row["cell_id"]].add(int(row["replicate_within_visit"]))
            require(all(len(value) == 1 for value in positions.values()), f"{family} visit {visit}: cell position drift")
            require(
                {next(iter(value)) for value in positions.values()} == set(range(1, len(family_cells) + 1)),
                f"{family} visit {visit}: positions are not a permutation",
            )
            require(
                all(value == set(range(1, replicates + 1)) for value in replicate_ids.values()),
                f"{family} visit {visit}: replicate identifiers are incomplete",
            )

    forbidden = {"capture.pcapng", "serial.log", "accepted_cases.csv", "attempt_ledger.csv"}
    require(
        not any(path.name in forbidden for path in protocol.rglob("*")),
        "expanded draft contains result artifacts",
    )
    if errors:
        raise ValueError("; ".join(errors))
    return design, schedule, cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    try:
        design, schedule, cells = validate(protocol.resolve())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(
        f"PASS: cells={len(cells)} runs={len(schedule)} "
        f"schedule_sha256={design['schedule_sha256']} gate={design['execution_gate']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
