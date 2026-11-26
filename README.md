# qos-extended-mros2-esp32

Selectable ROS 2 QoS for mROS 2 on the ESP32-S3.

mROS 2 runs an RTPS stack (embeddedRTPS) directly on the microcontroller and
talks to ROS 2 nodes without a host-side Agent. Upstream mros2 takes a `qos`
argument in `create_publisher` / `create_subscription` but does not use it:
every endpoint is Best Effort and Volatile. This fork makes the policy a real
choice. A `QoSProfile` is passed at endpoint creation, checked there, carried
into SEDP discovery, compared against the remote endpoint, and enforced by the
writer and reader state machines on the board.

```text
ESP32-S3 (mros2 + embeddedRTPS + QoSProfile)  <-- Wi-Fi / UDP / RTPS -->  ROS 2 host (Fast DDS)
```

## Policies

| Policy | Values | What the board does |
| --- | --- | --- |
| Reliability | Best Effort, Reliable | stateful writer/reader, HEARTBEAT, ACKNACK, retransmission, GAP |
| Durability | Volatile, Transient Local | keeps samples across matching, replays them to a late reader |
| History | Keep Last(d), Keep All | bounded writer cache; evicted samples answered with GAP |
| Deadline | infinite, or finite on Reliable endpoints | reader-side missed-deadline count and callback |
| Lifespan | infinite, or finite on Reliable endpoints | expired samples purged from the writer cache |
| Liveliness | Automatic with lease duration | reader lease tracking, lost / recovered transitions |
| Resource limits | `max_samples`, `max_bytes` | admission cap on the writer cache (`max_bytes` is local only) |

A profile the implementation cannot honour is rejected when the endpoint is
created, with the violated rule in the error, rather than being downgraded.
Reliability, Durability, Deadline and Liveliness lease take part in
offered/requested matching. Everything except `max_bytes` is advertised in
SEDP, so a ROS 2 peer sees the same QoS the application asked for.

```cpp
mros2::QoSProfile qos;                 // Reliable, Volatile, Keep Last(10)
qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
qos.depth = 10;
auto pub = node.create_publisher<std_msgs::msg::String>("state", qos);
```

Reliable writers keep a bounded cache (depth, `max_samples`, `max_bytes` and
the compiled-in slot count, whichever is smallest). ACKNACK handling answers at
most `B` requested sequences per message (default 4) and sends GAP for
sequences that were evicted or are irrelevant to that reader. Readers deliver
strictly in order and hold no reorder buffer: a sample ahead of the expected
one is dropped and re-requested, and a HEARTBEAT whose first available
sequence is past the expected one moves the reader forward. HEARTBEAT period,
cache size and `B` are build-time parameters.

## Layout

```text
mros2/                     mros2 API: mros2/include/mros2/qos.h, mros2/src/mros2.cpp
mros2/embeddedRTPS/        RTPS stack. QoS additions live mainly in
                           include/rtps/discovery/QoSCompatibility.h,
                           include/rtps/entities/{ReliabilityState,DurabilityState,
                           ReaderSequence,ResourceLimits}.h, StatefulWriter.tpp,
                           StatefulReader.tpp, src/discovery/TopicData.cpp
platform/                  ESP32 Wi-Fi glue, RTPS build-time parameters (platform/rtps/config.h)
components/                benchmark_telemetry: CPU, heap and stack telemetry on the board
workspace/qos_eval/        hardware validation firmware
workspace/seven_qos_*/     parameterised firmware used for the measurement campaigns
tools/echo_cpp/            ROS 2 host nodes: echo responder, RTT probe, QoS compatibility probe
microros_bench/, upstream_bench/
                           same workload on micro-ROS and on unmodified mros2-esp32
scripts/experiment/        campaign runners, netem loss injection, audits, analysis
scripts/validation/        flashing, preflight, WSL firewall helpers
scripts/test/              host-side test runner
tests/                     host unit tests (C++) and harness tests (Python)
docs/                      protocols, runbooks, QoS status, figures
data/paper_campaign/       measured results: per-run values, statistics, plotted series
```

`docs/DESIGN_MAP.md` says which file implements which mechanism and which
script produced which measurement.

## Building and testing

Host tests need only g++ (C++17) and python3. They compile the same headers
the firmware uses, with small lwIP stubs from `tests/stubs`:

```bash
./scripts/test/run_host_tests.sh
```

Firmware needs ESP-IDF v5.1.7 and an ESP32-S3:

```bash
cp platform/wifi/wifi_secrets.example.h platform/wifi/wifi_secrets.h   # SSID and password, git-ignored
./scripts/validation/qos_set_remote_ip.sh                               # writes platform/rtps/config_local.h
cd workspace/qos_eval && idf.py set-target esp32s3 && idf.py build flash monitor
```

The host side is a ROS 2 Humble workspace with `rmw_fastrtps_cpp`;
`tools/echo_cpp` builds with colcon. `docs/validation/QUICK_START.md` has the
full hardware checklist, including the WSL2 firewall step.

## Measurements

The board sends 64-byte requests at 10 Hz to a ROS 2 echo node over Wi-Fi;
`tc netem` drops packets in one direction at 0, 5 or 15 %. Each condition is
30 runs of 200 requests. On the ESP32-S3:

- Reliable received a reply to every one of the 6000 requests at 15 % loss in
  either direction; Best Effort lost about 15 %. The price is tail latency:
  median run-level p95 RTT 150.8 ms (host-to-board loss) and 194.8 ms
  (board-to-host) against 32.6 ms on a clean link.
- Transient Local with Keep Last(1) and Keep Last(10) replayed exactly the
  newest 1 and 10 samples to a late-joining subscriber in every run.
- Against micro-ROS running the same workload on the same board, the mros2
  build used 4.1 % CPU and left 144 KiB of heap (micro-ROS: 25.8 %, 20 KiB);
  the micro-ROS Agent on the host is not counted.
- A 48-case campaign against a Fast DDS host matched or refused endpoints
  exactly as the DDS offered/requested rules require, for Reliability,
  Durability, Deadline and Liveliness lease, in both directions and both
  creation orders.

Per-run values, per-condition statistics and the plotted series are in
`data/paper_campaign/`. Raw captures, serial logs and build trees are not in
the repository; the protocols, audit scripts and analysis code that produced
the numbers are (`docs/benchmark/`, `scripts/experiment/`).

## Scope

Reliability, Durability and History were measured on hardware. Deadline,
Lifespan, Liveliness and the resource limits are implemented and covered by
host tests but were not measured on the board. This is a bounded QoS
extension for a microcontroller, not a complete DDS QoS implementation.

## License

Apache License 2.0, as upstream mros2 and mros2-esp32. embeddedRTPS (MIT),
Micro-CDR (Apache-2.0), lwIP (BSD-3-Clause) and CMSIS-RTOS2 (Apache-2.0) keep
their own licenses; see `NOTICE`.
