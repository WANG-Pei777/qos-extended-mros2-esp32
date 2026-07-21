#!/usr/bin/env python3
# flake8: noqa: E501
"""Validate the frozen 48-case Seven-QoS compatibility protocol."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from freeze_seven_qos_compatibility_protocol import canonical_sha256
from generate_seven_qos_deterministic_protocol import FIELDS as SOURCE_FIELDS
from run_seven_qos_compatibility_case import (
    load_frozen_bundle,
    resolve_case,
    sha256,
)


REPO = Path(__file__).resolve().parents[2]
FROZEN_FIELDS = SOURCE_FIELDS + (
    "artifact_manifest_relative_path",
    "artifact_manifest_sha256",
    "firmware_sha256",
)


def validate_protocol(
    protocol: Path, *, verify_bound_sources: bool = True
) -> tuple[dict, list[dict[str, str]]]:
    protocol = protocol.resolve()
    design_path = protocol / "design_manifest.json"
    schedule_path = protocol / "schedule.csv"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    errors = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(design.get("status") == "FROZEN_NO_DATA", "protocol is not FROZEN_NO_DATA")
    require(
        design.get("classification")
        == "seven_qos_compatibility_formal_preregistration",
        "unexpected protocol classification",
    )
    require(
        sha256(schedule_path) == design.get("schedule_sha256"),
        "schedule SHA-256 mismatch",
    )
    require(
        sha256(protocol / "source/expanded_schedule.csv")
        == design.get("source_expanded_schedule_sha256"),
        "copied expanded schedule SHA-256 mismatch",
    )
    require(
        sha256(protocol / "source/expanded_design_manifest.json")
        == design.get("source_expanded_design_sha256"),
        "copied expanded design SHA-256 mismatch",
    )
    with schedule_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == FROZEN_FIELDS, "schedule schema mismatch")
        rows = list(reader)
    require(len(rows) == 48, "schedule must contain 48 cases")
    require(
        [int(row["ordinal"]) for row in rows] == list(range(1, 49)),
        "schedule ordinals are not canonical 1..48",
    )
    require(len({row["case_id"] for row in rows}) == 48, "duplicate case IDs")

    for row in rows:
        try:
            resolve_case(row)
            relative = row["artifact_manifest_relative_path"]
            manifest_path = (protocol / relative).resolve()
            require(manifest_path.is_relative_to(protocol), f"{row['case_id']}: artifact path escapes protocol")
            require(manifest_path.is_file(), f"{row['case_id']}: missing artifact manifest")
            if not manifest_path.is_file():
                continue
            require(
                sha256(manifest_path) == row["artifact_manifest_sha256"],
                f"{row['case_id']}: artifact manifest SHA-256 mismatch",
            )
            manifest = load_frozen_bundle(manifest_path.parent, row["case_id"])
            source_row = {field: row[field] for field in SOURCE_FIELDS}
            require(
                manifest.get("schedule_row_sha256") == canonical_sha256(source_row),
                f"{row['case_id']}: frozen schedule-row hash mismatch",
            )
            require(
                manifest.get("app_sha256") == row["firmware_sha256"],
                f"{row['case_id']}: app firmware SHA-256 mismatch",
            )
        except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
            errors.append(f"{row.get('case_id', '<unknown>')}: {error}")

    require(
        dict(sorted(Counter(row["policy"] for row in rows).items()))
        == design.get("policy_counts"),
        "policy counts mismatch",
    )
    require(
        dict(sorted(Counter(row["direction"] for row in rows).items()))
        == design.get("direction_counts"),
        "direction counts mismatch",
    )
    require(
        dict(sorted(Counter(row["endpoint_creation_order"] for row in rows).items()))
        == design.get("order_counts"),
        "endpoint-order counts mismatch",
    )
    match_counts = Counter(
        str(json.loads(row["expected_json"])["expected_match"]).lower()
        for row in rows
    )
    require(
        dict(sorted(match_counts.items())) == design.get("expected_match_counts"),
        "expected-match counts mismatch",
    )

    for label, record in design.get("host_artifacts", {}).items():
        if not label.endswith("_relative_path"):
            continue
        prefix = label.removesuffix("_relative_path")
        path = (protocol / record).resolve()
        require(path.is_relative_to(protocol), f"host {prefix} path escapes protocol")
        require(path.is_file(), f"missing frozen host {prefix}")
        if path.is_file():
            require(
                sha256(path) == design["host_artifacts"].get(prefix + "_sha256"),
                f"frozen host {prefix} SHA-256 mismatch",
            )

    snapshot = design.get("environment_snapshot", {})
    snapshot_root = (protocol / snapshot.get("relative_root", "")).resolve()
    require(snapshot_root.is_relative_to(protocol), "environment path escapes protocol")
    for relative, expected in snapshot.get("files", {}).items():
        path = (snapshot_root / relative).resolve()
        require(path.is_relative_to(snapshot_root), "environment file path escapes snapshot")
        require(path.is_file(), f"missing environment snapshot file: {relative}")
        if path.is_file():
            require(sha256(path) == expected, f"environment snapshot drift: {relative}")

    if verify_bound_sources:
        for relative, expected in design.get("bound_source_files", {}).items():
            path = REPO / relative
            require(path.is_file(), f"missing bound source: {relative}")
            if path.is_file():
                require(sha256(path) == expected, f"bound source drift: {relative}")
        for record in design.get("excluded_prefreeze_smoke_releases", []):
            path = REPO / record["verification_path"]
            require(path.is_file(), f"missing smoke verification: {path}")
            if path.is_file():
                require(
                    sha256(path) == record["verification_sha256"],
                    f"smoke verification drift: {path}",
                )
        verification = REPO / snapshot.get("source_verification_path", "")
        require(verification.is_file(), "missing environment release verification")
        if verification.is_file():
            require(
                sha256(verification) == snapshot.get("source_verification_sha256"),
                "environment release verification drift",
            )

    if errors:
        raise ValueError("; ".join(errors))
    return design, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("protocol", type=Path)
    parser.add_argument("--skip-bound-source-check", action="store_true")
    args = parser.parse_args()
    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    try:
        design, rows = validate_protocol(
            protocol,
            verify_bound_sources=not args.skip_bound_source_check,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    print(
        f"PASS: frozen_cases={len(rows)} schedule_sha256={design['schedule_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
