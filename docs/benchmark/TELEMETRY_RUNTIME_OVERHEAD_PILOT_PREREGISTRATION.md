# Telemetry Runtime-Overhead Pilot Preregistration

Status: FROZEN, NO PILOT DATA

Frozen: 2026-07-17T05:16:07.710045Z

Schedule SHA-256:
`20849d0e044f9021eaba8ec037f9180d677dac9fe2f8cea07cad4e6fdb21e399`

Design-manifest SHA-256:
`c9d0926dc1a61d49a70947f823ef7b78605b8a80821e7dbbe03e1b0ea91b503a`

## Evidence Boundary

This is an engineering instrumentation-overhead pilot. It selects whether the
common telemetry implementation is acceptable for later formal campaigns. Its
measurements are excluded from all formal cross-system, QoS, workload, impairment,
resource, and energy tables.

Six N=1 control-probe hardware smokes were completed before this freeze. They are
feasibility checks only and are excluded from the 60 scheduled runs and every
pilot estimator below.

## Frozen Design

- Systems: current mROS2-QoS, upstream mros2-esp32, and micro-ROS.
- Modes: full telemetry on and endpoint-only CPU control probe off.
- Workload: 64-byte BEST_EFFORT payloads, 10 Hz, 200 transmissions, 20 s clean
  network window, 5 s reply grace.
- Replication: 10 on/off pairs per system, 20 accepted runs per system and 60
  accepted runs total.
- Blocking: 10 superblocks. Each contains all three systems; system order and
  within-system on/off order are randomized.
- Random seed: `2026071701`.
- Every attempt uses a fresh board reset and exact binary flash. UART capture
  continues for six seconds after the terminal record to expose late task-watchdog
  failures.
- Maximum attempts: three per scheduled run. Every failed or interrupted attempt
  remains retained. Exhausting three attempts stops the pilot; it does not silently
  drop or replace the scheduled run.

The machine schedule and artifact hashes are frozen in
`results/protocols/20260717_telemetry_runtime_overhead_pilot`. Each of the six
system/mode cells has exactly 10 rows. A campaign runner must reject a firmware
hash that differs from its schedule row.

## Acceptance

An accepted run must pass its strict mode-specific UART validator and the common
control-probe validator. It must have 200/200 unique deliveries, zero publish
failures, duplicates, malformed messages, crashes, watchdogs, allocation failures,
telemetry faults, missed intervals, and CRC failures. Both control-probe wall
intervals must be within 19.5 to 20.5 s, and CPU ppm must exactly reconstruct from
the retained wall and idle-counter deltas.

A network, agent, host, flash, or readiness failure may be retried only under the
three-attempt rule and remains visible in the attempt ledger. Any runtime crash,
watchdog, arithmetic fault, or telemetry-integrity failure is an immediate pilot
gate failure even if a replacement attempt later succeeds.

## Estimands And Gate

The primary estimand for each system is the mean of the 10 paired differences:

```text
telemetry-on control CPU mean - telemetry-off control CPU mean
```

CPU is expressed in percentage points across two cores. The control probe uses
the same endpoint idle-counter algorithm in both modes; the 100 ms on-mode CPU
series is a secondary agreement check and is not substituted for the paired
control estimate.

A deterministic 20,000-resample paired percentile bootstrap, seeded
`2026071702`, supplies the two-sided 95% interval. The runtime CPU overhead gate
passes only when both the point estimate and the upper 95% endpoint are at most
2.0 percentage points for every system.

Secondary paired outcomes are mean RTT difference, mean RTT ratio, maximum RTT,
ready time, and delivery. RTT has no post hoc pass threshold: its full paired
distribution and interval are reported. A greater than 10% mean paired RTT
increase is a preregistered review trigger requiring root-cause analysis before
formal collection, not an automatic data deletion rule.

The pilot also fails if full-telemetry sample CPU and control-probe CPU differ by
more than 0.5 percentage points in any accepted on run, because that indicates a
measurement-semantic mismatch.

## Remaining Hard Gate

Passing this pilot does not permit the 3,270-run formal expansion to begin. Energy
per successful delivery is mandatory, and no supported external power monitor is
currently present. GPIO 4 marker alignment, known-load calibration, idle stability,
and power-trace provenance remain hard preregistration gates.
