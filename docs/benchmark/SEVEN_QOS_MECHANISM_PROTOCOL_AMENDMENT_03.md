# Seven-QoS Mechanism Protocol Amendment 03

## Status

This amendment replaces Amendment 02 for the next mechanism protocol. It does
not change the 36 deterministic claims, their expected outcomes, or their
unit/hardware assignment.

## Trigger

The protocol frozen on commit `ff57906` used a clean qdisc snapshot with an
`mq` root and `pfifo_fast` child queues. During the first
`HIST-DUP-ONCE` attempt, the configured netem behavior completed and both
endpoint validations passed. Removing the root netem qdisc caused Linux to
recreate the child queues as `fq_codel`. Exact restoration validation failed,
and the campaign stopped before a second attempt.

The interrupted protocol and campaign remain immutable diagnostic evidence.
They are not resumed or pooled with the replacement campaign.

## Replacement Gate

Before environment capture, campaign validation, and every hardware attempt,
the runner now requires a clean `mq` interface and normalizes legacy
`pfifo_fast` child queues to the kernel's stable `fq_codel` baseline. Any
pre-existing netem, ingress, or clsact state is rejected. Unknown clean qdisc
layouts are also rejected rather than silently rewritten.

Before the frozen board-neighbor snapshot and every campaign environment
check, one bounded ICMP probe refreshes the operating system's neighbor cache.
This gate traffic occurs before packet capture and measurement; it is used only
to make the frozen board MAC check independent of ARP cache expiry.

The excluded pre-freeze smoke set is expanded from seven to eight cases by
adding `HIST-DUP-ONCE`. Its smoke evidence must show:

- the expected duplicate impairment was installed;
- host and board behavior passed;
- the final qdisc text exactly equals the normalized pre-attempt text; and
- no impairment qdisc remains.

## Evidence Boundary

A new source commit, eight-case smoke tree, protocol identifier, campaign
identifier, audit, analysis, and release seals are required. The Amendment 02
protocol and its incomplete campaign cannot supply accepted executions to the
replacement result.

Energy remains a deferred secondary metric and is outside this deterministic
stage.
