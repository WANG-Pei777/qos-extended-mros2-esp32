#!/usr/bin/env python3
# flake8: noqa: E501
"""Build evidence-facing tables for a sealed compatibility campaign."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from run_seven_qos_compatibility_case import sha256
from validate_seven_qos_compatibility_frozen import validate_protocol
from verify_result_tree_seal import verify


REPO = Path(__file__).resolve().parents[2]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def configuration_label(row: dict[str, str]) -> tuple[str, str]:
    config = json.loads(row["configuration_json"])
    if row["policy"] in {"reliability", "durability"}:
        return str(config["offered"]), str(config["requested"])
    if row["policy"] == "deadline":
        return f"{config['offered_ms']} ms", f"{config['requested_ms']} ms"
    if row["policy"] == "liveliness":
        return (
            f"automatic / {config['offered_lease_ms']} ms",
            f"automatic / {config['requested_lease_ms']} ms",
        )
    raise ValueError(f"unsupported policy: {row['policy']}")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    campaign = args.campaign if args.campaign.is_absolute() else REPO / args.campaign
    protocol = args.protocol if args.protocol.is_absolute() else REPO / args.protocol
    output = args.output if args.output.is_absolute() else REPO / args.output
    if output.exists():
        parser.error(f"output already exists: {output}")

    protocol_verification = verify(protocol)
    campaign_verification = verify(campaign)
    audit = json.loads(
        (campaign / "audit/audit_report.json").read_text(encoding="utf-8")
    )
    if not all(
        value.get("status") == "PASS"
        for value in (protocol_verification, campaign_verification, audit)
    ):
        raise SystemExit("protocol, campaign, and audit must all be verified PASS")
    try:
        design, schedule = validate_protocol(
            protocol, verify_bound_sources=False
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"frozen protocol validation failed: {error}") from error

    campaign_manifest = json.loads(
        (campaign / "campaign_manifest.json").read_text(encoding="utf-8")
    )
    if campaign_manifest.get("protocol_design_sha256") != sha256(
        protocol / "design_manifest.json"
    ):
        raise SystemExit("campaign does not bind the supplied protocol")
    if campaign_manifest.get("protocol_schedule_sha256") != design.get(
        "schedule_sha256"
    ):
        raise SystemExit("campaign schedule binding differs from the protocol")

    accepted = read_csv(campaign / "accepted_cases.csv")
    attempts = read_csv(campaign / "attempt_ledger.csv")
    pcap_inventory = read_csv(campaign / "audit/pcap_inventory.csv")
    accepted_by_case = {row["case_id"]: row for row in accepted}
    attempts_by_case = defaultdict(list)
    for row in attempts:
        attempts_by_case[row["case_id"]].append(row)
    if len(schedule) != 48 or len(accepted_by_case) != 48:
        raise SystemExit("expected 48 scheduled and accepted cases")

    matrix_groups = defaultdict(list)
    for row in schedule:
        offered, requested = configuration_label(row)
        expected = json.loads(row["expected_json"])["expected_match"]
        matrix_groups[(row["policy"], offered, requested, expected)].append(row)

    matrix_rows = []
    for (policy, offered, requested, expected), rows in sorted(
        matrix_groups.items()
    ):
        statuses = {}
        first_attempt_passes = 0
        for row in rows:
            case_id = row["case_id"]
            accepted_row = accepted_by_case.get(case_id)
            first_attempt = (
                len(attempts_by_case[case_id]) == 1
                and attempts_by_case[case_id][0]["status"] == "PASS"
            )
            first_attempt_passes += int(first_attempt)
            key = f"{row['direction']}_{row['endpoint_creation_order']}"
            statuses[key] = "PASS" if accepted_row else "MISSING"
        matrix_rows.append(
            {
                "policy": policy,
                "offered": offered,
                "requested": requested,
                "expected_match": int(expected),
                "scheduled_cases": len(rows),
                "accepted_cases": sum(
                    row["case_id"] in accepted_by_case for row in rows
                ),
                "first_attempt_passes": first_attempt_passes,
                "b2h_remote_first": statuses.get("b2h_remote_first", "MISSING"),
                "b2h_local_first": statuses.get("b2h_local_first", "MISSING"),
                "h2b_remote_first": statuses.get("h2b_remote_first", "MISSING"),
                "h2b_local_first": statuses.get("h2b_local_first", "MISSING"),
            }
        )

    policy_rows = []
    for policy in ("reliability", "durability", "deadline", "liveliness"):
        rows = [row for row in schedule if row["policy"] == policy]
        compatible = sum(
            json.loads(row["expected_json"])["expected_match"] for row in rows
        )
        policy_rows.append(
            {
                "policy": policy,
                "scheduled_cases": len(rows),
                "compatible_cases": compatible,
                "incompatible_cases": len(rows) - compatible,
                "accepted_cases": sum(
                    row["case_id"] in accepted_by_case for row in rows
                ),
                "first_attempt_passes": sum(
                    len(attempts_by_case[row["case_id"]]) == 1
                    and attempts_by_case[row["case_id"]][0]["status"] == "PASS"
                    for row in rows
                ),
                "directions": len({row["direction"] for row in rows}),
                "endpoint_creation_orders": len(
                    {row["endpoint_creation_order"] for row in rows}
                ),
            }
        )

    output.mkdir(parents=True)
    write_csv(output / "compatibility_matrix.csv", matrix_rows)
    write_csv(output / "policy_summary.csv", policy_rows)
    pcap_copy = output / "pcap_inventory.csv"
    with pcap_copy.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pcap_inventory[0]))
        writer.writeheader()
        writer.writerows(pcap_inventory)

    attempt_counts = Counter(row["status"] for row in attempts)
    first_attempt_passes = sum(
        len(rows) == 1 and rows[0]["status"] == "PASS"
        for rows in attempts_by_case.values()
    )
    compatible_cases = sum(
        json.loads(row["expected_json"])["expected_match"] for row in schedule
    )
    incompatible_cases = len(schedule) - compatible_cases
    if first_attempt_passes == len(schedule):
        attempt_statement = "All cases passed on their first attempt."
    else:
        attempt_statement = (
            f"{first_attempt_passes} of {len(schedule)} cases passed on their "
            "first attempt; all retained attempts remain in the campaign ledger."
        )
    analysis_source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    report = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_evidence_analysis",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "scheduled_cases": len(schedule),
        "accepted_cases": len(accepted),
        "first_attempt_passes": first_attempt_passes,
        "attempt_status_counts": dict(sorted(attempt_counts.items())),
        "compatible_cases": compatible_cases,
        "incompatible_cases": incompatible_cases,
        "pcaps": len(pcap_inventory),
        "revalidated_endpoints": audit["revalidated_endpoints"],
        "policy_summary_sha256": sha256(output / "policy_summary.csv"),
        "compatibility_matrix_sha256": sha256(
            output / "compatibility_matrix.csv"
        ),
        "pcap_inventory_sha256": sha256(pcap_copy),
        "protocol_tree_sha256": protocol_verification["tree_sha256"],
        "campaign_tree_sha256": campaign_verification["tree_sha256"],
        "frozen_source_commit": design["source_git"]["commit"],
        "analysis_source_commit": analysis_source_commit,
        "formal_claim": (
            "Across 48 frozen deterministic hardware cases covering "
            "Reliability, Durability, Deadline, and automatic Liveliness in "
            "both communication directions and both endpoint-creation "
            "orders, all expected compatible and incompatible outcomes were "
            f"accepted. {attempt_statement}"
        ),
        "claim_boundary": (
            "This result establishes ROS 2 endpoint compatibility behavior "
            "for four QoS policies. It is not latency, loss, energy, or "
            "resource-performance evidence and does not replace the pending "
            "History/Depth, Lifespan, event-state, and resource-limit "
            "mechanism evaluations."
        ),
    }
    (output / "analysis_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Seven-QoS Compatibility Result",
        "",
        "## Result",
        "",
        report["formal_claim"],
        "",
        "| Policy | Cases | Compatible | Incompatible | Accepted | First-attempt PASS |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in policy_rows:
        lines.append(
            f"| {row['policy'].replace('_', ' ').title()} | "
            f"{row['scheduled_cases']} | {row['compatible_cases']} | "
            f"{row['incompatible_cases']} | {row['accepted_cases']} | "
            f"{row['first_attempt_passes']} |"
        )
    lines.extend(
        [
            "",
            "## Evidence Summary",
            "",
            "Forty-eight frozen hardware cases cross Reliability, "
            "Durability, Deadline, and automatic Liveliness configurations "
            "with board-to-host and host-to-board communication and remote- "
            "and local-first endpoint creation. All "
            f"{compatible_cases} expected-compatible and "
            f"{incompatible_cases} expected-incompatible cases were accepted. "
            f"{attempt_statement} Incompatible cases required zero endpoint "
            "matches and zero application traffic.",
            "",
            "## Claim Boundary",
            "",
            report["claim_boundary"],
            "",
        ]
    )
    (output / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(
        f"PASS: accepted={len(accepted)}/{len(schedule)} "
        f"first_attempt={first_attempt_passes}/{len(schedule)} "
        f"matrix_rows={len(matrix_rows)} pcaps={len(pcap_inventory)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
