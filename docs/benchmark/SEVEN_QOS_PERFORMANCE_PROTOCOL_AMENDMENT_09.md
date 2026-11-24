# Seven-QoS Performance Protocol Amendment 09

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the board-to-host ingress-loss harness and the excluded
History/Depth ingress-efficacy smoke. It does not collect or accept any row
from the frozen 51-cell, 1,530-run schedule.

## Board-to-Host Ingress Harness

Commit `ab978316c3836254bdf8864f9a991f64647ad1a1` adds a root-only wrapper
that redirects only IPv4 packets sourced by the ESP32-S3 through an IFB device.
The wrapper applies `netem` on the IFB, records the source-scoped ingress
filter, IFB packet/drop counters, PCAP, and qdisc state, and unconditionally
removes the ingress qdisc and disables the IFB.

Commit `7d8f8e07ee81a7d829e2b5f29cf120283b4ad0a3` adds a fail-closed efficacy
validator. For the 5% pilot profile it requires at least 500 packets, an
effective IFB drop rate in the predeclared 2--8% pilot interval, matching PCAP
metadata, a passing telemetry attempt, a passing History/Depth policy oracle,
and the canonical post-cleanup qdisc state.

## Diagnostic Attempts

Attempt 01 is retained at:

`results/diagnostics/20260723_seven_qos_performance_history_HSM20_ingress_ab97831_attempt01/`

It stopped before flashing because two default tool paths were unavailable.
No board result was produced and ingress cleanup passed.

Attempt 02 is retained at:

`results/diagnostics/20260723_seven_qos_performance_history_HSM20_ingress_ab97831_attempt02/`

The ingress wrapper and telemetry validator passed, but the manually invoked
History/Depth validator was missing required workload-expectation arguments.
The sealed tree is retained as a low-level diagnostic and is not the final
family gate.

## Complete Excluded Gate

The complete gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_history_HSM20_ingress_ab97831_attempt03/`

Configuration: RELIABLE, VOLATILE, KEEP_LAST, capacity 40, runtime depth 20,
64-byte payload, burst size 10, 10 Hz workload, and an independent 5% B2H
ingress-loss profile. The firmware SHA-256 is
`c8620d167826dd37bdbaeee09a49aaece4cd7cc1cd6301c3759b9776ca094b37`.
The host echo SHA-256 is
`99de77d4bebda7a01ee559956ddd99b12b66b4bac68bb961b63941ceebe2522d`.

The IFB handled 2,196 packets and dropped 119, for an effective rate of
5.4189435337%. The efficacy validator passed. The History/Depth oracle retained
and returned all ten burst samples with reply mask `0x00000000000003ff`, and
the measured workload delivered 200/200 with zero publish failures. The PCAP
contains 558,628 bytes and has SHA-256
`ffbd1d8cb65596fdabb2457e16729645b6b7834ba27757f6f0a1685d2784b743`.
The qdisc returned to the canonical `mq` plus `fq_codel` state.

The 27-file tree passed release-seal verification with tree SHA-256
`ade1a7ea2a3ff2efe35d516a36bcd7b692745314774d5d7a199ec62485f77a0f`.

## Evidence Boundary and Remaining Gate

This N=1 result is an excluded harness and efficacy smoke. It demonstrates a
source-scoped B2H loss mechanism and its audit oracle; it is not a formal
performance observation and cannot be promoted into the 1,530-run campaign.

History/Depth formal collection remains blocked until the formal runner,
artifact freeze, accepted/rejected ledger, retry behavior, and schedule
completeness checks are implemented and verified. Resource Limits still
requires a frozen ACK-suppression episode. The root formal launch gate and
every family formal launch gate remain false.

Energy remains `deferred_not_collected` under Amendment 01. This smoke supports
no energy-use conclusion.
