#!/usr/bin/env python3
"""Shared parser and arithmetic checks for telemetry control-probe records."""

from __future__ import annotations

from typing import Iterable


PREFIX = "COMPARE_CPU_CONTROL "
MIN_WINDOW_US = 19_500_000
MAX_WINDOW_US = 20_500_000


def parse_fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            raise ValueError(f"malformed control-probe token: {token!r}")
        key, value = token.split("=", 1)
        if key in fields:
            raise ValueError(f"duplicate control-probe field: {key!r}")
        fields[key] = value
    return fields


def integer(fields: dict[str, str], key: str) -> int:
    if key not in fields:
        raise ValueError(f"missing control-probe field: {key!r}")
    return int(fields[key], 0)


def validate_control_probe(
    lines: Iterable[str],
    *,
    system: str,
    telemetry: str,
    required: bool,
) -> dict[str, int | str] | None:
    records = [line for line in lines if line.startswith(PREFIX)]
    if not records:
        if required:
            raise ValueError("missing COMPARE_CPU_CONTROL record")
        return None
    if len(records) != 1:
        raise ValueError(f"expected one control-probe record, found {len(records)}")

    fields = parse_fields(records[0])
    expected_text = {
        "schema": "1",
        "system": system,
        "telemetry": telemetry,
    }
    for key, expected in expected_text.items():
        if fields.get(key) != expected:
            raise ValueError(
                f"control-probe {key}={fields.get(key)!r}, expected {expected!r}"
            )

    start_begin_us = integer(fields, "start_begin_us")
    end_end_us = integer(fields, "end_end_us")
    wall0_us = integer(fields, "wall0_us")
    wall1_us = integer(fields, "wall1_us")
    idle0_delta_us = integer(fields, "idle0_delta_us")
    idle1_delta_us = integer(fields, "idle1_delta_us")
    busy0_ppm = integer(fields, "busy0_ppm")
    busy1_ppm = integer(fields, "busy1_ppm")
    busy_mean_ppm = integer(fields, "busy_mean_ppm")
    fault_flags = integer(fields, "fault_flags")

    if fault_flags != 0:
        raise ValueError(f"control-probe fault_flags=0x{fault_flags:08x}")
    if end_end_us <= start_begin_us:
        raise ValueError("control-probe capture times regress")
    for core, wall_us, idle_delta_us in (
        (0, wall0_us, idle0_delta_us),
        (1, wall1_us, idle1_delta_us),
    ):
        if not MIN_WINDOW_US <= wall_us <= MAX_WINDOW_US:
            raise ValueError(f"core {core} control window is {wall_us} us")
        if not 0 <= idle_delta_us <= wall_us:
            raise ValueError(
                f"core {core} idle delta {idle_delta_us} exceeds wall {wall_us}"
            )

    expected_busy0 = ((wall0_us - idle0_delta_us) * 1_000_000) // wall0_us
    expected_busy1 = ((wall1_us - idle1_delta_us) * 1_000_000) // wall1_us
    expected_mean = (expected_busy0 + expected_busy1) // 2
    if busy0_ppm != expected_busy0 or busy1_ppm != expected_busy1:
        raise ValueError("control-probe busy ppm does not match raw counters")
    if busy_mean_ppm != expected_mean:
        raise ValueError("control-probe mean ppm does not match per-core values")

    return {
        "system": system,
        "telemetry": telemetry,
        "wall0_us": wall0_us,
        "wall1_us": wall1_us,
        "idle0_delta_us": idle0_delta_us,
        "idle1_delta_us": idle1_delta_us,
        "busy0_ppm": busy0_ppm,
        "busy1_ppm": busy1_ppm,
        "busy_mean_ppm": busy_mean_ppm,
    }
