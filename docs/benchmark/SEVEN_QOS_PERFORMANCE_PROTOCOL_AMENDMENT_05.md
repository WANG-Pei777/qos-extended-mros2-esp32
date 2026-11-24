# Seven-QoS Performance Protocol Amendment 05

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the Resource Limits family smoke harness, its failed
diagnostic attempts, and the same-commit R00/R01 hardware gates. It preserves
all earlier deterministic and performance-development evidence boundaries.

No row from the frozen 51-cell, 1,530-run schedule is collected or accepted by
this amendment.

## Resource Limits Harness

Commit `63c481e` added a Resource Limits family mode with:

- RELIABLE, VOLATILE, KEEP_ALL board-side publishing;
- a compile-time `max_samples` value and a zero-or-one excess probe;
- board-side transmission hold for deterministic history saturation;
- publish-attempt, acceptance, rejection, allocation-failure, history-peak,
  history-release, and probe-reply records; and
- a Resource Limits policy validator with explicit capacity and recovery
  oracles.

The pre-window probe verifies mechanism wiring only. It does not replace or
freeze the fixed ACK-suppression episode required by the formal Resource Limits
cells.

## Retained Failed Diagnostics

The first same-commit R01 attempt is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R01_63c481e_attempt01/`

One warmup sample was still present when the probe started because the global
match signal became true before the user-writer reader proxy was installed.
With a five-sample limit, the probe therefore accepted four new samples and
rejected two instead of accepting five and rejecting one. History remained at
five after the bounded release wait, and the following workload reported 262
publish failures. Both the generic and policy validators recorded failure. The
attempt is not sealed or accepted as a passing smoke.

A dirty development rerun is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R01_dev_waitdrain_attempt02/`

The harness first waited for warmup history to be acknowledged and drained.
The probe then produced the intended `6 attempts / 5 accepted / 1 rejected`,
five replies, and zero history after release. The workload delivered all 910
successful publishes and reported 90 resource rejections. The old generic
validator still failed because it required zero publish failures for every
family. This dirty run is diagnostic only and is not sealed or accepted.

## Saturation Outcome Contract

Commit `1b86118c0e778c5102430950138d348e70178bd0` makes publish failures an
explicit opt-in telemetry outcome. The default validator remains unchanged:
zero publish failures are required unless the runner records and forwards the
exception. Resource Limits uses the exception because rejection fraction is a
prespecified primary outcome.

The generic validator still requires internally consistent counts and rejects
delivery greater than the successful-publish count. The Resource Limits oracle
then checks the exact boundary, one-over-capacity rejection, zero allocation
failures, history drain, probe replies, and delivery of every successful
workload publish. Attempt manifests record `publish_failure_policy` as
either `zero` or `outcome`.

## Same-Commit Resource Limits Gates

The within-capacity R00 gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R00_1b86118_attempt01/`

Configuration: RELIABLE, KEEP_ALL, 512 bytes, 50 Hz, 20-second workload,
`max_samples=20`, no excess probe, and clean network profile. The probe
accepted 20/20 samples, rejected zero, reached a history peak of 20, received
20 replies, and drained to zero. The workload delivered 1,000/1,000 with zero
publish or allocation failures. Telemetry recorded 200 intervals, 20 tasks,
zero missed intervals, and zero fault flags. Both validators passed and qdisc
returned to the canonical state. The firmware SHA-256 is
`07707408029414cfb98c33414c4a4d67d5f04854f4e933488941878a6af87f94`.
The 25-file tree passed seal verification with tree SHA-256
`30dc419c3aae33dc31bfefa02ea596d285de6f5703c45f36c0242bb7d9d08455`.

The one-over-capacity R01 gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R01_1b86118_attempt01/`

It used the same workload with `max_samples=5` and one excess probe. The probe
produced `6 attempts / 5 accepted / 1 rejected`, reached a history peak of
five, received five replies, and drained to zero. During the policy-applied
workload, 74 attempts were rejected at the resource limit and all 926
successful publishes were delivered. Allocation failures, telemetry missed
intervals, and fault flags were zero. Both validators passed and qdisc returned
to the canonical state. The firmware SHA-256 is
`8dcdd763be24db19bb35a54263f5e75fae42dcb03e8c7519ff898bd450e83a42`.
The 25-file tree passed seal verification with tree SHA-256
`555286b245c8ad4e23f99ebdd5a119efeaaae00dbc796580a15736bb7df11e1b`.

The execution contract may now classify Deadline, Lifespan, and Resource
Limits as `smoke_gate_passed_formal_blocked`.

## Remaining Gate

Resource Limits formal collection remains blocked. The final ACK-suppression
implementation, timing efficacy oracle, per-cell runner, retry ledger, and
schedule-completeness gate are not frozen. History/Depth, Durability, and
Liveliness still lack family-specific performance smokes. The root formal gate
and every family formal gate remain false.

Energy remains `deferred_not_collected` under Amendment 01. These smokes support
no energy-use conclusion.
