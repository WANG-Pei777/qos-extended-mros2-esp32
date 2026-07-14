import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/analyze_round6_complete.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_round6_complete", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AnalyzeRound6CompleteTests(unittest.TestCase):
    def test_primary_family_has_24_contrasts(self):
        self.assertEqual(len(MODULE.OUTCOMES) * 6, 24)

    def test_sensitivity_outcome_is_not_primary(self):
        self.assertNotIn(MODULE.SENSITIVITY_OUTCOME, MODULE.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
