#!/usr/bin/env python3
"""Audit manuscript-facing claims against sealed formal result trees."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_result_tree_seal import verify as verify_result_tree


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def values_equal(actual, expected, tolerance):
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (int, float)):
        try:
            return math.isclose(
                float(actual), float(expected), rel_tol=0.0, abs_tol=tolerance
            )
        except (TypeError, ValueError):
            return False
    return actual == expected


def check_expected(label, actual, expected, tolerance, errors):
    for key, expected_value in expected.items():
        if key not in actual:
            errors.append(f"{label}: missing field {key!r}")
            continue
        if not values_equal(actual[key], expected_value, tolerance):
            errors.append(
                f"{label}: {key} expected {expected_value!r}, "
                f"found {actual[key]!r}"
            )


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def check_csv_assertion(root, assertion, tolerance, errors):
    path = root / assertion["path"]
    if not path.is_file():
        errors.append(f"missing CSV evidence: {path}")
        return
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selector = {key: str(value) for key, value in assertion["selector"].items()}
    matches = [
        row
        for row in rows
        if all(row.get(key) == value for key, value in selector.items())
    ]
    label = f"{path}:{selector}"
    if len(matches) != 1:
        errors.append(f"{label}: expected one row, found {len(matches)}")
        return
    check_expected(label, matches[0], assertion["expected"], tolerance, errors)


def parse_root_overrides(items):
    overrides = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"campaign root must use NAME=PATH: {item}")
        name, raw_path = item.split("=", 1)
        if not name or not raw_path:
            raise ValueError(f"campaign root must use NAME=PATH: {item}")
        overrides[name] = Path(raw_path).expanduser()
    return overrides


def audit(config_path, repo_root, root_overrides, verify_trees):
    config = read_json(config_path)
    if config.get("classification") != "paper_formal_claim_contract":
        raise ValueError("paper claim contract classification mismatch")
    tolerance = float(config.get("numeric_tolerance", 1e-9))
    errors = []
    campaign_reports = {}
    accepted_total = 0
    pcap_total = 0

    unknown_overrides = set(root_overrides) - set(config["campaigns"])
    if unknown_overrides:
        raise ValueError(
            "unknown campaign root override(s): " + ", ".join(sorted(unknown_overrides))
        )

    for name, campaign in config["campaigns"].items():
        root = root_overrides.get(name, repo_root / campaign["root"]).resolve()
        campaign_errors = []
        audit_path = root / campaign["audit"]["path"]
        if not audit_path.is_file():
            campaign_errors.append(f"missing audit evidence: {audit_path}")
            audit_data = {}
        else:
            audit_data = read_json(audit_path)
            check_expected(
                f"{name} audit",
                audit_data,
                campaign["audit"]["expected"],
                tolerance,
                campaign_errors,
            )
            accepted_total += int(audit_data.get("accepted_runs", 0))
            pcap_total += int(audit_data.get(campaign["audit"]["pcap_field"], 0))

        seal_path = root / "release_seal.json"
        if not seal_path.is_file():
            campaign_errors.append(f"missing release seal: {seal_path}")
        else:
            seal_data = read_json(seal_path)
            check_expected(
                f"{name} seal",
                seal_data,
                campaign["seal"],
                tolerance,
                campaign_errors,
            )

        for assertion in campaign.get("csv_assertions", []):
            check_csv_assertion(root, assertion, tolerance, campaign_errors)

        tree_report = None
        if verify_trees and seal_path.is_file():
            tree_report = verify_result_tree(root)
            if tree_report.get("status") != "PASS":
                campaign_errors.extend(
                    f"{name} tree: {error}" for error in tree_report.get("errors", [])
                )

        campaign_reports[name] = {
            "status": "PASS" if not campaign_errors else "FAIL",
            "root": str(root),
            "accepted_runs": audit_data.get("accepted_runs"),
            "unique_pcaps": audit_data.get(campaign["audit"]["pcap_field"]),
            "tree_verified": bool(tree_report and tree_report.get("status") == "PASS"),
            "errors": campaign_errors,
        }
        errors.extend(campaign_errors)

    aggregate_actual = {
        "accepted_runs": accepted_total,
        "unique_pcaps": pcap_total,
    }
    check_expected(
        "aggregate",
        aggregate_actual,
        config["aggregate"],
        tolerance,
        errors,
    )

    for assertion in config.get("prose_assertions", []):
        path = repo_root / assertion["path"]
        if not path.is_file():
            errors.append(f"missing prose file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for required in assertion.get("required", []):
            if required not in text:
                errors.append(f"{path}: missing required text {required!r}")

    for relative_manifest in config.get("artifact_manifests", []):
        manifest_path = repo_root / relative_manifest
        if not manifest_path.is_file():
            errors.append(f"missing artifact manifest: {manifest_path}")
            continue
        manifest = read_json(manifest_path)
        if manifest.get("classification") != "paper_figure_generation_manifest":
            errors.append(f"{manifest_path}: artifact classification mismatch")
        generator_path = repo_root / manifest.get("generator", "")
        if not generator_path.is_file():
            errors.append(f"{manifest_path}: missing generator {generator_path}")
        elif sha256_file(generator_path) != manifest.get("generator_sha256"):
            errors.append(f"{manifest_path}: generator hash mismatch")
        for output_name, expected in manifest.get("outputs", {}).items():
            output_path = manifest_path.parent / output_name
            if not output_path.is_file():
                errors.append(f"{manifest_path}: missing output {output_name}")
                continue
            if output_path.stat().st_size != expected.get("bytes"):
                errors.append(f"{manifest_path}: byte count mismatch for {output_name}")
            if sha256_file(output_path) != expected.get("sha256"):
                errors.append(f"{manifest_path}: hash mismatch for {output_name}")

    return {
        "schema_version": 1,
        "classification": "paper_formal_claim_audit",
        "status": "PASS" if not errors else "FAIL",
        "config": str(config_path.resolve()),
        "aggregate": aggregate_actual,
        "tree_verification_enabled": verify_trees,
        "campaigns": campaign_reports,
        "errors": errors,
    }


def main():
    repo_root = SCRIPT_DIR.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=repo_root / "docs/papers/formal_claims.json",
    )
    parser.add_argument(
        "--campaign-root",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="override a campaign evidence root; may be repeated",
    )
    parser.add_argument(
        "--skip-tree-verification",
        action="store_true",
        help="check seals and claim rows without hashing every sealed file",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        overrides = parse_root_overrides(args.campaign_root)
        report = audit(
            args.config,
            repo_root,
            overrides,
            verify_trees=not args.skip_tree_verification,
        )
    except (csv.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        report = {
            "schema_version": 1,
            "classification": "paper_formal_claim_audit",
            "status": "FAIL",
            "errors": [str(exc)],
        }

    output_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
    print(output_text, end="")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
