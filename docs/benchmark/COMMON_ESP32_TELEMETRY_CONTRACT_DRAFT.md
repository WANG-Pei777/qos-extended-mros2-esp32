# Common ESP32 Telemetry Contract

Status: DRAFT -- implementation and pilot gate, no formal data
Version: 1
Drafted: 2026-07-16

## Scope

Current mROS2-QoS, upstream mros2-esp, and micro-ROS must use the same telemetry
semantics, sampling cadence, measurement window, and parser contract. Instrumented
baseline builds are benchmark harness variants; their source patches and hashes are
reported separately from the unmodified upstream commits.

## Measurement Window

Each accepted run has this order:

1. fresh board reset and exact firmware/config verification;
2. network and endpoint readiness;
3. fixed warm-up outside the measurement window;
4. GPIO marker high and board `window_start_us` capture;
5. 20 s performance/energy window;
6. board `window_end_us` capture and GPIO marker low;
7. bounded reply grace and final application counters;
8. telemetry dump over UART after the measured window.

The window contains no periodic UART logging. Fatal conditions may print
immediately but make the attempt ineligible. The GPIO transition and board timer
are captured in one short critical section; their measured skew is retained.

## Frozen Runtime Configuration

Each formal firmware contains a generated allowlist derived from the sealed cell
manifest. After reset and before network/entity creation, the board requests a
configuration. The host sends only a scheduled `cell_id`, unique `run_token`, and
CRC-32. The board looks up all policy/workload values,
rejects an unknown cell or second configuration in the same boot, and echoes the
canonical configuration and manifest hash in `BENCH_CONFIG`. The host ledger
rejects a run token reused anywhere in the campaign.

No factor value is accepted as unrestricted free-form input during formal
collection. Compile-time factors such as RTPS history capacity and telemetry build
mode use separate prebuilt firmware artifacts; their binary/config hashes are also
bound by the cell allowlist. A fresh board reset is still required for every
independent run, but a reflash is required only when the scheduled firmware family
changes.

The host acceptance audit reconstructs every echoed configuration from the sealed
manifest. Configuration mismatch, a config received after entity creation, an
unlisted cell, reused run token, wrong firmware family, or manifest-hash mismatch is
an instrumentation rejection.

## Static Buffering

A dedicated telemetry task samples every 100 ms into a compile-time, preallocated
array. A 20 s window therefore requires exactly 200 interval slots plus start/end
snapshots. No heap allocation, file I/O, or serial formatting is allowed between
the start and end markers.

The telemetry array is part of `.bss` and is included in static-memory results. All
three systems use the same slot layout and capacity. Buffer overflow, a missed
interval, timer regression, or task-list truncation is an instrumentation rejection,
not a performance outcome.

## CPU Semantics

Enable FreeRTOS trace facility and run-time statistics with the same microsecond
time base in every firmware. Record each core's idle-task run-time counter at every
100 ms boundary. For interval `i`:

```text
busy_core_ppm[i] = 1,000,000
                   * (wall_delta_us - idle_delta_us)
                   / wall_delta_us
```

Clamp-free arithmetic is required: an idle delta greater than wall delta is an
instrumentation failure. Total busy utilization is the arithmetic mean of the two
core values. Primary run summaries are mean and p95 total busy utilization; per-
core summaries and end-of-window task run-time shares are secondary.

Use 64-bit delta arithmetic and retain raw wall/idle counters. The 20 s window is
short enough to avoid ambiguity, but wrap handling is still tested with synthetic
counters.

## Memory Semantics

Capture these fields at application entry, window start, every 100 ms, and window
end where the API is applicable:

- free internal heap bytes;
- free total heap bytes;
- minimum free internal/total heap since boot;
- largest free internal block bytes;
- cumulative allocation-failure count.

Primary dynamic memory outcomes are since-entry peak consumption and minimum
steady-window free heap. Since-boot minimum remains separate because initialization
and warm-up are included. Largest-block/free-heap ratio is a fragmentation outcome,
not a replacement for free heap.

Register an allocation-failure callback that increments a lock-free counter and
stores only the first failure size/capability/time in preallocated storage. It must
not print or allocate in the callback.

## Stack Semantics

After the end marker, enumerate every live FreeRTOS task into a fixed-capacity task
status array and record task name, core affinity/current core, configured stack
bytes where available, and minimum remaining stack bytes (high-water mark). The
raw API unit is converted once in the telemetry component and emitted explicitly
as bytes.

The primary run stack outcome is the minimum remaining bytes across required
middleware/application tasks. The manifest freezes the required task-name set for
each system. Missing required tasks, duplicate ambiguous names, or truncation makes
the attempt ineligible.

## Serial Records

Records are single-line ASCII key/value messages. Every line includes `schema=1`,
`run_token`, and a monotonic `record_seq`. Required record families are:

- `BENCH_CONFIG`: system, firmware/config hashes, QoS, payload, rate, target count,
  impairment ID, window duration, telemetry period, and GPIO number;
- `BENCH_WINDOW_START` / `BENCH_WINDOW_END`: board time and marker state;
- `BENCH_SAMPLE`: index, board time, raw wall/idle counters, CPU ppm, and heap fields;
- `BENCH_TASK`: one post-window record per task;
- `BENCH_ALLOC_FAIL`: zero or one first-failure detail plus cumulative count;
- `BENCH_FINAL`: attempted TX, publish rejects, RX, duplicate/malformed counts,
  RTT sample count, missed telemetry intervals, and completion state;
- `BENCH_DUMP_END`: record count and CRC-32 over the canonical buffered records.

Host parsing rejects unknown schema versions, duplicate `(run_token, record_seq)`,
missing sequence numbers, a CRC mismatch, nonmonotonic timestamps, wrong sample
count, or records carrying another run token. Raw serial bytes are always retained.

## Static Size Artifacts

For every firmware variant, retain ELF, map, build configuration, and ESP-IDF size
output. Report flash/text/rodata and static RAM (`.data + .bss`) with a documented
tool version. Compare telemetry-enabled and telemetry-disabled builds so the
instrumentation's static cost is visible rather than attributed to the middleware.

## Overhead Gate

Before any formal run, randomize telemetry enabled/disabled pilots at 64 bytes,
10 Hz, clean network for every system. The telemetry build passes only when:

- added mean CPU is at most 2 percentage points;
- delivery shows no structural regression;
- RTT change is reported with a run-level interval and shows no unexplained mode;
- no allocation failure, stack-margin violation, sample miss, or serial CRC failure
  occurs;
- GPIO/board timestamps and an external logic/power trace pass marker alignment.

Pilot outcomes select implementation details but never enter formal comparison
tables. Any gate change occurs before preregistration freeze and is recorded.
