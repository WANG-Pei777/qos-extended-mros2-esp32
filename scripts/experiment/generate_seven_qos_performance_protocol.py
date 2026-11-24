#!/usr/bin/env python3
"""Expand the Seven-QoS performance draft into a no-data randomized schedule."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO / "docs/benchmark/seven_qos_formal_cells_draft.json"
DEFAULT_AMENDMENT = (
    REPO / "docs/benchmark/SEVEN_QOS_PERFORMANCE_PROTOCOL_AMENDMENT_13.md"
)
DEFAULT_IDENTITY_AMENDMENT = (
    REPO / "docs/benchmark/SEVEN_QOS_PERFORMANCE_PROTOCOL_AMENDMENT_12.md"
)
DEFAULT_EXECUTION_CONTRACTS = (
    REPO / "docs/benchmark/seven_qos_performance_execution_contracts.json"
)
FAMILY_ORDER = (
    "history_depth",
    "durability",
    "deadline",
    "lifespan",
    "liveliness",
    "resource_limits",
)
SCHEDULE_FIELDS = (
    "ordinal",
    "run_token",
    "family",
    "family_ordinal",
    "visit",
    "visit_position",
    "replicate_within_visit",
    "cell_id",
    "role",
    "direction",
    "fixed_json",
    "configuration_json",
    "energy_status",
)
CELL_FIELDS = (
    "family",
    "cell_id",
    "role",
    "direction",
    "fixed_json",
    "configuration_json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def family_seed(seed: int, family: str) -> int:
    material = f"{seed}:{family}".encode("ascii")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def split_cell(cell: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    cell_id = str(cell["id"])
    role = str(cell["role"])
    configuration = {
        key: value for key, value in cell.items() if key not in {"id", "role"}
    }
    return cell_id, role, configuration


def expand_schedule(source: dict[str, Any], seed: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    visits = int(source["visits_per_family"])
    replicates = int(source["accepted_runs_per_cell_per_visit"])
    families = source["new_families"]
    rows: list[dict[str, str]] = []
    cells_out: list[dict[str, str]] = []
    ordinal = 0

    for family in FAMILY_ORDER:
        spec = families[family]
        direction = str(spec["direction"])
        fixed_json = canonical_json(spec["fixed"])
        cells = list(spec["cells"])
        for cell in cells:
            cell_id, role, configuration = split_cell(cell)
            cells_out.append({
                "family": family,
                "cell_id": cell_id,
                "role": role,
                "direction": direction,
                "fixed_json": fixed_json,
                "configuration_json": canonical_json(configuration),
            })

        rng = random.Random(family_seed(seed, family))
        family_ordinal = 0
        for visit in range(1, visits + 1):
            permutation = list(cells)
            rng.shuffle(permutation)
            for visit_position, cell in enumerate(permutation, start=1):
                cell_id, role, configuration = split_cell(cell)
                for replicate in range(1, replicates + 1):
                    ordinal += 1
                    family_ordinal += 1
                    rows.append({
                        "ordinal": str(ordinal),
                        "run_token": f"sqp-{ordinal:04d}",
                        "family": family,
                        "family_ordinal": str(family_ordinal),
                        "visit": str(visit),
                        "visit_position": str(visit_position),
                        "replicate_within_visit": str(replicate),
                        "cell_id": cell_id,
                        "role": role,
                        "direction": direction,
                        "fixed_json": fixed_json,
                        "configuration_json": canonical_json(configuration),
                        "energy_status": "deferred_not_collected",
                    })
    return rows, cells_out


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git_state() -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--short", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"commit": commit, "tracked_worktree_dirty": bool(status)}


def generate(
    source_path: Path,
    amendment_path: Path,
    identity_amendment_path: Path,
    execution_contracts_path: Path,
    output: Path,
    seed: int,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    source = load_json(source_path)
    rows, cells = expand_schedule(source, seed)
    output.mkdir(parents=True)
    (output / "source").mkdir()
    shutil.copy2(source_path, output / "source" / source_path.name)
    shutil.copy2(amendment_path, output / "source" / amendment_path.name)
    shutil.copy2(
        identity_amendment_path,
        output / "source" / identity_amendment_path.name,
    )
    shutil.copy2(
        execution_contracts_path,
        output / "source" / execution_contracts_path.name,
    )
    write_csv(output / "schedule.csv", SCHEDULE_FIELDS, rows)
    write_csv(output / "cell_manifest.csv", CELL_FIELDS, cells)

    design = {
        "schema_version": 1,
        "classification": "seven_qos_performance_expanded_draft",
        "status": "DRAFT_NO_DATA",
        "execution_gate": "BLOCKED_FORMAL_PROTOCOL_FINALIZATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_git": git_state(),
        "source_manifest": f"source/{source_path.name}",
        "source_manifest_sha256": sha256(output / "source" / source_path.name),
        "amendment": f"source/{amendment_path.name}",
        "amendment_sha256": sha256(output / "source" / amendment_path.name),
        "identity_amendment": f"source/{identity_amendment_path.name}",
        "identity_amendment_sha256": sha256(
            output / "source" / identity_amendment_path.name
        ),
        "execution_contracts": (
            f"source/{execution_contracts_path.name}"
        ),
        "execution_contracts_sha256": sha256(
            output / "source" / execution_contracts_path.name
        ),
        "randomization": {
            "algorithm": "python_random_mt19937_integer_seed_v1",
            "seed": seed,
            "family_seed_derivation": "sha256(seed:family) first 64 bits",
            "family_order": list(FAMILY_ORDER),
            "visits_per_family": int(source["visits_per_family"]),
            "accepted_runs_per_cell_per_visit": int(
                source["accepted_runs_per_cell_per_visit"]
            ),
        },
        "energy_policy": source["energy_policy"],
        "cell_count": len(cells),
        "scheduled_run_count": len(rows),
        "cell_manifest_sha256": sha256(output / "cell_manifest.csv"),
        "schedule_sha256": sha256(output / "schedule.csv"),
        "evidence_boundary": (
            "no-data schedule draft; not executable or acceptable as formal evidence"
        ),
    }
    (output / "design_manifest.json").write_text(
        json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return design


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--amendment", type=Path, default=DEFAULT_AMENDMENT)
    parser.add_argument(
        "--identity-amendment",
        type=Path,
        default=DEFAULT_IDENTITY_AMENDMENT,
    )
    parser.add_argument(
        "--execution-contracts", type=Path, default=DEFAULT_EXECUTION_CONTRACTS
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026072301)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else REPO / args.output
    design = generate(
        args.source.resolve(),
        args.amendment.resolve(),
        args.identity_amendment.resolve(),
        args.execution_contracts.resolve(),
        output.resolve(),
        args.seed,
    )
    print(
        f"PASS: cells={design['cell_count']} runs={design['scheduled_run_count']} "
        f"schedule_sha256={design['schedule_sha256']} gate={design['execution_gate']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
