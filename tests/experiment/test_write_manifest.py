import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "experiment"
    / "write_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("write_manifest", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BinaryArchiveTests(unittest.TestCase):
    def test_archive_is_content_addressed_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build" / "firmware.bin"
            source.parent.mkdir()
            source.write_bytes(b"firmware payload")
            artifact_dir = root / "results" / "artifacts"
            digest = hashlib.sha256(source.read_bytes()).hexdigest()

            first = MODULE.archive_binary(
                source,
                artifact_dir,
                "firmware",
                root,
            )
            second = MODULE.archive_binary(
                source,
                artifact_dir,
                "firmware",
                root,
            )

            self.assertEqual(first, second)
            self.assertEqual(first["sha256"], digest)
            self.assertEqual(
                first["path"],
                f"results/artifacts/firmware_{digest}.bin",
            )
            self.assertEqual((root / first["path"]).read_bytes(), source.read_bytes())

    def test_archive_rejects_corrupted_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "firmware.bin"
            source.write_bytes(b"expected")
            artifact_dir = root / "artifacts"
            record = MODULE.archive_binary(
                source,
                artifact_dir,
                "firmware",
                root,
            )
            archived = root / record["path"]
            archived.chmod(0o644)
            archived.write_bytes(b"corrupted")

            with self.assertRaisesRegex(ValueError, "archive hash mismatch"):
                MODULE.archive_binary(
                    source,
                    artifact_dir,
                    "firmware",
                    root,
                )


if __name__ == "__main__":
    unittest.main()
