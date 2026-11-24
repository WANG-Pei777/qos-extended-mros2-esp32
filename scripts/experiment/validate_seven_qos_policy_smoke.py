#!/usr/bin/env python3
"""Validate the policy-specific record in an excluded Seven-QoS pilot."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_record(line: str, prefix: str) -> dict[str, str]:
    if not line.startswith(prefix + " "):
        raise ValueError(f"expected {prefix} record")
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            raise ValueError(f"malformed token {token!r}")
        key, value = token.split("=", 1)
        if key in fields:
            raise ValueError(f"duplicate field {key!r}")
        fields[key] = value
    return fields


def integer(fields: dict[str, str], key: str) -> int:
    if key not in fields:
        raise ValueError(f"missing field {key!r}")
    return int(fields[key], 0)


def require_fields(
    record_name: str, actual: dict[str, str], expected: dict[str, str]
) -> None:
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError(
                f"{record_name} {key}={actual.get(key)!r}, expected {value!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("serial_log", type=Path)
    parser.add_argument(
        "--family",
        choices=(
            "deadline", "lifespan", "resource_limits", "history_depth",
            "durability", "liveliness",
        ),
        required=True,
    )
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--deadline-ms", type=int, default=0)
    parser.add_argument("--publish-period-ms", type=int, required=True)
    parser.add_argument(
        "--expected-events", choices=("zero", "positive", "any"), default="any"
    )
    parser.add_argument("--lifespan-ms", type=int, default=0)
    parser.add_argument("--release-delay-ms", type=int, default=0)
    parser.add_argument(
        "--expected-lifespan-drops", choices=("zero", "positive")
    )
    parser.add_argument("--expected-probe-replies", type=int)
    parser.add_argument(
        "--expected-measurement-delivery",
        choices=("zero", "full", "published", "any"),
    )
    parser.add_argument("--resource-max-samples", type=int, default=0)
    parser.add_argument("--resource-probe-extra", type=int, default=0)
    parser.add_argument("--resource-ack-suppression-ms", type=int, default=0)
    parser.add_argument(
        "--expected-resource-rejections", choices=("zero", "one")
    )
    parser.add_argument(
        "--expected-resource-probe-replies",
        choices=("accepted", "positive", "any"),
        default="accepted",
    )
    parser.add_argument(
        "--expected-measurement-publish-failures",
        choices=("zero", "nonzero", "any"),
    )
    parser.add_argument("--history-depth", type=int, default=0)
    parser.add_argument("--history-burst-size", type=int, default=0)
    parser.add_argument(
        "--durability", choices=("volatile", "transient_local")
    )
    parser.add_argument("--durability-cache-depth", type=int, default=0)
    parser.add_argument("--durability-prejoin-samples", type=int, default=0)
    parser.add_argument("--liveliness-lease-ms", type=int, default=0)
    parser.add_argument("--liveliness-outage-ms", type=int, default=0)
    parser.add_argument(
        "--expected-liveliness-transition",
        choices=("none", "lost_recovered"),
    )
    args = parser.parse_args()

    if (
        args.deadline_ms < 0
        or args.lifespan_ms < 0
        or args.release_delay_ms < 0
        or args.publish_period_ms <= 0
    ):
        parser.error("policy durations must be nonnegative and period positive")
    if args.family == "lifespan" and (
        args.expected_lifespan_drops is None
        or args.expected_probe_replies is None
        or args.expected_probe_replies < 0
        or args.expected_measurement_delivery is None
    ):
        parser.error(
            "Lifespan requires drop, probe-reply, and delivery expectations"
        )
    if args.family == "resource_limits" and (
        args.resource_max_samples <= 0
        or args.resource_probe_extra not in (0, 1)
        or args.resource_ack_suppression_ms < 0
        or args.expected_resource_rejections is None
        or args.expected_measurement_delivery is None
        or args.expected_measurement_publish_failures is None
    ):
        parser.error(
            "Resource Limits requires cap, rejection, and delivery expectations"
        )
    if args.family == "history_depth" and (
        not 1 <= args.history_depth <= 40
        or not 1 <= args.history_burst_size <= 40
        or args.expected_measurement_delivery is None
        or args.expected_measurement_publish_failures is None
    ):
        parser.error(
            "History/Depth requires depth, burst, and workload expectations"
        )
    if args.family == "durability" and (
        args.durability is None
        or not 1 <= args.durability_cache_depth <= 40
        or not 1 <= args.durability_prejoin_samples <= 40
        or args.expected_measurement_delivery is None
        or args.expected_measurement_publish_failures is None
    ):
        parser.error(
            "Durability requires kind, cache, pre-join, and workload expectations"
        )
    if args.family == "liveliness" and (
        args.liveliness_lease_ms <= 0
        or args.liveliness_outage_ms <= 0
        or args.expected_liveliness_transition is None
        or args.expected_measurement_delivery is None
        or args.expected_measurement_publish_failures is None
    ):
        parser.error(
            "Liveliness requires lease, outage, transition, and workload expectations"
        )

    text = args.serial_log.read_bytes().decode("utf-8", errors="replace")
    lines = [ANSI_RE.sub("", line).strip() for line in text.splitlines()]
    if "Backtrace:" in text or "watchdog" in text.lower():
        print("FAIL: crash/watchdog evidence found", file=sys.stderr)
        return 1

    configs = [line for line in lines if line.startswith("COMPARE_CONFIG ")]
    policies = [line for line in lines if line.startswith("PERF_POLICY_FINAL ")]
    if len(configs) != 1 or len(policies) != 1:
        print(
            "FAIL: expected one COMPARE_CONFIG and PERF_POLICY_FINAL, "
            f"found {len(configs)}/{len(policies)}",
            file=sys.stderr,
        )
        return 1

    try:
        config = parse_record(configs[0], "COMPARE_CONFIG")
        policy = parse_record(policies[0], "PERF_POLICY_FINAL")
        require_fields(
            "config",
            config,
            {
                "family": args.family,
                "cell_id": args.cell_id,
                "deadline_ms": str(args.deadline_ms),
                "period_ms": str(args.publish_period_ms),
            },
        )
        require_fields(
            "policy",
            policy,
            {
                "family": args.family,
                "cell_id": args.cell_id,
                "deadline_ms": str(args.deadline_ms),
                "publish_period_ms": str(args.publish_period_ms),
            },
        )
        expected_family_code = {
            "deadline": "1",
            "lifespan": "2",
            "resource_limits": "3",
            "history_depth": "4",
            "durability": "5",
            "liveliness": "6",
        }[args.family]
        if (
            policy.get("schema") != "1"
            or policy.get("family_code") != expected_family_code
        ):
            raise ValueError("unexpected policy schema or family code")

        if args.family == "deadline":
            before = integer(policy, "deadline_missed_before")
            after = integer(policy, "deadline_missed_after")
            delta = integer(policy, "deadline_missed_delta")
            callbacks = integer(policy, "deadline_callbacks")
            first_offset = integer(policy, "first_deadline_callback_offset_us")
            if after < before or delta != after - before:
                raise ValueError("deadline counter delta is inconsistent")
            if callbacks != delta:
                raise ValueError(
                    "callback count does not match deadline counter delta"
                )
            if callbacks == 0 and first_offset != -1:
                raise ValueError("zero callbacks require offset -1")
            if callbacks > 0 and not 0 <= first_offset <= 20_100_000:
                raise ValueError("first callback is outside the measurement window")
            if args.expected_events == "zero" and callbacks != 0:
                raise ValueError("expected zero deadline events")
            if args.expected_events == "positive" and callbacks == 0:
                raise ValueError("expected at least one deadline event")
            summary = (
                f"deadline_ms={args.deadline_ms} events={callbacks} "
                f"first_offset_us={first_offset}"
            )
        elif args.family == "lifespan":
            bench_finals = [
                line for line in lines if line.startswith("BENCH_FINAL ")
            ]
            if len(bench_finals) != 1:
                raise ValueError(
                    f"expected one BENCH_FINAL, found {len(bench_finals)}"
                )
            bench_final = parse_record(bench_finals[0], "BENCH_FINAL")
            require_fields(
                "config",
                config,
                {
                    "lifespan_ms": str(args.lifespan_ms),
                    "release_delay_ms": str(args.release_delay_ms),
                },
            )
            require_fields(
                "policy",
                policy,
                {
                    "lifespan_ms": str(args.lifespan_ms),
                    "release_delay_ms": str(args.release_delay_ms),
                    "lifespan_probe_accepted": "1",
                    "lifespan_probe_replies": str(args.expected_probe_replies),
                },
            )
            before = integer(policy, "lifespan_drop_before")
            after = integer(policy, "lifespan_drop_after")
            delta = integer(policy, "lifespan_drop_delta")
            final = integer(policy, "lifespan_drop_final")
            total_delta = integer(policy, "lifespan_total_drop_delta")
            hold_start = integer(policy, "hold_start_us")
            hold_end = integer(policy, "hold_end_us")
            hold_duration = integer(policy, "hold_duration_us")
            if after < before or delta != after - before:
                raise ValueError("Lifespan drop counter delta is inconsistent")
            if final < after or total_delta != final - before:
                raise ValueError("Lifespan total drop counter is inconsistent")
            if args.expected_lifespan_drops == "zero" and delta != 0:
                raise ValueError("expected zero Lifespan drops")
            if args.expected_lifespan_drops == "positive" and delta == 0:
                raise ValueError("expected at least one Lifespan drop")
            if hold_start < 0 or hold_end < hold_start:
                raise ValueError("invalid Lifespan hold timestamps")
            if hold_duration != hold_end - hold_start:
                raise ValueError("Lifespan hold duration is inconsistent")
            requested_hold_us = args.release_delay_ms * 1000
            minimum_hold_us = max(0, requested_hold_us - 2_000)
            if not minimum_hold_us <= hold_duration <= requested_hold_us + 50_000:
                raise ValueError("Lifespan hold duration is outside tolerance")
            attempted = integer(bench_final, "attempted_tx")
            delivered = integer(bench_final, "rx")
            if args.expected_measurement_delivery == "zero" and delivered != 0:
                raise ValueError("expected zero measurement delivery")
            if (
                args.expected_measurement_delivery == "full"
                and delivered != attempted
            ):
                raise ValueError("expected full measurement delivery")
            summary = (
                f"lifespan_ms={args.lifespan_ms} "
                f"release_delay_ms={args.release_delay_ms} drops={delta} "
                f"total_drops={total_delta} delivery={delivered}/{attempted} "
                f"probe_replies={args.expected_probe_replies} "
                f"hold_duration_us={hold_duration}"
            )
        elif args.family == "resource_limits":
            bench_finals = [
                line for line in lines if line.startswith("BENCH_FINAL ")
            ]
            if len(bench_finals) != 1:
                raise ValueError(
                    f"expected one BENCH_FINAL, found {len(bench_finals)}"
                )
            bench_final = parse_record(bench_finals[0], "BENCH_FINAL")
            require_fields(
                "config",
                config,
                {
                    "resource_max_samples": str(args.resource_max_samples),
                    "resource_probe_extra": str(args.resource_probe_extra),
                    "resource_ack_suppression_ms": str(
                        args.resource_ack_suppression_ms
                    ),
                },
            )
            require_fields(
                "policy",
                policy,
                {
                    "resource_max_samples": str(args.resource_max_samples),
                    "resource_probe_extra": str(args.resource_probe_extra),
                    "resource_ack_suppression_ms": str(
                        args.resource_ack_suppression_ms
                    ),
                },
            )
            attempts = integer(policy, "resource_attempt_delta")
            accepted = integer(policy, "resource_accept_delta")
            rejected = integer(policy, "resource_reject_delta")
            allocation_failures = integer(
                policy, "resource_allocation_failure_delta"
            )
            history_peak = integer(policy, "resource_history_peak")
            history_after = integer(policy, "resource_history_after_release")
            probe_replies = integer(policy, "resource_probe_replies")
            expected_rejected = (
                0 if args.expected_resource_rejections == "zero" else 1
            )
            if attempts != args.resource_max_samples + args.resource_probe_extra:
                raise ValueError("resource probe attempt count is inconsistent")
            if accepted != args.resource_max_samples:
                raise ValueError("resource probe accepted count is inconsistent")
            if rejected != expected_rejected:
                raise ValueError("resource probe rejection count is inconsistent")
            if rejected != args.resource_probe_extra:
                raise ValueError("resource rejection does not match probe excess")
            if allocation_failures != 0:
                raise ValueError("resource probe has allocation failures")
            if history_peak != args.resource_max_samples:
                raise ValueError("resource history peak does not reach the cap")
            if history_after != 0:
                raise ValueError("resource history did not drain after release")
            if (
                args.expected_resource_probe_replies == "accepted"
                and probe_replies != accepted
            ):
                raise ValueError("resource probe replies do not match acceptance")
            if (
                args.expected_resource_probe_replies == "positive"
                and probe_replies <= 0
            ):
                raise ValueError("resource probe has no recovery reply")
            attempted = integer(bench_final, "attempted_tx")
            delivered = integer(bench_final, "rx")
            publish_failures = integer(bench_final, "publish_failures")
            if args.expected_measurement_delivery == "zero" and delivered != 0:
                raise ValueError("expected zero measurement delivery")
            if (
                args.expected_measurement_delivery == "full"
                and delivered != attempted
            ):
                raise ValueError("expected full measurement delivery")
            if args.expected_measurement_delivery == "published" and (
                delivered == 0 or delivered != attempted - publish_failures
            ):
                raise ValueError(
                    "measurement delivery does not match successful publishes"
                )
            if (
                args.expected_measurement_publish_failures == "zero"
                and publish_failures != 0
            ):
                raise ValueError("resource workload has publish failures")
            if (
                args.expected_measurement_publish_failures == "nonzero"
                and publish_failures == 0
            ):
                raise ValueError("resource workload did not exercise rejection")
            summary = (
                f"max_samples={args.resource_max_samples} attempts={attempts} "
                f"accepted={accepted} rejected={rejected} "
                f"ack_suppression_ms={args.resource_ack_suppression_ms} "
                f"probe_replies={probe_replies} delivery={delivered}/{attempted} "
                f"publish_failures={publish_failures}"
            )
        elif args.family == "history_depth":
            bench_finals = [
                line for line in lines if line.startswith("BENCH_FINAL ")
            ]
            if len(bench_finals) != 1:
                raise ValueError(
                    f"expected one BENCH_FINAL, found {len(bench_finals)}"
                )
            bench_final = parse_record(bench_finals[0], "BENCH_FINAL")
            expected_fields = {
                "history_depth": str(args.history_depth),
                "history_burst_size": str(args.history_burst_size),
            }
            require_fields("config", config, expected_fields)
            require_fields("policy", policy, expected_fields)
            attempts = integer(policy, "history_attempt_delta")
            accepted = integer(policy, "history_accept_delta")
            rejected = integer(policy, "history_reject_delta")
            allocation_failures = integer(
                policy, "history_allocation_failure_delta"
            )
            history_peak = integer(policy, "history_peak")
            history_after = integer(policy, "history_after_release")
            probe_replies = integer(policy, "history_probe_replies")
            reply_mask = integer(policy, "history_probe_reply_mask")
            retained = min(args.history_depth, args.history_burst_size)
            retained_start = args.history_burst_size - retained
            expected_mask = ((1 << retained) - 1) << retained_start
            if attempts != args.history_burst_size or accepted != attempts:
                raise ValueError("History/Depth burst acceptance is inconsistent")
            if rejected != 0 or allocation_failures != 0:
                raise ValueError("History/Depth burst has an unexpected failure")
            if history_peak != retained:
                raise ValueError("History/Depth peak does not match retained depth")
            if history_after != 0:
                raise ValueError("History/Depth history did not drain")
            if probe_replies != retained or reply_mask != expected_mask:
                raise ValueError("History/Depth retained sequence suffix is wrong")
            attempted = integer(bench_final, "attempted_tx")
            delivered = integer(bench_final, "rx")
            publish_failures = integer(bench_final, "publish_failures")
            if (
                args.expected_measurement_delivery == "full"
                and delivered != attempted
            ):
                raise ValueError("expected full measurement delivery")
            if (
                args.expected_measurement_publish_failures == "zero"
                and publish_failures != 0
            ):
                raise ValueError("History/Depth workload has publish failures")
            summary = (
                f"depth={args.history_depth} burst={args.history_burst_size} "
                f"retained={retained} replies={probe_replies} "
                f"reply_mask=0x{reply_mask:016x} "
                f"delivery={delivered}/{attempted}"
            )
        elif args.family == "durability":
            prejoin_ready = [
                line for line in lines
                if line.startswith("PERF_DURABILITY_PREJOIN_READY ")
            ]
            bidirectional_ready = [
                line for line in lines
                if line.startswith("PERF_DURABILITY_BIDIRECTIONAL_READY ")
            ]
            if len(prejoin_ready) != 1 or len(bidirectional_ready) != 1:
                raise ValueError(
                    "expected one Durability pre-join and bidirectional marker"
                )
            if lines.index(prejoin_ready[0]) >= lines.index(bidirectional_ready[0]):
                raise ValueError("Durability readiness markers are out of order")
            prejoin = parse_record(
                prejoin_ready[0], "PERF_DURABILITY_PREJOIN_READY"
            )
            bidirectional = parse_record(
                bidirectional_ready[0],
                "PERF_DURABILITY_BIDIRECTIONAL_READY",
            )
            require_fields(
                "prejoin marker",
                prejoin,
                {
                    "schema": "1",
                    "cell_id": args.cell_id,
                    "durability": args.durability,
                    "samples": str(args.durability_prejoin_samples),
                    "history": str(
                        min(
                            args.durability_prejoin_samples,
                            args.durability_cache_depth,
                        )
                    ),
                },
            )
            require_fields(
                "bidirectional marker",
                bidirectional,
                {"schema": "1", "cell_id": args.cell_id},
            )
            bench_finals = [
                line for line in lines if line.startswith("BENCH_FINAL ")
            ]
            if len(bench_finals) != 1:
                raise ValueError(
                    f"expected one BENCH_FINAL, found {len(bench_finals)}"
                )
            bench_final = parse_record(bench_finals[0], "BENCH_FINAL")
            expected_fields = {
                "durability": args.durability,
                "durability_cache_depth": str(args.durability_cache_depth),
                "durability_prejoin_samples": str(
                    args.durability_prejoin_samples
                ),
            }
            require_fields("config", config, expected_fields)
            require_fields("policy", policy, expected_fields)
            expected_code = "1" if args.durability == "transient_local" else "0"
            require_fields("policy", policy, {"durability_code": expected_code})
            attempts = integer(policy, "durability_attempt_delta")
            accepted = integer(policy, "durability_accept_delta")
            rejected = integer(policy, "durability_reject_delta")
            allocation_failures = integer(
                policy, "durability_allocation_failure_delta"
            )
            history_prejoin = integer(policy, "durability_history_prejoin")
            history_after_join = integer(
                policy, "durability_history_after_join"
            )
            replies = integer(policy, "durability_probe_replies")
            reply_mask = integer(policy, "durability_probe_reply_mask")
            reader_matched = integer(policy, "durability_reader_matched")
            if attempts != args.durability_prejoin_samples or accepted != attempts:
                raise ValueError("Durability pre-join acceptance is inconsistent")
            if rejected != 0 or allocation_failures != 0:
                raise ValueError("Durability pre-join cache has a failure")
            retained = min(
                args.durability_prejoin_samples,
                args.durability_cache_depth,
            )
            if history_prejoin != retained:
                raise ValueError("Durability pre-join history is incomplete")
            if reader_matched != 1:
                raise ValueError("Durability writer has no matched host reader")
            if args.durability == "volatile":
                if replies != 0 or reply_mask != 0 or history_after_join != 0:
                    raise ValueError("Volatile writer replayed pre-join history")
            else:
                retained_start = args.durability_prejoin_samples - retained
                expected_mask = ((1 << retained) - 1) << retained_start
                if (
                    replies != retained
                    or reply_mask != expected_mask
                    or history_after_join != retained
                ):
                    raise ValueError("Transient-Local replay is incomplete")
            attempted = integer(bench_final, "attempted_tx")
            delivered = integer(bench_final, "rx")
            publish_failures = integer(bench_final, "publish_failures")
            if (
                args.expected_measurement_delivery == "full"
                and delivered != attempted
            ):
                raise ValueError("expected full measurement delivery")
            if (
                args.expected_measurement_publish_failures == "zero"
                and publish_failures != 0
            ):
                raise ValueError("Durability workload has publish failures")
            summary = (
                f"durability={args.durability} "
                f"prejoin={args.durability_prejoin_samples} "
                f"replies={replies} reply_mask=0x{reply_mask:016x} "
                f"delivery={delivered}/{attempted}"
            )
        else:
            outage_markers = [
                line for line in lines
                if line.startswith("PERF_LIVELINESS_OUTAGE_READY ")
            ]
            if len(outage_markers) != 1:
                raise ValueError(
                    f"expected one Liveliness outage marker, found {len(outage_markers)}"
                )
            outage_marker = parse_record(
                outage_markers[0], "PERF_LIVELINESS_OUTAGE_READY"
            )
            expected_fields = {
                "liveliness_lease_ms": str(args.liveliness_lease_ms),
                "liveliness_outage_ms": str(args.liveliness_outage_ms),
            }
            require_fields("config", config, expected_fields)
            require_fields("policy", policy, expected_fields)
            require_fields(
                "outage marker",
                outage_marker,
                {
                    "schema": "1",
                    "cell_id": args.cell_id,
                    "lease_ms": str(args.liveliness_lease_ms),
                    "outage_ms": str(args.liveliness_outage_ms),
                },
            )
            bench_finals = [
                line for line in lines if line.startswith("BENCH_FINAL ")
            ]
            if len(bench_finals) != 1:
                raise ValueError(
                    f"expected one BENCH_FINAL, found {len(bench_finals)}"
                )
            bench_final = parse_record(bench_finals[0], "BENCH_FINAL")
            lost_before = integer(policy, "liveliness_lost_before")
            lost_after = integer(policy, "liveliness_lost_after")
            lost_delta = integer(policy, "liveliness_lost_delta")
            recovered_before = integer(policy, "liveliness_recovered_before")
            recovered_after = integer(policy, "liveliness_recovered_after")
            recovered_delta = integer(policy, "liveliness_recovered_delta")
            lost_callbacks = integer(policy, "liveliness_lost_callbacks")
            recovered_callbacks = integer(
                policy, "liveliness_recovered_callbacks"
            )
            lost_offset = integer(
                policy, "first_liveliness_lost_offset_us"
            )
            recovered_offset = integer(
                policy, "first_liveliness_recovered_offset_us"
            )
            writer_alive = integer(policy, "liveliness_writer_alive_final")
            if (
                lost_after < lost_before
                or lost_delta != lost_after - lost_before
                or recovered_after < recovered_before
                or recovered_delta != recovered_after - recovered_before
            ):
                raise ValueError("Liveliness counter delta is inconsistent")
            if lost_callbacks != lost_delta or recovered_callbacks != recovered_delta:
                raise ValueError("Liveliness callbacks do not match counter deltas")
            if args.expected_liveliness_transition == "none":
                if lost_delta != 0 or recovered_delta != 0:
                    raise ValueError("unexpected Liveliness transition")
                if lost_offset != -1 or recovered_offset != -1:
                    raise ValueError("zero Liveliness events require offset -1")
            else:
                if lost_delta != 1 or recovered_delta != 1:
                    raise ValueError("expected one lost/recovered transition")
                if not 0 < lost_offset < recovered_offset:
                    raise ValueError("Liveliness event offsets are out of order")
                max_lost_offset = (args.liveliness_lease_ms + 500) * 1000
                max_recovered_offset = (args.liveliness_outage_ms + 2000) * 1000
                if lost_offset > max_lost_offset:
                    raise ValueError("Liveliness lost event is too late")
                if recovered_offset > max_recovered_offset:
                    raise ValueError("Liveliness recovery event is too late")
            if writer_alive != 1:
                raise ValueError("Liveliness writer is not alive after recovery")
            attempted = integer(bench_final, "attempted_tx")
            delivered = integer(bench_final, "rx")
            publish_failures = integer(bench_final, "publish_failures")
            if (
                args.expected_measurement_delivery == "full"
                and delivered != attempted
            ):
                raise ValueError("expected full measurement delivery")
            if (
                args.expected_measurement_publish_failures == "zero"
                and publish_failures != 0
            ):
                raise ValueError("Liveliness workload has publish failures")
            summary = (
                f"lease_ms={args.liveliness_lease_ms} "
                f"outage_ms={args.liveliness_outage_ms} "
                f"lost={lost_delta} recovered={recovered_delta} "
                f"lost_offset_us={lost_offset} "
                f"recovered_offset_us={recovered_offset} "
                f"delivery={delivered}/{attempted}"
            )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        "PASS: "
        f"family={args.family} cell_id={args.cell_id} "
        f"period_ms={args.publish_period_ms} {summary}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
