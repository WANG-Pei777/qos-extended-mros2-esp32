import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "experiment"
    / "run_round6_smoke_gates.py"
)
SPEC = importlib.util.spec_from_file_location("run_round6_smoke_gates", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Round6SmokeTests(unittest.TestCase):
    def test_verification_parser_requires_exact_summary_lines(self):
        text = "\n".join(
            ["[PASS] check"] * 22 + ["[verify] RESULT: PASS"]
        )
        self.assertEqual(
            MODULE.parse_verification(text),
            {"pass": 22, "fail": 0, "result": "PASS"},
        )
        self.assertEqual(
            MODULE.parse_verification(text + "\n[FAIL] later"),
            {"pass": 22, "fail": 1, "result": "PASS"},
        )

    def test_serial_configuration_is_checked_exactly(self):
        parameters = {
            "MROS2_QOS_HISTORY_DEPTH": 20,
            "MROS2_RTPS_HISTORY_CAPACITY": 48,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": 1000,
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": 48,
            "MROS2_QOS_RESOURCE_MAX_BYTES": 65536,
        }
        serial = "\n".join(
            MODULE.expected_serial_lines(parameters)
            + ["App version:      test-version"]
        )
        self.assertEqual(
            MODULE.validate_serial(serial, parameters, "test-version"),
            [],
        )
        self.assertTrue(
            MODULE.validate_serial(serial, parameters, "wrong-version")
        )

    def test_artifact_resolution_rejects_escape_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifacts" / "firmware.bin"
            artifact.parent.mkdir()
            artifact.write_bytes(b"firmware")
            record = {
                "path": "artifacts/firmware.bin",
                "sha256": MODULE.sha256_file(artifact),
                "bytes": artifact.stat().st_size,
            }
            self.assertEqual(MODULE.resolve_artifact(root, record), artifact)
            record["path"] = "../outside.bin"
            with self.assertRaisesRegex(ValueError, "escapes firmware set"):
                MODULE.resolve_artifact(root, record)


if __name__ == "__main__":
    unittest.main()
