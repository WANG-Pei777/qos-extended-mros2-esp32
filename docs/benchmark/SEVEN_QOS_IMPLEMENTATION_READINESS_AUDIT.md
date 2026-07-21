# Seven-QoS Implementation Readiness Audit

Status: DRAFT -- pre-formal engineering gate, no performance evidence
Inspected source: `8ca77cd6b07839b488c69550d52468d30d7e66cd`
Inspected: 2026-07-16

## Remediation Status (2026-07-16, uncommitted engineering branch)

The findings below record the baseline inspection. This table records subsequent
source remediation without promoting it to hardware or performance evidence.

| Gate | Source/unit/build status | Remaining closure evidence |
|---|---|---|
| G1 | Shared requested/offered predicate now covers immediate and delayed matching; 14/14 host cases and the six-unit bidirectional hardware smoke pass. | Run the frozen 48-case bidirectional/creation-order hardware compatibility matrix. |
| G2 | Formal protocol fixes all affected mechanism studies to RELIABLE Stateful entities. | Manifest generator and audit must reject an unexpected Stateless entity. |
| G3 | Formal protocol specifies a measured board-side release hold. | Implement and hardware-calibrate the hold; external `tc delay` remains invalid as a substitute. |
| G4 | KEEP_ALL resource assertion is corrected to `max_samples <= capacity`; clean capacity-100 builds pass at limits 5 and 100 with nonbinding `max_bytes=262144`. | Implement fixed ACK suppression and reconcile hardware attempt/accept/reject counts. |
| G5 | One Domain monitor now checks writer/reader Deadline and reader Liveliness at a build-bound 5 ms period. Clock wrap and exact boundaries pass 10/10 host cases; startup no longer begins alive. | Verify exact callback/counter transitions and monitor jitter on hardware. |
| G6 | Durability formal cells remain frozen at 64 bytes. | Large-payload transient-local replay remains unsupported until a fragmented replay/repair test passes. |
| G7 | Capacity is a build parameter and the capacity-100 family compiles. | Build, hash, flash, and smoke the fixed capacity-40 History/Durability family. |
| G8 | Deadline and Liveliness ordering joined Reliability/Durability in the shared discovery predicate; delayed records preserve Liveliness. The reusable runner resolves all 48 draft compatibility rows. | Complete all formal match/no-match hardware cases for both endpoint directions and creation orders. |
| G9 | One wrap-safe Lifespan predicate now purges expired history before capacity checks, normal send, repair, replay, and HEARTBEAT range construction; 8/8 boundary cases pass. | Run `LS-RECONNECT` and reconcile nonduplicated drop counts on hardware. |
| G10 | Failed pbuf reserve/append no longer advances history; `publish()` returns acceptance and exposes attempt, accepted, policy-reject, and allocation-failure counters. Large-message callbacks own a message copy. | Add an explicit serialization-failure outcome/counter and run synthetic plus hardware pressure reconciliation. |
| G11 | Public registration now exists for offered/requested Deadline and Liveliness lost/recovered callbacks; callbacks execute outside entity locks. | Replace/scaffold callbacks with typed timestamp/count records and verify exactly-once ordering on hardware. |
| G12 | Removed/evicted slots reset immediately; 19/19 ownership/failure/wrap host cases pass. | Reconcile history bytes with free-heap recovery in ACK/recovery hardware cases. |

Current host gate total is 163/163 passing tests. ESP-IDF builds pass for the
default diagnostic configuration and the two resource boundaries above. The
compatibility runner and its strict host/board validators pass 18 Python tests.
These are engineering checks only: no Seven-QoS formal run has yet been accepted.

The common ESP32 telemetry implementation now passes exact telemetry-on/off builds
and board smokes for this work, upstream mros2-esp32, and micro-ROS. The exact on
build adds 27,008 `.bss` bytes and 16 `.data` bytes in every system. The randomized
60-run runtime-overhead pilot also passes its preregistered +2 pp CPU gate for all
three systems, with 60/60 accepted logs independently revalidated and sealed. See
`TELEMETRY_RUNTIME_OVERHEAD_PILOT_PREREGISTRATION.md` and the sealed result tree
`results/experiments/20260717_telemetry_runtime_overhead_pilot`.

The deterministic source draft now expands reproducibly to 48 compatibility and
36 mechanism cases. The review tree is
`results/protocols/20260717_seven_qos_deterministic_expanded_draft`, with schedule
SHA-256 `6096483eed4c66dd4aec0408e2cb3d6e35321680a304e2858148e76105b3fb80`.
Its execution gate remains `BLOCKED_HARNESS_BINDING`. Compatibility rows now have
a schedule-driven case runner with exact firmware/host hashes, PCAP capture,
machine-readable assertions, and explicit endpoint-order gates. The 36 mechanism
rows, immutable campaign attempt ledger, and final protocol freeze remain open.
External GPIO and power-trace calibration is also still open and blocks all
formal energy-bearing performance matrices.

## Compatibility Harness Smoke Closure (2026-07-17)

The minimum hardware harness smoke gate now passes six accepted units:

- B2H compatible RELIABLE/VOLATILE endpoints in remote-first and local-first
  creation order, each with board `tx=10/10` and host `rx=10`.
- B2H incompatible BEST_EFFORT-offered/RELIABLE-requested endpoints in both
  creation orders, with `actual_match=0`, `tx=0`, and `rx=0` on both sides.
- H2B compatible RELIABLE/VOLATILE endpoints in both creation orders, each with
  host `tx=10` and board `rx=10`.

Fast DDS now uses a project-bound unicast initial peer for the ESP32 PDP listener
at `192.0.2.1:7410`. Once SPDP reveals the host GUID, all four SEDP builtin
directions are bound. Remote-first recovery requires retaining the host long
enough for the constrained reader to ACKNACK through pre-existing ROS 2 SEDP
history; the runner therefore uses an explicit post-match hold and validates
application delivery, not endpoint match alone.

The schedule-driven runner is
`scripts/experiment/run_seven_qos_compatibility_case.py`. It resolves all 48
compatibility rows in the draft schedule and binds build configuration, flash,
endpoint order, PCAP, strict host/board validation, and artifact hashes. An exact
runner self-validation against `CMP-REL-b2h-remote-first-p3` passes.

The sealed diagnostic release is
`results/diagnostics/20260717_seven_qos_compatibility_smoke_release`: 117 files,
14,759,960 bytes, tree SHA-256
`daf480c9f4880325676c9b14b12b2ec1c4deeb27b8c381448513a328383b43aa`, and file
manifest SHA-256
`4e3b399f5658c93395c400db09b13280f23f19a031266004455a50557da59ce1`.
The independent release verification passes at
`results/audits/20260717_seven_qos_compatibility_smoke_release/release_verification.json`.
Do not modify the sealed tree.

This release is engineering smoke evidence only. It executes zero rows as formal
evidence and does not support a claim that all 48 compatibility cases, all seven
QoS policy families, or any performance matrix have been evaluated.

### Compatibility Family Smoke Closure

Representative current-source smokes now also pass compatible and incompatible
schedule rows for Durability, Deadline, and AUTOMATIC Liveliness. The first
Deadline compatible attempt was correctly rejected and retained: PCAP showed the
board writing nanoseconds directly into the RTPS Duration fraction field, so a
nominal 100 ms request decoded as approximately 23.28 ms. Liveliness lease was
also applied to the runtime entity but omitted from SEDP TopicData.

The repair uses rounded `seconds / 2^32` RTPS fractions for Deadline, Lifespan,
and Liveliness wire values and propagates the configured Liveliness lease through
Domain endpoint creation. Five conversion boundary tests raise the host gate from
158 to 163 cases. In the repaired PCAP, the board's Deadline request decodes as
`0.100000 sec (0x1999999a)` and its Liveliness request decodes as exactly
`2.000000 sec`.

The six accepted family smokes use one current protocol source set: Durability,
Deadline, and Liveliness each have one compatible delivery case and one
incompatible zero-traffic case, crossing B2H/H2B and remote/local-first order.
The sealed release is
`results/diagnostics/20260717_seven_qos_compatibility_family_smoke_release`: 153
files, 7,767,207 bytes, tree SHA-256
`b01133dacd79d6bce06c27f3086fc2a217e55493dc8a935a407e509c8bfb2d99`, and file
manifest SHA-256
`03998e38a63a11b1c1e5724c387ec06338c71e39e7e4a9cefda54f81a1a5291d`.
Verification passes at
`results/audits/20260717_seven_qos_compatibility_family_smoke_release/release_verification.json`.
Do not modify the sealed tree.

These are still excluded engineering smokes. No case is accepted into a formal
48-case campaign, and the protocol remains unfrozen.

## Purpose

This audit maps each proposed mechanism experiment to the ESP32 code path that
must produce the outcome. A formal cell is invalid if it primarily exercises a
host DDS behavior, a no-op virtual method, or an impairment placed after the
embedded mechanism under test.

## Blocking Findings

### G1. SEDP offered/requested compatibility is reversed for remote readers

`SEDPAgent::onNewSubscriber()` currently rejects a RELIABLE writer with a
BEST_EFFORT reader and a TRANSIENT_LOCAL writer with a VOLATILE reader. DDS
requested/offered compatibility permits both combinations. The opposite
combinations are the incompatible ones and are already expressed correctly by
`QoSPolicy::is_compatible()`.

Required gate: use one shared compatibility predicate in both discovery
directions and add endpoint-level tests for all four Reliability and all four
Durability offered/requested pairs. The deterministic hardware suite must confirm
match/no-match behavior in both board-publisher and board-subscriber directions
and with each endpoint created first.

The delayed `tryMatchUnmatchedEndpoints()` path currently bypasses compatibility
checks entirely. It can therefore match an incompatible pair when the remote
endpoint was discovered before the local endpoint. The shared predicate must be
called by both immediate and delayed matching paths.

### G2. Several mechanisms exist only on the Stateful path

The Stateless writer/reader inherit no-op setters and zero counters for History,
Resource Limits, Deadline, and Liveliness. The corresponding formal mechanism
studies must therefore fix Reliability=RELIABLE unless a real Stateless
implementation is added and separately validated.

Required gate: every run manifest records the concrete RTPS entity class and
fails audit if a mechanism study instantiated a no-op path.

### G3. External network delay does not exercise the embedded Lifespan gate

The ESP32 Lifespan check occurs in `StatefulWriter::progress()` before packet
transmission. A `tc netem delay` applied after transmission can cause a host DDS
reader to observe stale data, but it does not test the ESP32 writer's expiry and
drop path.

Required gate: use a measured board-side pre-transmit release hold for the
Lifespan mechanism experiment. Keep any separate end-to-end ROS 2 interoperability
test clearly labeled and do not substitute it for the embedded mechanism result.

### G4. Resource Limits are masked by KEEP_LAST in the current configuration

The Stateful writer evicts to `history_depth` before checking `max_samples`.
Consequently, `max_samples >= depth` cannot bind under KEEP_LAST. The current
benchmark build also requires `max_samples >= compile_time_capacity`, preventing
small limits with a constant larger capacity.

Required gate: run the sample-limit mechanism with KEEP_ALL, a constant capacity
of at least 100, and a nonbinding byte limit. Replace the benchmark-only
`max_samples >= capacity` assertion with `max_samples <= capacity`.
Add a fixed, prespecified ACK-suppression episode so all cells create outstanding
history, and audit the resource-reject counter against attempted publications.
Test the byte-limit boundary separately as a deterministic case.

### G5. Deadline and Liveliness checks depend on application polling

Reader deadline and liveliness transitions occur only when the application calls
their check methods. Detection latency therefore includes the polling interval.
The liveliness state also begins as alive before a heartbeat has been observed.

Required gate: use a dedicated periodic monitor with a recorded interval no more
than 5 ms for the 50 ms Deadline level and no more than 50 ms for the 0.5 s
Liveliness lease. Start Liveliness timing only after a matched writer and first
valid heartbeat. Add deterministic tests for startup, exact boundary, repeated
checks, one lost transition, and one recovered transition.

### G6. Transient-local replay is not yet safe for fragmented cached samples

The late-reader replay path emits cached `change->data` directly. Large samples
stored through the serializer callback/fragment path need a separate verified
replay implementation.

Required gate: hold the Durability mechanism experiment at a 64-byte payload.
Large-payload transient-local replay remains unsupported until a fragmentation
test passes; it must not be inferred from the general payload sweep.

### G7. History depth is bounded by a compile-time cache capacity

Depth 20 and 40 require firmware built with capacity at least 40. Building a
different capacity for each depth would confound runtime depth with static memory.

Required gate: use one capacity-40 build family for all History and Durability
depth cells, and bind ELF/map hashes in each manifest. Treat capacity as a fixed
background constant, not as the measured History factor.

### G8. Deadline and Liveliness requested/offered checks are not enforced

Endpoint discovery serializes Deadline and Liveliness lease values, but SEDP
matching currently checks only Reliability and Durability. A host endpoint can
therefore match even when the offered Deadline or Liveliness contract does not
satisfy the request.

`TopicDataCompressed`, used for delayed unmatched endpoints, also omits Liveliness
fields. It must preserve every field required by the shared predicate so matching
does not depend on endpoint creation order.

Required gate: centralize DDS requested/offered comparison for all implemented
compatible policies and call it from both discovery directions. Add deterministic
match/no-match cases for Deadline and AUTOMATIC Liveliness lease ordering. Lifespan,
History, and Resource Limits remain local/non-RxO policies and must not be assigned
invented match rules.

### G9. Transient-local replay can resend expired Lifespan samples

The normal Stateful writer progress path skips an expired change but leaves it in
history. The late-reader transient-local replay loop sends cached changes without a
Lifespan check, so a sample suppressed as expired on the normal path can be emitted
after a reader reconnects or joins late.

Required gate: centralize the writer's expiry predicate and apply it consistently
to normal send, repair, and transient-local replay paths. `LS-RECONNECT` must prove
that expired history is never delivered after a reader lifecycle change, while
expiry counters remain exactly defined and nonduplicated.

### G10. History allocation failures can be reported as successful changes

`SimpleHistoryCache::addChange(data, size)` ignores the Boolean results from both
`PBufWrapper::reserve()` and `append()`. It can advance history and return a change
after an allocation/copy failure, while `Publisher::publish()` does not expose the
writer return value to the application.

Required gate: do not advance sequence/history on reserve or append failure; expose
an unambiguous per-attempt publish result; and maintain separate counters for policy
limit rejection, allocation failure, and serialization failure. Synthetic pbuf
failure injection plus `RES-ALLOC-FAIL` hardware pressure must reconcile attempted,
accepted, rejected, failed, and delivered counts exactly.

### G11. QoS event callbacks are not exposed consistently by the public API

The Stateful reader contains a Deadline callback slot, but the mROS2 subscription
API does not expose registration. Liveliness loss/recovery and writer Deadline are
available only as counters/polling. Calling these paths event-triggered in a paper
would overstate the current interface.

Required gate: expose typed public callbacks (or explicitly scoped event records)
for requested/offered Deadline and Liveliness lost/recovered transitions, with
monotonic event time and cumulative count. Deterministic tests verify callback
ordering, exactly-once transition behavior, and consistency with the counters. If
the API remains polling-only, use that narrower wording throughout the paper.

### G12. Removed history slots can retain pbuf allocations

`SimpleHistoryCache::removeUntilIncl()` advances or resets ring indices without
resetting the removed `CacheChange` objects. Their `PBufWrapper` references can keep
acknowledged or evicted payload buffers allocated until those physical slots are
overwritten by later publications. Logical history bytes can therefore be zero
while actual heap remains occupied.

Required gate: destroy/reset each removed slot before advancing the tail, including
the remove-all path. Unit tests track pbuf ownership through partial removal,
remove-all, wraparound, KEEP_LAST eviction, and failed insertion. A hardware
ACK/recovery case must reconcile history count/bytes with free-heap recovery before
formal memory or Resource-Limit claims.

## Provisional Mechanism Mapping

| Policy family | Direction and embedded entity | Fixed background contract | Varied mechanism |
|---|---|---|---|
| Reliability | H2B board StatefulReader and B2H board StatefulWriter | Existing frozen Round 4 semantics | Reliability x loss x direction |
| History/Depth | B2H board StatefulWriter | RELIABLE, KEEP_LAST, capacity 40, 64-byte payload | depth x burst size x loss |
| Durability | B2H board StatefulWriter; late host reader | RELIABLE, capacity 40, 64-byte payload | durability x late-join delay x cache depth |
| Deadline | H2B board StatefulReader | RELIABLE, board event monitor, ingress-only delay | deadline x host publish period x delay |
| Lifespan | B2H board StatefulWriter | RELIABLE, board-side pre-transmit hold | lifespan x injected release delay |
| Liveliness | H2B board StatefulReader | RELIABLE, heartbeat <=100 ms, ingress-only outage | lease x outage duration |
| Resource Limits | B2H board StatefulWriter | RELIABLE, KEEP_ALL, capacity 100, fixed ACK suppression | max samples x payload x rate |

The mapping remains provisional until unit tests, exact-binary hardware smoke,
impairment efficacy checks, and runtime/storage pilots pass. Changes are allowed
only before the final preregistration freeze and must be recorded there.

## Deterministic/Performance Separation

Compatibility matrices, exact threshold boundaries, callback ordering, startup
state, recovery state, overflow semantics, and unsupported combinations belong to
the deterministic result tree. Random performance cells remain N=30 independent
runs and report run-level outcomes. A deterministic repetition is never counted as
a performance replicate.

## Formal 48-Case Compatibility Result (2026-07-17)

The compatibility subset is now formally complete. A dedicated no-data protocol
froze 48 unique firmware images plus bootloader, partition table, flash arguments,
host probe, Fast DDS profile, source hashes, hardware identities, retry rules, and
an immutable attempt ledger. The protocol schedule SHA-256 is
`831744ed0b227dfcdd1efa002b0103b8b72d55d0de1499e979d436824da3a0f5`.
Its sealed tree contains 304 files and 49,103,780 bytes; tree SHA-256 is
`7d9fcc0178dbb3885ff2519fb7246f3b6f55338f413e37b863d3177464cc75d7`.

All 48 scheduled cases passed on their first attempt: 16 Reliability, 16
Durability, 8 Deadline, and 8 AUTOMATIC Liveliness cases, balanced across B2H/H2B
and remote/local-first endpoint creation. The set contains 32 expected-compatible
and 16 expected-incompatible outcomes. Compatible cases required delivery;
incompatible cases required zero endpoint matches and zero application traffic.
The independent audit rebuilt the ledger, revalidated 96 endpoint logs, checked
all frozen bundle and board identities, and indexed 48 readable PCAPs with zero
errors and zero fatal attempts.

The sealed campaign contains 800 files and 38,980,946 bytes; tree SHA-256 is
`9c0f331a32f844af64f72edd3e599c4861b2819c35ce1c49a214cdb1521c35af`.
The sealed paper-facing analysis tree has tree SHA-256
`597e186316aeda5d31bd160aedd8b90f40702ef38fd26c027ed5570d511f0ebe`.
Its configuration matrix, policy summary, PCAP inventory, formal claim, and table
caption are under `results/analysis/20260717_seven_qos_compatibility_formal`.

This closes formal endpoint compatibility for four QoS policies only. The 36
History/Depth, Lifespan, Deadline/Liveliness event-state, Durability replay, and
Resource-Limit mechanism cases remain unbound and unexecuted. The paper must not
claim a systematic evaluation of all seven QoS families until those deterministic
mechanisms and the separately blocked energy-bearing performance campaign pass.
