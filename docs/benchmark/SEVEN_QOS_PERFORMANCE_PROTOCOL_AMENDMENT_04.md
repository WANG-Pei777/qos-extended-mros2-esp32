# Seven-QoS Performance Protocol Amendment 04

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records schedule-bound run identity, fail-closed family
execution contracts, and the Lifespan family smoke gate. It preserves all
earlier deterministic and performance-development evidence boundaries.

No row from the frozen 51-cell, 1,530-run schedule is collected or accepted by
this amendment.

## Run Identity Gate

Commit `e7d72c32687c825b78c08a3ec7f9f3cdf1c21bf8` adds a compile-time,
machine-safe run token. The token is emitted in every `BENCH_*` telemetry
record, recorded as an expectation in the inner attempt manifest and outer
impairment manifest, and checked exactly by the telemetry validator. CMake
rejects unsafe tokens before firmware generation.

The same-commit identity smoke is retained at:

`results/diagnostics/20260723_seven_qos_performance_run_identity_e7d72c3_attempt01/`

The firmware, both manifests, and all telemetry records used the unique token
`idgate-e7d72c3`. The generic and policy validators passed, the post-run qdisc
returned to the canonical state, and the 25-file result tree passed seal
verification with tree SHA-256
`aac56d8ea7dd83912169fa0c35827bae35fad24ec40dc73eae575a0cf5c06982`.
The firmware SHA-256 is
`dec3d8cdf3fc6721d483442b1f9501db9a9840f6c03545572d8562a84835f505`.

## Execution Contract Boundary

The machine-readable execution contract covers all six families and all 51
cells. It records endpoint sides, startup order, impairment locus, required
configuration fields, required observations, smoke state, and a per-family
formal-launch gate. The root gate and every family gate remain false.

The first contract-bound no-data protocol is retained at:

`results/protocols/20260723_seven_qos_performance_contract_bound_e7d72c3/`

It binds the unchanged schedule SHA-256
`3e76421e2c07869df73e76663c80084f875ab8cbbcabaf7d52fc7a46e4309abe`
to Amendment 03 and execution-contract SHA-256
`b9c9a4b6ccef1bb7dad44ca3c1ebf31e1fdcc3e657db44dfc32de36ddc4f6a8d`.
The protocol source is a clean `e7d72c3` worktree, its execution gate is
`BLOCKED_HARNESS_AND_SMOKE`, and its six-file tree passed seal verification
with tree SHA-256
`139de3605059efeb79fb63e8971d4307e2244455e65896733c04a015516c0bbb`.

## Lifespan Harness

Commit `3ff67da` added a Lifespan family mode with:

- a publisher-only Lifespan QoS value;
- a bounded pre-window transmission-hold probe;
- probe acceptance, reply, hold timing, and isolated drop-counter records;
- a policy-applied 20-second workload with normal telemetry; and
- a Lifespan validator for the disabled/fresh and expired outcomes.

The first LS02 hardware attempt is retained at:

`results/diagnostics/20260723_seven_qos_performance_lifespan_LS02_3ff67da_attempt01/`

Its outer telemetry runner passed, but the policy validator failed because a
100 ms RTOS delay measured 99,961 microseconds against an exact lower bound.
The same attempt also showed that a 50 ms Lifespan applies to the full workload,
not only the pre-window probe: delivery was 0/200. Its `policy_validation.txt`
records the failure. It is not sealed or accepted as a passing smoke.

Commit `5571281` corrected the oracle without changing the mechanism. It allows
a bounded 2 ms tick-quantization undershoot, records the final Lifespan drop
counter after the workload, reconciles total drops, and requires an explicit
zero or full workload-delivery class.

## Same-Commit Lifespan Gates

The expired LS02 gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_lifespan_LS02_5571281_attempt02/`

Configuration: RELIABLE, 64 bytes, 10 Hz, 50 ms Lifespan, 100 ms pre-window
hold, and clean network profile. The probe was accepted, produced one isolated
Lifespan drop and no reply, and measured a 99,959-microsecond hold. The full
workload delivered 0/200; total drop delta was 201, exactly reconciling one
probe plus 200 workload samples. Telemetry recorded 200 intervals, 20 tasks,
zero publish or allocation failures, and zero fault flags. Both validators
passed. The firmware SHA-256 is
`d6fb78cedc13cd1fa1454ac6fe2dbda58ae2afc1e59a9226221acba51aa5f11c`,
and the 25-file tree passed seal verification with tree SHA-256
`70c913358be685f942a9df8b5b317206ff527c7dfcd3c01affea5ce985d59718`.

The disabled LS01 gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_lifespan_LS01_5571281_attempt01/`

It used the same workload and hold with Lifespan disabled. The probe was
accepted and replied once, isolated and total Lifespan drops were zero, and the
workload delivered 200/200. The hold measured 99,962 microseconds. Telemetry
again recorded 200 intervals, 20 tasks, zero publish or allocation failures,
and zero fault flags. Both validators passed. The firmware SHA-256 is
`22aefdfc541b83743781bb148e35e359e51c6bb2b8c2e65d63ee2c0fd3cede02`,
and the 25-file tree passed seal verification with tree SHA-256
`0c7bb820a8058b9c0424ac422c691d42c948d17e191109e864f1b83fe3ebab9b`.

Both passing attempts restored the canonical qdisc state. The execution
contract may now classify Deadline and Lifespan as
`smoke_gate_passed_formal_blocked`.

## Remaining Gate

Lifespan formal collection remains blocked. The pre-window probe verifies
mechanism wiring, while the policy-applied workload demonstrates the observable
delivery boundary; neither freezes the final per-cell estimand, run duration,
or acceptance rule. History/Depth, Durability, Liveliness, and Resource Limits
still lack family-specific performance smokes. The formal runner, retry ledger,
and schedule-completeness gate are also not frozen.

Energy remains `deferred_not_collected` under Amendment 01. These smokes support
no energy-use conclusion.
