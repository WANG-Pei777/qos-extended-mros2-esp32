#!/usr/bin/env python3

from __future__ import annotations

import unittest

from validate_qos_compatibility_host_probe import validate


def records(
    *,
    role: str = "publisher",
    expected_match: int = 1,
    actual_match: int = 1,
    match_count: int = 1,
    tx: int = 3,
    rx: int = 0,
    status: str = "PASS",
) -> list[str]:
    config = (
        "QOS_HOST_CONFIG schema=1 case_id=CASE-01 "
        f"role={role} expected_match={expected_match} message_count=3"
    )
    final = (
        "QOS_HOST_FINAL schema=1 case_id=CASE-01 "
        f"role={role} expected_match={expected_match} actual_match={actual_match} "
        f"max_match_count={match_count} tx={tx} rx={rx} status={status}"
    )
    return [config, final]


class HostProbeValidationTest(unittest.TestCase):
    def test_matched_publisher(self) -> None:
        summary = validate(records(), "CASE-01", "publisher", True)
        self.assertEqual(summary["tx"], 3)

    def test_expected_mismatch(self) -> None:
        summary = validate(
            records(expected_match=0, actual_match=0, match_count=0, tx=0),
            "CASE-01",
            "publisher",
            False,
        )
        self.assertEqual(summary["actual_match"], 0)

    def test_matched_subscriber(self) -> None:
        summary = validate(
            records(role="subscriber", tx=0, rx=3),
            "CASE-01",
            "subscriber",
            True,
        )
        self.assertEqual(summary["rx"], 3)

    def test_matched_subscriber_without_data_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "received no application message"):
            validate(
                records(role="subscriber", tx=0, rx=0),
                "CASE-01",
                "subscriber",
                True,
            )

    def test_unexpected_match_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "actual match"):
            validate(
                records(expected_match=0, actual_match=1, match_count=1, tx=0),
                "CASE-01",
                "publisher",
                False,
            )

    def test_short_publisher_send_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "configured message count"):
            validate(records(tx=2), "CASE-01", "publisher", True)

    def test_mismatched_endpoint_with_data_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "application traffic"):
            validate(
                records(
                    role="subscriber",
                    expected_match=0,
                    actual_match=0,
                    match_count=0,
                    tx=0,
                    rx=1,
                ),
                "CASE-01",
                "subscriber",
                False,
            )

    def test_error_record_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "QOS_HOST_ERROR"):
            validate(
                ["QOS_HOST_ERROR schema=1 reason=invalid_arguments"],
                "CASE-01",
                "publisher",
                True,
            )


if __name__ == "__main__":
    unittest.main()
