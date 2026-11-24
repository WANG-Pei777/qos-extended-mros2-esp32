import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/audit_round6_formal.py"
)
SPEC = importlib.util.spec_from_file_location("audit_round6_formal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AuditRound6FormalTests(unittest.TestCase):
    def test_expected_cell_design(self):
        self.assertEqual(len(MODULE.EXPECTED_CELLS), 12)
        self.assertIn("d05_h0250", MODULE.EXPECTED_CELLS)
        self.assertIn("d40_h4000", MODULE.EXPECTED_CELLS)

    def test_parse_tc_state(self):
        text = """
phase=final timestamp=now
 random type netrand drop val 7
 Action statistics:
 Sent 179012 bytes 2018 pkt (dropped 306, overlimits 0 requeues 0)
"""
        self.assertEqual(MODULE.parse_tc_state(text), (2018, 306))

    def test_parse_tc_state_rejects_zero_drop(self):
        text = """
phase=final
 random type netrand drop val 7
 Sent 100 bytes 2 pkt (dropped 0, overlimits 0 requeues 0)
"""
        with self.assertRaises(ValueError):
            MODULE.parse_tc_state(text)


if __name__ == "__main__":
    unittest.main()
