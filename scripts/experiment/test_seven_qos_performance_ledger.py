#!/usr/bin/env python3

import json
from pathlib import Path
import tempfile
import unittest

from seven_qos_performance_ledger import (
    build_acceptance_receipt,
    sha256,
    validate_attempt,
)


SCHEDULE_SHA = "3e76421e2c07869df73e76663c80084f875ab8cbbcabaf7d52fc7a46e4309abe"
HEX = "a" * 64
SOURCE_COMMIT = "abcdef0123456789abcdef0123456789abcdef01"


class SevenQosPerformanceLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.attempt = Path(self.temp.name)
        (self.attempt / "artifacts").mkdir()
        firmware = self.attempt / "artifacts/firmware.bin"
        firmware.write_bytes(b"firmware")
        self.firmware_sha = sha256(firmware)
        elf = self.attempt / "artifacts/app.elf"
        elf.write_bytes(b"elf")
        sdkconfig = self.attempt / "artifacts/sdkconfig"
        sdkconfig.write_bytes(b"sdkconfig")
        project = self.attempt / "artifacts/project_description.json"
        project.write_text('{"project_version":"abcdef0"}')
        (self.attempt / "serial.raw").write_bytes(b"PERF_RUN_COMPLETE\n")
        (self.attempt / "validation.txt").write_text("PASS\n")
        (self.attempt / "traffic.pcapng").write_bytes(b"pcap")
        self.plan = {
            "ordinal": "1",
            "run_token": "sqp-0001",
            "family": "history_depth",
            "cell_id": "H05",
            "runner_kind": "workload_ingress",
            "candidate_relative_path": "runs/0001_sqp-0001_history_depth_H05/attempt_01",
            "artifact_bundle_status": "FROZEN",
            "launch_status": "READY",
        }
        self.requirement = {
            "configuration_sha256": HEX,
            "firmware_run_token": "sqc-history_depth-H05-abcdef012345",
            "source_commit": SOURCE_COMMIT,
            "build_dir": "/build",
            "app_name": "app",
            "firmware_sha256": self.firmware_sha,
            "elf_sha256": sha256(elf),
            "sdkconfig_sha256": sha256(sdkconfig),
            "project_description_sha256": sha256(project),
            "runtime_arguments_json": '{"profile":"clean"}',
            "artifact_bundle_status": "FROZEN",
            "runtime_binding_status": "BOUND",
            "acceptance_oracle_status": "VERIFIED",
        }
        identity = {
            "mode": "formal_candidate",
            "campaign_run_token": "sqp-0001",
            "protocol_schedule_sha256": SCHEDULE_SHA,
            "schedule_ordinal": 1,
            "cell_id": "H05",
        }
        manifest = {
            "classification": "seven_qos_performance_formal_attempt",
            "status": "PASS",
            "evidence_identity": identity,
            "workload": {
                "firmware_run_token": "sqc-history_depth-H05-abcdef012345"
            },
            "project_version": "abcdef0",
            "artifacts": {
                "firmware": {
                    "path": "artifacts/firmware.bin",
                    "sha256": self.firmware_sha,
                },
                "elf": {"path": "artifacts/app.elf", "sha256": sha256(elf)},
                "sdkconfig": {
                    "path": "artifacts/sdkconfig",
                    "sha256": sha256(sdkconfig),
                },
                "project_description": {
                    "path": "artifacts/project_description.json",
                    "sha256": sha256(project),
                },
            },
        }
        (self.attempt / "attempt_manifest.json").write_text(json.dumps(manifest))
        wrapper = {
            "classification": "seven_qos_performance_formal_ingress_attempt",
            "status": "PASS",
            "evidence_identity": identity,
            "firmware_run_token": "sqc-history_depth-H05-abcdef012345",
            "cleanup_ok": True,
            "pcap_sha256": sha256(self.attempt / "traffic.pcapng"),
        }
        (self.attempt / "ingress_impairment_manifest.json").write_text(
            json.dumps(wrapper)
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def assessment(self) -> dict:
        return validate_attempt(
            self.attempt, self.plan, self.requirement, SCHEDULE_SHA
        )

    def test_complete_formal_candidate_is_acceptable(self) -> None:
        self.assertEqual(self.assessment()["status"], "ACCEPTABLE")

    def test_receipt_binds_identity_and_artifact_hashes(self) -> None:
        receipt = build_acceptance_receipt(
            self.attempt, self.plan, self.requirement, SCHEDULE_SHA
        )
        self.assertEqual(receipt["run_token"], "sqp-0001")
        self.assertEqual(receipt["firmware_sha256"], self.firmware_sha)
        self.assertIn("traffic.pcapng", receipt["artifacts"])
        self.assertIn("artifacts/sdkconfig", receipt["artifacts"])

    def test_smoke_classification_is_rejected(self) -> None:
        path = self.attempt / "attempt_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["classification"] = "telemetry_control_probe_engineering_smoke"
        path.write_text(json.dumps(manifest))
        result = self.assessment()
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("collector classification is not formal", result["reasons"])

    def test_identity_drift_is_rejected(self) -> None:
        path = self.attempt / "attempt_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["evidence_identity"]["schedule_ordinal"] = 2
        path.write_text(json.dumps(manifest))
        self.assertIn("collector evidence identity mismatch", self.assessment()["reasons"])

    def test_collector_firmware_token_drift_is_rejected(self) -> None:
        path = self.attempt / "attempt_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["workload"]["firmware_run_token"] = "sqc-history_depth-H06-bad"
        path.write_text(json.dumps(manifest))
        self.assertIn("firmware run token mismatch", self.assessment()["reasons"])

    def test_wrapper_firmware_token_drift_is_rejected(self) -> None:
        path = self.attempt / "ingress_impairment_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["firmware_run_token"] = "sqc-history_depth-H06-bad"
        path.write_text(json.dumps(manifest))
        self.assertIn(
            "network wrapper firmware run token mismatch",
            self.assessment()["reasons"],
        )

    def test_unbound_artifact_is_rejected(self) -> None:
        self.requirement["artifact_bundle_status"] = "UNBOUND"
        self.assertIn(
            "artifact_bundle_status is not FROZEN", self.assessment()["reasons"]
        )

    def test_pcap_hash_drift_is_rejected(self) -> None:
        (self.attempt / "traffic.pcapng").write_bytes(b"changed")
        self.assertIn("PCAP SHA-256 mismatch", self.assessment()["reasons"])

    def test_copied_firmware_drift_is_rejected(self) -> None:
        (self.attempt / "artifacts/firmware.bin").write_bytes(b"tampered")
        reasons = self.assessment()["reasons"]
        self.assertIn("firmware manifest SHA-256 mismatch", reasons)
        self.assertIn("firmware frozen SHA-256 mismatch", reasons)

    def test_fatal_marker_stops_acceptance(self) -> None:
        (self.attempt / "serial.raw").write_text("Guru Meditation Error")
        result = self.assessment()
        self.assertEqual(result["status"], "FATAL_REJECTED")
        self.assertEqual(result["fatal_markers"], ["guru meditation"])


if __name__ == "__main__":
    unittest.main()
