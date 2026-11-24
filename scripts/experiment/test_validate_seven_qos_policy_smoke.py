#!/usr/bin/env python3

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from validate_seven_qos_policy_smoke import main


class SevenQosPolicySmokeValidatorTest(unittest.TestCase):
    def run_validator(self, policy: str, expected_events: str) -> int:
        config = (
            "COMPARE_CONFIG system=mros2qos qos=RELIABLE payload_bytes=64 "
            "messages=200 period_ms=100 settle_ms=1000 grace_ms=5000 "
            "telemetry=on family=deadline cell_id=DL01 deadline_ms=50\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.raw"
            path.write_text(config + policy + "\n")
            argv = [
                "validate_seven_qos_policy_smoke.py",
                str(path),
                "--family",
                "deadline",
                "--cell-id",
                "DL01",
                "--deadline-ms",
                "50",
                "--publish-period-ms",
                "100",
                "--expected-events",
                expected_events,
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                return main()

    def run_lifespan_validator(
        self,
        policy: str,
        *,
        lifespan_ms: int,
        expected_drops: str,
        expected_replies: int,
        expected_delivery: str,
    ) -> int:
        cell_id = "LS01" if lifespan_ms == 0 else "LS02"
        config = (
            "COMPARE_CONFIG system=mros2qos qos=RELIABLE payload_bytes=64 "
            "messages=200 period_ms=100 settle_ms=1000 grace_ms=5000 "
            f"telemetry=on family=lifespan cell_id={cell_id} deadline_ms=0 "
            f"lifespan_ms={lifespan_ms} release_delay_ms=100\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.raw"
            delivered = 0 if expected_delivery == "zero" else 200
            bench_final = (
                "BENCH_FINAL schema=1 run_token=test record_seq=1 "
                f"attempted_tx=200 rx={delivered}\n"
            )
            path.write_text(config + policy + "\n" + bench_final)
            argv = [
                "validate_seven_qos_policy_smoke.py",
                str(path),
                "--family",
                "lifespan",
                "--cell-id",
                cell_id,
                "--publish-period-ms",
                "100",
                "--lifespan-ms",
                str(lifespan_ms),
                "--release-delay-ms",
                "100",
                "--expected-lifespan-drops",
                expected_drops,
                "--expected-probe-replies",
                str(expected_replies),
                "--expected-measurement-delivery",
                expected_delivery,
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                return main()

    def run_resource_validator(
        self,
        policy: str,
        *,
        cell_id: str,
        max_samples: int,
        probe_extra: int,
        expected_rejections: str,
        delivered: int = 1000,
        publish_failures: int = 0,
        expected_delivery: str = "full",
        expected_publish_failures: str = "zero",
        ack_suppression_ms: int = 0,
        expected_probe_replies: str = "accepted",
    ) -> int:
        config = (
            "COMPARE_CONFIG system=mros2qos qos=RELIABLE payload_bytes=512 "
            "messages=1000 period_ms=20 settle_ms=1000 grace_ms=5000 "
            f"telemetry=on family=resource_limits cell_id={cell_id} "
            "deadline_ms=0 lifespan_ms=0 release_delay_ms=0 "
            f"resource_max_samples={max_samples} "
            f"resource_probe_extra={probe_extra} "
            f"resource_ack_suppression_ms={ack_suppression_ms}\n"
        )
        bench_final = (
            "BENCH_FINAL schema=1 run_token=test record_seq=1 "
            f"attempted_tx=1000 publish_failures={publish_failures} "
            f"rx={delivered}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.raw"
            policy_with_ack = (
                policy
                + f" resource_ack_suppression_ms={ack_suppression_ms}"
            )
            path.write_text(config + policy_with_ack + "\n" + bench_final)
            argv = [
                "validate_seven_qos_policy_smoke.py",
                str(path),
                "--family",
                "resource_limits",
                "--cell-id",
                cell_id,
                "--publish-period-ms",
                "20",
                "--resource-max-samples",
                str(max_samples),
                "--resource-probe-extra",
                str(probe_extra),
                "--resource-ack-suppression-ms",
                str(ack_suppression_ms),
                "--expected-resource-rejections",
                expected_rejections,
                "--expected-resource-probe-replies",
                expected_probe_replies,
                "--expected-measurement-delivery",
                expected_delivery,
                "--expected-measurement-publish-failures",
                expected_publish_failures,
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                return main()

    def run_history_validator(
        self,
        policy: str,
        *,
        depth: int,
        burst_size: int,
    ) -> int:
        config = (
            "COMPARE_CONFIG system=mros2qos qos=RELIABLE payload_bytes=64 "
            "messages=200 period_ms=100 settle_ms=1000 grace_ms=5000 "
            "telemetry=on family=history_depth cell_id=HSM "
            "deadline_ms=0 lifespan_ms=0 release_delay_ms=0 "
            "resource_max_samples=0 resource_probe_extra=0 "
            f"history_depth={depth} history_burst_size={burst_size}\n"
        )
        bench_final = (
            "BENCH_FINAL schema=1 run_token=test record_seq=1 "
            "attempted_tx=200 publish_failures=0 rx=200\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.raw"
            path.write_text(config + policy + "\n" + bench_final)
            argv = [
                "validate_seven_qos_policy_smoke.py",
                str(path),
                "--family",
                "history_depth",
                "--cell-id",
                "HSM",
                "--publish-period-ms",
                "100",
                "--history-depth",
                str(depth),
                "--history-burst-size",
                str(burst_size),
                "--expected-measurement-delivery",
                "full",
                "--expected-measurement-publish-failures",
                "zero",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                return main()

    def run_durability_validator(
        self, policy: str, durability: str, *, include_markers: bool = True
    ) -> int:
        config = (
            "COMPARE_CONFIG system=mros2qos qos=RELIABLE payload_bytes=64 "
            "messages=200 period_ms=100 settle_ms=1000 grace_ms=5000 "
            "telemetry=on family=durability cell_id=DSM "
            "deadline_ms=0 lifespan_ms=0 release_delay_ms=0 "
            "resource_max_samples=0 resource_probe_extra=0 "
            "history_depth=0 history_burst_size=0 "
            f"durability={durability} durability_cache_depth=10 "
            "durability_prejoin_samples=10\n"
        )
        bench_final = (
            "BENCH_FINAL schema=1 run_token=test record_seq=1 "
            "attempted_tx=200 publish_failures=0 rx=200\n"
        )
        markers = (
            "PERF_DURABILITY_PREJOIN_READY schema=1 cell_id=DSM "
            f"durability={durability} samples=10 history=10\n"
            "PERF_DURABILITY_BIDIRECTIONAL_READY schema=1 cell_id=DSM\n"
            if include_markers
            else ""
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.raw"
            path.write_text(config + markers + policy + "\n" + bench_final)
            argv = [
                "validate_seven_qos_policy_smoke.py",
                str(path),
                "--family",
                "durability",
                "--cell-id",
                "DSM",
                "--publish-period-ms",
                "100",
                "--durability",
                durability,
                "--durability-cache-depth",
                "10",
                "--durability-prejoin-samples",
                "10",
                "--expected-measurement-delivery",
                "full",
                "--expected-measurement-publish-failures",
                "zero",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                return main()

    def run_liveliness_validator(
        self,
        policy: str,
        *,
        lease_ms: int,
        outage_ms: int,
        expected_transition: str,
        include_marker: bool = True,
    ) -> int:
        config = (
            "COMPARE_CONFIG system=mros2qos qos=RELIABLE payload_bytes=64 "
            "messages=200 period_ms=100 settle_ms=1000 grace_ms=5000 "
            "telemetry=on family=liveliness cell_id=LVSM deadline_ms=0 "
            f"liveliness_lease_ms={lease_ms} liveliness_outage_ms={outage_ms}\n"
        )
        marker = (
            "PERF_LIVELINESS_OUTAGE_READY schema=1 cell_id=LVSM "
            f"lease_ms={lease_ms} outage_ms={outage_ms}\n"
            if include_marker
            else ""
        )
        bench_final = (
            "BENCH_FINAL schema=1 run_token=test record_seq=1 "
            "attempted_tx=200 publish_failures=0 rx=200\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.raw"
            path.write_text(config + marker + policy + "\n" + bench_final)
            argv = [
                "validate_seven_qos_policy_smoke.py",
                str(path),
                "--family", "liveliness",
                "--cell-id", "LVSM",
                "--publish-period-ms", "100",
                "--liveliness-lease-ms", str(lease_ms),
                "--liveliness-outage-ms", str(outage_ms),
                "--expected-liveliness-transition", expected_transition,
                "--expected-measurement-delivery", "full",
                "--expected-measurement-publish-failures", "zero",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(
                StringIO()
            ), redirect_stderr(StringIO()):
                return main()

    def test_positive_deadline_event_passes(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=deadline family_code=1 "
            "cell_id=DL01 deadline_ms=50 publish_period_ms=100 "
            "deadline_missed_before=2 deadline_missed_after=12 "
            "deadline_missed_delta=10 deadline_callbacks=10 "
            "first_deadline_callback_offset_us=50000"
        )
        self.assertEqual(self.run_validator(policy, "positive"), 0)

    def test_zero_deadline_event_passes(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=deadline family_code=1 "
            "cell_id=DL01 deadline_ms=50 publish_period_ms=100 "
            "deadline_missed_before=2 deadline_missed_after=2 "
            "deadline_missed_delta=0 deadline_callbacks=0 "
            "first_deadline_callback_offset_us=-1"
        )
        self.assertEqual(self.run_validator(policy, "zero"), 0)

    def test_counter_callback_disagreement_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=deadline family_code=1 "
            "cell_id=DL01 deadline_ms=50 publish_period_ms=100 "
            "deadline_missed_before=2 deadline_missed_after=12 "
            "deadline_missed_delta=10 deadline_callbacks=9 "
            "first_deadline_callback_offset_us=50000"
        )
        self.assertEqual(self.run_validator(policy, "positive"), 1)

    def test_expired_lifespan_probe_passes(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=lifespan family_code=2 "
            "cell_id=LS02 deadline_ms=0 publish_period_ms=100 "
            "lifespan_ms=50 release_delay_ms=100 lifespan_drop_before=0 "
            "lifespan_drop_after=1 lifespan_drop_delta=1 "
            "lifespan_drop_final=201 lifespan_total_drop_delta=201 "
            "lifespan_probe_accepted=1 lifespan_probe_replies=0 "
            "hold_start_us=100000 hold_end_us=200500 hold_duration_us=100500"
        )
        self.assertEqual(
            self.run_lifespan_validator(
                policy,
                lifespan_ms=50,
                expected_drops="positive",
                expected_replies=0,
                expected_delivery="zero",
            ),
            0,
        )

    def test_disabled_lifespan_probe_passes(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=lifespan family_code=2 "
            "cell_id=LS01 deadline_ms=0 publish_period_ms=100 "
            "lifespan_ms=0 release_delay_ms=100 lifespan_drop_before=0 "
            "lifespan_drop_after=0 lifespan_drop_delta=0 "
            "lifespan_drop_final=0 lifespan_total_drop_delta=0 "
            "lifespan_probe_accepted=1 lifespan_probe_replies=1 "
            "hold_start_us=100000 hold_end_us=200500 hold_duration_us=100500"
        )
        self.assertEqual(
            self.run_lifespan_validator(
                policy,
                lifespan_ms=0,
                expected_drops="zero",
                expected_replies=1,
                expected_delivery="full",
            ),
            0,
        )

    def test_lifespan_hold_duration_mismatch_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=lifespan family_code=2 "
            "cell_id=LS02 deadline_ms=0 publish_period_ms=100 "
            "lifespan_ms=50 release_delay_ms=100 lifespan_drop_before=0 "
            "lifespan_drop_after=1 lifespan_drop_delta=1 "
            "lifespan_drop_final=201 lifespan_total_drop_delta=201 "
            "lifespan_probe_accepted=1 lifespan_probe_replies=0 "
            "hold_start_us=100000 hold_end_us=200500 hold_duration_us=99999"
        )
        self.assertEqual(
            self.run_lifespan_validator(
                policy,
                lifespan_ms=50,
                expected_drops="positive",
                expected_replies=0,
                expected_delivery="zero",
            ),
            1,
        )

    def test_resource_within_capacity_probe_passes(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=resource_limits family_code=3 "
            "cell_id=R00 deadline_ms=0 publish_period_ms=20 "
            "resource_max_samples=20 resource_probe_extra=0 "
            "resource_attempt_delta=20 resource_accept_delta=20 "
            "resource_reject_delta=0 resource_allocation_failure_delta=0 "
            "resource_history_peak=20 resource_history_after_release=0 "
            "resource_probe_replies=20"
        )
        self.assertEqual(
            self.run_resource_validator(
                policy,
                cell_id="R00",
                max_samples=20,
                probe_extra=0,
                expected_rejections="zero",
            ),
            0,
        )

    def test_resource_one_over_capacity_probe_passes(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=resource_limits family_code=3 "
            "cell_id=R01 deadline_ms=0 publish_period_ms=20 "
            "resource_max_samples=5 resource_probe_extra=1 "
            "resource_attempt_delta=6 resource_accept_delta=5 "
            "resource_reject_delta=1 resource_allocation_failure_delta=0 "
            "resource_history_peak=5 resource_history_after_release=0 "
            "resource_probe_replies=5"
        )
        self.assertEqual(
            self.run_resource_validator(
                policy,
                cell_id="R01",
                max_samples=5,
                probe_extra=1,
                expected_rejections="one",
            ),
            0,
        )

    def test_resource_pressure_delivery_reconciles(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=resource_limits family_code=3 "
            "cell_id=R01 deadline_ms=0 publish_period_ms=20 "
            "resource_max_samples=5 resource_probe_extra=1 "
            "resource_attempt_delta=6 resource_accept_delta=5 "
            "resource_reject_delta=1 resource_allocation_failure_delta=0 "
            "resource_history_peak=5 resource_history_after_release=0 "
            "resource_probe_replies=5"
        )
        self.assertEqual(
            self.run_resource_validator(
                policy,
                cell_id="R01",
                max_samples=5,
                probe_extra=1,
                expected_rejections="one",
                delivered=910,
                publish_failures=90,
                expected_delivery="published",
                expected_publish_failures="any",
            ),
            0,
        )

    def test_resource_ack_suppression_allows_positive_recovery_reply(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=resource_limits family_code=3 "
            "cell_id=R01ACK deadline_ms=0 publish_period_ms=20 "
            "resource_max_samples=5 resource_probe_extra=1 "
            "resource_attempt_delta=6 resource_accept_delta=5 "
            "resource_reject_delta=1 resource_allocation_failure_delta=0 "
            "resource_history_peak=5 resource_history_after_release=0 "
            "resource_probe_replies=1"
        )
        self.assertEqual(
            self.run_resource_validator(
                policy,
                cell_id="R01ACK",
                max_samples=5,
                probe_extra=1,
                expected_rejections="one",
                delivered=938,
                publish_failures=62,
                expected_delivery="published",
                expected_publish_failures="any",
                ack_suppression_ms=1000,
                expected_probe_replies="positive",
            ),
            0,
        )

    def test_resource_history_peak_mismatch_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=resource_limits family_code=3 "
            "cell_id=R01 deadline_ms=0 publish_period_ms=20 "
            "resource_max_samples=5 resource_probe_extra=1 "
            "resource_attempt_delta=6 resource_accept_delta=5 "
            "resource_reject_delta=1 resource_allocation_failure_delta=0 "
            "resource_history_peak=4 resource_history_after_release=0 "
            "resource_probe_replies=5"
        )
        self.assertEqual(
            self.run_resource_validator(
                policy,
                cell_id="R01",
                max_samples=5,
                probe_extra=1,
                expected_rejections="one",
            ),
            1,
        )

    def test_history_depth_evicts_oldest_suffix(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=history_depth family_code=4 "
            "cell_id=HSM deadline_ms=0 publish_period_ms=100 "
            "history_depth=5 history_burst_size=10 "
            "history_attempt_delta=10 history_accept_delta=10 "
            "history_reject_delta=0 history_allocation_failure_delta=0 "
            "history_peak=5 history_after_release=0 "
            "history_probe_replies=5 history_probe_reply_mask=0x00000000000003e0"
        )
        self.assertEqual(
            self.run_history_validator(policy, depth=5, burst_size=10), 0
        )

    def test_history_depth_retains_complete_burst(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=history_depth family_code=4 "
            "cell_id=HSM deadline_ms=0 publish_period_ms=100 "
            "history_depth=20 history_burst_size=10 "
            "history_attempt_delta=10 history_accept_delta=10 "
            "history_reject_delta=0 history_allocation_failure_delta=0 "
            "history_peak=10 history_after_release=0 "
            "history_probe_replies=10 history_probe_reply_mask=0x00000000000003ff"
        )
        self.assertEqual(
            self.run_history_validator(policy, depth=20, burst_size=10), 0
        )

    def test_history_depth_wrong_suffix_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=history_depth family_code=4 "
            "cell_id=HSM deadline_ms=0 publish_period_ms=100 "
            "history_depth=5 history_burst_size=10 "
            "history_attempt_delta=10 history_accept_delta=10 "
            "history_reject_delta=0 history_allocation_failure_delta=0 "
            "history_peak=5 history_after_release=0 "
            "history_probe_replies=5 history_probe_reply_mask=0x000000000000001f"
        )
        self.assertEqual(
            self.run_history_validator(policy, depth=5, burst_size=10), 1
        )

    def test_volatile_durability_does_not_replay(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=durability family_code=5 "
            "cell_id=DSM deadline_ms=0 publish_period_ms=100 "
            "durability=volatile durability_code=0 "
            "durability_cache_depth=10 durability_prejoin_samples=10 "
            "durability_attempt_delta=10 durability_accept_delta=10 "
            "durability_reject_delta=0 durability_allocation_failure_delta=0 "
            "durability_history_prejoin=10 durability_history_after_join=0 "
            "durability_probe_replies=0 durability_probe_reply_mask=0x0 "
            "durability_reader_matched=1"
        )
        self.assertEqual(self.run_durability_validator(policy, "volatile"), 0)

    def test_transient_local_durability_replays_cache(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=durability family_code=5 "
            "cell_id=DSM deadline_ms=0 publish_period_ms=100 "
            "durability=transient_local durability_code=1 "
            "durability_cache_depth=10 durability_prejoin_samples=10 "
            "durability_attempt_delta=10 durability_accept_delta=10 "
            "durability_reject_delta=0 durability_allocation_failure_delta=0 "
            "durability_history_prejoin=10 durability_history_after_join=10 "
            "durability_probe_replies=10 "
            "durability_probe_reply_mask=0x00000000000003ff "
            "durability_reader_matched=1"
        )
        self.assertEqual(
            self.run_durability_validator(policy, "transient_local"), 0
        )

    def test_transient_local_missing_replay_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=durability family_code=5 "
            "cell_id=DSM deadline_ms=0 publish_period_ms=100 "
            "durability=transient_local durability_code=1 "
            "durability_cache_depth=10 durability_prejoin_samples=10 "
            "durability_attempt_delta=10 durability_accept_delta=10 "
            "durability_reject_delta=0 durability_allocation_failure_delta=0 "
            "durability_history_prejoin=10 durability_history_after_join=10 "
            "durability_probe_replies=9 durability_probe_reply_mask=0x1ff "
            "durability_reader_matched=1"
        )
        self.assertEqual(
            self.run_durability_validator(policy, "transient_local"), 1
        )

    def test_durability_missing_readiness_markers_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=durability family_code=5 "
            "cell_id=DSM deadline_ms=0 publish_period_ms=100 "
            "durability=volatile durability_code=0 "
            "durability_cache_depth=10 durability_prejoin_samples=10 "
            "durability_attempt_delta=10 durability_accept_delta=10 "
            "durability_reject_delta=0 durability_allocation_failure_delta=0 "
            "durability_history_prejoin=10 durability_history_after_join=0 "
            "durability_probe_replies=0 durability_probe_reply_mask=0x0 "
            "durability_reader_matched=1"
        )
        self.assertEqual(
            self.run_durability_validator(
                policy, "volatile", include_markers=False
            ),
            1,
        )

    def test_liveliness_short_outage_has_no_transition(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=liveliness family_code=6 "
            "cell_id=LVSM deadline_ms=0 publish_period_ms=100 "
            "liveliness_lease_ms=2000 liveliness_outage_ms=250 "
            "liveliness_lost_before=0 liveliness_lost_after=0 "
            "liveliness_lost_delta=0 liveliness_recovered_before=0 "
            "liveliness_recovered_after=0 liveliness_recovered_delta=0 "
            "liveliness_lost_callbacks=0 liveliness_recovered_callbacks=0 "
            "first_liveliness_lost_offset_us=-1 "
            "first_liveliness_recovered_offset_us=-1 "
            "liveliness_writer_alive_final=1"
        )
        self.assertEqual(
            self.run_liveliness_validator(
                policy,
                lease_ms=2000,
                outage_ms=250,
                expected_transition="none",
            ),
            0,
        )

    def test_liveliness_long_outage_loses_and_recovers(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=liveliness family_code=6 "
            "cell_id=LVSM deadline_ms=0 publish_period_ms=100 "
            "liveliness_lease_ms=500 liveliness_outage_ms=1000 "
            "liveliness_lost_before=0 liveliness_lost_after=1 "
            "liveliness_lost_delta=1 liveliness_recovered_before=0 "
            "liveliness_recovered_after=1 liveliness_recovered_delta=1 "
            "liveliness_lost_callbacks=1 liveliness_recovered_callbacks=1 "
            "first_liveliness_lost_offset_us=475000 "
            "first_liveliness_recovered_offset_us=1120000 "
            "liveliness_writer_alive_final=1"
        )
        self.assertEqual(
            self.run_liveliness_validator(
                policy,
                lease_ms=500,
                outage_ms=1000,
                expected_transition="lost_recovered",
            ),
            0,
        )

    def test_liveliness_missing_marker_fails(self) -> None:
        policy = (
            "PERF_POLICY_FINAL schema=1 family=liveliness family_code=6 "
            "cell_id=LVSM deadline_ms=0 publish_period_ms=100 "
            "liveliness_lease_ms=500 liveliness_outage_ms=1000 "
            "liveliness_lost_before=0 liveliness_lost_after=1 "
            "liveliness_lost_delta=1 liveliness_recovered_before=0 "
            "liveliness_recovered_after=1 liveliness_recovered_delta=1 "
            "liveliness_lost_callbacks=1 liveliness_recovered_callbacks=1 "
            "first_liveliness_lost_offset_us=475000 "
            "first_liveliness_recovered_offset_us=1120000 "
            "liveliness_writer_alive_final=1"
        )
        self.assertEqual(
            self.run_liveliness_validator(
                policy,
                lease_ms=500,
                outage_ms=1000,
                expected_transition="lost_recovered",
                include_marker=False,
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
