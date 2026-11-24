# Seven-QoS Performance Protocol Amendment 02

Status: ACTIVE FOR HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the common-path performance harness correction made
after the deterministic Seven-QoS releases. It preserves the code-line and
evidence boundaries while the 51-cell performance campaign remains blocked.

## Preserved Evidence Boundary

The accepted compatibility and mechanism releases bound to source commit
`3cb2cf792ec6200286cd04750f6a08f349340048` remain immutable. Their 48
compatibility cases and 36 mechanism claims are not rerun, relabeled, or pooled
with the later performance harness.

Commit `dda5d20` added only the no-data schedule and protocol tooling. The
implementation changes described here form a later performance-harness code
line at commit `01276b1`. All attempts under `results/diagnostics/` remain
excluded development evidence and cannot be promoted into the formal 1,530-run
campaign.

## Trigger and Root Cause

The first common-path pilots did not discover the host endpoint even though the
earlier deterministic workspaces remained valid. Bounded diagnostics showed
`udp_sendto()` returning `ERR_VAL` (`-6`) for otherwise valid IPv4 destinations.

The ESP32 component places the embeddedRTPS compatibility headers before the
ESP-IDF headers. The compatibility `lwipopts.h` defines an IPv4-only
`ip_addr_t`, while a newly generated external ESP-IDF configuration had IPv6
enabled and linked a dual-stack lwIP implementation. The resulting ABI mismatch
made the linked function interpret adjacent memory as an address type. Earlier
accepted workspaces explicitly disabled IPv6 and therefore did not exercise
this mismatch.

FreeRTOS core locking was tested as a separate hypothesis and did not remove the
failure. It is not part of this correction.

## Harness Corrections

The performance-harness code line makes the following scoped changes:

- `components/mros2-esp32/CMakeLists.txt` now rejects
  `CONFIG_LWIP_IPV6=y` at configuration time and no longer mutates a source-tree
  `sdkconfig` with a delayed shell command;
- `mros2/src/mros2.cpp` zero-initializes `osThreadAttr_t` and treats an mROS2
  initialization-thread allocation failure as `RESOURCE_EXHAUSTED`;
- the host echo process starts before the board reset for non-micro-ROS runs,
  and the runner records host, flash-start, and flash-complete timestamps;
- runner inputs for the host executable, Fast DDS profile, ESP-IDF Python, flash
  tool, and serial port are explicit and copied into the attempt manifest;
- the host echo executable accepts an explicit topic base so the comparison
  path uses `/system_compare` without changing its legacy default; and
- `workspace/seven_qos_performance_pilot/` provides an excluded common-path
  workload with explicit 8,192-byte main-task stack, 1,000 Hz RTOS tick, and
  IPv4-only defaults.

Temporary UDP transmit diagnostics and task snapshots used during diagnosis are
not present in the cleaned harness.

## Development-Pilot Result

The excluded clean common-path pilot is retained at:

`results/diagnostics/20260723_seven_qos_performance_common_path_clean_ipv4_accepted/`

Its manifest classifies the attempt as an engineering smoke and explicitly
states that it is never a formal comparison run. The pilot used RELIABLE QoS,
512-byte payloads, 50 Hz, a 20-second measurement window, and the clean network
profile. It recorded:

- 1,000 attempted transmissions, 1,000 replies, and 1,000 RTT samples;
- 200 telemetry samples and 20 task records;
- zero missing samples, publish failures, allocation failures, duplicates,
  malformed replies, arrival inversions, or telemetry fault flags;
- mean RTT 10,779 microseconds and mean controlled CPU utilization 144,617 ppm;
- minimum internal heap 146,732 bytes and minimum stack high-watermark 528
  bytes; and
- a readable 4,797-packet PCAP with SHA-256
  `83f6f92431ba7dcabb5c2425697028566137f1f46199fa50e3ef63fee06ba9fd`.

The firmware SHA-256 is
`ba6e57087f9c035251bc4f173e28d37eb416d461aef0c2ac07363fa42887984e`;
the external `sdkconfig` SHA-256 is
`3ae74f45c5a50eb2beef98448be12e47bfe325857f0341331ccccd2a695c8d34`.
Post-run qdisc state returned to the canonical `mq` root with eight
`fq_codel` children.

The 24-file development-pilot tree passed release-seal verification with tree
SHA-256
`043d2cefe29b21e4cec894f67d049fd59af2e54af52998f1928f639786845b04`.

An explicit negative configuration test with `CONFIG_LWIP_IPV6=y` failed at
CMake configuration with the expected IPv4-only ABI message. This is the
required fail-closed behavior.

## Same-Commit Verification

After commit `01276b1` was created, the firmware was rebuilt with the same
external `sdkconfig` and the full clean pilot was repeated at:

`results/diagnostics/20260723_seven_qos_performance_common_path_clean_01276b1/`

The embedded application version is `01276b1`. The attempt and wrapper both
passed with 1,000 transmissions, 1,000 replies, 1,000 RTT samples, 200 telemetry
samples, 20 task records, zero publish or allocation failures, and zero fault
flags. Mean RTT was 10,144 microseconds, controlled mean CPU utilization was
147,943 ppm, minimum in-window internal heap was 153,036 bytes, and minimum
stack high-watermark was 528 bytes.

The same-commit firmware SHA-256 is
`52d3664458c40196a9c6d1c046ae0f0d8bf6b161b187898041dc1dbc6ec2fb28`.
The 5,529-packet PCAP SHA-256 is
`eb75275103dda1c407930c97e0fb909cf304a0b16c83ccc3993c0ff2aac4673b`.
The 24-file result tree passed seal verification with tree SHA-256
`9788e0c080b42e6b38d9befacda83d6380cfc13b8b6a925c186e4abd892df754`.
The post-run qdisc again matched the canonical `mq` root with eight
`fq_codel` children. This same-commit result supersedes the earlier dirty-tree
pilot as the common-path gate, but it remains an excluded engineering smoke.

## Remaining Gate

This result closes only the shared telemetry, delivery, RTT, resource, PCAP,
flash, and cleanup path. Formal collection remains blocked until each policy
family has a representative hardware smoke, family-specific acceptance checks,
exact artifact freeze, storage and retry validation, and a clean-commit release
protocol. No row from the frozen 1,530-run schedule has been collected.

Energy remains `deferred_not_collected` under Amendment 01. This stage supports
no energy-use conclusion.
