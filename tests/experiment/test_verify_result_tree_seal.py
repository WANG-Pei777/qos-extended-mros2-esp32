import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEAL = load("seal_result_tree", ROOT / "scripts/experiment/seal_result_tree.py")
VERIFY = load(
    "verify_result_tree_seal",
    ROOT / "scripts/experiment/verify_result_tree_seal.py",
)


def create_seal(root):
    rows = SEAL.inventory(root)
    manifest = root / "release_file_manifest.csv"
    SEAL.write_manifest(manifest, rows)
    seal = {
        "schema_version": 1,
        "classification": "experiment_result_tree_release_seal",
        "root": str(root),
        "file_count": len(rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "tree_sha256": SEAL.tree_digest(rows),
        "file_manifest_sha256": SEAL.sha256_file(manifest),
        "excluded_self_referential_files": sorted(SEAL.EXCLUDED),
    }
    (root / "release_seal.json").write_text(
        __import__("json").dumps(seal), encoding="utf-8"
    )


class VerifyResultTreeSealTests(unittest.TestCase):
    def test_valid_tree_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("evidence", encoding="utf-8")
            create_seal(root)
            report = VERIFY.verify(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["verified_files"], 1)

    def test_mutation_and_extra_file_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.txt"
            evidence.write_text("evidence", encoding="utf-8")
            create_seal(root)
            evidence.write_text("changed", encoding="utf-8")
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            report = VERIFY.verify(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any("file size mismatch" in error for error in report["errors"])
            )
            self.assertTrue(
                any("unsealed extra file" in error for error in report["errors"])
            )


if __name__ == "__main__":
    unittest.main()
