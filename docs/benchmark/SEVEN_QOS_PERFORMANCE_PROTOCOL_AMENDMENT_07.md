# Seven-QoS Performance Protocol Amendment 07

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the Durability late-join harness and its same-commit
Volatile/Transient-Local hardware gates. It preserves all earlier evidence
boundaries and does not collect or accept any row from the frozen 51-cell,
1,530-run schedule.

## Deterministic Late-Join Boundary

Commit `85ab4d66be170732c408484bd0755f9b6ea9c90d` adds a Durability family mode
with a bounded pre-join writer cache. The board emits the configured pre-join
samples and a UART readiness marker before the host process exists. The runner
starts the host only after observing that marker and records the marker wait and
startup order in the attempt manifest.

The host echo process enters its executor before creating the input
subscription. It buffers Durability probe samples until the board reports that
both communication directions are matched, then releases only those buffered
probe replies. This prevents endpoint-discovery startup from being confused
with Durability replay. The board records pre-join attempts, acceptance,
rejection, allocation failures, history before join, history after join, unique
probe replies, and a 64-bit reply mask.

Fixed-delay and early marker development runs exposed startup races. Some
started the host before the board completed Wi-Fi startup; later runs received
only sequences 1--9 because the host subscription was discoverable before its
executor callback path was active. These development attempts remain unsealed
under `results/diagnostics/` and are excluded from the same-commit gates below.

## Same-Commit Durability Gates

The Transient-Local complete-replay gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_durability_DSMTL_85ab4d6_attempt01/`

Configuration: RELIABLE, TRANSIENT_LOCAL, KEEP_LAST depth 10, 10 pre-join
samples, 64-byte payload, 10 Hz workload, and clean network profile. The host
started only after the UART pre-join marker, with a recorded marker wait of
6.942 seconds. All 10 pre-join attempts were accepted with zero rejections or
allocation failures; pre-join history was 10. After bidirectional endpoint
readiness, the host released exactly sequences 0--9, represented by mask
`0x00000000000003ff`, and board history remained at the configured depth of 10.
The workload delivered 200/200 with zero publish failures, missed intervals, or
telemetry faults. Both validators passed and qdisc returned to the canonical
state. The firmware SHA-256 is
`490a14230825a43e1b96b63494f440c7dbd50f41c4eb4e1f7a7586028674f3d0` and the
host echo binary SHA-256 is
`aba87ddecafafeb2e51aff4204f244c6c69e9a235743e415f57ba9e5dc775f31`. The
25-file tree passed seal verification with tree SHA-256
`ea65b29f9fd8f268b015319eaa18152b64d5ecbf39823b3d01b71c2c2abe268c`.

The Volatile non-replay gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_durability_DSMV_85ab4d6_attempt01/`

It used the same cache depth, pre-join count, payload, rate, workload, network
profile, host binary, and deterministic startup protocol with VOLATILE
Durability. The marker wait was 7.082 seconds. All 10 pre-join attempts were
accepted and pre-join history was 10; after reader join, writer history was
zero, the host released zero probe replies, and the reply mask was
`0x0000000000000000`. The workload delivered 200/200 with zero publish
failures, missed intervals, or telemetry faults. Both validators passed and
qdisc returned to the canonical state. The firmware SHA-256 is
`81ff7800c43f45c9a1c587732a01ea7b4794483bb53e4e1a57d6f895adf20bdf`. The
25-file tree passed seal verification with tree SHA-256
`e3dec570ae0a0518611ea74e007ff0ee54abd0cc7748faf427502e7848e727f8`.

The execution contract may now classify History/Depth, Durability, Deadline,
Lifespan, and Resource Limits as `smoke_gate_passed_formal_blocked`.

## Remaining Gate

Durability formal collection remains blocked. These two clean probes verify
the late-join startup boundary and opposite replay outcomes, but they do not
freeze all formal late-join timing levels, the formal cache-depth estimand,
retry and replacement rules, or schedule-completeness acceptance. Liveliness
still lacks a family-specific performance smoke. The root formal gate and every
family formal gate remain false.

Energy remains `deferred_not_collected` under Amendment 01. These smokes support
no energy-use conclusion.
