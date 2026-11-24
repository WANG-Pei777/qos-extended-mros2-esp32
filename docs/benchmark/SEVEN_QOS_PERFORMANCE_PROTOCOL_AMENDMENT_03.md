# Seven-QoS Performance Protocol Amendment 03

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the first family-specific extension of the excluded
Seven-QoS performance pilot. It adds a Deadline event gate while preserving the
accepted deterministic releases and the common-path correction recorded in
Amendment 02.

No row from the frozen 51-cell, 1,530-run schedule is collected or accepted by
this amendment.

## Code-Line Boundary

The Deadline extension is implemented at source commit
`b129266f5ea5` (`Add Deadline performance family smoke gate`). The workspace
accepts only `common` and `deadline` as family identifiers. It fails at CMake
configuration for any other family, and its README explicitly forbids using
the workspace for a formal performance run.

The implementation adds:

- a machine-safe family and cell identifier plus a compile-time subscriber
  Deadline;
- one callback registration for requested-deadline-missed events;
- before/after middleware counters, a window-gated callback count, and the
  first callback offset;
- one `PERF_POLICY_FINAL` record emitted only after the telemetry seal and
  control-probe record; and
- a fail-closed validator that binds the configuration to the policy record,
  checks counter deltas against callbacks, and enforces the expected zero or
  positive event class.

The implementation does not unlock History/Depth, Durability, Lifespan,
Liveliness, or Resource Limits.

## Excluded Development Attempt

The first DL01 attempt is retained at:

`results/diagnostics/20260723_seven_qos_performance_deadline_DL01_attempt01/`

It produced 233 internally consistent Deadline events, but the policy record
was emitted before `BENCH_DUMP_END`. The generic telemetry validator therefore
correctly rejected it as measurement-window UART activity. The attempt is
classified `FAIL`, is excluded from every accepted result set, and is not
pooled with later attempts. The implementation was then changed so the policy
record is emitted after the telemetry seal.

## Same-Commit Positive Gate

The clean DL01 smoke is retained at:

`results/diagnostics/20260723_seven_qos_performance_deadline_DL01_b129266_attempt01/`

Configuration: RELIABLE, 64-byte payload, 10 Hz, 20-second window, 50 ms
subscriber Deadline, and clean network profile. The embedded application
version is `b129266`. The run recorded:

- 200 attempted transmissions, 200 replies, and 200 RTT samples;
- 200 telemetry samples and 20 task records;
- zero publish failures, allocation failures, missing replies, malformed
  replies, arrival inversions, missed telemetry intervals, or fault flags;
- 254 middleware Deadline events and 254 callbacks; and
- first in-window callback offset 58,052 microseconds.

The generic validator and the Deadline-specific validator both passed. The
firmware SHA-256 is
`6df431e5f463473f4b854c3f72643f66be0e26bafc7966d1a5e94bd527bb4165`,
and the PCAP SHA-256 is
`d62f8f69ea576f6764f96632b53df2517133f979a9c085f8078a4218d67b965d`.
The 25-file result tree passed seal verification with tree SHA-256
`b526dd91692feeb10efc6b971070372165414c44fa061213f8f12f0f0f089385`.

## Same-Commit Zero-Event Gate

The clean DL02 smoke is retained at:

`results/diagnostics/20260723_seven_qos_performance_deadline_DL02_b129266_attempt01/`

It uses the same workload and network profile with a 500 ms subscriber
Deadline. The embedded application version is `b129266`. It recorded 200/200
replies, 200 telemetry samples, 20 task records, zero fault or allocation
flags, zero Deadline events, zero callbacks, and the required `-1` first-event
offset. Both validators passed.

The firmware SHA-256 is
`74e7a5a6da944fa5b3a34078c453571fc588c3981fd907764980bdba7b84b2af`,
and the PCAP SHA-256 is
`39c2728c0bdd105dae568c7834c3a89087e56204d984b11ad26fe3b815e21583`.
The 25-file result tree passed seal verification with tree SHA-256
`bbe1ccfbb03a2ec641d0a11c56d71b92f3b3fc0b0fb2615daa64974cb8a2bc93`.

Both post-run qdisc states matched the canonical `mq` root with eight
`fq_codel` children.

## Remaining Gate

The positive/zero pair closes only the Deadline event-observation smoke gate.
Formal collection remains blocked because:

- the runner still uses a fixed engineering-smoke run token and evidence
  classification instead of a schedule-bound formal token;
- the five remaining policy families do not yet have family-specific execution
  and validation paths;
- storage, retry, and schedule-completeness gates have not been frozen for the
  formal runner; and
- a fixed host-side network delay changes transit latency but does not by itself
  change steady inter-arrival spacing. The exact Deadline estimand and delay
  efficacy check must therefore be frozen before any Deadline schedule row is
  collected.

Energy remains `deferred_not_collected` under Amendment 01. These smokes support
no energy-use conclusion.
