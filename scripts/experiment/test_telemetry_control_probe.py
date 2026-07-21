#!/usr/bin/env python3

from __future__ import annotations

import unittest

from telemetry_control_probe import validate_control_probe


def record(**overrides: str | int) -> str:
    fields: dict[str, str | int] = {
        "schema": 1,
        "system": "mros2qos",
        "telemetry": "off",
        "start_begin_us": 1_000_000,
        "end_end_us": 21_000_100,
        "wall0_us": 20_000_000,
        "wall1_us": 20_000_000,
        "idle0_delta_us": 19_000_000,
        "idle1_delta_us": 18_000_000,
        "busy0_ppm": 50_000,
        "busy1_ppm": 100_000,
        "busy_mean_ppm": 75_000,
        "fault_flags": "0x00000000",
    }
    fields.update(overrides)
    return "COMPARE_CPU_CONTROL " + " ".join(
        f"{key}={value}" for key, value in fields.items()
    )


class ControlProbeValidationTest(unittest.TestCase):
    def test_valid_record(self) -> None:
        result = validate_control_probe(
            [record()], system="mros2qos", telemetry="off", required=True
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["busy_mean_ppm"], 75_000)

    def test_optional_legacy_record(self) -> None:
        self.assertIsNone(
            validate_control_probe(
                [], system="mros2qos", telemetry="off", required=False
            )
        )

    def test_required_record_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_control_probe(
                [], system="mros2qos", telemetry="off", required=True
            )

    def test_raw_counter_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "raw counters"):
            validate_control_probe(
                [record(busy0_ppm=49_999)],
                system="mros2qos",
                telemetry="off",
                required=True,
            )

    def test_fault_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "fault_flags"):
            validate_control_probe(
                [record(fault_flags="0x4")],
                system="mros2qos",
                telemetry="off",
                required=True,
            )

    def test_duplicate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected one"):
            validate_control_probe(
                [record(), record()],
                system="mros2qos",
                telemetry="off",
                required=True,
            )


if __name__ == "__main__":
    unittest.main()
