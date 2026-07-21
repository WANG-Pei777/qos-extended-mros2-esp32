#!/usr/bin/env python3
"""Validate machine-readable output from one mechanism board boot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CRASH_MARKERS = (
    "Guru Meditation",
    "abort()",
    "LoadProhibited",
    "StoreProhibited",
    "stack overflow",
)


def parse_marker(line: str, prefix: str) -> dict[str, str] | None:
    if not line.startswith(prefix + " "):
        return None
    fields: dict[str, str] = {}
    for token in line[len(prefix) + 1 :].split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    return fields


def integer(fields: dict[str, str], name: str, errors: list[str]) -> int:
    try:
        return int(fields[name])
    except (KeyError, ValueError):
        errors.append(f"missing or invalid integer field: {name}")
        return -1


def validate_log(
    text: str, case_id: str, kind: str, sample_limit: int
) -> dict[str, object]:
    errors: list[str] = []
    lines = text.splitlines()
    configs = [
        marker
        for line in lines
        if (marker := parse_marker(line, "MECH_BOARD_CONFIG")) is not None
    ]
    finals = [
        marker
        for line in lines
        if (marker := parse_marker(line, "MECH_BOARD_FINAL")) is not None
    ]
    if len(configs) != 1:
        errors.append(f"expected one config marker, found {len(configs)}")
    if len(finals) != 1:
        errors.append(f"expected one final marker, found {len(finals)}")
    else:
        final_index = next(
            index for index, line in enumerate(lines)
            if line.startswith("MECH_BOARD_FINAL ")
        )
        post_final = [
            line for line in lines[final_index + 1 :]
            if line.startswith("MECH_BOARD_")
        ]
        if post_final:
            errors.append(
                f"found {len(post_final)} machine marker(s) after board final"
            )
    for marker in CRASH_MARKERS:
        if marker.lower() in text.lower():
            errors.append(f"crash marker present: {marker}")

    config = configs[0] if len(configs) == 1 else {}
    final = finals[0] if len(finals) == 1 else {}
    for name, expected in (("case_id", case_id), ("kind", kind)):
        if config.get(name) != expected:
            errors.append(f"config {name}={config.get(name)!r}, expected {expected!r}")
        if final.get(name) != expected:
            errors.append(f"final {name}={final.get(name)!r}, expected {expected!r}")
    if config.get("schema") != "1" or final.get("schema") != "1":
        errors.append("unsupported board marker schema")
    if final.get("status") != "PASS":
        errors.append(f"board final status is {final.get('status')!r}")

    attempts = integer(final, "attempts", errors)
    accepted = integer(final, "accepted", errors)
    rejected = integer(final, "rejected", errors)
    allocation_failures = integer(final, "allocation_failures", errors)
    history_count = integer(final, "history_count", errors)
    history_bytes = integer(final, "history_bytes", errors)
    sample_bytes = integer(final, "sample_bytes", errors)
    heap_before = integer(final, "heap_before", errors)
    heap_after = integer(final, "heap_after", errors)
    minimum_heap = integer(final, "minimum_free_heap", errors)
    stack_watermark = integer(final, "stack_high_watermark", errors)
    integrity = integer(final, "heap_integrity", errors)
    pressure_pbufs = integer(final, "pressure_pbufs", errors)
    matched = integer(final, "matched", errors)
    recovery = integer(final, "recovery_observed", errors)
    app_rx = integer(final, "app_rx", errors)
    reader_received = integer(final, "reader_received", errors)
    out_of_order = integer(final, "out_of_order_drops", errors)
    first_rx_hash = integer(final, "first_rx_hash", errors)
    second_rx_hash = integer(final, "second_rx_hash", errors)
    deadline_missed = integer(final, "deadline_missed", errors)
    deadline_callbacks = integer(final, "deadline_callbacks", errors)
    deadline_latency_us = integer(final, "deadline_latency_us", errors)
    deadline_latency_ms = integer(final, "deadline_latency_ms", errors)
    liveliness_lost = integer(final, "liveliness_lost", errors)
    liveliness_recovered = integer(final, "liveliness_recovered", errors)
    liveliness_lost_callbacks = integer(final, "liveliness_lost_callbacks", errors)
    liveliness_recovered_callbacks = integer(
        final, "liveliness_recovered_callbacks", errors
    )
    lifespan_drops = integer(final, "lifespan_drops", errors)
    hold_start_us = integer(final, "hold_start_us", errors)
    hold_end_us = integer(final, "hold_end_us", errors)
    heap_after_pressure = integer(final, "heap_after_pressure", errors)
    boot_epoch = integer(final, "boot_epoch", errors)

    capacity = integer(config, "history_capacity", errors)
    monitor_period = integer(config, "monitor_period_ms", errors)
    tick_hz = integer(config, "tick_hz", errors)
    if monitor_period != 5 or tick_hz != 1000:
        errors.append(
            f"timing background is monitor={monitor_period}ms tick_hz={tick_hz}"
        )
    expected_capacity = 100 if kind.startswith("resource_") else 40
    if capacity != expected_capacity:
        errors.append(f"history_capacity={capacity}, expected={expected_capacity}")

    if attempts != accepted + rejected + allocation_failures:
        errors.append("attempt accounting does not reconcile")
    if sample_bytes <= 0 or history_bytes != history_count * sample_bytes:
        errors.append("history byte accounting does not reconcile")
    if min(heap_before, heap_after, minimum_heap, stack_watermark) <= 0:
        errors.append("heap/stack observability contains a nonpositive value")
    if integrity != 1:
        errors.append("heap integrity check failed")

    if kind == "resource_sample_bound":
        expected = (sample_limit, sample_limit, 0, 0, sample_limit)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected:
            errors.append(f"sample-bound counters={observed}, expected={expected}")
    elif kind == "resource_sample_reject":
        expected = (sample_limit + 1, sample_limit, 1, 0, sample_limit)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected:
            errors.append(f"sample-reject counters={observed}, expected={expected}")
    elif kind == "resource_byte_bound":
        expected = (3, 2, 1, 0, 2)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected or history_bytes != sample_bytes * 2:
            errors.append(f"byte-bound counters={observed}, expected={expected}")
    elif kind == "resource_alloc_fail":
        expected = (1, 0, 0, 1, 0)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected or pressure_pbufs <= 0:
            errors.append(
                f"allocation-failure counters={observed}, expected={expected}, "
                f"pressure_pbufs={pressure_pbufs}"
            )
    elif kind == "resource_recovery":
        expected = (sample_limit + 2, sample_limit + 1, 1, 0)
        observed = (attempts, accepted, rejected, allocation_failures)
        if observed != expected or matched != 1 or recovery != 1:
            errors.append(f"resource-recovery counters={observed}, expected={expected}")
    elif kind == "resource_no_corruption":
        expected = (sample_limit + 20, sample_limit, 20, 0, sample_limit)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected:
            errors.append(f"pressure counters={observed}, expected={expected}")
    elif kind == "history_keep_last_order":
        expected = (5, 5, 0, 0, 3)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected or matched != 1:
            errors.append(f"KEEP_LAST counters={observed}, expected={expected}")
    elif kind == "history_keep_all_bound":
        expected = (capacity + 1, capacity, 1, 0, capacity)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if observed != expected:
            errors.append(f"KEEP_ALL counters={observed}, expected={expected}")
    elif kind == "history_duplicate_once":
        if matched != 1 or app_rx != 1 or reader_received < 2 or out_of_order < 1:
            errors.append("duplicate was not suppressed exactly at application delivery")
    elif kind == "history_gap_safe":
        if matched != 1 or app_rx < 2 or out_of_order < 1:
            errors.append("gap/repair path did not deliver safely and reject stale repair")
    elif kind == "history_epoch_reset":
        if (
            matched != 1
            or recovery != 1
            or app_rx != 2
            or min(first_rx_hash, second_rx_hash) <= 0
            or first_rx_hash == second_rx_hash
        ):
            errors.append("writer epoch transition is not content-distinguishable")
    elif kind == "history_pbuf_release":
        expected = (5, 5, 0, 0, 0)
        observed = (attempts, accepted, rejected, allocation_failures, history_count)
        if (
            observed != expected
            or matched != 1
            or recovery != 1
            or heap_after_pressure <= 0
            or heap_after <= heap_after_pressure
        ):
            errors.append(f"pbuf-release counters={observed}, expected={expected}")
    elif kind == "durability_volatile_late":
        if (attempts, accepted, rejected, allocation_failures) != (4, 4, 0, 0) or matched != 1:
            errors.append("volatile late-reader board transition is inconsistent")
    elif kind in {"durability_tl_order", "durability_tl_epoch"}:
        if (attempts, accepted, rejected, allocation_failures, history_count) != (5, 5, 0, 0, 3) or matched != 1:
            errors.append("transient-local replay history is not the newest depth-3 window")
        if kind == "durability_tl_epoch":
            if config.get("boot_epoch_store") != "nvs":
                errors.append("transient-local epoch label is not NVS-backed")
            if boot_epoch < 2:
                errors.append("transient-local epoch case did not execute after a persistent reset")
    elif kind == "durability_tl_depth":
        if (attempts, accepted, rejected, allocation_failures, history_count) != (5, 5, 0, 0, 2) or matched != 1:
            errors.append("transient-local depth-2 history is inconsistent")
    elif kind == "durability_frag_capability":
        if (attempts, accepted, rejected, allocation_failures, history_count) != (1, 1, 0, 0, 1) or matched != 1 or sample_bytes <= 100:
            errors.append("fragmented transient-local replay was not exercised")
    elif kind == "deadline_disabled":
        if matched != 1 or app_rx != 1 or deadline_missed != 0 or deadline_callbacks != 0:
            errors.append("disabled deadline emitted an event or lacked a matched baseline")
    elif kind in {"deadline_boundary", "deadline_polling"}:
        upper = 65000 if kind == "deadline_polling" else 70000
        if (
            matched != 1
            or app_rx != 1
            or deadline_missed != 1
            or deadline_callbacks != 1
            or not 50 <= deadline_latency_ms <= upper // 1000
        ):
            errors.append(
                f"deadline boundary latency={deadline_latency_ms}ms "
                f"diagnostic_us={deadline_latency_us}"
            )
    elif kind == "deadline_repeated":
        if matched != 1 or app_rx != 1 or deadline_missed != 3 or deadline_callbacks != 3:
            errors.append("repeated deadline periods did not reconcile exactly")
    elif kind == "deadline_recovery":
        if (
            matched != 1
            or recovery != 1
            or app_rx != 2
            or deadline_missed != 2
            or deadline_callbacks != 2
            or not 50 <= deadline_latency_ms <= 70
        ):
            errors.append("deadline recovery did not reset the baseline exactly once")
    elif kind.startswith("lifespan_"):
        measured_hold = hold_end_us - hold_start_us
        expected_hold = 150000 if kind in {"lifespan_expired", "lifespan_reconnect"} else 100000
        if (
            matched != 1
            or attempts != 1
            or accepted != 1
            or rejected != 0
            or allocation_failures != 0
            or not expected_hold <= measured_hold <= expected_hold + 20000
        ):
            errors.append(f"lifespan hold measured {measured_hold}us")
        expected_drops = 1 if kind in {"lifespan_expired", "lifespan_reconnect"} else 0
        if lifespan_drops != expected_drops:
            errors.append(f"lifespan_drops={lifespan_drops}, expected={expected_drops}")
        if expected_drops == 1 and history_count != 0:
            errors.append("expired lifespan sample remains in history")
    elif kind == "liveliness_startup":
        if matched != 0 or app_rx != 0 or liveliness_lost != 0 or liveliness_recovered != 0:
            errors.append("startup emitted a false liveliness transition")
    elif kind in {"liveliness_loss_once", "liveliness_no_duplicate"}:
        if (
            matched != 1
            or app_rx != 1
            or liveliness_lost != 1
            or liveliness_recovered != 0
            or liveliness_lost_callbacks != 1
            or liveliness_recovered_callbacks != 0
        ):
            errors.append("liveliness loss transition did not occur exactly once")
    elif kind == "liveliness_recovery_once":
        if (
            matched != 1
            or recovery != 1
            or app_rx < 1
            or liveliness_lost != 1
            or liveliness_recovered != 1
            or liveliness_lost_callbacks != 1
            or liveliness_recovered_callbacks != 1
        ):
            errors.append("liveliness loss/recovery transitions did not reconcile")
    elif kind == "liveliness_infinite":
        if matched != 1 or app_rx != 1 or liveliness_lost != 0 or liveliness_recovered != 0:
            errors.append("infinite liveliness lease emitted a transition")
    else:
        errors.append(f"unsupported validator kind: {kind}")

    return {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_board_log_validation",
        "case_id": case_id,
        "kind": kind,
        "sample_limit": sample_limit,
        "config": config,
        "final": final,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial-log", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate_log(
        args.serial_log.read_text(encoding="utf-8", errors="replace"),
        args.case_id,
        args.kind,
        args.sample_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"BOARD_LOG case_id={args.case_id} kind={args.kind} "
        f"status={report['status']}"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
