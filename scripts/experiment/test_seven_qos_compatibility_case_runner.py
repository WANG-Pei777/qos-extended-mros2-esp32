#!/usr/bin/env python3

from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_seven_qos_compatibility_case import (
    DEFAULT_SCHEDULE,
    frozen_flash_command,
    load_frozen_bundle,
    resolve_case,
)


class CompatibilityCaseResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with Path(DEFAULT_SCHEDULE).open(
            newline="", encoding="utf-8"
        ) as stream:
            cls.rows = [
                row
                for row in csv.DictReader(stream)
                if row["case_type"] == "compatibility"
            ]

    def find(self, case_id: str):
        return resolve_case(
            next(row for row in self.rows if row["case_id"] == case_id)
        )

    def test_all_48_hardware_compatibility_rows_resolve(self) -> None:
        resolved = [resolve_case(row) for row in self.rows]
        self.assertEqual(len(resolved), 48)
        self.assertEqual(len({case.case_id for case in resolved}), 48)
        self.assertEqual(
            {case.policy for case in resolved},
            {"reliability", "durability", "deadline", "liveliness"},
        )

    def test_b2h_reliability_offer_and_request_mapping(self) -> None:
        case = self.find("CMP-REL-b2h-remote-first-p3")
        self.assertEqual(case.board_role, "publisher")
        self.assertEqual(case.host_role, "subscriber")
        self.assertEqual(case.board_qos.reliability, "best_effort")
        self.assertEqual(case.host_qos.reliability, "reliable")
        self.assertFalse(case.expected_match)

    def test_h2b_durability_offer_and_request_mapping(self) -> None:
        case = self.find("CMP-DUR-h2b-local-first-p2")
        self.assertEqual(case.board_role, "subscriber")
        self.assertEqual(case.host_role, "publisher")
        self.assertEqual(case.host_qos.durability, "transient_local")
        self.assertEqual(case.board_qos.durability, "volatile")
        self.assertTrue(case.expected_match)

    def test_deadline_and_liveliness_arguments(self) -> None:
        deadline = self.find("CMP-DL-b2h-remote-first-p2")
        self.assertEqual(deadline.board_qos.deadline_ms, "100")
        self.assertEqual(deadline.host_qos.deadline_ms, "50")
        liveliness = self.find("CMP-LV-h2b-local-first-p1")
        self.assertEqual(liveliness.host_qos.liveliness_lease_ms, "500")
        self.assertEqual(liveliness.board_qos.liveliness_lease_ms, "2000")

    def test_resolved_cases_are_json_serializable(self) -> None:
        for row in self.rows:
            value = asdict(resolve_case(row))
            self.assertIn(value["direction"], {"b2h", "h2b"})

    def test_frozen_bundle_is_hash_checked_and_flashable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            firmware = root / "firmware.bin"
            firmware.write_bytes(b"frozen-firmware")
            digest = hashlib.sha256(firmware.read_bytes()).hexdigest()
            manifest = {
                "case_id": "CMP-REL-b2h-remote-first-p1",
                "app_relative_path": "firmware.bin",
                "files": {
                    "firmware.bin": {
                        "bytes": firmware.stat().st_size,
                        "sha256": digest,
                    }
                },
                "flash": {
                    "chip": "esp32s3",
                    "baud": 460800,
                    "before": "default_reset",
                    "after": "hard_reset",
                    "write_flash_args": ["--flash_size", "2MB"],
                    "flash_files": [
                        {
                            "offset": "0x10000",
                            "relative_path": "firmware.bin",
                        }
                    ],
                },
            }
            (root / "artifact_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            loaded = load_frozen_bundle(root, manifest["case_id"])
            command = frozen_flash_command(
                Path("/tmp/export.sh"), "/dev/ttyUSB0", root, loaded
            )
            self.assertIn("write_flash", command[-1])
            self.assertIn(str(firmware), command[-1])

            firmware.write_bytes(b"drift")
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                load_frozen_bundle(root, manifest["case_id"])

    def test_frozen_bundle_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "case_id": "case",
                "files": {"../outside": {"bytes": 0, "sha256": ""}},
            }
            (root / "artifact_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "escapes"):
                load_frozen_bundle(root, "case")


if __name__ == "__main__":
    unittest.main()
