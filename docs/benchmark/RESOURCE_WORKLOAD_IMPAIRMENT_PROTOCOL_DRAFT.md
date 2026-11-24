# Resource, Workload, Impairment, and Three-System Extension Protocol

Status: DRAFT -- excluded engineering smokes only; no formal data or claim authorized
Drafted: 2026-07-16
Primary statistical unit: one independently reset hardware run

## Evidence Boundary

This protocol covers measurements that the existing PCAPs and fixed 64-byte
workload cannot provide. Wireshark is used for wire behavior only. It does not
measure ESP32 CPU, heap, stack, or energy, and it does not replace application RTT.

Pilot runs produced while implementing this protocol are development evidence.
They must remain in separate result roots and must not enter formal summaries.

Engineering protocol readiness and native-support boundaries as of 2026-07-20
are audited in `WORKLOAD_PROTOCOL_READINESS_AUDIT_20260720.md`. That audit does
not freeze this draft or authorize formal collection. In particular, unsupported
upstream Reliable and large-sample return paths must remain explicit, and the
energy-bearing campaign remains blocked on calibrated external instrumentation.

## Common Run Contract

The implementation-level record format, static buffering, CPU arithmetic, memory/
stack units, GPIO timing, CRC, and overhead gate are frozen in
`COMMON_ESP32_TELEMETRY_CONTRACT_DRAFT.md`. This section defines the campaign-level
contract and outcomes.

All three systems must expose the same machine-readable records and window markers:

- `BENCH_CONFIG`: system, firmware hash, QoS, payload bytes, rate, impairment
  profile, duration, seed, and run token.
- `BENCH_WINDOW_START` and `BENCH_WINDOW_END`: board monotonic timestamps and a
  dedicated GPIO level transition for external power alignment.
- `BENCH_CPU`: 100 ms steady-state intervals with CPU utilization per core and
  total utilization.
- `BENCH_MEMORY`: free heap, minimum free heap since boot, largest free block, and
  allocation-failure count at start and end plus 100 ms steady-state samples.
- `BENCH_STACK`: task name, core, configured stack size, and high-water mark for
  every live task at the end of the measurement window.
- `BENCH_FINAL`: attempted TX, successful RX, duplicate/malformed counts, publish
  failures, application RTT sample count, missing-run structure, arrival
  inversions, RTT first/second moments, and run completion status.

The 100 ms records are buffered in preallocated static memory and dumped only after
the measurement marker closes; periodic UART output is forbidden inside the formal
window.

Each run uses a fresh board reset, a fixed warm-up, a 20 s steady-state measurement
window, and a bounded reply grace period. Setup and warm-up are excluded from CPU
and energy primary outcomes but retained in logs. All raw telemetry remains nested
within the run; 100 ms intervals and individual messages are not independent
statistical observations.

## Resource Metrics

### CPU

Enable the same FreeRTOS run-time statistics configuration in every firmware.
Compute utilization from deltas between 100 ms snapshots. Per-core utilization is
`100 * (1 - idle_delta / core_elapsed_delta)`; total utilization is the equally
weighted mean of the two ESP32-S3 cores. Primary run outcomes are steady-state mean
total CPU and steady-state p95 total CPU. Per-core mean/p95 and task-level run-time
shares are secondary.

An instrumentation-overhead pilot compares telemetry enabled and disabled under the
same clean 64-byte/10 Hz workload. The telemetry build is not released for formal
collection until the added mean CPU is at most 2 percentage points and application
delivery/RTT checks show no structural regression.

### Memory

For every sealed firmware variant, extract flash/text/rodata and static RAM
(`.data + .bss`) from the ELF/map using the same ESP-IDF size tool and retain its
machine-readable output.

For every run, report:

- free heap at first application entry, measurement start, and measurement end;
- minimum free heap since boot;
- peak heap consumption as first-entry free heap minus minimum free heap;
- minimum sampled free heap during the steady-state window;
- largest free block at measurement start/end and its ratio to free heap;
- allocation failures, if any;
- minimum stack high-water mark over all live tasks and per-task values.

The since-boot heap peak includes initialization and warm-up and is labeled as such.
The sampled steady-state minimum is reported separately because ESP-IDF 5.1 does
not expose a resettable local minimum-free-heap monitor in this environment.

### Energy

Energy requires an external monitor in the ESP32 supply path. The monitor must log
timestamped voltage and current at at least 1 ksample/s and capture the GPIO start
and end markers or an electrically aligned trigger. UART must not back-power the
board. Monitor model, serial number, firmware, range, sample rate, calibration date,
supply voltage, shunt/range, and raw samples are frozen in the release manifest.

For each run:

- window joules are the numerical integral of voltage times current between markers;
- the primary normalized outcome is window joules per successfully delivered
  application sample;
- total window joules and mean/peak power are always reported;
- joules per delivered sample is undefined, not zero, when delivery is zero;
- idle-adjusted energy is secondary and uses a separately randomized idle-window
  baseline collected in the same block.

No energy result is formal until the monitor and trigger path pass a marker-alignment,
known-load, missing-marker, and repeated-idle stability smoke test.

Because energy per successful delivery is a required outcome of the new workload
and three-system campaigns, their formal N=30 collection does not start before this
gate passes. Firmware development, deterministic checks, and explicitly labeled
pilots may proceed without the monitor; those runs are never backfilled into the
formal matrix.

## Formal Stage W: Current-Implementation Workload Surface

Purpose: identify payload/rate saturation and fragmentation behavior in the current
implementation under a clean network.

- System: current mROS2-QoS implementation.
- QoS: Best Effort, Reliable.
- Payload bytes: 64, 512, 1024, 2048.
- Publish rates: 10, 50, 100 Hz.
- Impairment: clean.
- Replication: N=30 accepted independent runs per cell.
- Total: 24 cells, 720 accepted runs.

The 20 s window gives 200, 1000, or 2000 attempted publications per run. PCAP
reconciliation verifies actual serialized size, DATA/DATA_FRAG use, NACK_FRAG where
applicable, goodput, wire bytes per delivery, and capture completeness.

## Formal Stage I: Current-Implementation Impairment Surface

Purpose: separate impairment mechanism effects at one workload anchor without
silently treating all loss as independent Bernoulli loss.

- System: current mROS2-QoS implementation.
- QoS: Best Effort, Reliable.
- Anchor workload: 512-byte payload, 50 Hz, 20 s.
- Replication: N=30 accepted independent runs per cell.
- Profiles frozen after efficacy pilots:
  - clean;
  - independent random loss 5%;
  - independent random loss 15%;
  - Gilbert-Elliott `gemodel 1% 25% 95% 0.1%` burst loss;
  - fixed 20 ms one-way injected delay;
  - fixed 50 ms one-way injected delay;
  - 20 ms delay with 10 ms normal delay variation (`RTT variability`, not
    synchronized one-way jitter);
  - 20 ms delay with 25% packet reordering, 50% correlation, and gap 5.
- Total: 16 cells, 480 accepted runs.

All Stage I profiles are applied to host-to-board egress only. This stage does not
support a bidirectional-impairment claim. A direction-interaction extension must
freeze and validate a separate ingress/AP/IFB mechanism before collection.

Every attempt stores the exact `tc` command, `tc -s` before/configured/after state,
configured seed where supported, PCAP, and impairment efficacy counts. A profile is
not accepted merely because the command exited successfully.

## Formal Stage X: Interleaved Three-System Sentinels

Purpose: compare micro-ROS, upstream mros2-esp, and the current implementation under
matched conditions while limiting claims to tested sentinels.

- Systems: current implementation, upstream mros2-esp, micro-ROS.
- Replication: N=30 accepted independent runs per system and sentinel.
- Systems are randomized within blocks on the same board, AP, host, and time window.
- Sentinel workloads:
  - Best Effort, 64 bytes, 10 Hz, clean;
  - Reliable, 64 bytes, 10 Hz, clean;
  - Best Effort, 2048 bytes, 10 Hz, clean;
  - Reliable, 2048 bytes, 10 Hz, clean;
  - Best Effort, 512 bytes, 100 Hz, independent random loss 5%;
  - Reliable, 512 bytes, 100 Hz, the frozen burst-loss profile.
- Total: 18 system-by-sentinel cells, 540 accepted runs.

The three systems must use the same application payload content, attempted publish
times, duration, host echo semantics, reset definition, energy window, resource
telemetry period, and acceptance boundary. Protocol differences such as RTPS versus
XRCE-DDS remain explicit. Unsupported features are reported as unsupported; they
are not emulated under the system name without a documented source-level extension.

## Acceptance and Exclusion

Acceptance is instrumentation-only and is frozen before formal collection. A run is
accepted when the firmware/config hashes match, board reset and readiness complete,
start/end markers exist, configured TX attempts complete, required raw telemetry and
PCAP files are present, impairment state is proven, and all hashes reconcile.

Delivery ratio, RTT, CPU level, heap consumption, stack margin, energy, and observed
system performance are outcomes and are never acceptance thresholds. All rejected
attempts and reasons remain in the ledger. A failed or partial visit is reviewed as
an operational incident; data are never silently deleted or overwritten.

## Pilot Gates Before Preregistration Freeze

1. Cross-system metric semantics and parser fixtures agree on synthetic logs.
2. Static size output reconciles against each ELF/map.
3. CPU telemetry overhead passes the frozen gate.
4. Heap/stack records include all expected application and middleware tasks.
5. Payload lengths and attempted rates reconcile at 64/512/1024/2048 bytes and
   10/50/100 Hz.
6. Fragmentation behavior is observed and classified rather than assumed.
7. Every impairment profile changes only the intended flow/direction and has an
   efficacy record.
8. External energy marker alignment and known-load tests pass.
9. Exact-binary smoke covers every firmware family and representative extremes.
10. A pilot runtime estimate and storage budget are frozen before formal launch.

The current host-egress efficacy set passes its excluded engineering gate in
`IMPAIRMENT_EFFICACY_READINESS_AUDIT_20260720.md`. This does not authorize formal
collection because the energy and storage gates remain blocked.

## Storage Gate

Per-run directories reference a content-addressed campaign-level firmware bundle;
they do not duplicate ELF, map, CMake cache, and firmware files for every run. A
preflight dry run measures PCAP, telemetry, power-trace, and manifest bytes and
freezes the projected campaign size. Formal launch requires free host capacity of
at least the larger of 50 GiB or twice that projection. The gate is checked before
every block, and a block never starts below the threshold.

## Statistical Plan Skeleton

Formal analysis uses run-level outcomes and 10,000 run-cluster bootstrap resamples.
Report effect sizes with 95% confidence intervals. Confirmatory outcome families and
contrasts are frozen after pilots and before formal collection; Holm correction is
applied within each declared family. Message and 100 ms telemetry samples are used
to construct run-level summaries only.

Primary candidate outcomes are delivery, run-level application RTT p95, mean ESP32
CPU, peak heap consumption, and joules per delivered sample. PCAP goodput,
fragmentation/recovery burden, largest-block ratio, stack margin, per-core CPU, and
peak power are secondary unless explicitly promoted before collection.

## Provenance and Release

Freeze source commits for all three repositories, reproducible firmware/host builds,
ELF/map/size outputs, redacted configurations, host/AP/board identifiers, tool
versions, schedules, seeds, commands, and smoke manifests. Each formal run receives
one immutable directory containing serial/host logs, telemetry, PCAP, `tc` state,
power trace, marker alignment, and SHA-256 records. Audit every accepted run before
analysis and seal each campaign tree before publication use.

Planned formal total: 1,740 accepted runs, excluding pilots and replacement attempts.
This count is provisional until hardware feasibility pilots and the external power
monitor are complete; any reduction must be preregistered before formal data exist.
