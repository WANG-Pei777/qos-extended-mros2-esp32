import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/analyze_round6_wire.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_round6_wire", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AnalyzeRound6WireTests(unittest.TestCase):
    def test_final_heartbeat_requests_are_right_censored(self):
        events = [
            {
                "run_id": 1,
                "flow": "board_to_host_app",
                "event_type": "data",
                "sequence": 7,
                "time_s": 1.0,
                "frame_number": 1,
                "acknack_count": None,
                "requested_sequences": [],
            },
            {
                "run_id": 1,
                "flow": "board_to_host_app",
                "event_type": "heartbeat",
                "sequence": 1,
                "last_sequence": 7,
                "time_s": 2.0,
                "frame_number": 2,
                "acknack_count": None,
                "requested_sequences": [],
            },
            {
                "run_id": 1,
                "flow": "board_to_host_app",
                "event_type": "acknack",
                "sequence": 7,
                "time_s": 2.1,
                "frame_number": 3,
                "acknack_count": 1,
                "requested_sequences": [7],
            },
        ]
        metrics = MODULE.derive_wire_metrics(events, 1)
        self.assertEqual(metrics["wire_unresolved_unique_sequences_all"], 1)
        self.assertEqual(
            metrics["wire_unresolved_unique_sequences_uncensored"], 0
        )
        self.assertEqual(metrics["wire_right_censored_request_observations"], 1)


if __name__ == "__main__":
    unittest.main()
