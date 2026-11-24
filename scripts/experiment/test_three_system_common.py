#!/usr/bin/env python3
"""Unit tests for the frozen three-system protocol."""

from pathlib import Path
import unittest

from three_system_common import (
    SYSTEM_ORDER,
    file_record,
    generate_schedule,
    parse_compare_serial,
    validate_schedule,
    verify_agent_runtime,
)


def serial_fixture(system="mros2qos", samples=3):
    values = [1000 + sequence * 100 for sequence in range(samples)]
    lines = [
        f"COMPARE_CONFIG system={system} qos=BEST_EFFORT payload_bytes=64 "
        "messages=40 period_ms=500 settle_ms=1000 grace_ms=5000",
    ]
    if system == "microros":
        lines.append("COMPARE_SESSION system=microros established_ms=120")
    lines.extend(
        [
            f"COMPARE_RESOURCE system={system} free_heap_bytes=123456",
            f"COMPARE_READY system={system} ready_ms=250",
        ]
    )
    lines.extend(
        f"COMPARE_RTT system={system} seq={sequence} rtt_us={value}"
        for sequence, value in enumerate(values)
    )
    suffix = " publish_failures=0" if system == "microros" else ""
    lines.append(
        f"COMPARE_FINAL system={system} tx=40 rx={samples} samples={samples} "
        f"min_us={min(values) if values else 0} "
        f"avg_us={sum(values) // samples if samples else 0} "
        f"max_us={max(values) if values else 0} ready_ms=250 "
        f"payload_bytes=64 period_ms=500 grace_ms=5000{suffix}"
    )
    return "\n".join(lines)


class ScheduleTests(unittest.TestCase):
    def test_schedule_is_deterministic_and_balanced(self):
        first = generate_schedule()
        self.assertEqual(first, generate_schedule())
        validate_schedule(first)
        self.assertEqual(len(first), 30)
        for system in SYSTEM_ORDER:
            self.assertEqual(sum(row["system"] == system for row in first), 10)

    def test_mutated_schedule_fails(self):
        rows = generate_schedule()
        rows[0]["system"] = rows[1]["system"]
        with self.assertRaises(ValueError):
            validate_schedule(rows)

    def test_agent_runtime_binds_binary_launcher_and_package_revision(self):
        launcher = Path("/usr/bin/echo")
        record = {
            "artifact": file_record(Path("/usr/bin/true")),
            "launcher": file_record(launcher),
            "launch_command": [str(launcher), "run", "micro-ros-agent"],
            "package_query_command": [str(launcher), "micro-ros-agent 1"],
            "package_query_output": "micro-ros-agent 1",
        }
        self.assertEqual(verify_agent_runtime(record), record["launch_command"])
        changed = {**record, "package_query_output": "micro-ros-agent 2"}
        with self.assertRaises(ValueError):
            verify_agent_runtime(changed)


class SerialContractTests(unittest.TestCase):
    def test_all_system_contracts(self):
        for system in SYSTEM_ORDER:
            with self.subTest(system=system):
                parsed = parse_compare_serial(serial_fixture(system), system)
                self.assertTrue(parsed["accepted"], parsed["errors"])

    def test_zero_rx_is_an_accepted_outcome(self):
        parsed = parse_compare_serial(serial_fixture(samples=0), "mros2qos")
        self.assertTrue(parsed["accepted"], parsed["errors"])
        self.assertEqual(parsed["rx"], 0)

    def test_missing_rtt_is_instrumentation_failure(self):
        text = serial_fixture(samples=3).replace(
            "COMPARE_RTT system=mros2qos seq=1 rtt_us=1100\n", ""
        )
        parsed = parse_compare_serial(text, "mros2qos")
        self.assertFalse(parsed["accepted"])
        self.assertIn("final_rtt_count_mismatch", parsed["errors"])

    def test_delivery_is_not_required_to_be_complete(self):
        parsed = parse_compare_serial(serial_fixture(samples=1), "mros2qos")
        self.assertTrue(parsed["accepted"], parsed["errors"])

    def test_duplicate_sequence_fails(self):
        text = serial_fixture(samples=3).replace(
            "COMPARE_FINAL",
            "COMPARE_RTT system=mros2qos seq=1 rtt_us=1100\nCOMPARE_FINAL",
        )
        parsed = parse_compare_serial(text, "mros2qos")
        self.assertFalse(parsed["accepted"])
        self.assertIn("rtt_duplicate:1", parsed["errors"])


if __name__ == "__main__":
    unittest.main()
