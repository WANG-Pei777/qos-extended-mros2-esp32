import importlib.util
from pathlib import Path
import random
import tempfile
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "experiment"
    / "summarize_round4_rtt_samples.py"
)
SPEC = importlib.util.spec_from_file_location("rtt_summary", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClusterBootstrapTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(MODULE.percentile([0.0, 10.0], 0.25), 2.5)

    def test_cluster_bootstrap_preserves_run_values(self):
        clusters = {"1": [1.0, 1.0], "2": [9.0, 9.0]}
        draws = MODULE.cluster_bootstrap(clusters, 1000, random.Random(7))
        self.assertEqual(len(draws["p95"]), 1000)
        self.assertTrue(set(draws["mean"]).issubset({1.0, 5.0, 9.0}))
        self.assertTrue(set(draws["p95"]).issubset({1.0, 8.6, 9.0}))

    def test_cluster_bootstrap_is_deterministic(self):
        clusters = {"1": [1.0, 2.0], "2": [4.0, 8.0]}
        left = MODULE.cluster_bootstrap(clusters, 20, random.Random("fixed"))
        right = MODULE.cluster_bootstrap(clusters, 20, random.Random("fixed"))
        self.assertEqual(left, right)

    def test_read_samples_rejects_qos_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.csv"
            path.write_text(
                "run_id,condition,qos_mode,rtt_us\n"
                "1,round4_transport_reliable_5pct_board_to_host,best_effort,1000\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "qos_mode"):
                MODULE.read_samples(path)


if __name__ == "__main__":
    unittest.main()
