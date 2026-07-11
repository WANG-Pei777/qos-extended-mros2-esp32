# ROUND4 Top-Tier Evidence Protocol

## Claim Boundary

The primary paper claim is transport behavior of QoS policies under controlled
RTPS/UDP impairment. It requires packet capture and a transport-layer loss
mechanism. `echo_node_lossy` is retained only as an application-reply-loss
control; it must never be described as network loss, RTPS loss, or evidence of
DDS retransmission.

## Frozen Experimental Unit

One experimental unit is one board reset, one host echo process, one 75-second
serial capture, one CSV row, and its paired host/serial logs. Formal units must
have all of the following:

- a clean committed worktree and a recorded commit hash;
- explicit board firmware mode, the SHA-256 of the flashed firmware binary,
  and matching host QoS mode;
- accepted link-quality gate values;
- endpoint matching in both directions;
- nonzero TX, RX, and RTT sample counts;
- a raw serial log and a raw host log; and
- a per-condition manifest with file checksums.

Rows that fail a gate are retained as failures in the raw archive. They are not
silently deleted or replaced.

## Primary Matrix

The primary transport experiment is a blocked factorial matrix:

| Factor | Levels |
|---|---|
| Board and host QoS | RELIABLE, BEST_EFFORT |
| Transport impairment | 0, 1, 5, 10, 15 percent |
| Loss direction | host-to-board, board-to-host |
| Repetitions | at least 30 accepted units per cell |

The 30-run minimum is a floor, not a power justification. Before formal data
collection, run a 10-unit clean pilot for each QoS arm at 0 and 15 percent and
compute the final N from the observed RTT variance and the predeclared minimum
effect of interest. If the calculation exceeds 30, collect the larger N.

QoS arms are interleaved in blocks. A block contains one loss level and a fixed
number of repetitions. Board firmware may only change between blocks, and each
switch must be recorded in the firmware ledger with the source hash, binary
hash, flash time, and operator confirmation.

## Transport Evidence

Each formal transport condition must use `tc netem` or an equivalently
documented network impairment mechanism. A pcapng capture starts before the
first board reset and stops after the final host process exits. The capture must
be retained with a SHA-256 checksum.

For every QoS mode and direction, inspect at least one zero-loss and one
15-percent capture for RTPS DATA, HEARTBEAT, and ACKNACK traffic. Any claim
about retransmission, packet overhead, discovery traffic, or wire timing must
cite this capture. Directional experiments must be reported as directional.

## Outcomes And Statistics

Primary outcomes are delivery ratio, RTT median, RTT 95th percentile, and
matched-endpoint rate. Secondary outcomes are retransmission/RTPS control
traffic from pcap, board resource usage, and recovery time after reset.

Report each condition with raw N, median, mean, standard deviation, 95 percent
confidence interval, and all exclusions. Compare QoS modes with effect sizes
and confidence intervals, not only p-values. Block and collection time are
recorded as covariates. No outlier removal is allowed except for prespecified
gate failures, which remain visible in the raw-data ledger.

## Comparator And Stability Claims

Do not claim a three-system comparison until upstream mros2-esp32 and micro-ROS
use matched message semantics, payload size, QoS, impairment, and repetition
counts. Do not claim reset-storm stability until E3 has a documented resource
configuration and completed pre-fix/post-fix evidence.

## Release Package

The paper artifact contains source commit(s), build instructions, firmware
ledger, raw CSV/log/pcap archives, manifests with checksums, analysis scripts,
figure-generation scripts, and a claim-to-evidence table. A fresh environment
must be able to regenerate every table and figure from the raw archive.

Run `validate_round4.py` on every formal CSV before analysis. Then run
`summarize_round4.py` over the validated CSVs to generate the condition table
and QoS effect-size table. The summarizer uses a recorded seed and percentile
bootstrap confidence intervals, so it must be invoked with the same resample
count and seed for a release build.
