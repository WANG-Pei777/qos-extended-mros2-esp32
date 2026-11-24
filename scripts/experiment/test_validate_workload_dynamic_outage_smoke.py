#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_workload_dynamic_outage_smoke import validate


class DynamicOutageValidatorTests(unittest.TestCase):
    def fixture(self, root: Path, dropped: int = 39) -> None:
        pcap = root / "traffic.pcapng"
        pcap.write_bytes(b"pcap")
        pcap_sha = hashlib.sha256(pcap.read_bytes()).hexdigest()
        (root / "impairment_manifest.json").write_text(json.dumps({
            "classification": "workload_impairment_engineering_smoke",
            "status": "PASS", "runner_status": "PASS",
            "direction": "host_to_board_dynamic_egress_only",
            "profile": "resource_ack_suppression_h2b",
            "dynamic_outage_kind": "resource_ack_suppression_h2b",
            "dynamic_outage_marker": "PERF_RESOURCE_ACK_SUPPRESSION_READY",
            "dynamic_outage_marker_wait_seconds": 34.3,
            "dynamic_outage_started_at_utc": "2026-07-23T02:40:53+00:00",
            "dynamic_outage_completed_at_utc": "2026-07-23T02:40:54.050000+00:00",
            "cleanup_ok": True, "wrapper_error": None,
            "pcap_sha256": pcap_sha, "pcap_bytes": pcap.stat().st_size,
        }))
        (root / "attempt_manifest.json").write_text(json.dumps({
            "status": "PASS",
            "workload": {"impairment": "resource_ack_suppression_h2b"},
        }))
        (root / "tc_outage_final.txt").write_text(
            f"qdisc netem 1: root loss 100%\n Sent 0 bytes 0 pkt (dropped {dropped})\n"
        )
        (root / "tc_after_cleanup.txt").write_text("qdisc mq 0: root\n")
        (root / "policy_validation.txt").write_text(
            "PASS: family=resource_limits cell_id=R01ACK\n"
        )

    def run_fixture(self, root: Path) -> dict:
        return validate(
            root, "resource_ack_suppression_h2b",
            "PERF_RESOURCE_ACK_SUPPRESSION_READY", 1.0,
            "resource_limits", 0.25,
        )

    def test_accepts_effective_marker_aligned_outage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            report = self.run_fixture(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["dropped_packets"], 39)

    def test_rejects_outage_without_drops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, dropped=0)
            report = self.run_fixture(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("outage:no_drops", report["errors"])


if __name__ == "__main__":
    unittest.main()
