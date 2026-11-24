#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from run_seven_qos_compatibility_campaign import (
    is_fatal_attempt,
    rebuild_ledgers,
    record_acceptance,
    verify_receipt,
)


class CompatibilityCampaignLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary.name)
        (self.output / "acceptance_receipts").mkdir()
        self.row = {
            "ordinal": "1",
            "case_id": "CMP-REL-b2h-remote-first-p1",
            "policy": "reliability",
            "direction": "b2h",
            "endpoint_creation_order": "remote_first",
            "firmware_sha256": "f" * 64,
            "artifact_manifest_sha256": "a" * 64,
        }
        self.attempt = (
            self.output
            / "runs/001_CMP-REL-b2h-remote-first-p1/attempt_01"
        )
        self.attempt.mkdir(parents=True)
        for relative in (
            "schedule_row.json",
            "serial.raw",
            "host.log",
            "host_validation.log",
            "board_validation.log",
            "capture.pcapng",
            "artifacts/firmware.bin",
            "artifacts/frozen_artifact_manifest.json",
        ):
            path = self.attempt / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode("ascii"))
        self.row["firmware_sha256"] = hashlib.sha256(
            (self.attempt / "artifacts/firmware.bin").read_bytes()
        ).hexdigest()
        manifest = {
            "status": "PASS",
            "started_at_utc": "2026-07-17T00:00:00+00:00",
            "completed_at_utc": "2026-07-17T00:01:00+00:00",
            "failure": "",
            "frozen_bundle_manifest_sha256": self.row[
                "artifact_manifest_sha256"
            ],
            "case": {"expected_match": True},
        }
        (self.attempt / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_receipt_and_ledgers_detect_accepted_evidence_drift(self) -> None:
        record_acceptance(self.output, self.row, self.attempt)
        receipt = verify_receipt(self.output, self.row, self.attempt)
        self.assertEqual(receipt["case_id"], self.row["case_id"])
        accepted, fatal = rebuild_ledgers(self.output, [self.row])
        self.assertEqual(accepted, 1)
        self.assertFalse(fatal)

        (self.attempt / "host.log").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "evidence drift"):
            verify_receipt(self.output, self.row, self.attempt)

    def test_fatal_markers_stop_the_campaign(self) -> None:
        manifest = json.loads(
            (self.attempt / "manifest.json").read_text(encoding="utf-8")
        )
        manifest["status"] = "FAIL"
        (self.attempt / "serial.raw").write_text(
            "Guru Meditation Error", encoding="ascii"
        )
        self.assertTrue(is_fatal_attempt(self.attempt, manifest))


if __name__ == "__main__":
    unittest.main()
