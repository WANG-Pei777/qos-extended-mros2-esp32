# Seven-QoS Performance Protocol Amendment 11

Status: ACTIVE FOR FORMAL-RUNNER DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment corrects the Resource Limits execution-contract label before
formal collection. It also records the introduction of fail-closed identity
fields for future formal-candidate attempts. No row from the frozen 51-cell,
1,530-run schedule has been collected or accepted.

## Resource Limits Direction Correction

The Resource Limits pressure mechanism suppresses RTPS acknowledgements sent
from the host to the ESP32-S3. The implemented wrapper therefore applies the
bounded 100% loss episode to the dedicated host-to-board egress path. Amendment
10 and the excluded hardware gate already record that direction and executed
it correctly.

The execution-contract value is corrected from
`host_ingress_ack_suppression_only` to
`host_egress_ack_suppression_only`. This is a no-data contract correction. It
does not alter the frozen cell matrix, randomization, run order, sample count,
estimands, accepted evidence, or the excluded Resource Limits smoke result.

## Formal-Candidate Identity Boundary

Commit `2aa4c00` introduces a separate `formal_candidate` mode in the low-level
collector and both network wrappers. Every future formal candidate must bind:

- the frozen schedule SHA-256;
- the unique `sqp-xxxx` campaign run token;
- the gapless schedule ordinal;
- the frozen cell ID; and
- the matching firmware run token.

Formal candidates may only be written below `results/experiments`. Engineering
smokes may only be written below `results/diagnostics` and cannot carry formal
identity fields. A passing attempt remains only a candidate until a separate
acceptance receipt and campaign ledger include it.

## Remaining Gate

The root formal launch gate and all six family launch gates remain false. The
51-cell artifact matrix, per-cell runtime bindings, accepted/rejected attempt
ledger, retry policy, storage preflight, and schedule-completeness audit must be
verified before formal collection starts.

Energy remains `deferred_not_collected` under Amendment 01. This amendment
supports no energy-use conclusion.
