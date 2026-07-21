#!/usr/bin/env python3
"""Build an auditable summary from strict telemetry smoke artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
FIELDS = (
    "system",
    "validation",
    "attempted_tx",
    "rx",
    "rtt_samples",
    "rtt_min_us",
    "rtt_avg_us",
    "rtt_max_us",
    "ready_ms",
    "cpu_mean_ppm",
    "cpu_p95_ppm",
    "min_internal_heap",
    "min_stack_hwm",
    "window_us",
    "max_lateness_us",
    "in_window_uart_lines",
    "firmware_bin_bytes",
    "total_size_bytes",
    "used_flash_non_ram_bytes",
    "diram_data_bytes",
    "diram_bss_bytes",
    "used_diram_bytes",
    "used_dram_bytes",
    "used_iram_bytes",
    "crc32",
)


def named_path(value: str) -> tuple[str, Path]:
    try:
        name, raw_path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected SYSTEM=PATH") from exc
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("expected SYSTEM=PATH")
    return name, Path(raw_path)


def parse_record(text: str, family: str) -> dict[str, str]:
    matches = []
    for raw_line in text.splitlines():
        line = ANSI_RE.sub("", raw_line).strip()
        if line.startswith(family + " "):
            matches.append(line)
    if len(matches) != 1:
        raise ValueError(f"expected one {family} record, found {len(matches)}")
    return dict(token.split("=", 1) for token in matches[0].split()[1:])


def parse_validation(line: str) -> dict[str, str]:
    if not line.startswith("PASS: "):
        raise ValueError(f"unexpected validator output: {line!r}")
    return dict(token.split("=", 1) for token in line[6:].split())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, type=named_path)
    parser.add_argument("--size", action="append", required=True, type=named_path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    runs = dict(args.run)
    sizes = dict(args.size)
    if runs.keys() != sizes.keys():
        parser.error("--run and --size systems must match")

    validator = Path(__file__).with_name("validate_benchmark_telemetry_smoke.py")
    rows = []
    for system, serial_path in runs.items():
        validation = subprocess.run(
            [sys.executable, str(validator), str(serial_path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        validation_fields = parse_validation(validation)
        serial_text = serial_path.read_bytes().decode("utf-8", errors="replace")
        final = parse_record(serial_text, "BENCH_FINAL")
        compare = parse_record(serial_text, "COMPARE_FINAL")
        dump = parse_record(serial_text, "BENCH_DUMP_END")
        size_path = sizes[system]
        size = json.loads(size_path.read_text(encoding="utf-8"))
        firmware_path = size_path.with_name("firmware.bin")

        row = {
            "system": system,
            "validation": "PASS",
            "attempted_tx": final["attempted_tx"],
            "rx": final["rx"],
            "rtt_samples": final["rtt_samples"],
            "rtt_min_us": compare["min_us"],
            "rtt_avg_us": compare["avg_us"],
            "rtt_max_us": compare["max_us"],
            "ready_ms": compare["ready_ms"],
            "cpu_mean_ppm": validation_fields["cpu_mean_ppm"],
            "cpu_p95_ppm": validation_fields["cpu_p95_ppm"],
            "min_internal_heap": validation_fields["min_internal_heap"],
            "min_stack_hwm": validation_fields["min_stack_hwm"],
            "window_us": validation_fields["window_us"],
            "max_lateness_us": validation_fields["max_lateness_us"],
            "in_window_uart_lines": validation_fields["in_window_uart_lines"],
            "firmware_bin_bytes": firmware_path.stat().st_size,
            "total_size_bytes": size["total_size"],
            "used_flash_non_ram_bytes": size["used_flash_non_ram"],
            "diram_data_bytes": size["diram_data"],
            "diram_bss_bytes": size["diram_bss"],
            "used_diram_bytes": size["used_diram"],
            "used_dram_bytes": size["used_dram"],
            "used_iram_bytes": size["used_iram"],
            "crc32": dump["crc32"],
        }
        rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"PASS: wrote {len(rows)} systems to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
