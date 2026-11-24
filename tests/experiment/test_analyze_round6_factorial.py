import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/analyze_round6_factorial.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_round6_factorial", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AnalyzeRound6FactorialTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(MODULE.percentile([1, 2, 3, 4], 0.5), 2.5)

    def test_holm_adjust_is_monotone_in_rank(self):
        adjusted = MODULE.holm_adjust([0.01, 0.04, 0.03])
        self.assertEqual(adjusted, [0.03, 0.06, 0.06])

    def test_contrast_weights_sum_to_zero(self):
        for _name, weights in MODULE.contrast_specs():
            self.assertAlmostEqual(sum(weights.values()), 0.0)

    def test_condition_parser(self):
        condition = "round6_d20_h0250_b2h_target15_gact1of7_eff14p285714"
        self.assertEqual(MODULE.cell_from_condition(condition), (20, 250))


if __name__ == "__main__":
    unittest.main()
