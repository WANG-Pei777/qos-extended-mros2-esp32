# Seven-QoS Formal Evaluation

Status: DRAFT -- planned evidence only
Drafted: 2026-07-16
Primary statistical unit: one independently reset hardware run

## Claim Gate

Current defensible wording:

> The system formally evaluates Reliability and History/Depth and provides
> implementation and hardware-functional validation for five additional QoS policy
> families.

Only after this protocol is frozen, executed, audited, analyzed, and sealed may the
paper say that the project systematically evaluated seven QoS policy families.

## Design Principle

Do not construct a full factorial across all policies and parameters. Each policy
family receives one mechanism-centered performance experiment:

1. vary each mechanism parameter along a frozen anchor path;
2. add only a small number of prespecified interaction corners;
3. target N=30 independent runs for every random performance cell;
4. randomize/interleave cells in complete blocks;
5. keep deterministic compatibility, event, and state-machine checks in separate
   result trees with pass/fail criteria.

Individual messages, deadline events, and state transitions are nested evidence,
not statistical replicates.

The concrete entity direction and fixed background policies are defined by
`SEVEN_QOS_IMPLEMENTATION_READINESS_AUDIT.md`. The new mechanism studies use the
RELIABLE Stateful path unless Reliability itself is the factor.

## Randomization and Sparse Interaction Estimands

Randomize each policy family separately. The provisional schedule uses ten
complete visits per family, with every cell appearing once per visit and three
independently reset accepted runs collected at that appearance. This yields N=30
per cell while interleaving cells across the full collection window. Rejected
attempts remain in the ledger and do not change the prespecified cell order.

For a corner that changes `k` factors away from the anchor, define its sparse
non-additivity estimand as:

```text
I_corner = mean(corner)
           - sum(mean(each matching one-factor main cell))
           + (k - 1) * mean(anchor)
```

Use risk-difference scale for fractions/count-normalized outcomes and log scale for
strictly positive latency, wire-cost, resource, and energy outcomes. Bootstrap the
complete run-level contrast rather than treating messages as replicates. A corner
supports only this prespecified departure-from-additivity claim; it does not support
a claim about the unmeasured full interaction surface.

## 1. Reliability

Mechanism experiment: Reliability x loss x direction.

The existing Round 4 formal matrix already contains Best Effort and Reliable at
0%, 1%, 5%, 10%, and 15% nominal loss in H2B and B2H directions with N=30 per cell.
P4 adds a same-hardware independent-window replication at common B2H cells. These
sealed results may satisfy this family without rerunning when the final Seven-QoS
manifest binds their exact semantics and hashes.

Primary outcomes: delivery and run-level application RTT p95. Secondary outcomes:
wire overhead, recovery burden, duplicate amplification, CPU, memory, and energy
when newly instrumented cells are available.

Deterministic validation remains separate: Best Effort/Reliable compatibility,
intentional QoS mismatch, ACKNACK/repair state transitions, duplicate suppression,
and reset/participant-epoch handling.

## 2. History/Depth

Mechanism experiment: History/Depth x burst size x loss.

Direction: B2H, exercising the ESP32 StatefulWriter. Fix History=KEEP_LAST,
payload=64 bytes, and compile-time cache capacity=40 across all cells.

Provisional levels:

- depth: 5, 20, 40;
- application burst size: 1, 10, 40 messages;
- independent random loss: 0%, 5%, 15%;
- anchor: depth 20, burst 10, loss 5%.

Use nine prespecified performance cells rather than all 27 combinations:

- depth main path: `(5,10,5)`, `(20,10,5)`, `(40,10,5)`;
- burst main path: `(20,1,5)`, `(20,40,5)`;
- loss main path: `(20,10,0)`, `(20,10,15)`;
- interaction corners: `(5,40,15)`, `(40,40,15)`.

Target: 9 cells, 270 accepted runs.

Primary outcomes: delivered fraction per burst, unresolved samples, run-level RTT
p95, and overflow/eviction count. Secondary: DATA/ACKNACK amplification, CPU,
peak heap, stack margin, and energy per delivery.

The existing Round 6 Depth x HEARTBEAT result remains formal History evidence but
does not replace this burst-size x loss mechanism experiment.

Deterministic validation: KEEP_LAST eviction order, KEEP_ALL boundary behavior,
history exhaustion, duplicate sequence handling, and no out-of-bounds state.

## 3. Durability

Mechanism experiment: Durability x late-join delay x cache depth.

Direction: B2H, exercising ESP32 transient-local replay to a late-starting host
reader. Fix Reliability=RELIABLE, payload=64 bytes, and cache capacity=40.

Provisional levels:

- durability: Volatile, Transient Local;
- late-join delay: 0, 2, 10 s;
- cache depth: 1, 10, 40;
- anchor cache depth: 10.

Use eight performance cells:

- both durability modes at each 0/2/10 s delay with depth 10 (six cells);
- Transient Local at 10 s delay with depths 1 and 40 (two interaction cells).

Target: 8 cells, 240 accepted runs.

Primary outcomes: eligible historical samples delivered to the late joiner, first
historical-sample latency, cache-drain completion time, and online delivery after
join. Secondary: CPU, heap, stack, wire bytes, and energy.

Deterministic validation: Volatile sends no pre-join samples, Transient Local cache
order and depth are correct, expired/restarted epochs are not replayed, and late
join callbacks transition exactly as specified.

## 4. Deadline

Mechanism experiment: Deadline x publish period x network delay.

Direction: H2B, exercising the ESP32 StatefulReader deadline monitor. Apply delay
only on ingress to the board and record the board polling interval.

Provisional levels:

- deadline: disabled, 50, 100, 500 ms;
- publish period: 20, 100 ms;
- injected one-way delay: 0, 50 ms;
- anchor: deadline 100 ms, period 100 ms, delay 0.

Use nine performance cells:

- deadline 50/100/500 ms at period 100 ms and delay 0;
- period 20 ms at deadline 100 ms and delay 0;
- delay 50 ms at deadline 100 ms and period 100 ms;
- interaction corners `(50,100,50)`, `(100,20,50)`, and `(500,20,50)`;
- one disabled-deadline baseline at period 100 ms and delay 0.

Target: 9 cells, 270 accepted runs.

Primary outcomes: run-level deadline-miss fraction under the configured policy,
delivery, and application RTT p95. Deadline-policy events are not inferred from the
existing exploratory 100 ms application threshold.

Deterministic validation: event timing, no false event before the deadline, exactly
defined repeated-miss behavior, recovery after a timely sample, and publisher/
subscriber compatibility.

## 5. Lifespan

Mechanism experiment: Lifespan x injected delay.

Direction: B2H, exercising the ESP32 StatefulWriter. The injected delay is a
measured board-side pre-transmit release hold; post-transmit `tc` delay is not a
substitute for this mechanism experiment.

Provisional levels:

- lifespan: disabled, 50, 200, 1000 ms;
- injected board-side release delay: 0, 100, 300 ms;
- anchor: lifespan 200 ms, delay 100 ms.

Use eight performance cells:

- all four lifespan settings at delay 100 ms;
- lifespan 200 ms at delays 0 and 300 ms;
- interaction corners lifespan 50/300 ms and 1000/300 ms.

Target: 8 cells, 240 accepted runs.

Primary outcomes: timely delivered fraction, expired-sample fraction, delivery, and
run-level application RTT p95 among received samples. Secondary outcomes include
wire cost, CPU, heap, and energy.

Deterministic validation: samples on each side of the expiry boundary, no callback
for expired data, no stale delivery after reconnect, and correct disabled-policy
behavior.

## 6. Liveliness

Mechanism experiment: Liveliness lease x outage duration.

Direction: H2B, exercising the ESP32 StatefulReader. Fix the writer HEARTBEAT
period at no more than 100 ms and apply the outage only on ingress to the board.

Provisional levels:

- lease: 0.5, 2, 5 s;
- controlled outage: 0.25, 1, 3, 6 s;
- anchor: lease 2 s, outage 1 s.

Use eight performance cells:

- all three lease values at outage 1 s;
- lease 2 s at outages 0.25, 3, and 6 s;
- interaction corners lease 0.5/outage 3 s and lease 5/outage 6 s.

Target: 8 cells, 240 accepted runs.

Primary outcomes: liveliness-loss detection latency, post-outage recovery latency,
delivery before/after outage, and false-loss count. Secondary: CPU, network control
traffic, heap, and energy.

Deterministic validation: lease boundary behavior, loss and recovery callback
ordering, no duplicate transition, automatic/manual assertion compatibility where
implemented, and reset cleanup.

## 7. Resource Limits

Mechanism experiment: Resource limit x payload x publish rate.

Direction: B2H, exercising the ESP32 StatefulWriter. Fix Reliability=RELIABLE,
History=KEEP_ALL, compile-time capacity=100, and a nonbinding byte limit. Every
cell includes the same prespecified ACK-suppression episode so the sample limit can
bind; max-bytes enforcement is a separate deterministic case.

Provisional levels:

- resource limit: 5, 20, 100 samples;
- payload: 64, 512, 2048 bytes;
- publish rate: 10, 50, 100 Hz;
- anchor: limit 20, payload 512 bytes, rate 50 Hz.

Use nine performance cells:

- all three limits at the anchor payload/rate;
- payload 64 and 2048 at limit 20/rate 50;
- rate 10 and 100 at limit 20/payload 512;
- interaction corners `(5,2048,100)` and `(100,2048,100)`.

Target: 9 cells, 270 accepted runs. These cells cannot be shared with the current
clean-network Stage W workload surface because the fixed KEEP_ALL and ACK-
suppression semantics differ.

Primary outcomes: delivery, overflow/rejection fraction, run-level RTT p95, peak
heap consumption, minimum stack margin, and mean CPU. Energy per successful
delivery is primary once the external monitor gate passes.

Deterministic validation: exact limit boundary, defined rejection/eviction behavior,
allocation-failure handling, no memory corruption, and recovery after pressure is
removed.

## Performance and Deterministic Evidence Separation

Random performance campaigns use randomized complete blocks, N=30 per cell,
instrumentation-only acceptance, immutable rejection ledgers, run-level summaries,
10,000 run-cluster bootstrap resamples, and prespecified multiplicity families.

Deterministic validation campaigns use frozen event sequences and explicit expected
state transitions. They report cases passed/total and exact failure traces. Repeating
a deterministic case does not create performance N and is never pooled with the
random campaigns.

The machine-readable deterministic draft is
`seven_qos_deterministic_cases_draft.json`. It currently expands to 48 requested/
offered compatibility cases across both directions and both endpoint creation
orders, plus 36 mechanism/state cases. Case count is not replication and is not a
performance sample size.

Validate both draft manifests and all sparse corner paths with:

```bash
python3 scripts/experiment/validate_seven_qos_protocol.py
```

## Provisional Run Budget

Reliability uses already sealed formal evidence subject to an exact semantic/hash
binding audit. The six new mechanism experiments above contain 51 provisional cells,
or 1,530 accepted runs at N=30. Together with the separate 1,740-run resource,
workload, impairment, and three-system extension, the current protocol budget is
3,270 new accepted runs after H2B. This is a sparse mechanism design, not a
seven-policy full factorial.

Cell levels and interaction corners remain draft until firmware feasibility, event
semantics, impairment efficacy, runtime, storage, and power-monitor pilots pass. Any
change must occur before formal collection and be recorded in the final
preregistration.

The 1,530-run performance collection does not start until the common external power
monitor and marker gate passes. Deterministic cases and development pilots may run
earlier but remain in separate trees and cannot be promoted later.

## Required Release Artifacts

Each policy family receives a design manifest, randomized schedule, deterministic
case manifest, exact firmware/host hashes, smoke report, acceptance ledger, raw
serial/host logs, PCAP and impairment state where relevant, resource/energy traces,
formal audit, run-level analysis, and a deterministic tree seal. Cross-policy claims
are generated only after all seven family-level audits pass.
