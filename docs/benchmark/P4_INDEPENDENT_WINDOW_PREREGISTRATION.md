# P4 Independent-Window Replication Preregistration

**Status:** FROZEN BEFORE DATA COLLECTION

**Earliest collection date:** 2026-07-15 (Asia/Tokyo)

P4 is a temporal/network-window replication of the key Round 4 board-to-host
QoS result. It is not an external-hardware replication and must not be described
as one. No Round 6 formal run may be reused in P4.

## Window Independence Gate

Before collection:

1. Start a new WSL/network session on or after the earliest date above.
2. Re-associate or restart the AP/board network path and record host/board IPs.
3. Confirm no ingress qdisc, stale host process, or previous capture process.
4. Pass three exact-binary smoke runs for each QoS firmware.
5. Record the new window start time and link-health distribution.

If these conditions are not met, the run is a same-window pilot and cannot be
used as P4 replication evidence.

## Frozen Design

| Factor | Levels |
| --- | --- |
| QoS | RELIABLE, BEST_EFFORT |
| Board-to-host nominal loss target | 0%, 5%, 15% |
| Accepted independent runs | 30 per cell |
| Randomization | 10 superblocks; all 6 cells once per block; 3 runs per visit |
| Random seed | `20260715` |

The 5% condition uses `gact` denominator 20 (exact configured probability 5%).
The nominal 15% condition uses denominator 7 (configured probability
14.285714%). Labels and analysis must report nominal and configured values.

Both QoS variants freeze these mechanism controls:

- runtime KEEP_LAST depth 5
- compile-time stateful history capacity 10
- heartbeat period 4,000 ms
- publisher `max_samples` 30
- publisher `max_bytes` 65,536

This restores the Round 4 mechanism settings rather than reusing the Round 6
capacity-48 intervention. Both variants must be reproducibly built from one
clean commit, archived by SHA-256, and differ in the intended QoS compile flag.

## Replication Hypotheses

- **R1:** At 5% and 15% board-to-host impairment, RELIABLE has a higher
  per-message RTT p95 than BEST_EFFORT.
- **R2:** At the nominal 15% target, RELIABLE does not improve delivery over
  BEST_EFFORT; the prespecified directional check is RELIABLE minus BEST_EFFORT
  less than or equal to zero.
- **R3:** The large nonzero-loss RTT-tail direction is absent or materially
  smaller at 0% impairment.

## Outcomes And Acceptance

Primary run-level outcomes are per-message RTT p95 and delivery ratio. Secondary
outcomes are RTT median/p99, endpoint match time, RTPS DATA/HEARTBEAT/ACKNACK
counts, and observed `gact` drop rate.

Acceptance is instrumentation-only: clean harness, exact firmware/configuration,
matched endpoints, complete behavior phase, valid sidecar, nonempty board-source
UDP capture, and hashed `tc` state. Delivery and RTT values are never acceptance
criteria. Every exclusion and replacement remains in the ledger.

## Frozen Analysis

- Runs are independent units; message-tail uncertainty resamples whole runs.
- Report all six cells with N, effect size, and 95% run-cluster bootstrap CI.
- Compare RELIABLE minus BEST_EFFORT at each loss target for both primary
  outcomes (six confirmatory contrasts total).
- Use exact block sign-flip randomization tests and Holm correction across the
  six-confirmatory-contrast family.
- Replication succeeds only if R1 has the same direction at both 5% and 15%,
  with the 15% RTT contrast confidence interval excluding zero. R2 and R3 are
  reported regardless of significance.

## Claim Boundary

P4 can support temporal/network-window reproducibility on the same ESP32,
mROS2, ROS 2, AP class, and directional impairment design. It cannot establish
cross-hardware, cross-site, or general DDS reproducibility. Any configuration or
source difference from Round 4 must be listed beside the comparison.

## Frozen Execution Entry Points

The P4 firmware set is archived at
`results/experiments/20260714_p4_firmware_set_c9489da`. On or after the earliest
collection date, open the independent window with
`scripts/experiment/run_p4_smoke_gates.py`; formal collection is then performed
by `scripts/experiment/run_p4_formal.py` against the resulting
`window_manifest.json`. Both executors fail closed on a dirty worktree, stale
impairment qdisc, firmware or host-binary hash mismatch, WSL-session change, or
an incomplete six-run smoke gate.

After all 180 accepted runs are complete, `audit_p4_formal.py` must report
`PASS` before either analysis entry point runs. `analyze_p4_complete.py`
implements the frozen six-contrast confirmatory family and publication figure;
`analyze_p4_wire.py` extracts the prespecified RTPS packet counts as secondary,
capture-hook evidence with an explicit mechanism-claim boundary.
