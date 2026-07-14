import importlib.util
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/run_p4_smoke_gates.py"
)
SPEC = importlib.util.spec_from_file_location("run_p4_smoke_gates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P4SmokeGateTests(unittest.TestCase):
    def test_collection_date_gate_uses_tokyo_date(self):
        tokyo = ZoneInfo("Asia/Tokyo")
        with self.assertRaisesRegex(ValueError, "frozen until"):
            MODULE.require_collection_window(datetime(2026, 7, 14, 23, 59, tzinfo=tokyo))
        accepted = MODULE.require_collection_window(
            datetime(2026, 7, 15, 0, 0, tzinfo=tokyo)
        )
        self.assertEqual(accepted.date(), MODULE.EARLIEST_DATE)

    def test_p4_requires_exactly_two_qos_modes(self):
        self.assertEqual(MODULE.QOS_MODES, ("reliable", "best_effort"))
        self.assertEqual(MODULE.REQUIRED_RUNS_PER_QOS, 3)

    def test_wsl_session_must_start_inside_collection_window(self):
        tokyo = ZoneInfo("Asia/Tokyo")
        with self.assertRaisesRegex(ValueError, "WSL session started"):
            MODULE.require_new_wsl_session(
                datetime(2026, 7, 14, 23, 59, tzinfo=tokyo)
            )
        accepted = MODULE.require_new_wsl_session(
            datetime(2026, 7, 15, 0, 0, tzinfo=tokyo)
        )
        self.assertEqual(accepted.date(), MODULE.EARLIEST_DATE)

    def test_kernel_boot_time_is_read_from_proc_stat(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stat"
            path.write_text("cpu 1 2 3\nbtime 1784041200\n", encoding="utf-8")
            observed = MODULE.kernel_boot_time(path)
            self.assertIsNotNone(observed.tzinfo)


if __name__ == "__main__":
    unittest.main()
