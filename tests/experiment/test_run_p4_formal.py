import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiment/run_p4_formal.py"
SPEC = importlib.util.spec_from_file_location("run_p4_formal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P4FormalTests(unittest.TestCase):
    def test_conditions_record_nominal_and_effective_loss(self):
        self.assertEqual(MODULE.condition_for("reliable", 0), "p4_reliable_target00_eff0")
        self.assertEqual(
            MODULE.condition_for("best_effort", 15),
            "p4_best_effort_target15_gact1of7_eff14p285714",
        )

    def test_injection_labels_match_transport_wrapper(self):
        self.assertEqual(
            MODULE.expected_injection(0),
            "transport_ingress_gact_board_to_host_target_0pct_effective_0pct",
        )
        self.assertIn("1of20_effective_5.000000pct", MODULE.expected_injection(5))

    def test_acceptance_ignores_performance_outcomes(self):
        parameters = {
            "MROS2_QOS_HISTORY_DEPTH": 5,
            "MROS2_RTPS_HISTORY_CAPACITY": 10,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": 4000,
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": 30,
            "MROS2_QOS_RESOURCE_MAX_BYTES": 65536,
        }
        serial = "\n".join([
            "App version:      v",
            "Reliability: BEST_EFFORT uplink, BEST_EFFORT reply path",
            "History    : KEEP_LAST(5)",
            "Resources  : 30 samples, 65536 bytes",
            "Mechanism    : capacity=10, heartbeat=4000ms",
            "All phases complete.",
        ])
        row = {
            "formal_run": "1", "worktree_state": "clean",
            "matched_pub": "1", "matched_sub": "1",
            "rx_count": "0", "rtt_count": "0",
        }
        self.assertEqual(
            MODULE.evaluate_row(
                row, serial, parameters, "v", "best_effort",
                {"board_to_host_udp_packets": 1}, {},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
