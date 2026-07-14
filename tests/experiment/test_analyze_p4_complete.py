import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiment/analyze_p4_complete.py"
SPEC = importlib.util.spec_from_file_location("analyze_p4_complete", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AnalyzeP4CompleteTests(unittest.TestCase):
    def test_exact_signflip_uses_ten_balanced_blocks(self):
        runs = []
        for block in range(1, 11):
            for qos, value in (("reliable", 2.0), ("best_effort", 1.0)):
                for _ in range(3):
                    runs.append({
                        "block": block,
                        "qos": qos,
                        "target_loss_percent": 15,
                        "outcome": value,
                    })
        estimate, p_value, effects = MODULE.exact_block_signflip(
            runs, "outcome", 15
        )
        self.assertEqual(estimate, 1.0)
        self.assertEqual(len(effects), 10)
        self.assertAlmostEqual(p_value, 2 / 1024)

    def test_primary_family_contains_exactly_six_contrasts(self):
        self.assertEqual(
            len(MODULE.PRIMARY_OUTCOMES) * len(MODULE.LOSS_TARGETS),
            6,
        )

    def test_inference_emits_balanced_primary_family(self):
        runs = []
        for block in range(1, 11):
            for loss in MODULE.LOSS_TARGETS:
                for qos in MODULE.QOS_MODES:
                    offset = 1.0 if qos == "reliable" else 0.0
                    for run in range(3):
                        runs.append({
                            "block": block,
                            "qos": qos,
                            "target_loss_percent": loss,
                            "rtt_p95_ms": 10 + loss + offset + run,
                            "delivery_ratio": 0.9 - loss / 100 + offset / 100,
                            "rtt_median_ms": 5 + offset,
                            "rtt_p99_ms": 12 + offset,
                            "match_wait_ms": 100 + run,
                            "link_ping_avg_ms": 10 + run,
                        })
        cells, contrasts = MODULE.infer(runs, 1000, 20260715)
        self.assertEqual(len(cells), 36)
        self.assertEqual(len(contrasts), 18)
        primary = [
            row for row in contrasts
            if row["holm_family"] == "confirmatory_6"
        ]
        self.assertEqual(len(primary), 6)
        self.assertTrue(all(row["holm_p"] != "" for row in primary))

    def test_replication_rule_requires_both_nonzero_directions(self):
        rows = []
        for outcome in ("rtt_p95_ms", "delivery_ratio"):
            for loss in MODULE.LOSS_TARGETS:
                estimate = 1.0 if outcome == "rtt_p95_ms" else 0.0
                rows.append({
                    "outcome": outcome,
                    "target_loss_percent": loss,
                    "estimate": estimate,
                    "ci_low": 0.5 if outcome == "rtt_p95_ms" else -0.1,
                    "holm_family": "confirmatory_6",
                })
        self.assertTrue(MODULE.primary_conclusions(rows)["replication_success"])
        rows[1]["estimate"] = -1.0
        self.assertFalse(MODULE.primary_conclusions(rows)["replication_success"])


if __name__ == "__main__":
    unittest.main()
