#!/usr/bin/env python3
"""Validate fail-closed execution contracts for the Seven-QoS schedule."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from generate_seven_qos_performance_protocol import FAMILY_ORDER, load_json


REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO / "docs/benchmark/seven_qos_formal_cells_draft.json"
DEFAULT_CONTRACTS = (
    REPO / "docs/benchmark/seven_qos_performance_execution_contracts.json"
)
VALID_STATES = {
    "blocked_missing_family_harness",
    "smoke_gate_passed_formal_blocked",
}


def validate_contracts(
    contracts: dict[str, Any], source: dict[str, Any]
) -> dict[str, int]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(contracts.get("schema_version") == 1, "unexpected schema version")
    require(
        contracts.get("status")
        == "family_harness_smoke_complete_formal_blocked",
        "unexpected contract status",
    )
    require(
        contracts.get("formal_launch_allowed") is False,
        "root formal launch gate must remain false",
    )

    family_contracts = contracts.get("family_contracts", {})
    require(
        set(family_contracts) == set(FAMILY_ORDER),
        "family contract set does not match the frozen family order",
    )

    cell_count = 0
    smoke_ready = 0
    for family in FAMILY_ORDER:
        if family not in family_contracts:
            continue
        contract = family_contracts[family]
        spec = source["new_families"][family]
        expected_cells = [str(cell["id"]) for cell in spec["cells"]]
        expected_fields = sorted(
            {
                key
                for cell in spec["cells"]
                for key in cell
                if key not in {"id", "role"}
            }
        )
        cell_count += len(expected_cells)
        require(
            contract.get("cell_ids") == expected_cells,
            f"{family}: cell IDs differ from the frozen source",
        )
        require(
            contract.get("direction") == spec["direction"],
            f"{family}: direction differs from the frozen source",
        )
        require(
            sorted(contract.get("required_configuration_fields", []))
            == expected_fields,
            f"{family}: required configuration fields are incomplete",
        )
        expected_sides = (
            ("board", "host")
            if spec["direction"] == "b2h"
            else ("host", "board")
        )
        require(
            (contract.get("publisher_side"), contract.get("subscriber_side"))
            == expected_sides,
            f"{family}: endpoint sides disagree with direction",
        )
        require(
            contract.get("formal_launch_allowed") is False,
            f"{family}: formal launch gate must remain false",
        )
        state = contract.get("implementation_state")
        require(state in VALID_STATES, f"{family}: unknown implementation state")
        require(
            bool(contract.get("startup_order")),
            f"{family}: startup order is missing",
        )
        require(
            bool(contract.get("impairment_locus")),
            f"{family}: impairment locus is missing",
        )
        require(
            bool(contract.get("required_observations")),
            f"{family}: required observations are missing",
        )
        if state == "smoke_gate_passed_formal_blocked":
            smoke_ready += 1
            require(
                family in {
                    "history_depth",
                    "durability",
                    "deadline",
                    "lifespan",
                    "liveliness",
                    "resource_limits",
                },
                f"{family}: family has no completed smoke gate",
            )

    deadline = family_contracts.get("deadline", {})
    require(
        deadline.get("smoke_gates")
        == ["DL01_positive_event", "DL02_zero_event"],
        "Deadline smoke gate pair is incomplete",
    )
    lifespan = family_contracts.get("lifespan", {})
    require(
        lifespan.get("smoke_gates")
        == ["LS01_disabled_full_delivery", "LS02_expired_zero_delivery"],
        "Lifespan smoke gate pair is incomplete",
    )
    resource_limits = family_contracts.get("resource_limits", {})
    require(
        resource_limits.get("impairment_locus")
        == "host_egress_ack_suppression_only",
        "Resource Limits ACK suppression must use host-to-board egress",
    )
    require(
        resource_limits.get("smoke_gates")
        == [
            "R00_within_capacity_full_delivery",
            "R01_one_over_capacity_saturation_recovery",
            "R01_external_ack_suppression_efficacy",
        ],
        "Resource Limits smoke gates are incomplete",
    )
    history_depth = family_contracts.get("history_depth", {})
    require(
        history_depth.get("smoke_gates")
        == [
            "HSM05_keep_last_suffix",
            "HSM20_complete_burst",
            "HSM20_ingress_loss5_efficacy",
        ],
        "History/Depth smoke gates are incomplete",
    )
    durability = family_contracts.get("durability", {})
    require(
        durability.get("smoke_gates")
        == ["DSMV_no_prejoin_replay", "DSMTL_complete_prejoin_replay"],
        "Durability smoke gate pair is incomplete",
    )
    liveliness = family_contracts.get("liveliness", {})
    require(
        liveliness.get("smoke_gates")
        == ["LVSM_SHORT_no_transition", "LVSM_LONG_lost_recovered"],
        "Liveliness smoke gate pair is incomplete",
    )
    require(cell_count == 51, f"contract covers {cell_count} cells, expected 51")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "families": len(family_contracts),
        "cells": cell_count,
        "smoke_ready_families": smoke_ready,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    try:
        summary = validate_contracts(
            load_json(args.contracts.resolve()), load_json(args.source.resolve())
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(
        "PASS: "
        f"families={summary['families']} cells={summary['cells']} "
        f"smoke_ready_families={summary['smoke_ready_families']} "
        "formal_launch_allowed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
