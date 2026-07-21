#!/usr/bin/env python3
"""Validate a raw UART log from benchmark_telemetry_smoke."""

from __future__ import annotations

import argparse
import math
import re
import statistics
import sys
import zlib
from pathlib import Path

from telemetry_control_probe import validate_control_probe


RECORD_RE = re.compile(r"^(BENCH_[A-Z_]+)(?:\s|$)")
TELEMETRY_WINDOW_MS = 20_000
TELEMETRY_PERIOD_MS = 100
TELEMETRY_INTERVAL_COUNT = 200


def parse_record(line: str) -> tuple[str, dict[str, str]]:
    match = RECORD_RE.match(line)
    if not match:
        raise ValueError(f"not a benchmark record: {line!r}")
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            raise ValueError(f"malformed token {token!r} in {line!r}")
        key, value = token.split("=", 1)
        if key in fields:
            raise ValueError(f"duplicate field {key!r}")
        fields[key] = value
    return match.group(1), fields


def integer(fields: dict[str, str], key: str) -> int:
    if key not in fields:
        raise ValueError(f"missing field {key!r}")
    return int(fields[key], 0)


def parse_key_value_record(line: str, prefix: str) -> dict[str, str]:
    if not line.startswith(prefix + " "):
        raise ValueError(f"expected {prefix} record")
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" not in token:
            raise ValueError(f"malformed token {token!r} in {prefix}")
        key, value = token.split("=", 1)
        if key in fields:
            raise ValueError(f"duplicate field {key!r} in {prefix}")
        fields[key] = value
    return fields


def validate_delivery_contract(
    raw_lines: list[bytes],
    bench_config: dict[str, str],
    bench_final: dict[str, str],
    *,
    expected_qos: str = "BEST_EFFORT",
    expected_payload_bytes: int = 64,
    expected_rate_hz: int = 10,
    expected_target_tx: int = 200,
    expected_impairment: str = "clean",
    require_full_delivery: bool = True,
) -> dict[str, str]:
    if expected_rate_hz <= 0 or 1000 % expected_rate_hz:
        raise ValueError("expected rate must be a positive divisor of 1000 Hz")
    expected_period_ms = 1000 // expected_rate_hz
    compare_configs = [
        raw.decode("ascii")
        for raw in raw_lines
        if raw.startswith(b"COMPARE_CONFIG ")
    ]
    compare_finals = [
        raw.decode("ascii")
        for raw in raw_lines
        if raw.startswith(b"COMPARE_FINAL ")
    ]
    if len(compare_configs) != 1 or len(compare_finals) != 1:
        raise ValueError(
            "expected exactly one COMPARE_CONFIG and one COMPARE_FINAL"
        )

    compare_config = parse_key_value_record(compare_configs[0], "COMPARE_CONFIG")
    compare_final = parse_key_value_record(compare_finals[0], "COMPARE_FINAL")
    system = bench_config.get("system", "")
    expected_config = {
        "system": system,
        "qos": expected_qos,
        "payload_bytes": str(expected_payload_bytes),
        "messages": str(expected_target_tx),
        "period_ms": str(expected_period_ms),
        "telemetry": "on",
    }
    expected_compare_final = {
        "system": system,
        "tx": str(expected_target_tx),
        "rx": str(expected_target_tx),
        "samples": str(expected_target_tx),
        "payload_bytes": str(expected_payload_bytes),
        "period_ms": str(expected_period_ms),
        "telemetry": "on",
    }
    expected_bench_config = {
        "qos": expected_qos,
        "payload_bytes": str(expected_payload_bytes),
        "rate_hz": str(expected_rate_hz),
        "target_tx": str(expected_target_tx),
        "impairment": expected_impairment,
        "window_ms": str(TELEMETRY_WINDOW_MS),
        "period_ms": str(TELEMETRY_PERIOD_MS),
        "interval_count": str(TELEMETRY_INTERVAL_COUNT),
    }
    expected_bench_final = {
        "attempted_tx": str(expected_target_tx),
        "publish_failures": "0",
        "rx": str(expected_target_tx),
        "duplicates": "0",
        "malformed": "0",
        "rtt_samples": str(expected_target_tx),
    }
    if not require_full_delivery:
        expected_compare_final.pop("rx")
        expected_compare_final.pop("samples")
        expected_bench_final.pop("rx")
        expected_bench_final.pop("rtt_samples")
    for record_name, actual, expected in (
        ("COMPARE_CONFIG", compare_config, expected_config),
        ("COMPARE_FINAL", compare_final, expected_compare_final),
        ("BENCH_CONFIG", bench_config, expected_bench_config),
        ("BENCH_FINAL", bench_final, expected_bench_final),
    ):
        for key, expected_value in expected.items():
            if actual.get(key) != expected_value:
                raise ValueError(
                    f"{record_name} {key}={actual.get(key)!r}, "
                    f"expected {expected_value!r}"
                )
    if not require_full_delivery:
        delivered = integer(compare_final, "rx")
        if delivered < 0 or delivered > expected_target_tx:
            raise ValueError(
                f"COMPARE_FINAL rx={delivered}, expected 0..{expected_target_tx}"
            )
        for record_name, actual, key in (
            ("COMPARE_FINAL", compare_final, "samples"),
            ("BENCH_FINAL", bench_final, "rx"),
            ("BENCH_FINAL", bench_final, "rtt_samples"),
        ):
            if integer(actual, key) != delivered:
                raise ValueError(
                    f"{record_name} {key}={actual.get(key)!r}, "
                    f"expected delivered count {delivered}"
                )

    observability_keys = (
        "missing",
        "missing_runs",
        "max_missing_run",
        "arrival_inversions",
        "rtt_sum_us",
        "rtt_sum_sq_us2",
    )
    compare_observability = {
        key for key in observability_keys if key in compare_final
    }
    bench_observability = {key for key in observability_keys if key in bench_final}
    if compare_observability or bench_observability:
        required = set(observability_keys)
        if compare_observability != required or bench_observability != required:
            raise ValueError("delivery observability fields are incomplete")
        for key in observability_keys:
            if compare_final[key] != bench_final[key]:
                raise ValueError(f"delivery observability {key} does not reconcile")

        delivered = integer(compare_final, "rx")
        missing = integer(compare_final, "missing")
        missing_runs = integer(compare_final, "missing_runs")
        max_missing_run = integer(compare_final, "max_missing_run")
        inversions = integer(compare_final, "arrival_inversions")
        sum_us = integer(compare_final, "rtt_sum_us")
        sum_sq_us2 = integer(compare_final, "rtt_sum_sq_us2")
        if missing != expected_target_tx - delivered:
            raise ValueError("delivery observability missing count is inconsistent")
        if inversions < 0 or inversions > delivered:
            raise ValueError("delivery observability arrival inversions are invalid")
        if missing == 0:
            if missing_runs != 0 or max_missing_run != 0:
                raise ValueError("zero missing count has nonzero missing-run metrics")
        elif not (
            1 <= missing_runs <= missing
            and (missing + missing_runs - 1) // missing_runs
            <= max_missing_run
            <= missing
        ):
            raise ValueError("delivery observability missing-run metrics are invalid")
        if delivered == 0:
            if sum_us != 0 or sum_sq_us2 != 0:
                raise ValueError("zero delivery has nonzero RTT moments")
        else:
            if sum_us // delivered != integer(compare_final, "avg_us"):
                raise ValueError("delivery observability RTT sum disagrees with mean")
            if sum_sq_us2 * delivered < sum_us * sum_us:
                raise ValueError("delivery observability RTT moments are impossible")
    return compare_final


def validate(
    path: Path,
    require_control_probe: bool = False,
    *,
    expected_qos: str = "BEST_EFFORT",
    expected_payload_bytes: int = 64,
    expected_rate_hz: int = 10,
    expected_target_tx: int = 200,
    expected_impairment: str = "clean",
    require_full_delivery: bool = True,
) -> list[str]:
    raw_lines = path.read_bytes().splitlines()
    if any(raw.startswith(b"BENCH_SMOKE_ERROR") for raw in raw_lines):
        raise ValueError("firmware emitted BENCH_SMOKE_ERROR")

    config_raw_indices = [
        index for index, raw in enumerate(raw_lines) if raw.startswith(b"BENCH_CONFIG ")
    ]
    start_raw_indices = [
        index
        for index, raw in enumerate(raw_lines)
        if raw.startswith(b"BENCH_WINDOW_START ")
    ]
    if len(config_raw_indices) != 1 or len(start_raw_indices) != 1:
        raise ValueError("raw stream must contain one config and one window start")
    between = [
        raw
        for raw in raw_lines[config_raw_indices[0] + 1 : start_raw_indices[0]]
        if raw.strip()
    ]
    if between:
        raise ValueError(
            f"UART activity occurred during the measurement window: {between[0]!r}"
        )

    lines = [
        raw.decode("ascii")
        for raw in raw_lines
        if raw.startswith(b"BENCH_") and not raw.startswith(b"BENCH_SMOKE_ERROR")
    ]
    if not lines:
        raise ValueError("no BENCH_ records found")

    parsed = [parse_record(line) for line in lines]
    families = [family for family, _ in parsed]
    if families.count("BENCH_CONFIG") != 1:
        raise ValueError("expected exactly one BENCH_CONFIG")
    if families.count("BENCH_WINDOW_START") != 1:
        raise ValueError("expected exactly one BENCH_WINDOW_START")
    if families.count("BENCH_WINDOW_END") != 1:
        raise ValueError("expected exactly one BENCH_WINDOW_END")
    if families.count("BENCH_FINAL") != 1:
        raise ValueError("expected exactly one BENCH_FINAL")
    if families.count("BENCH_DUMP_END") != 1:
        raise ValueError("expected exactly one BENCH_DUMP_END")

    dump_index = families.index("BENCH_DUMP_END")
    if dump_index != len(lines) - 1:
        raise ValueError("BENCH_DUMP_END must be the last record")

    run_tokens = {fields.get("run_token") for _, fields in parsed}
    if len(run_tokens) != 1 or None in run_tokens:
        raise ValueError(f"inconsistent run tokens: {run_tokens}")
    schemas = {integer(fields, "schema") for _, fields in parsed}
    if schemas != {1}:
        raise ValueError(f"unexpected schemas: {schemas}")

    sequences = [integer(fields, "record_seq") for _, fields in parsed]
    if sequences != list(range(len(sequences))):
        raise ValueError("record_seq values are not gapless from zero")

    samples = [fields for family, fields in parsed if family == "BENCH_SAMPLE"]
    if len(samples) != 200:
        raise ValueError(f"expected 200 samples, found {len(samples)}")
    indices = [integer(fields, "index") for fields in samples]
    if indices != list(range(200)):
        raise ValueError("sample indices are not exactly 0..199")

    sample_times = [integer(fields, "board_time_us") for fields in samples]
    if any(after <= before for before, after in zip(sample_times, sample_times[1:])):
        raise ValueError("sample board timestamps are not strictly increasing")
    if any(integer(fields, "fault_flags") != 0 for fields in samples):
        raise ValueError("one or more samples report a telemetry fault")

    start = parsed[families.index("BENCH_WINDOW_START")][1]
    end = parsed[families.index("BENCH_WINDOW_END")][1]
    if integer(start, "marker_state") != 1 or integer(end, "marker_state") != 0:
        raise ValueError("marker states do not describe a high measurement window")
    if integer(start, "marker_post_us") < integer(start, "marker_pre_us"):
        raise ValueError("start marker timestamps regress")
    if integer(end, "marker_post_us") < integer(end, "marker_pre_us"):
        raise ValueError("end marker timestamps regress")

    config = parsed[families.index("BENCH_CONFIG")][1]
    final = parsed[families.index("BENCH_FINAL")][1]
    if final.get("completion") != "complete":
        raise ValueError("smoke did not complete")
    if integer(final, "samples") != 200:
        raise ValueError("BENCH_FINAL sample count mismatch")
    if integer(final, "tasks") == 0:
        raise ValueError("no task records were captured")
    if integer(final, "missed_intervals") != 0:
        raise ValueError("telemetry window missed one or more intervals")
    if integer(final, "fault_flags") != 0:
        raise ValueError("BENCH_FINAL reports a telemetry fault")
    compare_final = validate_delivery_contract(
        raw_lines,
        config,
        final,
        expected_qos=expected_qos,
        expected_payload_bytes=expected_payload_bytes,
        expected_rate_hz=expected_rate_hz,
        expected_target_tx=expected_target_tx,
        expected_impairment=expected_impairment,
        require_full_delivery=require_full_delivery,
    )

    dump = parsed[-1][1]
    canonical = b"".join((line + "\n").encode("ascii") for line in lines[:-1])
    expected_crc = zlib.crc32(canonical) & 0xFFFFFFFF
    if integer(dump, "record_count") != len(lines) - 1:
        raise ValueError("BENCH_DUMP_END record_count mismatch")
    if integer(dump, "crc32") != expected_crc:
        raise ValueError(
            f"CRC mismatch: record={integer(dump, 'crc32'):08x} "
            f"computed={expected_crc:08x}"
        )

    task_count = families.count("BENCH_TASK")
    if task_count != integer(final, "tasks"):
        raise ValueError("BENCH_TASK count does not match BENCH_FINAL")

    duration_us = integer(end, "marker_pre_us") - integer(start, "marker_post_us")
    busy_total_ppm = [
        (integer(fields, "busy0_ppm") + integer(fields, "busy1_ppm")) / 2
        for fields in samples
    ]
    p95_busy_ppm = sorted(busy_total_ppm)[math.ceil(0.95 * len(samples)) - 1]
    lateness_us = [integer(fields, "lateness_us") for fields in samples]
    minimum_heap = min(integer(fields, "free_internal") for fields in samples)
    tasks = [fields for family, fields in parsed if family == "BENCH_TASK"]
    minimum_stack = min(integer(fields, "stack_hwm_bytes") for fields in tasks)
    control = validate_control_probe(
        [raw.decode("ascii", errors="replace").strip() for raw in raw_lines],
        system=config.get("system", ""),
        telemetry="on",
        required=require_control_probe,
    )
    summary = [
        f"records={len(lines)}",
        "samples=200",
        f"tx={compare_final['tx']}",
        f"rx={compare_final['rx']}",
        f"tasks={task_count}",
        f"window_us={duration_us}",
        f"cpu_mean_ppm={statistics.fmean(busy_total_ppm):.0f}",
        f"cpu_p95_ppm={p95_busy_ppm:.0f}",
        f"max_lateness_us={max(lateness_us)}",
        f"min_internal_heap={minimum_heap}",
        f"min_stack_hwm={minimum_stack}",
        "in_window_uart_lines=0",
        f"crc32=0x{expected_crc:08x}",
    ]
    if control is not None:
        summary.append(f"control_cpu_mean_ppm={control['busy_mean_ppm']}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("uart_log", type=Path)
    parser.add_argument("--require-control-probe", action="store_true")
    parser.add_argument("--expected-qos", default="BEST_EFFORT")
    parser.add_argument("--expected-payload-bytes", type=int, default=64)
    parser.add_argument("--expected-rate-hz", type=int, default=10)
    parser.add_argument("--expected-target-tx", type=int, default=200)
    parser.add_argument("--expected-impairment", default="clean")
    parser.add_argument("--allow-delivery-loss", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate(
            args.uart_log,
            args.require_control_probe,
            expected_qos=args.expected_qos,
            expected_payload_bytes=args.expected_payload_bytes,
            expected_rate_hz=args.expected_rate_hz,
            expected_target_tx=args.expected_target_tx,
            expected_impairment=args.expected_impairment,
            require_full_delivery=not args.allow_delivery_loss,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: " + " ".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
