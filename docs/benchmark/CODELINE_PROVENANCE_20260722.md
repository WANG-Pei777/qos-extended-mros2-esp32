# Code-Line Provenance And Experiment Boundary

This document separates the frozen code lines used by completed experiments
from the current Seven-QoS compatibility work-in-progress. Historical results
must not be reinterpreted as if they were produced by the current worktree.

## Frozen Historical Lines

The following result sets retain their original source, firmware, harness, and
worktree provenance in their manifests.

| Result set | Direction or scope | Accepted data | Frozen harness commit | Status |
| --- | --- | ---: | --- | --- |
| `results/experiments/20260711_net37` | H2B transport impairment | 300 runs | `64e7ec710b3342b838b9561c5808e882c082efe` | Frozen and audited |
| `results/experiments/20260712_b2h_net37` | B2H transport impairment | 300 runs | `4837a369bad28dc8b84e495f8cba22d6c556a1fd` | Frozen and audited |
| `results/experiments/20260713_round6_formal_5dabf7e` | B2H factorial follow-up | 360 accepted runs | `5946a74a116b0241494f02791ec04ca06793fff3` | Frozen and audited |

These result trees are historical evidence. Their CSV files, PCAP files,
serial logs, manifests, and audit outputs must remain unchanged.

The Round4 H2B and B2H workloads use a bidirectional echo path. The network
impairment is directional, but the application workload includes the forward
message and the echo reply. The correct scope is therefore:

```text
end-to-end RTT and delivery under directional network impairment
```

It is not a pure one-way application-delivery measurement.

## Current Seven-QoS Source Line

The current Seven-QoS compatibility line is not a replacement for the frozen
historical lines. Its source freeze is the commit containing this document;
every collected artifact must additionally record the exact commit and binary
hashes in its own manifest.

For the Round6 result tree, the harness commit is
`5946a74a116b0241494f02791ec04ca06793fff3`; the archived firmware-set source
commit is `5dabf7ed5798065b9ebfb87b4d4ad42d0ee1970b`. Both values must remain
paired with the Round6 result tree.

### Core protocol changes

| File | Change | Evidence impact |
| --- | --- | --- |
| `mros2/src/mros2.cpp` | Match helpers also consult the underlying RTPS proxy counts. | Improves endpoint-match observation in the new probe; does not alter historical manifests. |
| `mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp` | Adds a configured unicast fallback when no reader proxy is available and advances the writer sequence only after an actual send. | B2H reliable data-path remediation frozen for the new compatibility line; it does not apply retroactively to historical results. |
| `mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp` | Retains an unsent sample until a usable route exists and provides one configured unicast fallback when proxy routing sends nothing. | B2H best-effort data-path remediation frozen for the new compatibility line; it does not apply retroactively to historical results. |
| `platform/rtps/config.h` | Adds the configured remote user-data port constant. | Supports the new unicast fallback path. |

### New compatibility harness

| File or directory | Purpose |
| --- | --- |
| `tools/echo_cpp/src/qos_compatibility_probe.cpp` | Machine-readable host publisher/subscriber probe for Seven-QoS cases. A matched subscriber remains active until it records an actual delivery or reaches its timeout. |
| `tools/echo_cpp/config/seven_qos_esp32_initial_peer.xml` | Fast DDS initial-peer profile for ESP32 discovery. This is a local smoke input and must be regenerated when the Wi-Fi network or board address changes. |
| `tools/echo_cpp/CMakeLists.txt` | Builds and installs `qos_compatibility_probe`. |
| `workspace/seven_qos_compatibility/` | Parameterized ESP32 board-side compatibility runner with machine-readable infinite-duration logging. |
| `scripts/experiment/run_seven_qos_compatibility_case.py` | Records the source commit at start and completion and hashes both writer implementations, the RTPS port configuration, the host probe, and the board runner for every case. |
| `scripts/experiment/capture_seven_qos_environment.py` | Verifies and snapshots the USB identity, board MAC, WSL interface, host address, and current AP identity before collection. |
| `scripts/experiment/freeze_seven_qos_compatibility_protocol.py` | Freezes exact flash bundles only from a clean tracked worktree and requires positive smoke evidence covering both directions and both endpoint creation orders. |
| `scripts/experiment/validate_seven_qos_compatibility_frozen.py` | Revalidates frozen binaries, bound source files, environment evidence, and pre-freeze smoke hashes before a campaign can start or resume. |

The cleaned worktree passed the following hardware smoke cases on 2026-07-22.
These directories are validation evidence only and are not accepted formal
Seven-QoS campaign data.

| Case | Coverage | Result directory |
| --- | --- | --- |
| `CMP-REL-b2h-remote-first-p1` | B2H, remote first, best effort positive | `results/validation/20260722_seven_qos_smoke/CMP-REL-b2h-remote-first-p1-clean` |
| `CMP-REL-h2b-remote-first-p1` | H2B, remote first, best effort positive | `results/validation/20260722_seven_qos_smoke/CMP-REL-h2b-remote-first-p1-clean` |
| `CMP-REL-h2b-remote-first-p3` | H2B, remote first, incompatible reliability negative | `results/validation/20260722_seven_qos_smoke/CMP-REL-h2b-remote-first-p3-negative-clean` |
| `CMP-REL-b2h-remote-first-p4` | B2H, remote first, reliable positive | `results/validation/20260722_seven_qos_smoke/CMP-REL-b2h-remote-first-p4-reliable-clean` |
| `CMP-REL-b2h-local-first-p4` | B2H, local first, reliable positive | `results/validation/20260722_seven_qos_smoke/CMP-REL-b2h-local-first-p4-reliable-clean` |
| `CMP-REL-h2b-local-first-p4` | H2B, local first, reliable positive | `results/validation/20260722_seven_qos_smoke/CMP-REL-h2b-local-first-p4-reliable-clean` |

For every positive B2H case above, the host log records at least one received
sample rather than match status alone. The host-side probe builds, and all
local protocol, QoS, RTPS, and compatibility-script tests pass. Failed and
diagnostic attempts in the same validation parent remain non-accepted
work-in-progress records and must not be cited as clean smoke evidence.

## Separation Rules

1. Historical result claims must use the commit, firmware hash, and manifest
   recorded inside the corresponding result tree.
2. The current Seven-QoS worktree must not be used to append to historical
   CSV, PCAP, serial-log, or audit trees.
3. A run made after the current changes must receive a new result identifier
   and a new manifest.
4. Seven-QoS collection must use the frozen source line and exact executable
   hashes recorded by the new campaign manifests.
5. The local ignored files `platform/wifi/wifi_secrets.h` and
   `platform/rtps/config_local.h` are environment configuration only; they are
   not part of the historical source line and must not be treated as evidence.
6. Generated build directories under `workspace/seven_qos_compatibility/`
   are build outputs, not frozen source inputs.

## Compatibility Campaign Interruption And Corrective Line

The compatibility campaign frozen at commit `30e4e0b06b226d8b257d8d79f4b088c1a728ee96`
was stopped after case 19. Cases 1 through 18 were accepted, while
`CMP-DUR-b2h-remote-first-p3` failed deterministically in three attempts: the
host correctly rejected a VOLATILE writer offered to a TRANSIENT_LOCAL reader,
but the ESP32 writer reported a match. This incomplete campaign is retained as
diagnostic evidence and must not be combined with a later corrected campaign.

The corrective source line introduces one requested/offered compatibility
function for Reliability, Durability, Deadline, and Liveliness. Both immediate
discovery and delayed endpoint matching call this function. RTPS duration
fields are represented as a seconds-plus-binary-fraction pair, and the user
Liveliness lease is propagated into SEDP endpoint data. A corrected formal
campaign requires a new commit, environment snapshot, smoke set, protocol
freeze, and result identifier.

## Corrected Compatibility Result

Commit `fd5073eda4b7b0ecca112860ffd1eba20f5e840f` completed a new frozen
compatibility campaign. All 48 deterministic cases were accepted on their
first attempt, and the independent audit passed with 48 PCAP files. The result
tree remains separate from the interrupted `30e4e0b` campaign.

| Tree | Path | SHA-256 |
| --- | --- | --- |
| Protocol | `results/protocols/20260722_seven_qos_compatibility_fd5073e` | `47f9cb41ca4d22a031927b102dbf84293ef6f25cfdf56a5e9b5fece0d07fde73` |
| Campaign | `results/experiments/20260722_seven_qos_compatibility_formal_fd5073e` | `23c2e15aa45c742c0cdf3c5a41fdeb868d2dc4aff807553028be3cdf6a379f2d` |

This result is valid only for the frozen `fd5073e` source line. It is a
pre-migration compatibility result and is not combined with mechanism results
from another commit.

## Integrated Mechanism Source Line

The commit containing this section migrates the separate Seven-QoS mechanism
implementation onto the corrected compatibility line. It adds bounded history
ownership, acknowledgement cleanup, transient-local replay, Deadline,
Lifespan, automatic Liveliness, Resource Limit outcomes, DATA_FRAG reassembly,
and the dedicated mechanism harness. It preserves the `fd5073e` unicast
fallback and send-success sequence advancement.

The migrated source is a new evidence boundary. The sealed 2026-07-20
mechanism campaign remains historical pilot evidence. Fresh smoke, protocol
freeze, 36-claim execution, audit, and seals are required before the migrated
implementation can support a deterministic mechanism result. The 48
compatibility cases must then be rerun on the same final commit before a single
84-claim result is reported.

### Pre-freeze host-probe correction

The first post-migration smoke attempt on commit
`bd532016b91c596435390ad130b00f64f79fe91e` built and flashed the board
firmware, but stopped before a mechanism verdict because the installed host
probe did not recognize the mechanism runner's delayed-send argument.
The failed attempt is retained at
`results/validation/20260722_seven_qos_mechanism_smoke_bd53201/HIST-KL-ORDER`.
No formal protocol was frozen and no accepted mechanism result was produced on
that commit. The subsequent source line extends the host probe with explicit
pre-send delay, exact receive-count, send-gate, and per-message
byte/hash evidence. New smoke and formal identifiers are required.

### Interrupted qdisc-bound mechanism campaign

Commit `ff579066dedea7f64d9acc3e0cd15556cc9c3d8b` produced a verified frozen
mechanism protocol. Its campaign accepted all 27 unit executions and the first
two hardware executions. The first `HIST-DUP-ONCE` attempt then passed its host
and board behavior but failed the qdisc restoration gate: removing the root
netem qdisc changed the clean multi-queue children from `pfifo_fast` to the
kernel default `fq_codel`. The runner stopped before a second attempt because
the current qdisc no longer matched the frozen baseline.

The protocol remains sealed at
`results/protocols/20260722_seven_qos_mechanism_ff57906`, with tree SHA-256
`ca07dfde9ce4b17c7a8a3373bd8d3943c4eecf07525700b40c977abbb0102aa8`.
The incomplete campaign remains at
`results/experiments/20260722_seven_qos_mechanism_formal_ff57906` as
diagnostic evidence only. It is not resumed or combined with a replacement
campaign.

The replacement source line normalizes a clean multi-queue interface to
`mq + fq_codel` before protocol capture, campaign gates, and hardware
attempts. It also adds `HIST-DUP-ONCE` to the excluded smoke gate so netem
installation and exact cleanup are exercised before a new protocol freeze.

## Current Evidence Boundary

At this point:

- Historical Round4 and Round6 result sets remain usable within their stated
  scope.
- The corrected `fd5073e` compatibility campaign is complete, audited, and
  sealed as an independent pre-migration result.
- The integrated mechanism line has no accepted post-migration mechanism or
  combined 84-claim result until its fresh gates complete.
- Energy measurement remains a deferred secondary metric under the existing
  protocol amendment.
- The reproducible two-direction smoke gate has passed for both endpoint
  creation orders in the reliable positive path, with additional best-effort
  positive and incompatible-reliability negative coverage.
- The source line is frozen. The next gate is to rebuild and hash the exact
  executable artifacts from the freeze, then run the complete 48-case
  compatibility and 36-case mechanism campaign in fresh result trees.
