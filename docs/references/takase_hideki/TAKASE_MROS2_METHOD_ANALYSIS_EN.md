# Method Analysis of Hideki Takase's mROS 2 Studies

## Purpose

This note analyzes how the mROS 2 studies define their scope, connect design
requirements to implementation, expose user-facing APIs, and construct
controlled evaluations. It then translates those methods into concrete changes
for the `qos-extended-mros2-esp32` project.

The central lesson is methodological: start from a small number of explicit
requirements, map each requirement to an implementation mechanism and a
measurable outcome, and compare systems under the same workload. A large test
matrix is useful only after that argument is fixed.

## Source Inventory

| ID | Source | Local copy | Official record |
|---|---|---|---|
| T1 | *mROS 2: A Lightweight Runtime Environment of ROS 2 Nodes for Embedded Devices* (2022) | `sources/2022_mros2_lightweight_runtime.pdf` | [IPSJ](https://ipsj.ixsq.nii.ac.jp/records/217257) |
| T2 | *Communication Processing Method for Arbitrary-Type Messages in mROS 2* (2022, Japanese) | `sources/2022_mros2_arbitrary_message_types.pdf` | [IPSJ](https://ipsj.ixsq.nii.ac.jp/records/217258) |
| T3 | *An Implementation and an Evaluation of mros2-posix* (2023) | `sources/2023_mros2_posix_evaluation.pdf` | [J-STAGE](https://www.jstage.jst.go.jp/article/jrsj/41/8/41_41_724/_article/-char/ja) |
| T4 | *Platform Technology for Robot Systems and Its Expansion to Embedded/IoT Computing* (2023, Japanese) | `sources/2023_robot_platform_embedded_iot_review.pdf` | [J-STAGE](https://www.jstage.jst.go.jp/article/isciesci/67/12/67_500/_article/-char/ja) |
| T5 | *Quantitative Evaluation of ROS 2 Node Runtime Environments for Embedded Systems* (2022, Japanese) | Not downloaded because the official full text requires authenticated access | [J-STAGE](https://www.jstage.jst.go.jp/article/jsmermd/2022/0/2022_1P1-Q09/_article/-char/ja) |

The downloaded files are local research references. They are ignored by the
repository's `docs/**/*.pdf` rule and should not be redistributed through the
public repository without checking the source license.

## How the Studies Build Their Argument

### 1. Define the system boundary before evaluating it

T1 begins with concrete requirements rather than a broad claim:

- direct RTPS communication without a mediation agent;
- no dependency on a general-purpose OS or its system calls;
- execution on an RTOS with priority-based scheduling;
- lightweight C/C++ communication components;
- operation on medium-class embedded hardware;
- an API that preserves the basic `rclcpp` programming model.

The initial feature boundary is also explicit. The study evaluates asynchronous
topic-based publish/subscribe and a limited message/API set. It identifies
arbitrary message types and additional features as later work.

**Implication for this project:** describe the contribution as **DDS/RTPS QoS
configuration and mechanism evaluation for mros2-esp on ESP32-S3**. Do not use
unqualified "network QoS" unless IP-layer mechanisms such as DSCP classification,
queuing, and congestion handling are also implemented and evaluated.

### 2. Map every requirement to a visible mechanism

T1 maps its requirements to a concrete stack:

`mROS 2 API -> mROS 2 communication library -> embeddedRTPS -> lwIP -> RTOS/HAL`

It then explains the writer and reader execution paths. For example, reception
is split between a high-priority reader task, RTPS parsing/deserialization, and
the user callback task. This makes later performance claims traceable to an
architecture choice.

T2 uses the same pattern for arbitrary message types:

1. identify the user-visible limitation;
2. separate type-independent processing from type-specific processing;
3. generate type-specific serialization code from message definitions;
4. expose the result through a ROS 2-like programming model;
5. evaluate latency, internal processing time, and program size.

**Implication for this project:** the QoS explanation should show this complete
chain:

`application requirement -> profile selection -> API validation -> Writer/Reader
configuration -> RTPS behavior -> observable application and PCAP evidence`

The current Seven-QoS implementation is not explained fully by listing policy
names. The user needs to see why a profile exists, how it is selected, which
values are accepted or rejected, and what protocol behavior it changes.

### 3. Preserve the user's programming model without claiming full equivalence

T1 presents API compatibility as a way to reduce learning and porting cost. Its
early publisher/subscriber API resembles `rclcpp`, but only exposes functionality
supported by the embedded runtime. The early QoS argument is limited mainly to
a history-depth value; it is not a Seven-QoS profile design.

**Implication for this project:** use the same conservative language. State
which `rclcpp` concepts are preserved and provide a policy-by-policy support
table with:

- public API field and valid range;
- default value;
- validation behavior;
- Writer-side and Reader-side mapping;
- RTPS or local-state effect;
- unsupported combinations and failure behavior.

### 4. Use a native-to-native baseline under the same workload

T1 evaluates a 32-bit integer echo workload. The host publishes one message per
second for 200 trials and measures host-side RTT with
`std::chrono::high_resolution_clock`. Four environments are compared over wired
Ethernet, including native ROS 2 to native ROS 2, two micro-ROS Agent placements,
and direct mROS 2.

T3 strengthens this design. It uses a String echo workload at 100 ms intervals,
varies String length from 1 to 64 bytes, performs 1,000 trials per condition, and
evaluates all four placements of native ROS 2 and mros2-posix nodes. The hardware,
compiler, transport, workload, and measurement point are held constant.

For the 8-byte String condition in T3, the reported mean RTT values are:

| pub/sub runtime | echo runtime | Mean RTT (ms) | Standard deviation (ms) |
|---|---|---:|---:|
| ROS 2 | ROS 2 | 0.802 | 0.038 |
| ROS 2 | mros2-posix | 0.722 | 0.035 |
| mros2-posix | ROS 2 | 0.699 | 0.038 |
| mros2-posix | mros2-posix | 0.608 | 0.021 |

These values are evidence for that specific testbed, not universal runtime
ordering.

**Implication for this project:** add a genuine native ROS 2-to-native ROS 2
baseline. The existing native echo endpoint is not sufficient. The baseline and
ESP32 conditions must use the same:

- payload definition and size;
- publish rate and accepted-run rule;
- Reliability/History/depth configuration;
- direction-specific impairment model;
- timing boundary and clock source;
- warm-up, timeout, and retry policy;
- application outcome and PCAP extraction procedure.

### 5. Attribute end-to-end differences with internal measurements

T2 first measures end-to-end communication delay, then records timestamps at
multiple points inside the embedded node. For the Twist workload, the proposed
method reports approximately 23.92 microseconds of embedded-node processing,
compared with approximately 96--97 microseconds for the two earlier versions.
The study also reports whole-program and application-only binary sizes.

This decomposition distinguishes implementation cost from network and host-side
cost. It prevents an end-to-end RTT difference from being assigned to the wrong
mechanism.

**Implication for this project:** retain three evidence layers:

1. application logs for delivery, timeout, order, and end-to-end latency;
2. board telemetry for CPU, heap, stack high-watermark, state transitions, and
   repair counters;
3. PCAP evidence for DATA, HEARTBEAT, ACKNACK, retransmission, packet size,
   byte volume, flow direction, timing, jitter, and DSCP.

No one layer substitutes for the others.

### 6. Connect the runtime to a realistic control workload

T4 describes a two-board inverted-pendulum example. One embedded node publishes
IMU measurements; another subscribes, computes PWM control, and publishes the
response. Both boards use mros2-mbed, and communication operates at about
100 Hz. This example gives the runtime a concrete application context without
turning every evaluation into a complete robot-system study.

**Implication for this project:** define representative application profiles
before expanding the formal matrix:

| Profile | Intended requirement | Representative workload | Primary policies |
|---|---|---|---|
| Low-latency telemetry | Fresh data is more important than recovery of old samples | periodic sensor stream | Best Effort, Keep Last, shallow depth, finite Lifespan |
| Reliable command/event | Missing a command is unacceptable | sparse command or alarm | Reliable, Keep Last, bounded Deadline/Liveliness |
| Late-joining state | A new subscriber needs the latest state immediately | configuration or mode state | Transient Local, Keep Last, bounded cache |
| Constrained high-rate stream | Memory and CPU must remain bounded | larger payload at higher rate | bounded depth and Resource Limits |

These are scenario-based selections to validate. They are not claims that one
profile is optimal for all applications.

## What Takase's Studies Do Not Establish

The sources should not be used as evidence for claims they did not test:

- They do not provide a Seven-QoS profile system.
- They do not justify this project's 5% and nominal 15% random-loss levels.
- They do not evaluate direction-specific `tc` loss injection.
- They do not provide a complete Wireshark/PCAP methodology.
- They do not evaluate DiffServ classes, priority queues, background traffic, or
  network congestion.
- They do not measure ESP32-S3 CPU, heap, stack high-watermark, or energy.
- Their results use different hardware, ROS 2 generations, operating systems,
  and networks from this project.

Accordingly, the current DSCP value of zero does not invalidate DDS/RTPS QoS
results. It limits the claim to middleware-level QoS. DiffServ should be treated
as a separate optional network-layer extension, not silently folded into the
current Seven-QoS campaign.

## Recommended Revision of the Evaluation Plan

### Phase A: freeze the argument before more formal collection

1. State the contribution boundary as DDS/RTPS QoS for mros2-esp.
2. Add a profile-to-API-to-RTPS mapping table.
3. Define three or four representative application profiles.
4. Add native ROS 2-to-native ROS 2 to the baseline matrix.
5. Record that `tc` loss is synthetic, direction-specific controlled stress.
6. Provide an explicit rationale for 0%, 5%, and nominal 15% loss, including the
   random-loss model and observed effective loss.
7. Expand the PCAP schema and state explicitly that representative current
   captures use DSCP 0.

### Phase B: run a small discriminating pilot

Use one payload, one publish rate, both directions, and selected Best Effort
and Reliable profiles across:

- native ROS 2 to native ROS 2;
- current mros2-esp to native ROS 2;
- upstream mros2-esp to native ROS 2;
- micro-ROS to native ROS 2.

The pilot should verify clock boundaries, impairment direction, PCAP fields, and
telemetry comparability before reopening the large formal matrix.

### Phase C: formal mechanism and performance evaluation

Run deterministic state/mechanism cases separately from randomized performance
sampling. Expand only along factors tied to a stated question:

- Reliability by loss and direction;
- History/depth by burst size and loss;
- Durability by late-join delay and cache depth;
- Deadline by publish period and delay;
- Lifespan by injected delay;
- Liveliness lease by outage duration;
- Resource Limits by payload and publish rate.

Energy can remain a deferred secondary metric unless it is made part of a
specific resource-efficiency question. Its absence must then be stated, and no
energy-efficiency conclusion should be made.

## Claim Language

Prefer bounded statements such as:

> Under the tested ESP32-S3, ROS 2, Wi-Fi, workload, and direction-specific
> controlled-loss conditions, Reliable delivery produced a larger RTT tail in
> the B2H condition, while the same confirmed effect was not observed in H2B.

Avoid universal statements such as "Reliable is always slower" or "History does
not matter."

## Bottom Line

Takase's strongest reusable pattern is:

`narrow requirement -> explicit architecture -> familiar API -> controlled
same-workload baseline -> end-to-end metric -> internal attribution -> bounded
conclusion`

For this project, the next priority is therefore not to launch the full
1,530-run Seven-QoS campaign immediately. First repair the evaluation argument
around the teacher's requested native baseline, profile/API mapping, synthetic
loss rationale, expanded PCAP evidence, application scenarios, and bounded
claim language. Then use a small pilot to validate that revised protocol before
formal collection.
