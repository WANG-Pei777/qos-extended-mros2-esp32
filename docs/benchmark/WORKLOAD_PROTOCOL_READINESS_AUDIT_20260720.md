# Workload and Protocol Readiness Audit

Status: ENGINEERING READINESS ONLY -- no formal workload comparison claim
Date: 2026-07-20

## Evidence Boundary

This audit records excluded engineering smokes used to bind payload, rate,
fragmentation, and baseline capability before preregistration. The runs are not
randomized N=30 cells and must not enter formal cross-system statistics. Delivery,
RTT, CPU, heap, and stack values below are diagnostic outcomes only.

The energy-bearing formal matrix remains blocked. No calibrated external power
monitor or electrically aligned GPIO trigger is installed, so joules per
successful delivery cannot be measured. None of the 3,270 planned formal runs may
start until that gate is calibrated and frozen.

## Accepted Engineering Anchors

| System and workload | Outcome | Diagnostic result |
| --- | --- | --- |
| This work, Best Effort, 2048 B, 100 Hz | PASS, 2000/2000 | `results/diagnostics/20260720_workload_p2048_r100_mros2qos_fastdds_fragment_smoke` |
| This work, Reliable, 2048 B, 10 Hz | PASS, 200/200 | `results/diagnostics/20260720_workload_rel_p2048_r10_mros2qos_smoke_retry2` |
| micro-ROS, Best Effort, 512 B, 100 Hz | PASS, 2000/2000 | `results/diagnostics/20260720_workload_p512_r100_microros_mtu1200_smoke_retry2` |
| micro-ROS, Reliable, 512 B, 10 Hz | PASS, 200/198 | `results/diagnostics/20260720_workload_rel_p512_r10_microros_agent242_smoke` |
| micro-ROS, Reliable, 2048 B, 10 Hz | PASS, 200/195 | `results/diagnostics/20260720_workload_rel_p2048_r10_microros_agent242_size4096_ddsmtu1200_smoke_retry2` |

The Best Effort 2048 B/100 Hz row retains its original `FAIL` attempt manifest:
the then-current validator incorrectly compared the 10 ms publication period with
the fixed 100 ms telemetry period. The unmodified UART artifact passes the current
validator, and the readiness audit reruns that validator on every invocation. This
post-hoc engineering revalidation is explicit and is not promoted to a formal run.

The final same-condition Reliable 2048 B/10 Hz smokes used 20 s measurement
windows. This work observed 200/200 delivery, 27,301 us mean application RTT,
3.4715% mean ESP32 CPU, 150,952-byte minimum internal heap, and a 496-byte minimum
task stack high-water mark. micro-ROS observed 195/200 delivery, 35,096 us mean
application RTT, 30.2093% mean ESP32 CPU, 205,828-byte minimum internal heap, and
a 528-byte minimum task stack high-water mark. These N=1 values are not estimates
of comparative performance.

The full-window PCAPs are:

- This work: 1,354 packets over 32.81 s, SHA-256
  `a85337bb6ca2e3ff5498375f3c4ed5f351458595f2fa147db83d84f5e9cb7b4c`.
- micro-ROS: 7,458 packets over 21.92 s, SHA-256
  `ba93f88d021c669cd35f65cafee9faafb293824f47642a909bb5b8e1de8c11c8`.

For this work, PCAP decoding shows 209 board-to-host samples as three RTPS
DATA_FRAG submessages with a 1,024-byte nominal fragment and 2,056-byte sample,
and 208 host-to-board samples as two fragments with a 1,084-byte nominal fragment
and 2,057-byte sample. For micro-ROS, the Wi-Fi hop is XRCE-DDS: the full capture
contains 1,975 Agent-to-board and 4,173 board-to-Agent control/ACK datagrams plus
the expected 1,224/909-byte downlink and 1,224/912-byte uplink large fragments.

## Capacity and Native-Support Boundaries

- micro-ROS Reliable 512 B/100 Hz is outside the tested capacity boundary. After
  preventing executor starvation, the run took 51.68 s instead of 20 s and
  delivered 1,559/2,000 replies. It is a retained FAIL, not an accepted run.
- upstream mros2-esp32 Best Effort 2048 B/100 Hz never became ready. The board
  emitted 64-byte DATA_FRAG traffic and the host echoed with two large fragments,
  but the native upstream reader cannot reassemble the return DATA_FRAG sample.
- upstream mros2-esp32 does not expose Reliable user-endpoint creation. The
  explicit compile gate fails at `telemetry_compare.cpp:42`; adding this work's
  Reliable implementation to that tree and still calling it upstream is forbidden.
- micro-ROS Best Effort cannot use XRCE reliable-stream fragmentation for samples
  above the configured transport MTU. Such cells must be classified as unsupported
  or separately amended before protocol freeze, not silently emulated.

## Engineering Fixes Bound by These Smokes

This work now has fixed-buffer DATA_FRAG reader reassembly, a 1,024-byte fragment
buffer, nominal-fragment writer sizing, normal DATA bounds correction, and a host
Fast DDS 1,200-byte UDP profile. The DATA_FRAG unit gate passes 20/20 cases.

The micro-ROS baseline uses a 1,200-byte XRCE UDP MTU, a 500 ms warm-up period,
and a post-publish nonblocking executor drain. Its project-local Agent is official
Micro XRCE-DDS Agent v2.4.2 at commit
`57d086216d01ec43121845d385894a25987f8a2c`, with Fast DDS pinned to v2.12.2
instead of the removed floating `2.12.x` branch. The Agent DDS topic capacity is
configured to 4,096 bytes; the resulting Agent shared-library SHA-256 is
`af7b801c8b4c82e6bf03f86bc7baeccb139da850748e8fb702630d752f0129f3`.
Both the Agent and local ROS 2 echo use the 1,200-byte Fast DDS profile for
cross-version large-sample DATA_FRAG interoperability. The XRCE Wi-Fi MTU remains
firmware controlled.

The smoke runner archives the exact firmware, ELF, map, Agent executable, Agent
shared library, Agent CMake cache, transport profile, commands, and hashes. Its
validator treats delivery as an outcome when explicitly requested, while still
requiring the exact attempt count, zero publication failures, zero duplicate or
malformed samples, and telemetry/CRC integrity. `COMPARE_CONFIG.period_ms` is the
publish period; `BENCH_CONFIG.period_ms` remains the fixed 100 ms telemetry period.

## Static Resource Snapshot

For the Reliable 2048 B/10 Hz telemetry builds, ESP-IDF size reports:

| System | DIRAM data | DIRAM BSS | Used DIRAM | Flash non-RAM | Total image |
| --- | ---: | ---: | ---: | ---: | ---: |
| This work | 17,916 | 80,912 | 168,567 | 682,715 | 786,753 |
| micro-ROS | 18,048 | 69,792 | 157,555 | 725,147 | 829,293 |

These are exact-build engineering snapshots, not middleware-only formal costs.

## Readiness Decision

The clean-network protocol/firmware smoke gate is ready for preregistration
revision. Before formal collection, freeze the supported-cell matrix, label every
native unsupported cell, bind the project-local Agent source patch and dynamic
libraries, incorporate the passed host-egress impairment efficacy audit, remediate
the formal storage gate, install and calibrate the external power monitor, and
freeze the randomized schedule. Until then, performance pooling and cross-system
superiority claims are forbidden.
