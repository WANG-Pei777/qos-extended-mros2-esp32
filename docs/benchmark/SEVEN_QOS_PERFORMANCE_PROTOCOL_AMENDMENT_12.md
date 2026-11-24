# Seven-QoS Performance Protocol Amendment 12

Status: ACTIVE PRE-DATA IDENTITY CORRECTION
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment separates immutable firmware identity from per-attempt campaign
identity before any formal Seven-QoS performance data are collected. The frozen
51-cell design contains 1,530 accepted-run slots, with 30 accepted runs per
cell. No formal performance row has been collected or accepted.

## Two-Level Identity

Each frozen cell has one stable firmware run token:

`sqc-<family>-<cell-id>-<configuration-sha256-prefix>`

The token is compiled into the cell firmware and must match the board telemetry,
the copied firmware bundle, the collector manifest, the network-wrapper
manifest when present, and the cell artifact requirement.

Each scheduled attempt retains a separate unique campaign identity:

- the `sqp-xxxx` campaign run token;
- the gapless schedule ordinal;
- the frozen schedule SHA-256; and
- the family and cell ID.

The campaign identity is stored in the evidence identity and acceptance ledger.
It is not compiled into the firmware. All 30 scheduled attempts for a cell may
therefore reuse the same hash-verified cell firmware while remaining distinct,
auditable campaign attempts.

## Reason for the Correction

The earlier runner-development wording required the firmware run token to equal
the unique campaign run token. That would require 1,530 separately compiled
firmware images and would contradict the intended one-artifact-per-cell
binding. The corrected two-level model requires 51 cell firmware bundles and
1,530 unique attempt identities.

This is a fail-closed, pre-data contract correction. It does not alter the
frozen cells, factor levels, run order, randomization, sample count, estimands,
retry policy, or acceptance criteria.

## Remaining Gate

Formal launch remains prohibited until all 51 cell firmware bundles and runtime
arguments are frozen, the acceptance oracle passes, storage preflight passes,
and exact committed artifacts pass the required engineering gates.

Energy remains `deferred_not_collected`; this amendment supports no energy-use
conclusion.
