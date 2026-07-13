import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "experiment"
    / "build_round6_variants.py"
)
SPEC = importlib.util.spec_from_file_location("build_round6_variants", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Round6BuildTests(unittest.TestCase):
    def test_factorial_cells_are_complete_and_unique(self):
        cells = MODULE.variants()
        self.assertEqual(len(cells), 12)
        self.assertEqual(len({cell["id"] for cell in cells}), 12)
        self.assertEqual(
            {(cell["depth"], cell["heartbeat_ms"]) for cell in cells},
            {
                (depth, heartbeat)
                for depth in MODULE.DEPTHS
                for heartbeat in MODULE.HEARTBEATS_MS
            },
        )

    def test_randomization_is_deterministic_and_balanced(self):
        first = MODULE.randomized_schedule()
        second = MODULE.randomized_schedule()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 120)
        expected_ids = {cell["id"] for cell in MODULE.variants()}
        for block in range(1, MODULE.SUPERBLOCKS + 1):
            rows = [row for row in first if row["block"] == block]
            self.assertEqual({row["id"] for row in rows}, expected_ids)
            self.assertEqual({row["visit"] for row in rows}, set(range(1, 13)))
        for cell_id in expected_ids:
            rows = [row for row in first if row["id"] == cell_id]
            self.assertEqual(len(rows), 10)
            self.assertEqual(
                sum(row["run_end"] - row["run_start"] + 1 for row in rows),
                30,
            )

    def test_archive_is_content_addressed_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "firmware.bin"
            source.write_bytes(b"round6 firmware")
            artifacts = root / "artifacts"
            record = MODULE.archive_file(source, artifacts, "cell")
            self.assertTrue(MODULE.verify_archived_record(record))
            archived = Path(record["path"])
            archived.chmod(0o644)
            archived.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "corrupt existing archive"):
                MODULE.archive_file(source, artifacts, "cell")

    def test_archive_can_emit_portable_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build" / "firmware.bin"
            source.parent.mkdir()
            source.write_bytes(b"portable firmware")
            record = MODULE.archive_file(
                source,
                root / "result" / "artifacts",
                "cell",
                manifest_root=root / "result",
            )
            self.assertFalse(Path(record["path"]).is_absolute())
            self.assertTrue(MODULE.verify_archived_record(record, root / "result"))


if __name__ == "__main__":
    unittest.main()
