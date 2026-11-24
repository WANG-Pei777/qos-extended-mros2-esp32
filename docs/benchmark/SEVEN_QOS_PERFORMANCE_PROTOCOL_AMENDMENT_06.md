# Seven-QoS Performance Protocol Amendment 06

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the History/Depth KEEP_LAST burst harness and its
same-commit HSM05/HSM20 hardware gates. It preserves all earlier evidence
boundaries and does not collect or accept any row from the frozen 51-cell,
1,530-run schedule.

## History/Depth Harness

Commit `480565866a20797a6e9cbbac61142477c1563930` adds a History/Depth family
mode with a constant RTPS history capacity of 40 and runtime KEEP_LAST depth.
A bounded pre-window board burst is held before transmission. The harness
records attempts, acceptance, rejection, allocation failures, history peak,
history after release, unique replies, and a 64-bit reply mask.

For a burst larger than depth, the oracle requires the exact newest sequence
suffix rather than only a reply count. For a burst within depth, it requires
the complete sequence set. Both paths require history drain before the normal
telemetry workload.

The development run is retained at:

`results/diagnostics/20260723_seven_qos_performance_history_HSM05_dev_attempt01/`

It used a dirty build only to verify compilation and the first board-side mask.
It passed its diagnostic checks but is not sealed or accepted as a same-commit
smoke.

## Same-Commit History/Depth Gates

The depth-five eviction gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_history_HSM05_4805658_attempt01/`

Configuration: RELIABLE, VOLATILE, KEEP_LAST, capacity 40, runtime depth 5,
64-byte payload, burst size 10, 10 Hz workload, and clean network profile. All
10 burst attempts were accepted with zero rejections or allocation failures.
History peaked at five; after release, the host returned exactly sequences
5--9, represented by mask `0x00000000000003e0`, and board history drained to
zero. The workload delivered 200/200 with zero publish failures, missed
intervals, or telemetry faults. Both validators passed and qdisc returned to
the canonical state. The firmware SHA-256 is
`efc5ff00fc1a712e4a21311344175d1a9b24224b080e85ecbeac5553a0f3f163`.
The 25-file tree passed seal verification with tree SHA-256
`e52096f3f9ca5c4a1fd4022db797cfd5d75f4aaef2a8b020ea4a4caff3d334d1`.

The depth-twenty complete-burst gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_history_HSM20_4805658_attempt01/`

It used the same capacity, payload, burst, workload, and network profile with
runtime depth 20. All 10 burst attempts were accepted; history peaked at 10;
the host returned sequences 0--9 with mask `0x00000000000003ff`; and history
drained to zero. The workload delivered 200/200 with zero publish failures,
missed intervals, or telemetry faults. Both validators passed and qdisc
returned to the canonical state. The firmware SHA-256 is
`29b45b6183f728e6028d7e9ac333f66c99b86b2ef3c9984116c955cd51f23192`.
The 25-file tree passed seal verification with tree SHA-256
`a5fefedf2d4f5f5b064f9c3231f18cd5ac96046094f6a33ccdc2c58033d501a9`.

The execution contract may now classify History/Depth, Deadline, Lifespan,
and Resource Limits as `smoke_gate_passed_formal_blocked`.

## Remaining Gate

History/Depth formal collection remains blocked. These clean pre-window probes
verify KEEP_LAST retention and release but do not implement or freeze the
required B2H host-ingress loss, ingress-loss efficacy oracle, per-burst formal
estimand, retry ledger, or schedule-completeness gate. Durability and Liveliness
still lack family-specific performance smokes. The root formal gate and every
family formal gate remain false.

Energy remains `deferred_not_collected` under Amendment 01. These smokes support
no energy-use conclusion.
