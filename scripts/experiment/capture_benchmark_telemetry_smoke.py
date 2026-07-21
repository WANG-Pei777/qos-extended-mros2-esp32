#!/usr/bin/env python3
"""Reset the smoke board and retain raw UART bytes through a terminal marker."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--terminal-prefix", default="BENCH_DUMP_END")
    parser.add_argument("--post-terminal-seconds", type=float, default=0.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.post_terminal_seconds < 0:
        parser.error("--post-terminal-seconds must be non-negative")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.timeout
    saw_dump_end = False
    post_terminal_deadline: float | None = None
    pending = bytearray()
    terminal_prefix = args.terminal_prefix.encode("ascii") + b" "

    with serial.Serial(args.port, args.baud, timeout=0.25) as uart:
        uart.reset_input_buffer()
        uart.dtr = False
        uart.rts = True
        time.sleep(0.15)
        uart.rts = False
        time.sleep(0.15)

        with args.output.open("wb") as raw_log:
            while time.monotonic() < deadline:
                if (
                    post_terminal_deadline is not None
                    and time.monotonic() >= post_terminal_deadline
                ):
                    break
                chunk = uart.read(4096)
                if not chunk:
                    continue
                raw_log.write(chunk)
                raw_log.flush()
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    if line.startswith(terminal_prefix):
                        saw_dump_end = True
                        post_terminal_deadline = (
                            time.monotonic() + args.post_terminal_seconds
                        )
                if saw_dump_end and args.post_terminal_seconds <= 0:
                    break

    if not saw_dump_end:
        print(
            f"FAIL: {args.terminal_prefix} not seen within {args.timeout:.1f}s",
            file=sys.stderr,
        )
        return 1
    print(f"PASS: captured {args.output.stat().st_size} raw UART bytes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
