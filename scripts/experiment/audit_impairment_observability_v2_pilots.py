#!/usr/bin/env python3
"""Audit v2 impairment observability pilots and decide the profile freeze gate."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from audit_current_impairment_matrix_pilots import audit_cell, write_csv


REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / "results/audits/20260720_impairment_observability_v2_pilots"


def efficacy_rows(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(row["qos"], row["profile"]): row for row in summary}
    rows = []
    for qos in ("BEST_EFFORT", "RELIABLE"):
        clean = by_key[(qos, "clean")]
        jitter = by_key[(qos, "delay20ms_jitter10ms_normal_h2b")]
        reorder = by_key[(qos, "delay20ms_reorder25_corr50_gap5_h2b")]
        loss = by_key[(qos, "loss5_independent_h2b")]
        burst = by_key[(qos, "burst_ge_p1_r25_h95_k999_h2b")]

        clean_stddev = float(clean["rtt_stddev_us"])
        jitter_stddev = float(jitter["rtt_stddev_us"])
        jitter_variance_added = math.sqrt(
            max(0.0, jitter_stddev**2 - clean_stddev**2)
        )
        jitter_pass = 5000 <= jitter_variance_added <= 16000
        rows.append(
            {
                "qos": qos,
                "profile_family": "jitter",
                "gate_status": "PASS" if jitter_pass else "FAIL",
                "expected": "added RTT stddev 5-16 ms under 10 ms netem variation",
                "observed": (
                    f"clean_stddev_us={clean_stddev:.3f};"
                    f" jitter_stddev_us={jitter_stddev:.3f};"
                    f" quadrature_added_us={jitter_variance_added:.3f}"
                ),
                "reason": "board RTT moments verify variability without in-window UART",
            }
        )

        reorder_pass = int(reorder["tc_requeues"]) > 0 and (
            qos == "RELIABLE" or int(reorder["arrival_inversions"]) > 0
        )
        rows.append(
            {
                "qos": qos,
                "profile_family": "reordering",
                "gate_status": "PASS" if reorder_pass else "FAIL",
                "expected": "netem requeues; Best Effort exposes board arrival inversions",
                "observed": (
                    f"tc_requeues={reorder['tc_requeues']};"
                    f" arrival_inversions={reorder['arrival_inversions']}"
                ),
                "reason": (
                    "Reliable may restore visible order; transport requeue remains explicit"
                ),
            }
        )

        loss_offered = int(loss["tc_offered_packets"])
        loss_ratio = float(loss["tc_drop_ratio"])
        loss_tolerance = max(
            0.02, 3.0 * math.sqrt(0.05 * 0.95 / loss_offered)
        )
        loss_pass = abs(loss_ratio - 0.05) <= loss_tolerance
        rows.append(
            {
                "qos": qos,
                "profile_family": "independent_loss",
                "gate_status": "PASS" if loss_pass else "FAIL",
                "expected": "5% host-egress tc drop ratio within pilot tolerance",
                "observed": (
                    f"tc_drop_ratio={loss_ratio:.6f};"
                    f" max_missing_run={loss['max_missing_run']}"
                ),
                "reason": "tc and board missing-message counts provide both-layer efficacy",
            }
        )

        burst_pass = (
            int(burst["tc_dropped_packets"]) > 0
            and int(burst["missing_runs"]) > 0
            and int(burst["max_missing_run"]) >= 3
            and int(burst["max_missing_run"]) > int(loss["max_missing_run"])
        )
        rows.append(
            {
                "qos": qos,
                "profile_family": "burst_loss",
                "gate_status": "PASS" if burst_pass else "FAIL",
                "expected": "GE loss has longer missing runs than independent 5% loss",
                "observed": (
                    f"burst_runs={burst['missing_runs']};"
                    f" burst_max={burst['max_missing_run']};"
                    f" independent_max={loss['max_missing_run']}"
                ),
                "reason": "board delivery bitmap summary verifies burst structure",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.audit_root.resolve()
    ledger = json.loads((root / "collection_ledger.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if ledger["expected_cells"] != 10 or ledger["collected_cells"] != 10:
        errors.append("collection ledger is not 10/10")

    summaries = []
    pcaps = []
    for entry in ledger["entries"]:
        try:
            summary, pcap = audit_cell(entry, errors)
            summaries.append(summary)
            pcaps.append(pcap)
        except (OSError, KeyError, ValueError) as exc:
            errors.append(f"{entry.get('qos')}/{entry.get('profile')}: {exc}")

    gates = efficacy_rows(summaries) if len(summaries) == 10 else []
    failed_gates = [row for row in gates if row["gate_status"] != "PASS"]
    write_csv(root / "pilot_summary.csv", summaries)
    write_csv(root / "pcap_inventory.csv", pcaps)
    if gates:
        write_csv(root / "efficacy_gate.csv", gates)

    report = {
        "schema_version": 1,
        "classification": "impairment_observability_v2_engineering_pilot_audit",
        "evidence_boundary": "excluded N=1 efficacy pilots; never formal comparison data",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_status": "PASS" if not errors else "FAIL",
        "profile_freeze_status": (
            "READY_FOR_PREREGISTRATION"
            if not errors and not failed_gates
            else "BLOCKED"
        ),
        "cells": len(summaries),
        "pcaps": len(pcaps),
        "efficacy_gates_passed": len(gates) - len(failed_gates),
        "efficacy_gates_failed": len(failed_gates),
        "energy_gate": "BLOCKED_EXTERNAL_CALIBRATED_MONITOR_AND_GPIO_ALIGNMENT",
        "errors": errors,
    }
    (root / "audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if errors or failed_gates:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        for gate in failed_gates:
            print(
                f"FAIL: {gate['qos']}/{gate['profile_family']}: {gate['observed']}",
                file=sys.stderr,
            )
        return 1
    print(
        "PASS: cells=10 pcaps=10 efficacy_gates=8/8 "
        "profile_freeze=READY_FOR_PREREGISTRATION energy_gate=BLOCKED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
