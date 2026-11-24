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

from validate_workload_ingress_impairment_smoke import validate


class IngressImpairmentValidatorTests(unittest.TestCase):
    def fixture(self, root: Path, dropped: int = 110) -> None:
        pcap = root / "traffic.pcapng"
        pcap.write_bytes(b"pcap-data")
        pcap_sha = hashlib.sha256(pcap.read_bytes()).hexdigest()
        (root / "ingress_impairment_manifest.json").write_text(json.dumps({
            "classification": "workload_ingress_impairment_engineering_smoke",
            "status": "PASS", "runner_status": "PASS",
            "direction": "board_to_host_ingress_only",
            "profile": "loss5_independent_b2h",
            "board_ip": "172.24.195.36",
            "source_filter": "ip src 172.24.195.36/32",
            "cleanup_ok": True, "wrapper_error": None,
            "pcap_sha256": pcap_sha, "pcap_bytes": pcap.stat().st_size,
        }))
        (root / "attempt_manifest.json").write_text(json.dumps({
            "status": "PASS",
            "workload": {
                "impairment": "loss5_independent_b2h",
                "delivery_policy": "outcome",
            },
        }))
        (root / "policy_validation.txt").write_text(
            "PASS: family=history_depth cell_id=HSM20\n"
        )
        (root / "tc_ifb_final.txt").write_text(
            "qdisc netem 1: root loss 5%\n"
            f" Sent 200000 bytes 2200 pkt (dropped {dropped}, overlimits 0 requeues 0)\n"
        )
        (root / "tc_after_cleanup.txt").write_text(
            "qdisc mq 0: root\nqdisc fq_codel 0: parent :1\n"
        )

    def test_accepts_bounded_effective_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            report = validate(root, "loss5_independent_b2h", "172.24.195.36", 500)
            self.assertEqual(report["status"], "PASS")
            self.assertAlmostEqual(report["effective_loss_percent"], 5.0)

    def test_rejects_ineffective_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, dropped=0)
            report = validate(root, "loss5_independent_b2h", "172.24.195.36", 500)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("ifb:effective_loss", report["errors"])


if __name__ == "__main__":
    unittest.main()
