import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/experiment/run_p4_pipeline.py"
SPEC = importlib.util.spec_from_file_location("run_p4_pipeline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RunP4PipelineTests(unittest.TestCase):
    def test_pipeline_order_is_fail_closed_and_complete(self):
        root = Path("/repo")
        commands = MODULE.pipeline_commands(
            root,
            Path("/firmware"),
            "p4_result",
            "/dev/ttyUSB0",
            "192.0.2.10",
            "eth1",
            "abc1234",
        )
        self.assertEqual(
            [name for name, _command in commands],
            [
                "verify_firmware_set_seal",
                "independent_window_smoke",
                "formal_collection",
                "formal_audit",
                "confirmatory_analysis",
                "wire_analysis",
                "seal_result_tree",
                "verify_result_tree_seal",
            ],
        )
        smoke = dict(commands)["independent_window_smoke"]
        self.assertIn("--new-window-ack", smoke)
        self.assertIn("--network-reassociated-ack", smoke)
        formal = dict(commands)["formal_collection"]
        self.assertIn("window_manifest.json", " ".join(formal))

    def test_idf_environment_is_loaded_from_export_script(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "export.sh"
            script.write_text("export IDF_PATH=/opt/test-idf\n", encoding="utf-8")
            environment = MODULE.load_idf_environment(script)
            self.assertEqual(environment["IDF_PATH"], "/opt/test-idf")


if __name__ == "__main__":
    unittest.main()
