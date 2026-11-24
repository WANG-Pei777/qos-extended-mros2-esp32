#!/usr/bin/env python3

from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest

from freeze_seven_qos_compatibility_protocol import REPO, validate_smoke_results


class SevenQosFreezeGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=REPO)
        self.root = Path(self.temporary.name)
        self.git_state = {
            "commit": "a" * 40,
            "tracked_worktree_dirty": False,
        }
        self.args = Namespace(board_ip="192.0.2.10", interface="eth1")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_result(self, name: str, direction: str, order: str) -> Path:
        root = self.root / name
        required = (
            "serial.raw",
            "host.log",
            "host_validation.log",
            "board_validation.log",
            "capture.pcapng",
            "artifacts/firmware.bin",
        )
        for relative in required:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode("ascii"))
        manifest = {
            "status": "PASS",
            "source_git": self.git_state,
            "source_git_at_completion": self.git_state,
            "board_ip": self.args.board_ip,
            "interface": self.args.interface,
            "case": {
                "case_id": name,
                "direction": direction,
                "endpoint_creation_order": order,
                "expected_match": True,
            },
            "return_codes": {
                "flash": 0,
                "host": 0,
                "capture": 0,
                "host_validation": 0,
                "board_validation": 0,
            },
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return root

    def test_accepts_exact_source_with_both_directions_and_orders(self) -> None:
        paths = [
            self.make_result("B2H", "b2h", "remote_first"),
            self.make_result("H2B", "h2b", "local_first"),
        ]
        evidence = validate_smoke_results(paths, self.args, self.git_state)
        self.assertEqual(len(evidence), 2)

    def test_rejects_smoke_from_another_source_revision(self) -> None:
        paths = [
            self.make_result("B2H", "b2h", "remote_first"),
            self.make_result("H2B", "h2b", "local_first"),
        ]
        manifest_path = paths[0] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_git"]["commit"] = "b" * 40
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source revision"):
            validate_smoke_results(paths, self.args, self.git_state)

    def test_rejects_incomplete_direction_or_order_coverage(self) -> None:
        path = self.make_result("B2H", "b2h", "remote_first")
        with self.assertRaisesRegex(ValueError, "both B2H and H2B"):
            validate_smoke_results([path], self.args, self.git_state)


if __name__ == "__main__":
    unittest.main()
