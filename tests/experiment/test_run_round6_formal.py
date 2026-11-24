import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "experiment"
    / "run_round6_formal.py"
)
SPEC = importlib.util.spec_from_file_location("run_round6_formal", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Round6FormalTests(unittest.TestCase):
    def test_condition_records_nominal_and_effective_loss(self):
        condition = MODULE.condition_for("d20_h1000")
        self.assertEqual(
            condition,
            "round6_d20_h1000_b2h_target15_gact1of7_eff14p285714",
        )

    def test_acceptance_does_not_select_on_measured_performance(self):
        parameters = {
            "MROS2_QOS_HISTORY_DEPTH": 20,
            "MROS2_RTPS_HISTORY_CAPACITY": 48,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": 1000,
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": 48,
            "MROS2_QOS_RESOURCE_MAX_BYTES": 65536,
        }
        serial = "\n".join(
            [
                "App version:      version",
                "History    : KEEP_LAST(20)",
                "Resources  : 48 samples, 65536 bytes",
                "Mechanism    : capacity=48, heartbeat=1000ms",
                "All phases complete.",
            ]
        )
        row = {
            "formal_run": "1",
            "worktree_state": "clean",
            "matched_pub": "1",
            "matched_sub": "1",
            "rx_count": "0",
            "rtt_count": "0",
        }
        self.assertEqual(
            MODULE.evaluate_row(
                row,
                serial,
                parameters,
                "version",
                {"board_to_host_udp_packets": 1},
                {},
            ),
            [],
        )

    def test_acceptance_rejects_instrumentation_failure(self):
        parameters = {
            "MROS2_QOS_HISTORY_DEPTH": 20,
            "MROS2_RTPS_HISTORY_CAPACITY": 48,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": 1000,
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": 48,
            "MROS2_QOS_RESOURCE_MAX_BYTES": 65536,
        }
        row = {
            "formal_run": "1",
            "worktree_state": "clean",
            "matched_pub": "0",
            "matched_sub": "1",
        }
        reasons = MODULE.evaluate_row(row, "", parameters, None, None, {})
        self.assertIn("endpoint_match_failed", reasons)
        self.assertIn("behavior_incomplete", reasons)
        self.assertIn("capture_missing", reasons)


if __name__ == "__main__":
    unittest.main()
