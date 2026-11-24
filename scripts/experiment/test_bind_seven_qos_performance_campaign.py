#!/usr/bin/env python3

import unittest

from bind_seven_qos_performance_campaign import (
    DURABILITY_MARKER,
    LIVELINESS_MARKER,
    RESOURCE_MARKER,
    cell_binding,
    milliseconds,
)
from generate_seven_qos_performance_protocol import (
    DEFAULT_SOURCE,
    expand_schedule,
    load_json,
)
from prepare_seven_qos_performance_campaign import build_tables


class BindSevenQosPerformanceCampaignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schedule, cells = expand_schedule(load_json(DEFAULT_SOURCE), 2026072301)
        cls.requirements, _ = build_tables(schedule, cells)
        cls.by_key = {
            (row["family"], row["cell_id"]): row for row in cls.requirements
        }

    def binding(self, family: str, cell_id: str):
        return cell_binding(
            self.by_key[(family, cell_id)],
            interface="eth1",
            board_ip="192.0.2.1",
            serial_port="/dev/serial/by-id/test",
            run_user="tester",
        )

    def test_all_51_cells_have_complete_bindings(self) -> None:
        for row in self.requirements:
            cmake, runtime = cell_binding(
                row,
                interface="eth1",
                board_ip="192.0.2.1",
                serial_port="/dev/serial/by-id/test",
                run_user="tester",
            )
            self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_RUN_TOKEN"], row["firmware_run_token"])
            self.assertEqual(runtime["expected_firmware_token"], row["firmware_run_token"])
            self.assertEqual(runtime["target_tx"], runtime["rate_hz"] * 20)

    def test_history_binding(self) -> None:
        cmake, runtime = self.binding("history_depth", "H07")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH"], "5")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE"], "40")
        self.assertEqual(runtime["profile"], "loss15_independent_b2h")

    def test_durability_keeps_prejoin_attempts_constant(self) -> None:
        shallow, runtime = self.binding("durability", "D06")
        deep, _ = self.binding("durability", "D07")
        self.assertEqual(
            shallow["SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES"], "10"
        )
        self.assertEqual(
            deep["SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES"], "10"
        )
        self.assertEqual(
            shallow["SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH"], "1"
        )
        self.assertEqual(runtime["host_start_marker"], DURABILITY_MARKER)
        self.assertEqual(runtime["host_start_delay_seconds"], 10.0)

    def test_deadline_rate_is_derived_from_period(self) -> None:
        cmake, runtime = self.binding("deadline", "DL06")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_DEADLINE_MS"], "100")
        self.assertEqual(runtime["rate_hz"], 50)
        self.assertEqual(runtime["target_tx"], 1000)
        disabled, _ = self.binding("deadline", "DL08")
        self.assertEqual(disabled["SEVEN_QOS_PERFORMANCE_DEADLINE_MS"], "0")

    def test_lifespan_disabled_is_explicit_zero(self) -> None:
        cmake, runtime = self.binding("lifespan", "LS01")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_LIFESPAN_MS"], "0")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS"], "100")
        self.assertEqual(runtime["payload_bytes"], 512)

    def test_liveliness_binds_compile_and_runtime_outage(self) -> None:
        cmake, runtime = self.binding("liveliness", "LV06")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS"], "500")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS"], "3000")
        self.assertEqual(runtime["dynamic_outage_marker"], LIVELINESS_MARKER)
        self.assertEqual(runtime["dynamic_outage_seconds"], 3.0)

    def test_resource_limits_binds_frozen_ack_episode(self) -> None:
        cmake, runtime = self.binding("resource_limits", "R07")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES"], "5")
        self.assertEqual(cmake["SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA"], "1")
        self.assertEqual(
            cmake["SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS"], "1000"
        )
        self.assertEqual(runtime["dynamic_outage_marker"], RESOURCE_MARKER)
        self.assertTrue(runtime["allow_publish_failures"])

    def test_seconds_must_map_exactly_to_milliseconds(self) -> None:
        self.assertEqual(milliseconds(0.25), 250)
        with self.assertRaises(ValueError):
            milliseconds(0.0005)


if __name__ == "__main__":
    unittest.main()
