import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiment/analyze_p4_wire.py"
SPEC = importlib.util.spec_from_file_location("analyze_p4_wire", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AnalyzeP4WireTests(unittest.TestCase):
    def test_submessage_ids_are_counted_by_direction(self):
        rows = [
            {
                "frame.time_relative": "0.1",
                "ip.src": "192.0.2.10",
                "ip.dst": "192.0.2.20",
                "rtps.sm.id": "0x15,0x07",
            },
            {
                "frame.time_relative": "0.4",
                "ip.src": "192.0.2.20",
                "ip.dst": "192.0.2.10",
                "rtps.sm.id": "0x06,0x15",
            },
        ]
        result = MODULE.summarize_rows(
            rows, "192.0.2.10", "192.0.2.20"
        )
        self.assertEqual(result["board_to_host_data"], 1)
        self.assertEqual(result["board_to_host_heartbeat"], 1)
        self.assertEqual(result["host_to_board_acknack"], 1)
        self.assertEqual(result["host_to_board_data"], 1)
        self.assertAlmostEqual(result["duration_s"], 0.3)

    def test_cell_summary_keeps_qos_and_loss_separate(self):
        base = {
            "rtps_packets": 10,
            "board_to_host_data": 4,
            "board_to_host_heartbeat": 2,
            "host_to_board_acknack": 1,
            "host_to_board_data": 3,
            "host_to_board_heartbeat": 2,
            "board_to_host_acknack": 1,
        }
        rows = []
        for qos in ("reliable", "best_effort"):
            row = dict(base, qos=qos, target_loss_percent=5)
            rows.append(row)
        summary = MODULE.cell_summary(rows)
        self.assertEqual(len(summary), 2)
        self.assertTrue(all(row["n_runs"] == 1 for row in summary))

    def test_host_ip_is_bound_to_window_evidence(self):
        window = {
            "network": {
                "interface_addresses": [{
                    "addr_info": [
                        {"family": "inet6", "scope": "link", "local": "::1"},
                        {
                            "family": "inet",
                            "scope": "global",
                            "local": "192.0.2.20",
                        },
                    ]
                }]
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            path.write_text(json.dumps(window), encoding="utf-8")
            self.assertEqual(MODULE.host_ip_from_window(path), "192.0.2.20")


if __name__ == "__main__":
    unittest.main()
