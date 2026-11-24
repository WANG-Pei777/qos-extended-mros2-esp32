# Evaluation Scope and Native Baseline Amendment

Status: ACTIVE FOR EVALUATION DEVELOPMENT -- NO NEW FORMAL PERFORMANCE DATA

Recorded: 2026-07-23 (Asia/Tokyo)

## Reason

Supervisor feedback identified gaps between the implemented DDS/RTPS policies
and the breadth of the current evaluation language. A review of Hideki Takase's
mROS 2 studies also showed that the strongest comparison structure is:

`bounded requirement -> architecture mechanism -> user API -> same-workload
baseline -> end-to-end metric -> internal attribution -> bounded conclusion`

This amendment changes the evaluation boundary before Seven-QoS performance
collection. It does not alter or invalidate previously sealed deterministic
evidence.

## Research Boundary

The current contribution is described as:

> DDS/RTPS QoS configuration, protocol behavior, and controlled evaluation for
> mros2-esp on ESP32-S3.

The unqualified term "network QoS" is not used for the present result set.
Representative current captures use DSCP 0 and do not activate DiffServ
classification or priority queuing.

DiffServ is a separate optional network-layer extension. A broader claim would
require controlled DSCP classes, queue disciplines, congestion, and background
traffic. DDS/RTPS policy results remain valid without that extension, but their
scope is middleware behavior.

## User Profile and API Explanation

Each evaluated profile must be documented through the following chain:

`application requirement -> profile selection -> API validation -> Writer/Reader
configuration -> RTPS or local-state behavior -> application/telemetry/PCAP
evidence`

The user-facing table must state:

- public API field, default, valid values, and rejection behavior;
- Writer-side and Reader-side mapping;
- wire-level or local-state effect;
- unsupported combinations;
- representative scenario and reason for selecting the profile.

The minimum scenario set is:

| Scenario | Main requirement | Representative profile intent |
|---|---|---|
| Periodic telemetry | Prefer fresh samples and bounded latency | Best Effort, Keep Last, shallow depth, finite Lifespan |
| Command or alarm | Avoid silent loss | Reliable with bounded Deadline and Liveliness |
| Late-joining state | Deliver the latest state after joining | Transient Local with bounded cache depth |
| High-rate constrained stream | Bound CPU and memory pressure | Explicit depth and Resource Limits |

These are representative selection rules, not universal optimal profiles.

## Native ROS 2 Baseline

Two baseline levels are distinguished.

### Level A: single-host UDP engineering pilot

Two native ROS 2 processes run in WSL with:

- `rmw_fastrtps_cpp`;
- built-in transports disabled;
- the repository's explicit UDPv4 Fast DDS profile;
- one native RTT probe and one native echo process;
- a unique ROS domain and topic base;
- PCAP capture and per-message RTT sidecar.

This level validates workload semantics, QoS matching, timing, output parsing,
and PCAP extraction. It estimates a same-host native middleware/process floor.
It is excluded engineering evidence and is not a two-physical-host network
baseline.

### Level B: two-host native formal baseline

The matched cross-system comparison requires two physical native ROS 2 hosts or
an equivalent independently justified topology. It must retain the same:

- ROS 2 distribution, RMW implementation, and DDS transport profile;
- message type and exact serialized application payload size;
- Best Effort or Reliable setting;
- publish rate, target count, warm-up, grace period, and timeout;
- direction-specific impairment condition;
- timing boundary and run-level estimand;
- PCAP and environment capture procedure.

Native-to-native data cannot be pooled with ESP32 data unless these fields are
bound in the frozen comparison manifest.

## Controlled Loss Model

The current 5% and nominal 15% conditions are Linux `tc netem` random-loss
stress conditions. They are not measurements of natural Wi-Fi loss.

- `H2B` applies host egress impairment to traffic sent toward the board.
- `B2H` redirects board-source ingress traffic to IFB and applies impairment
  there.
- `0%` is the clean reference.
- `5%` is a moderate controlled stress level.
- nominal `15%` is a high controlled stress level intended to expose recovery
  and tail behavior without defining a natural deployment distribution.

Every result must report the configured model and observed effective drop
evidence. Conclusions are conditional on that model and direction.

## Expanded PCAP Evidence

Application logs establish outcomes. PCAP establishes the mechanism that
produced those outcomes. The extraction schema must include, where available:

- timestamp and frame length;
- source/destination address and UDP ports;
- DSCP value;
- flow direction;
- RTPS DATA, HEARTBEAT, and ACKNACK submessages;
- packet and byte counts;
- packet timing and jitter summaries;
- retransmission or repeated-sequence evidence;
- delivery reconciliation with application logs.

DSCP 0 must be reported explicitly rather than interpreted as an active
DiffServ class.

## Effect on Existing Evidence

- The sealed 48-case compatibility campaign remains accepted deterministic
  evidence.
- The sealed 36-claim mechanism campaign remains accepted deterministic
  evidence.
- Existing H2B and B2H direction evidence is not reclassified as single-endpoint
  testing.
- No Seven-QoS formal performance row has been accepted as of this amendment.
- The 51-cell, 1,530-run performance launch gate remains closed until runner
  bindings, acceptance oracles, storage checks, and a small discriminating pilot
  pass.
- Native Level A pilot results remain below `results/diagnostics`.
- Level B is required before a matched native-to-native cross-system conclusion.

## Energy Boundary

Energy remains deferred under
`ENERGY_DEFERMENT_AMENDMENT_20260721.md`. Current collection may evaluate RTT,
delivery, CPU, heap, stack margin, and wire behavior. It must not make an
energy-efficiency conclusion.

## Claim Form

Use:

> Under the tested ESP32-S3, ROS 2, Wi-Fi, workload, and direction-specific
> controlled-loss conditions, the observed effect was ...

Do not use universal statements such as "Reliable is always slower" or "History
does not matter."
