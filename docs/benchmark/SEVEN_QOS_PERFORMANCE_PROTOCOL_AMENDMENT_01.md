# Seven-QoS Performance Protocol Amendment 01

Status: ACTIVE FOR HARNESS DEVELOPMENT -- NO PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment removes the external power monitor as a start gate for the
51-cell Seven-QoS performance campaign. The change is made before any run from
that campaign is collected or accepted.

## Energy Boundary

Energy is deferred to a separate supplemental campaign after an external power
monitor and GPIO marker path are calibrated. The current campaign:

- does not collect energy traces;
- does not estimate energy per successful delivery;
- does not support an energy-efficiency conclusion; and
- does not treat missing energy as a failed run.

Delivery, run-level RTT, CPU utilization, heap, stack margin, mechanism counters,
and PCAP-derived wire behavior remain in scope where the family protocol defines
them. Every result manifest must record `energy_status=deferred_not_collected`.

## Evidence Boundary

The deterministic compatibility and mechanism releases bound to source commit
`3cb2cf792ec6200286cd04750f6a08f349340048` remain immutable. Performance-harness
development begins on a later code line. Deterministic releases are not rewritten,
pooled, or relabeled as performance observations.

The 51-cell source manifest remains `DRAFT_NO_DATA`. Its expanded schedule must
remain blocked until all of the following pass on one clean source commit:

1. randomized complete-block schedule validation;
2. exact firmware and host artifact freeze;
3. telemetry and network-control acceptance validation;
4. representative hardware smoke for every policy family; and
5. runtime, storage, retry, and failure-retention checks.

Development pilots remain excluded evidence and cannot later be promoted into the
formal campaign.

## Statistical Design

The design remains 51 cells with 30 independently reset accepted runs per cell.
Each policy family uses ten complete visits. Every cell appears once per visit,
and three independently reset runs are collected at that appearance. Rejected
attempts remain in an immutable ledger and do not change the frozen order.

No cell level, interaction corner, primary statistical unit, or accepted sample
count is changed by this amendment.
