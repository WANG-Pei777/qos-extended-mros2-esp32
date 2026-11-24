#!/usr/bin/env python3
"""Validate the draft Seven-QoS performance and deterministic manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PERFORMANCE = (
    ROOT / "docs" / "benchmark" / "seven_qos_formal_cells_draft.json"
)
DEFAULT_DETERMINISTIC = (
    ROOT / "docs" / "benchmark" / "seven_qos_deterministic_cases_draft.json"
)

EXPECTED_FAMILY_COUNTS = {
    "history_depth": 9,
    "durability": 8,
    "deadline": 9,
    "lifespan": 8,
    "liveliness": 8,
    "resource_limits": 9,
}

INTERACTION_FACTORS = {
    "history_depth": ("depth", "burst_size", "loss_pct"),
    "deadline": ("deadline_ms", "publish_period_ms", "delay_ms"),
    "lifespan": ("lifespan_ms", "release_delay_ms"),
    "liveliness": ("lease_s", "outage_s"),
    "resource_limits": ("max_samples", "payload_bytes", "publish_rate_hz"),
}


class ProtocolError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"cannot load {path}: {exc}") from exc
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def factor_tuple(cell: dict[str, Any], factors: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(cell.get(name) for name in factors)


def validate_interaction_paths(
    family_name: str, family: dict[str, Any], factors: tuple[str, ...]
) -> None:
    cells = family["cells"]
    anchors = [cell for cell in cells if cell.get("role") == "anchor"]
    require(len(anchors) == 1, f"{family_name}: expected exactly one anchor")
    anchor = anchors[0]

    observed = {
        factor_tuple(cell, factors): cell
        for cell in cells
        if cell.get("role") != "interaction_corner"
    }
    for corner in (cell for cell in cells if cell.get("role") == "interaction_corner"):
        changed = [name for name in factors if corner.get(name) != anchor.get(name)]
        require(
            len(changed) >= 2,
            f"{family_name}/{corner['id']}: corner changes fewer than two factors",
        )
        for changed_name in changed:
            main_values = {name: anchor.get(name) for name in factors}
            main_values[changed_name] = corner.get(changed_name)
            key = tuple(main_values[name] for name in factors)
            require(
                key in observed,
                f"{family_name}/{corner['id']}: missing one-factor main cell "
                f"for {changed_name}={corner.get(changed_name)!r}",
            )


def validate_performance(data: dict[str, Any]) -> tuple[int, int]:
    require(data.get("status") == "draft_no_data", "performance status is not draft_no_data")
    n_per_cell = data.get("accepted_runs_per_cell")
    visits = data.get("visits_per_family")
    per_visit = data.get("accepted_runs_per_cell_per_visit")
    require(isinstance(n_per_cell, int) and n_per_cell > 0, "invalid accepted_runs_per_cell")
    require(visits * per_visit == n_per_cell, "visit schedule does not produce N per cell")

    families = data.get("new_families")
    require(isinstance(families, dict), "new_families must be an object")
    require(set(families) == set(EXPECTED_FAMILY_COUNTS), "unexpected performance family set")

    all_ids: list[str] = []
    total_cells = 0
    for family_name, expected_count in EXPECTED_FAMILY_COUNTS.items():
        family = families[family_name]
        cells = family.get("cells")
        require(isinstance(cells, list), f"{family_name}: cells must be a list")
        require(len(cells) == expected_count, f"{family_name}: expected {expected_count} cells")
        ids = [cell.get("id") for cell in cells]
        require(all(isinstance(cell_id, str) and cell_id for cell_id in ids), f"{family_name}: invalid cell id")
        require(len(ids) == len(set(ids)), f"{family_name}: duplicate cell id")
        all_ids.extend(ids)
        total_cells += len(cells)

        if family_name in INTERACTION_FACTORS:
            validate_interaction_paths(
                family_name, family, INTERACTION_FACTORS[family_name]
            )

    require(len(all_ids) == len(set(all_ids)), "cell ids are not globally unique")
    total_runs = total_cells * n_per_cell
    require(total_cells == data.get("expected_new_cells"), "performance cell total mismatch")
    require(total_runs == data.get("expected_new_accepted_runs"), "performance run total mismatch")
    require(
        total_runs + 1740 == data.get("expected_combined_new_runs_after_h2b"),
        "combined post-H2B run budget mismatch",
    )
    return total_cells, total_runs


def validate_deterministic(data: dict[str, Any]) -> tuple[int, int, int]:
    require(data.get("status") == "draft_no_data", "deterministic status is not draft_no_data")
    require(data.get("performance_pooling_forbidden") is True, "performance pooling must be forbidden")

    matrices = data.get("compatibility_matrices")
    require(isinstance(matrices, list), "compatibility_matrices must be a list")
    matrix_ids = [matrix.get("id") for matrix in matrices]
    require(len(matrix_ids) == len(set(matrix_ids)), "duplicate compatibility matrix id")

    expanded = 0
    for matrix in matrices:
        directions = matrix.get("directions")
        creation_orders = matrix.get("endpoint_creation_orders")
        pairs = matrix.get("pairs")
        require(isinstance(directions, list) and directions, f"{matrix.get('id')}: no directions")
        require(isinstance(creation_orders, list) and creation_orders, f"{matrix.get('id')}: no creation orders")
        require(isinstance(pairs, list) and pairs, f"{matrix.get('id')}: no pairs")
        require(all(isinstance(pair.get("expected_match"), bool) for pair in pairs), f"{matrix.get('id')}: invalid expected_match")
        matrix_count = len(directions) * len(creation_orders) * len(pairs)
        require(matrix_count == matrix.get("expected_expanded_cases"), f"{matrix.get('id')}: expanded count mismatch")
        expanded += matrix_count

    mechanism = data.get("mechanism_cases")
    require(isinstance(mechanism, list), "mechanism_cases must be a list")
    mechanism_ids = [case.get("id") for case in mechanism]
    require(all(isinstance(case_id, str) and case_id for case_id in mechanism_ids), "invalid mechanism case id")
    require(len(mechanism_ids) == len(set(mechanism_ids)), "duplicate mechanism case id")

    mechanism_count = len(mechanism)
    require(expanded == data.get("expected_expanded_compatibility_cases"), "compatibility total mismatch")
    require(mechanism_count == data.get("expected_mechanism_cases"), "mechanism total mismatch")
    require(expanded + mechanism_count == data.get("expected_total_cases"), "deterministic total mismatch")
    return expanded, mechanism_count, expanded + mechanism_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--performance", type=Path, default=DEFAULT_PERFORMANCE)
    parser.add_argument("--deterministic", type=Path, default=DEFAULT_DETERMINISTIC)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        performance_cells, performance_runs = validate_performance(
            load_json(args.performance)
        )
        compatibility, mechanism, deterministic_total = validate_deterministic(
            load_json(args.deterministic)
        )
    except ProtocolError as exc:
        print(f"FAIL: {exc}")
        return 1

    print(
        "PASS: "
        f"performance={performance_cells} cells/{performance_runs} runs; "
        f"deterministic={compatibility} compatibility+{mechanism} mechanism="
        f"{deterministic_total} cases"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
