#!/usr/bin/env python3

from __future__ import annotations

import unittest

from validate_qos_compatibility_board_probe import validate


def records(
    *,
    role: str = "publisher",
    expected_match: int = 1,
    actual_match: int = 1,
    tx_attempts: int = 3,
    tx_accepted: int = 3,
    rx: int = 0,
    status: str = "PASS",
) -> list[str]:
    return [
        "QOS_BOARD_CONFIG schema=1 case_id=CASE-01 "
        f"role={role} reliability=reliable durability=volatile deadline_ms=infinite "
        f"liveliness=automatic liveliness_lease_ms=infinite expected_match={expected_match} "
        "message_count=3",
        "QOS_BOARD_LOCAL_READY schema=1 case_id=CASE-01 board_time_us=100",
        "QOS_BOARD_FINAL schema=1 case_id=CASE-01 "
        f"role={role} expected_match={expected_match} actual_match={actual_match} "
        f"tx_attempts={tx_attempts} tx_accepted={tx_accepted} rx={rx} status={status}",
    ]


def validate_records(lines: list[str], role: str, expected_match: bool) -> dict[str, int]:
    return validate(
        lines,
        case_id="CASE-01",
        role=role,
        reliability="reliable",
        durability="volatile",
        deadline_ms="infinite",
        liveliness_lease_ms="infinite",
        expected_match=expected_match,
    )


class BoardProbeValidationTest(unittest.TestCase):
    def test_matched_publisher(self) -> None:
        self.assertEqual(validate_records(records(), "publisher", True)["tx_accepted"], 3)

    def test_matched_subscriber(self) -> None:
        summary = validate_records(
            records(role="subscriber", tx_attempts=0, tx_accepted=0, rx=3),
            "subscriber",
            True,
        )
        self.assertEqual(summary["rx"], 3)

    def test_mismatch(self) -> None:
        summary = validate_records(
            records(expected_match=0, actual_match=0, tx_attempts=0, tx_accepted=0),
            "publisher",
            False,
        )
        self.assertEqual(summary["actual_match"], 0)

    def test_short_publish_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "all configured"):
            validate_records(records(tx_accepted=2), "publisher", True)

    def test_watchdog_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "watchdog"):
            validate_records(records() + ["Task watchdog got triggered"], "publisher", True)


if __name__ == "__main__":
    unittest.main()
