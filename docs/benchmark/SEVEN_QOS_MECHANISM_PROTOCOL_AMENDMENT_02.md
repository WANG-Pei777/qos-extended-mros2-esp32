# Seven-QoS Mechanism Protocol Amendment 02

## Status

This amendment must be committed before a new mechanism protocol is frozen.
It does not change the 36 deterministic claims, their expected outcomes, or
the rule that mechanism executions must not be pooled as performance samples.

## Reason

The 2026-07-20 mechanism implementation existed in a separate development
worktree. The corrected compatibility line at commit `fd5073e` fixed DDS
requested/offered matching and established a new source boundary. Mechanism
support is now migrated onto that line so compatibility and mechanism evidence
can be regenerated from one reviewable implementation.

## Source Changes

The migrated implementation adds or completes:

- bounded History and Resource Limit decisions with explicit publish outcome
  counters and immediate history-buffer ownership release;
- Volatile acknowledgement cleanup and Transient Local late-reader replay;
- wrap-safe Deadline, Lifespan, and automatic Liveliness state handling;
- callback registration and a periodic state monitor for reliable stateful
  endpoints;
- guarded DATA_FRAG transmission and bounded receive-side reassembly;
- deterministic template generation and a dedicated ESP32-S3 mechanism
  harness;
- host-probe controls for delayed sending, exact receive counts,
  impairment release gates, and per-message byte/hash evidence;
- a time-bounded initial Wi-Fi connection gate.

The current configured unicast fallback and send-success sequence advancement
remain in both writer paths. They are not replaced by the older multicast-only
fallback behavior.

## Evidence Separation

The sealed 2026-07-20 mechanism results remain historical pilot evidence tied
to their original manifests and binaries. They are not combined with the new
campaign. The new source line requires fresh static tests, ESP32-S3 builds,
excluded hardware smoke, protocol freeze, deterministic execution, audit, and
result-tree seals.

The corrected compatibility campaign at commit `fd5073e` remains a separate
pre-migration result. After mechanism integration, the 48 compatibility cases
must also be rerun on the final mechanism commit before reporting one combined
84-claim functional result.

## Measurement Boundary

This amendment covers deterministic compatibility and mechanism behavior only.
It does not add latency, delivery-rate, CPU, heap, stack, wire-efficiency, or
energy conclusions. Energy remains a deferred secondary metric and does not
block this deterministic stage.
