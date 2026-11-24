# Seven-QoS Mechanism Protocol Amendment 04

## Status

This amendment applies to the next same-commit compatibility and mechanism
protocols derived from parent commit `a99d449`. It does not change the 48
compatibility claims, the 36 mechanism claims, or their expected outcomes.

## Trigger

The host probe extension introduced after the corrected compatibility line
allowed an expected-match subscriber to finish after its post-match interval
without first satisfying its receive goal. The compatibility board publisher
intentionally waits through its complete discovery window before publishing.
The host subscriber could therefore exit immediately before the first board
sample and report `matched=1, rx=0`.

The following diagnostic roots retain the resulting failures and are excluded
from accepted evidence:

- `results/validation/20260722_seven_qos_samecommit_smoke/`
- `results/validation/20260722_seven_qos_samecommit_diagnostics/`
- `results/validation/20260723_seven_qos_samecommit_diagnostics/`

## Cross-Check

The frozen compatibility firmware from the earlier accepted code line failed
when paired with the extended host probe, then passed on the same network when
paired with its frozen host probe:

- extended host probe: `results/validation/20260723_seven_qos_environment_ab/CMP-REL-b2h-remote-first-p4-frozen-30e4e0b-current-network/`;
- frozen host probe: `results/validation/20260723_seven_qos_environment_ab/CMP-REL-b2h-remote-first-p4-frozen-30e4e0b-old-host-probe/`.

After correcting the completion condition, the frozen firmware and the current
source firmware both passed on the same network:

- `results/validation/20260723_seven_qos_host_probe_fix/CMP-REL-b2h-remote-first-p4-frozen-30e4e0b-fixed-host-probe/`;
- `results/validation/20260723_seven_qos_host_probe_fix/CMP-REL-b2h-remote-first-p4-a99d449-current-source-fixed-host/`.

This A/B sequence identifies the host completion gate, rather than the board
writer or the network, as the cause of the false negative.

## Replacement Gate

For an expected-match host subscriber, early completion now requires both the
post-match interval and the receive goal. An explicit expected receive count
requires exact equality; the default compatibility mode requires at least one
received sample. The global wait limit remains an upper bound and can no longer
be overwritten by the post-match branch.

The compatibility board probe also records whether each publish call was
accepted together with publish attempts, accepted publishes, history samples,
history bytes, resource-limit rejections, and allocation failures. These
markers distinguish application acceptance from peer delivery.

A static gate protects the host receive-goal completion condition. The host
probe must be rebuilt before all replacement smoke and formal executions.

## Evidence Boundary

The commit containing this amendment requires a new 16-case compatibility
smoke, an eight-case mechanism smoke, replacement frozen protocols, and new
formal campaign, audit, analysis, and seal roots. Diagnostic failures remain
immutable and cannot supply accepted executions. Existing sealed campaigns
remain valid only for their recorded code lines and are not pooled with the
replacement same-commit result.

Energy remains a deferred secondary metric and is outside this deterministic
stage.
