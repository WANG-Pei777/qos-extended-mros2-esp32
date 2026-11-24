import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/experiment/seal_result_tree.py"
)
SPEC = importlib.util.spec_from_file_location("seal_result_tree", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SealResultTreeTests(unittest.TestCase):
    def test_inventory_is_sorted_and_excludes_seal_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.txt").write_text("b", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "release_seal.json").write_text("old", encoding="utf-8")
            rows = MODULE.inventory(root)
            self.assertEqual([row["path"] for row in rows], ["a.txt", "b.txt"])

    def test_tree_digest_changes_with_content(self):
        rows = [{"path": "a", "bytes": 1, "sha256": "first"}]
        changed = [{"path": "a", "bytes": 1, "sha256": "second"}]
        self.assertNotEqual(MODULE.tree_digest(rows), MODULE.tree_digest(changed))


if __name__ == "__main__":
    unittest.main()
