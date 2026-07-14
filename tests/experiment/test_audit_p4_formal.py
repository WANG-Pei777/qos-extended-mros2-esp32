import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiment/audit_p4_formal.py"
SPEC = importlib.util.spec_from_file_location("audit_p4_formal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AuditP4FormalTests(unittest.TestCase):
    def test_zero_loss_requires_unimpaired_baseline(self):
        parsed = MODULE.parse_tc_state("phase=baseline\nqdisc fq_codel 0: root\n", 0)
        self.assertEqual(parsed["observed_rate"], 0.0)
        with self.assertRaisesRegex(ValueError, "random gact"):
            MODULE.parse_tc_state(
                "phase=baseline\nrandom type netrand drop val 20\n", 0
            )

    def test_impaired_state_validates_denominator_and_counters(self):
        text = (
            "phase=final\nrandom type netrand drop val 20\n"
            "Sent 1000 bytes 100 pkt (dropped 5, overlimits 0 requeues 0)\n"
        )
        parsed = MODULE.parse_tc_state(text, 5)
        self.assertAlmostEqual(parsed["observed_rate"], 0.05)
        with self.assertRaisesRegex(ValueError, "denominator"):
            MODULE.parse_tc_state(text, 15)


if __name__ == "__main__":
    unittest.main()
