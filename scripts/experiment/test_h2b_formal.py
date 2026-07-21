#!/usr/bin/env python3
"""Synthetic gates for the formal H2B schedule, acceptance, and inference."""

import unittest

from analyze_h2b_formal import (
    exact_block_signflip,
    infer_message_level,
    infer_run_level,
)
from build_h2b_design_assets import build_schedule
from h2b_formal_common import (
    EXPECTED_VISITS,
    condition_for,
    expected_injection,
    validate_schedule,
)
from run_h2b_formal import evaluate_row
from run_round6_smoke_gates import expected_serial_lines


class H2BFormalTests(unittest.TestCase):
    def test_schedule_is_complete_and_deterministic(self):
        first = build_schedule()
        second = build_schedule()
        self.assertEqual(first, second)
        self.assertEqual(len(first), EXPECTED_VISITS)
        validate_schedule(first)

    def test_condition_and_effective_loss_contract(self):
        self.assertEqual(
            condition_for("reliable", 15),
            "round4_transport_reliable_15pct_host_to_board",
        )
        self.assertEqual(
            expected_injection(0),
            "transport_egress_gact_host_to_board_target_0pct_effective_0pct",
        )
        self.assertEqual(
            expected_injection(15),
            "transport_egress_gact_host_to_board_target_15pct_1of7_"
            "effective_14.285714pct",
        )

    def test_exact_signflip_uses_ten_blocks(self):
        runs = []
        for block in range(1, 11):
            for qos, value in (("reliable", 20.0), ("best_effort", 10.0)):
                for run in range(3):
                    runs.append({
                        "block": block,
                        "qos": qos,
                        "target_loss_percent": 5,
                        "rtt_p95_ms": value + run,
                    })
        estimate, p_value, effects = exact_block_signflip(
            runs, "rtt_p95_ms", 5
        )
        self.assertEqual(estimate, 10.0)
        self.assertEqual(p_value, 2 / 1024)
        self.assertEqual(len(effects), 10)

    def test_acceptance_does_not_require_delivery_or_rtt_magnitude(self):
        parameters = {
            "MROS2_QOS_HISTORY_DEPTH": 5,
            "MROS2_RTPS_HISTORY_CAPACITY": 10,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": 4000,
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": 30,
            "MROS2_QOS_RESOURCE_MAX_BYTES": 65536,
        }
        serial = "\n".join(
            expected_serial_lines(parameters)
            + [
                "Reliability: RELIABLE uplink, RELIABLE reply path",
                "All phases complete.",
            ]
        )
        condition = condition_for("reliable", 15)
        row = {
            "formal_run": "1",
            "worktree_state": "clean",
            "condition": condition,
            "qos_mode": "reliable",
            "firmware_mode": "reliable",
            "host_mode": "cpp",
            "injection_layer": expected_injection(15),
            "commit_hash": "abc",
            "manifest_sha256": "manifest",
            "matched_pub": "1",
            "matched_sub": "1",
            "rtt_count": "0",
            "rx_count": "0",
        }
        reasons = evaluate_row(
            row,
            serial,
            {"parameters": parameters, "app_version": None},
            "reliable",
            condition,
            15,
            "abc",
            "manifest",
            "firmware",
            {"firmware_binary": {"sha256": "firmware"}},
            {"host_to_board_udp_packets": 1},
            [],
        )
        self.assertEqual(reasons, [])

    def test_complete_synthetic_matrix_runs_frozen_analysis(self):
        runs = []
        clusters = {}
        run_id = 0
        for block in range(1, 11):
            for qos in ("reliable", "best_effort"):
                for loss in (0, 1, 5, 10, 15):
                    for repetition in range(3):
                        run_id += 1
                        qos_offset = 10.0 if qos == "reliable" else 0.0
                        rtt = 20.0 + loss + qos_offset + repetition
                        runs.append({
                            "block": block,
                            "qos": qos,
                            "target_loss_percent": loss,
                            "rtt_p95_ms": rtt,
                            "delivery_ratio": 1.0 - loss / 200.0,
                            "rtt_median_ms": rtt - 2.0,
                            "rtt_p99_ms": rtt + 2.0,
                            "match_wait_ms": 1000.0,
                            "link_ping_avg_ms": 10.0,
                        })
                        clusters[(qos, loss, block, run_id)] = [
                            rtt - 1.0,
                            rtt + 1.0,
                        ]
        cells, contrasts = infer_run_level(runs, 1000, 123)
        messages, effects = infer_message_level(clusters, 1000, 123)
        self.assertEqual(len(cells), 60)
        self.assertEqual(len(contrasts), 30)
        self.assertEqual(
            sum(row["holm_family"] == "confirmatory_10" for row in contrasts),
            10,
        )
        self.assertEqual(len(messages), 10)
        self.assertEqual(len(effects), 5)


if __name__ == "__main__":
    unittest.main()
