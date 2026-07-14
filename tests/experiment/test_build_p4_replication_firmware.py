import importlib.util
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/build_p4_replication_firmware.py"
)
SPEC = importlib.util.spec_from_file_location("build_p4_replication", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuildP4ReplicationTests(unittest.TestCase):
    def test_cells_cover_qos_and_loss(self):
        cells = MODULE.cells()
        self.assertEqual(len(cells), 6)
        self.assertEqual({cell["qos"] for cell in cells}, set(MODULE.QOS_MODES))
        self.assertEqual(
            {cell["target_loss_percent"] for cell in cells},
            set(MODULE.LOSS_TARGETS),
        )

    def test_quantized_loss_is_explicit(self):
        by_loss = {cell["target_loss_percent"]: cell for cell in MODULE.cells()}
        self.assertEqual(by_loss[5]["gact_denominator"], 20)
        self.assertEqual(by_loss[5]["effective_loss_percent"], 5.0)
        self.assertEqual(by_loss[15]["gact_denominator"], 7)

    def test_schedule_is_balanced(self):
        rows = MODULE.randomized_schedule()
        self.assertEqual(len(rows), 60)
        for block in range(1, 11):
            selected = [row for row in rows if row["block"] == block]
            self.assertEqual(len({row["id"] for row in selected}), 6)


if __name__ == "__main__":
    unittest.main()
