#!/usr/bin/env python3

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import tempfile
import unittest

from generate_seven_qos_performance_protocol import (
    DEFAULT_AMENDMENT,
    DEFAULT_EXECUTION_CONTRACTS,
    DEFAULT_IDENTITY_AMENDMENT,
    DEFAULT_SOURCE,
    FAMILY_ORDER,
    expand_schedule,
    generate,
    load_json,
)
from validate_seven_qos_execution_contracts import validate_contracts

REPO = Path(__file__).resolve().parents[2]


class SevenQosPerformanceProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = load_json(DEFAULT_SOURCE)
        cls.rows, cls.cells = expand_schedule(cls.source, 2026072301)

    def test_total_counts(self) -> None:
        self.assertEqual(len(self.cells), 51)
        self.assertEqual(len(self.rows), 1530)
        self.assertEqual(len({row["run_token"] for row in self.rows}), 1530)

    def test_every_cell_has_n30(self) -> None:
        counts = Counter((row["family"], row["cell_id"]) for row in self.rows)
        self.assertEqual(set(counts.values()), {30})

    def test_every_visit_is_complete_with_three_replicates(self) -> None:
        expected = defaultdict(set)
        for row in self.cells:
            expected[row["family"]].add(row["cell_id"])
        grouped = defaultdict(list)
        for row in self.rows:
            grouped[(row["family"], int(row["visit"]))].append(row)
        for family in FAMILY_ORDER:
            for visit in range(1, 11):
                counts = Counter(
                    row["cell_id"] for row in grouped[(family, visit)]
                )
                self.assertEqual(set(counts), expected[family])
                self.assertEqual(set(counts.values()), {3})

    def test_seed_is_reproducible_and_effective(self) -> None:
        same, _ = expand_schedule(self.source, 2026072301)
        other, _ = expand_schedule(self.source, 2026072302)
        self.assertEqual(self.rows, same)
        self.assertNotEqual(
            [(row["family"], row["cell_id"]) for row in self.rows],
            [(row["family"], row["cell_id"]) for row in other],
        )

    def test_energy_is_explicitly_deferred(self) -> None:
        self.assertTrue(
            all(row["energy_status"] == "deferred_not_collected" for row in self.rows)
        )
        self.assertFalse(self.source["energy_policy"]["energy_claims_allowed"])

    def test_generated_bundle_retains_both_controlling_amendments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "protocol"
            design = generate(
                DEFAULT_SOURCE,
                DEFAULT_AMENDMENT,
                DEFAULT_IDENTITY_AMENDMENT,
                DEFAULT_EXECUTION_CONTRACTS,
                output,
                2026072301,
            )
            self.assertEqual(
                design["schedule_sha256"],
                "3326942f48098fc0adfb0fdee03a81574add6b34ad34c0b30337078aa9734d09",
            )
            self.assertTrue((output / design["amendment"]).is_file())
            self.assertTrue((output / design["identity_amendment"]).is_file())

    def test_execution_contracts_cover_schedule_and_block_formal_launch(self) -> None:
        contracts = load_json(DEFAULT_EXECUTION_CONTRACTS)
        summary = validate_contracts(contracts, self.source)
        self.assertEqual(summary["cells"], 51)
        self.assertFalse(contracts["formal_launch_allowed"])
        self.assertEqual(
            contracts["family_contracts"]["resource_limits"]["impairment_locus"],
            "host_egress_ack_suppression_only",
        )

    def test_mros2_esp32_rejects_ipv6_abi_mismatch(self) -> None:
        cmake = (REPO / "components/mros2-esp32/CMakeLists.txt").read_text()
        self.assertIn("if(CONFIG_LWIP_IPV6)", cmake)
        self.assertIn("uses an IPv4-only lwIP ABI", cmake)
        self.assertNotIn("sed -i", cmake)
        self.assertNotIn("add_custom_target(Sdkconfig", cmake)

    def test_pilot_runtime_defaults_are_explicit(self) -> None:
        defaults = (
            REPO / "workspace/seven_qos_performance_pilot/sdkconfig.defaults"
        ).read_text()
        self.assertIn("CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192", defaults)
        self.assertIn("CONFIG_FREERTOS_HZ=1000", defaults)
        self.assertIn("# CONFIG_LWIP_IPV6 is not set", defaults)

    def test_non_micro_ros_runner_isolates_host_history_after_board_reset(self) -> None:
        runner = (
            REPO / "scripts/experiment/run_telemetry_control_probe_smoke.py"
        ).read_text()
        host_start = runner.index('manifest["host_started_at_utc"]')
        flash_start = runner.index('manifest["flash_started_at_utc"]')
        self.assertGreater(host_start, flash_start)
        self.assertIn('"board_reset_then_capture_then_host"', runner)
        self.assertNotIn('"host_then_board_reset"', runner)

    def test_collector_copies_build_configuration_evidence(self) -> None:
        runner = (
            REPO / "scripts/experiment/run_telemetry_control_probe_smoke.py"
        ).read_text()
        self.assertIn('source_artifacts["project_description"]', runner)
        self.assertIn('source_artifacts["sdkconfig"]', runner)
        self.assertIn('"project_version": project_description.get', runner)

    def test_pilot_contains_no_temporary_udp_diagnostics(self) -> None:
        cmake = (
            REPO / "workspace/seven_qos_performance_pilot/CMakeLists.txt"
        ).read_text()
        app = (
            REPO / "workspace/seven_qos_performance_pilot/main/app.cpp"
        ).read_text()
        self.assertNotIn("MROS2_UDP_TX_DIAGNOSTICS", cmake)
        self.assertNotIn("PERF_PILOT_TASK", app)


if __name__ == "__main__":
    unittest.main()
