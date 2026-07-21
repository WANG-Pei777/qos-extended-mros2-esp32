#!/usr/bin/env python3

import unittest

from validate_seven_qos_mechanism_board_log import validate_log


def log_for(kind: str, final_fields: str, status: str = "PASS") -> str:
    return (
        f"MECH_BOARD_CONFIG schema=1 case_id=CASE kind={kind} "
        f"history_capacity=100 monitor_period_ms=5 tick_hz=1000\n"
        f"MECH_BOARD_FINAL schema=1 case_id=CASE kind={kind} "
        f"sample_bytes=72 heap_before=100 heap_after=90 minimum_free_heap=80 "
        f"stack_high_watermark=50 heap_integrity=1 matched=0 "
        f"pressure_pbufs=0 recovery_observed=0 app_rx=0 reader_received=0 "
        f"out_of_order_drops=0 first_rx_hash=0 second_rx_hash=0 "
        f"deadline_missed=0 deadline_callbacks=0 deadline_latency_us=0 "
        f"deadline_latency_ms=0 "
        f"liveliness_lost=0 liveliness_recovered=0 "
        f"liveliness_lost_callbacks=0 liveliness_recovered_callbacks=0 "
        f"lifespan_drops=0 hold_start_us=0 hold_end_us=0 "
        f"heap_after_pressure=0 boot_epoch=0 {final_fields} status={status}\n"
    )


class BoardLogValidationTests(unittest.TestCase):
    def test_sample_reject_passes(self) -> None:
        report = validate_log(
            log_for(
                "resource_sample_reject",
                "attempts=6 accepted=5 rejected=1 allocation_failures=0 "
                "history_count=5 history_bytes=360",
            ),
            "CASE",
            "resource_sample_reject",
            5,
        )
        self.assertEqual(report["status"], "PASS")

    def test_byte_accounting_failure_is_rejected(self) -> None:
        report = validate_log(
            log_for(
                "resource_byte_bound",
                "attempts=3 accepted=2 rejected=1 allocation_failures=0 "
                "history_count=2 history_bytes=145",
            ),
            "CASE",
            "resource_byte_bound",
            5,
        )
        self.assertEqual(report["status"], "FAIL")

    def test_pbuf_pressure_allocation_failure_passes(self) -> None:
        text = log_for(
            "resource_alloc_fail",
            "attempts=1 accepted=0 rejected=0 allocation_failures=1 "
            "history_count=0 history_bytes=0",
        ).replace("pressure_pbufs=0", "pressure_pbufs=117")
        report = validate_log(text, "CASE", "resource_alloc_fail", 5)
        self.assertEqual(report["status"], "PASS")

    def test_unpressured_allocation_failure_is_rejected(self) -> None:
        report = validate_log(
            log_for(
                "resource_alloc_fail",
                "attempts=1 accepted=0 rejected=0 allocation_failures=1 "
                "history_count=0 history_bytes=0",
            ),
            "CASE",
            "resource_alloc_fail",
            5,
        )
        self.assertEqual(report["status"], "FAIL")

    def test_crash_marker_is_rejected(self) -> None:
        report = validate_log(
            log_for(
                "resource_sample_bound",
                "attempts=5 accepted=5 rejected=0 allocation_failures=0 "
                "history_count=5 history_bytes=360",
            )
            + "Guru Meditation Error\n",
            "CASE",
            "resource_sample_bound",
            5,
        )
        self.assertEqual(report["status"], "FAIL")

    def test_machine_marker_after_final_is_rejected(self) -> None:
        report = validate_log(
            log_for(
                "resource_sample_bound",
                "attempts=5 accepted=5 rejected=0 allocation_failures=0 "
                "history_count=5 history_bytes=360",
            )
            + "MECH_BOARD_EVENT schema=1 case_id=CASE event=late\n",
            "CASE",
            "resource_sample_bound",
            5,
        )
        self.assertEqual(report["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
