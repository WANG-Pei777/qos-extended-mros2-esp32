# Common ESP32 Telemetry Engineering Audit

Status: ENGINEERING PASS -- diagnostic only, no formal performance evidence
Date: 2026-07-16
Branch: `codex/seven-qos-formal` (uncommitted engineering state)

## Scope

This audit covers the reusable ESP32 telemetry component and a no-network board
smoke for the current mROS2 implementation. It does not cover upstream mros2-esp,
micro-ROS, a benchmark workload, an external power trace, or the preregistered
Seven-QoS cells.

The implementation uses a static telemetry task and `.bss` buffers for one entry
snapshot, one window-start snapshot, 200 interval samples at 100 ms, one
window-end snapshot, and 48 task records. No telemetry formatting or UART output
occurs while the marker is high. The component records per-core idle counters,
CPU busy ppm, internal/total heap state, allocation failures, task stack
high-water marks, marker command timestamps, sample lateness, and explicit
instrumentation fault bits.

## Verification

- Host telemetry arithmetic tests pass 10/10, including one 32-bit idle-counter
  wrap, zero-wall rejection, idle-greater-than-wall rejection, and ambiguous
  multi-wrap rejection.
- The complete host gate passes 158/158 tests.
- Strict ESP-IDF compilation exposed and fixed target-specific `uint32_t` format
  mismatches that the QoS diagnostic build's legacy `-w` setting had hidden.
- Clean telemetry-on and telemetry-off QoS firmware builds both pass with the
  same source, QoS parameters, ESP-IDF 5.1.7 toolchain, and ESP32-S3 target.
- The standalone telemetry smoke builds without the mROS2 component and has 80%
  of its 1 MiB app partition free.

## Instrumentation Static Cost

`idf_size.py` reports the following telemetry-on minus telemetry-off differences
for the QoS diagnostic firmware:

| Metric | Off (B) | On (B) | Delta (B) |
|---|---:|---:|---:|
| `.data` in D/IRAM | 18,028 | 18,076 | +48 |
| `.bss` in D/IRAM | 41,432 | 63,016 | +21,584 |
| executable D/IRAM text | 69,803 | 72,095 | +2,292 |
| total used D/IRAM | 129,263 | 153,187 | +23,924 |
| flash code | 555,219 | 557,275 | +2,056 |
| flash rodata | 123,352 | 123,824 | +472 |
| total used flash (non-RAM) | 678,827 | 681,355 | +2,528 |
| total image accounting | 783,041 | 787,909 | +4,868 |

The enabled QoS binary SHA-256 is
`131aa086b1f66b366dfa3f8578665f9502e21b3400ea654220f5a13c390dc254`;
the disabled binary SHA-256 is
`2a203bb708d3215155a6306712c31ee59cb6aa848859433a736ff859050973d6`.
These costs are instrumentation costs and must not be attributed to middleware.

## Hardware Smoke

The first retained attempt is an engineering failure. Its post-window UART dump
ran continuously for more than the task-watchdog period; the watchdog message
interrupted sample record 166 and invalidated the serial stream. The fix yields
one FreeRTOS tick after every post-window record. No code in the measurement
window changed.

The second attempt passes the strict host validator:

```text
records=213 samples=200 tasks=7 window_us=20004988
cpu_mean_ppm=1044 cpu_p95_ppm=925 max_lateness_us=4944
min_internal_heap=363632 min_stack_hwm=528
in_window_uart_lines=0 crc32=0x1f725388
```

All 200 sample fault fields and the final fault field are zero. Allocation
failures and missed intervals are zero. The 528-byte minimum stack high-water
mark belongs to the ESP-IDF `ipc1` task; the telemetry task retains 3,204 bytes.
The start marker command bracket is 6 us and the end bracket is 1 us. The GPIO
high window is 4,988 us longer than 20 s, which remains an external-marker
calibration item rather than being silently normalized away.

The passing raw UART log SHA-256 is
`c49fa17f57ace2fefb070168d8957f085c4e7c80575e75bf412d3019340b35f4`.
The retained failed log SHA-256 is
`261bf0fb33766ae1c20bc179f4cab73a86ca53a00df33818a0150fbe5b47e0f8`.

## Evidence Boundary And Remaining Gates

This audit closes source, host-math, target-build, serial-integrity, and one-board
empty-window smoke gates only. It does not support a CPU, memory, energy, or
cross-system comparison claim.

Before formal collection:

1. Port the same component semantics to instrumented upstream mros2-esp and
   micro-ROS builds and bind each patch/binary/config hash.
2. Calibrate GPIO 4 against an external logic/power trace and preregister an
   allowable marker-duration/skew tolerance.
3. Run randomized telemetry-on/off workload pilots for every system and apply the
   frozen overhead gate.
4. Add the sealed cell allowlist, run-token replay protection, complete
   `BENCH_CONFIG`/`BENCH_FINAL` fields, and required task-name manifests.
5. Keep energy per successful delivery blocked until a supported external power
   monitor is present and calibrated.

The engineering artifact tree is
`results/diagnostics/20260716_benchmark_telemetry_smoke`. It retains both UART
attempts, size JSON/CSV files, and on/off/smoke ELF, map, binary, and sdkconfig
artifacts.
