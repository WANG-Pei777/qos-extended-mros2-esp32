#!/usr/bin/env python3
"""Expand the Seven-QoS deterministic draft into a reviewable no-data schedule."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_seven_qos_protocol import load_json, validate_deterministic


REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO / "docs/benchmark/seven_qos_deterministic_cases_draft.json"
DEFAULT_PERFORMANCE = REPO / "docs/benchmark/seven_qos_formal_cells_draft.json"
DEFAULT_OUTPUT = REPO / "results/protocols/20260717_seven_qos_deterministic_expanded_draft"
FIELDS = (
    "ordinal",
    "case_id",
    "case_type",
    "source_id",
    "policy",
    "direction",
    "endpoint_creation_order",
    "level",
    "configuration_json",
    "expected_json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def slug(value: str) -> str:
    return value.lower().replace("_", "-")


def expand_cases(data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for matrix in data["compatibility_matrices"]:
        pair_width = len(str(len(matrix["pairs"])))
        for direction in matrix["directions"]:
            for creation_order in matrix["endpoint_creation_orders"]:
                for pair_index, pair in enumerate(matrix["pairs"], start=1):
                    configuration = {
                        key: value for key, value in pair.items() if key != "expected_match"
                    }
                    if "kind" in matrix:
                        configuration["kind"] = matrix["kind"]
                    case_id = "-".join(
                        (
                            matrix["id"],
                            slug(direction),
                            slug(creation_order),
                            f"p{pair_index:0{pair_width}d}",
                        )
                    )
                    rows.append(
                        {
                            "case_id": case_id,
                            "case_type": "compatibility",
                            "source_id": matrix["id"],
                            "policy": matrix["policy"],
                            "direction": direction,
                            "endpoint_creation_order": creation_order,
                            "level": "hardware",
                            "configuration_json": canonical(configuration),
                            "expected_json": canonical(
                                {"expected_match": pair["expected_match"]}
                            ),
                        }
                    )
    for case in data["mechanism_cases"]:
        rows.append(
            {
                "case_id": case["id"],
                "case_type": "mechanism",
                "source_id": case["id"],
                "policy": case["policy"],
                "direction": "",
                "endpoint_creation_order": "",
                "level": case["level"],
                "configuration_json": canonical({}),
                "expected_json": canonical({"statement": case["expected"]}),
            }
        )
    return [{"ordinal": str(index), **row} for index, row in enumerate(rows, start=1)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--performance", type=Path, default=DEFAULT_PERFORMANCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.source.resolve()
    performance = args.performance.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output already exists: {output}")

    source_data = load_json(source)
    compatibility_count, mechanism_count, total_count = validate_deterministic(
        source_data
    )
    rows = expand_cases(source_data)
    if len(rows) != total_count:
        raise SystemExit("expanded row count differs from validated source")
    case_ids = [row["case_id"] for row in rows]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("expanded case IDs are not unique")

    output.mkdir(parents=True)
    schedule_path = output / "schedule.csv"
    with schedule_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    policy_counts = Counter(row["policy"] for row in rows)
    manifest = {
        "schema_version": 1,
        "classification": "seven_qos_deterministic_expanded_protocol_draft",
        "status": "DRAFT_EXPANDED_NO_DATA",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_deterministic_path": str(source.relative_to(REPO)),
        "source_deterministic_sha256": sha256(source),
        "source_performance_path": str(performance.relative_to(REPO)),
        "source_performance_sha256": sha256(performance),
        "schedule_sha256": sha256(schedule_path),
        "compatibility_cases": compatibility_count,
        "mechanism_cases": mechanism_count,
        "total_cases": total_count,
        "policy_counts": dict(sorted(policy_counts.items())),
        "execution_order": "canonical source order; deterministic cases are not pooled as performance observations",
        "performance_pooling_forbidden": True,
        "execution_gate_status": "BLOCKED_HARNESS_BINDING",
        "remaining_before_freeze": [
            "bind each case to exact firmware and host executable hashes",
            "bind machine-readable assertions and timeout semantics",
            "pass one excluded smoke per firmware family",
            "freeze board/AP/host identities and immutable attempt ledger rules",
        ],
    }
    (output / "design_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: expanded={total_count} compatibility={compatibility_count} "
        f"mechanism={mechanism_count} schedule_sha256={manifest['schedule_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
