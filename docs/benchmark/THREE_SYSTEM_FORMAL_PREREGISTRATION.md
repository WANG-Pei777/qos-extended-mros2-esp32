# Three-System Matched-Workload Preregistration

**Status:** FROZEN BEFORE NEW THREE-SYSTEM SMOKE OR FORMAL DATA COLLECTION

**Frozen at:** 2026-07-15 Asia/Tokyo

Historical N=1 comparator measurements are disclosed in
`MICROROS_COMPARISON_PROTOCOL.md`; they are pilot evidence only and are not
reused here.

## Claim Boundary

This experiment compares clean-network data-path and reconnection behavior on
one ESP32-S3, one AP, and one ROS 2 Humble host. It does not establish general
cross-device or cross-network superiority. P4 separately evaluates RELIABLE
transport behavior under loss.

All three systems use BEST_EFFORT so architecture and implementation, rather
than QoS reliability, are the intended contrast:

- mROS2-QoS, direct RTPS;
- upstream mros2-esp32, direct RTPS;
- micro-ROS, XRCE-DDS through a continuously running Agent.

## Frozen Workload

The same C++ echo binary serves `/system_compare` and
`/system_compare_reply`. Each board reset first sends unmeasured warm-up
messages until one echo returns. After a 1,000 ms settle interval, the board
sends exactly 40 measured `std_msgs/String` messages, 64 payload bytes each,
at 500 ms intervals. It then sends nothing further, waits up to 5,000 ms for
late replies, and emits one `COMPARE_FINAL` record. Every accepted run retains
all `COMPARE_RTT` records.

Cold-ready time is reset-to-first-warm-up-echo. It includes native DDS
discovery for the direct systems and network/session/proxy setup for micro-ROS.
The primary value is measured by the host harness from RTS reset deassertion to
receipt of `COMPARE_READY` on serial using one monotonic clock. The firmware's
own `ready_ms` is retained as a diagnostic cross-check, not substituted for the
primary outcome.
The host echo remains running within a system visit; the micro-ROS Agent also
remains running within its visit.

All three Wi-Fi bootstraps disable modem power save on the USB-powered board,
accept WPA2-or-stronger association, and use the same bounded 180,000 ms
initial-association window. These bootstrap settings do not alter either
direct RTPS implementation or the micro-ROS XRCE-DDS data path.
The mROS2-QoS WSL unicast-discovery peer IPv4 is treated as a local build
input: the builder requires an explicit expected address, verifies the ignored
`config_local.h`, and archives that non-secret peer configuration with its
hash. A placeholder peer address is a smoke failure and cannot be formal data.

## Frozen Schedule

| Factor | Value |
| --- | --- |
| Systems | mROS2-QoS, upstream mros2-esp32, micro-ROS |
| Accepted runs per system | 100 |
| Superblocks | 10 |
| Visits per superblock | all 3 systems in seeded random order |
| Accepted runs per visit | 10 |
| Total accepted runs | 300 |
| Random seed | `202607153` |

Each run resets the board and retains serial, host, Agent where applicable,
PCAP, link-health, and configuration evidence. Firmware changes occur only at
visit boundaries. Rejected attempts are never deleted and replacements occur
within the same visit.

## Outcomes And Acceptance

Primary run-level outcomes are per-message RTT p95 and cold-ready time.
Secondary outcomes are RTT median/p99, delivery ratio, flash bytes, free heap,
wire packets/bytes per delivered measurement, and reset success.

Acceptance is instrumentation-only: clean committed harness, exact sealed
firmware and host hashes, expected system/config record, exactly 40 transmitted
measurement messages, one complete final record, valid sidecars, and nonempty
board-source capture. RX count, delivery, ready time, and RTT values are never
acceptance criteria.

## Frozen Analysis

Runs are independent units. Report N=100 per system with run-cluster bootstrap
95% intervals. The confirmatory family contains six pairwise contrasts: all
three system pairs for RTT p95 and cold-ready time. Use superblock-level exact
sign-flip tests and Holm correction across the six contrasts. Delivery and
wire/resource outcomes are descriptive secondary evidence. No outlier removal
is permitted beyond prespecified instrumentation failures retained in the
ledger.

## Precollection Gates

Before formal collection:

1. Build every firmware from a recorded clean source/patch state and seal all
   binaries, bootloaders, partition tables, build logs, and compile evidence.
2. Verify the shared C++ host binary hash and micro-ROS Agent version/hash.
3. Pass three exact-binary smoke runs per system with the finite 40-message
   contract, valid PCAP, and no stale process or qdisc.
4. Freeze the generated schedule and formal executor tests.

Any protocol, firmware, or smoke correction before formal collection must be
recorded as a timestamped amendment. No comparator formal run exists until all
four gates pass.

## Amendment 1: ESP-IDF lwIP ABI Correction

**Recorded at:** 2026-07-15 12:13 Asia/Tokyo

**Formal comparator runs collected before this amendment:** 0

The first exact-binary mROS2-QoS smoke set failed before producing
`COMPARE_READY`. PCAP showed host discovery traffic addressed to the board,
while a temporary firmware trace showed every received RTPS packet being
reported with destination port zero. Startup instrumentation then confirmed
that `udp_bind()` returned success for ports 7400, 7401, 7410, and 7411 while
the application observed `udp_pcb.local_port == 0`.

The ESP-IDF component had placed embeddedRTPS's desktop
`thirdparty/lwip/lwipopts.h` ahead of ESP-IDF's own lwIP configuration. This
compiled the application and the linked ESP-IDF lwIP library with incompatible
`udp_pcb` layouts. Before any formal run, the direct-RTPS components were
amended to use only ESP-IDF's lwIP configuration and IPv4 access/conversion
APIs. A diagnostic mROS2-QoS run after the correction completed 40/40 echoes
with no protocol errors and is retained as engineering evidence only.

This correction does not change the frozen workload, QoS, timing, schedule,
acceptance rules, outcomes, or analysis. All earlier executable sets and failed
smoke attempts remain rejected pilot/engineering evidence. New source commits,
two-build reproducibility records, sealed binaries, and three-run smoke gates
are required for every system before formal collection can begin.

## Amendment 2: Snap Agent Launch And Identity Binding

**Recorded at:** 2026-07-15 12:49 Asia/Tokyo

**Formal comparator runs collected before this amendment:** 0

After the lwIP correction, three mROS2-QoS and three upstream exact-binary
smoke runs passed. The micro-ROS visit stopped before its first run because the
asset builder resolved `/snap/bin/micro-ros-agent` to `/usr/bin/snap` and then
attempted to execute that resolved path as the Agent. The Snap command link
depends on its original basename and cannot be treated as the Agent ELF.

Before formal collection, the asset and execution contract was amended to:

- hash the revision-specific `micro_ros_agent` ELF inside the mounted Snap;
- hash the `/usr/bin/snap` launcher and execute the explicit
  `snap run micro-ros-agent` command;
- freeze `snap list micro-ros-agent` output, including version and revision;
- revalidate both file hashes and the installed package revision before smoke
  and formal execution.

The six passed direct-system smoke runs remain retained engineering evidence,
but their executable set is rejected because its Agent identity was sealed
incorrectly. This amendment changes no firmware protocol, workload, outcome,
schedule, acceptance rule, or analysis. A fresh executable set and all nine
smoke runs are required before formal collection.

## Amendment 3: Upstream Participant GUID Uniqueness

**Recorded at:** 2026-07-15 14:15 Asia/Tokyo

**Formal comparator runs collected before this amendment:** 0

The first smoke set with a correctly bound micro-ROS Agent passed all nine
required runs, but retained three consecutive rejected upstream attempts. PCAP
audit showed that the preceding accepted reset and all three rejected resets
advertised the identical RTPS participant GUID. The upstream embeddedRTPS code
seeded `rand()` from the deterministic FreeRTOS boot tick, allowing rapid
resets to reuse a participant identity while the host still retained its
reliable discovery state. A later reset drew a different GUID and immediately
recovered.

Before formal collection, upstream GUID generation on ESP-IDF was amended to
fill the prefix from `esp_random()`, matching the already validated mROS2-QoS
behavior. An engineering-only diagnostic then ran six consecutive board resets
against one continuously running host: all six completed the finite workload,
and all six PCAPs contained distinct participant GUIDs.

This correction changes participant identity generation only. It does not
change the workload, QoS, timing, schedule, outcomes, acceptance boundary, or
analysis. The earlier smoke-pass executable set remains rejected engineering
evidence because its reset behavior was not sufficiently stable for formal
collection. A fresh two-build seal and all nine smoke runs are required.
