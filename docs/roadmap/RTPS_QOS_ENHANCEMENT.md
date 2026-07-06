# RTPS-Level QoS Enhancement Roadmap

This document describes the gaps between the current app-level QoS behavior checks
and true RTPS protocol-level QoS enforcement, with concrete steps to close them.

## Current State

The current implementation has two layers of QoS behavior:

1. **App-level checks** (in `workspace/step7_full_qos/main/app.cpp`):
   - DeadlineManager: uses `esp_timer_get_time()` to detect missed deadlines
   - LifespanManager: simulates cache aging by comparing timestamps
   - ResourceLimitsManager: local sample/byte counting

2. **RTPS-level representation** (in `mros2/` and `mros2/embeddedRTPS/`):
   - QoS fields are serialized into SEDP discovery messages
   - Writer cache enforces KEEP_LAST depth
   - StatefulWriter/StatefulReader paths exist for RELIABLE

The gap: app-level checks verify the *logic* works, but don't prove that the
RTPS protocol itself enforces these policies correctly.

## Gap Analysis

### Deadline

**Current:** App-level timer checks if messages arrive within deadline.
**RTPS requirement:** Writer should assert deadline, reader should detect deadline
missed and invoke `on_deadline_missed` status callback.
**Gap:** No RTPS-level deadline assertion or callback.

### Lifespan

**Current:** App-level timestamp comparison.
**RTPS requirement:** `StatefulWriter::progress()` should expire cached changes
when lifespan elapses, preventing retransmission of stale data.
**Gap:** Writer cache does not actively expire changes by lifespan.

### Liveliness

**Current:** App-level activity observation and lease simulation.
**RTPS requirement:** Writer should periodically assert liveliness (SPDP/SEDP);
reader should detect liveliness lost and invoke `on_liveliness_lost` callback.
**Gap:** No periodic liveliness assertion; no lost/recovered state machine.

### Durability (TRANSIENT_LOCAL)

**Current:** Writer cache exists but late-joiner behavior is not tested.
**RTPS requirement:** Late-joining reader should receive historical data from
writer cache via HEARTBEAT/ACKNACK exchange.
**Gap:** Needs hardware verification (see `docs/transient_local/TEST_PLAN.md`).

## Recommended Implementation Steps

### Step 1: Deadline RTPS Integration

Files to modify:
- `mros2/embeddedRTPS/include/rtps/entities/Writer.h` — add deadline timer
- `mros2/embeddedRTPS/src/entities/Writer.cpp` — implement deadline assertion
- `mros2/embeddedRTPS/include/rtps/entities/Reader.h` — add deadline missed callback
- `mros2/src/mros2.cpp` — expose deadline status through API

Implementation:
```
1. Add a deadline_duration field to Writer/Reader entities
2. Writer: start a periodic timer on create; on each tick, check if any
   change was written within the deadline period. If not, advance the
   missed count and invoke the callback.
3. Reader: on receiving a heartbeat, check if the writer's last write
   exceeds the requested deadline. If so, invoke on_deadline_missed.
```

### Step 2: Lifespan Cache Expiry

Files to modify:
- `mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.h`
- `mros2/embeddedRTPS/src/entities/StatefulWriter.cpp` (if it exists)
- `mros2/embeddedRTPS/include/rtps/storages/CacheChange.h`

Implementation:
```
1. Add a timestamp to each CacheChange upon creation
2. In the writer's progress() or heartbeat generation loop,
   check each cached change: if (now - timestamp) > lifespan,
   mark it as expired and do not include it in retransmission.
3. Add a lifespan_drop_count() accessor for observability.
```

### Step 3: Liveliness Assertion

Files to modify:
- `mros2/embeddedRTPS/src/entities/Writer.cpp`
- `mros2/embeddedRTPS/src/discovery/SPDPAgent.cpp`

Implementation:
```
1. For AUTOMATIC liveliness: start a periodic timer that sends
   a heartbeat or SPDP update to assert liveliness.
2. Timer interval = liveliness_lease_duration / 3 (standard DDS practice).
3. Reader: track time since last heartbeat from each matched writer.
   If (now - last_heartbeat) > lease_duration, mark writer as not alive.
```

### Step 4: TRANSIENT_LOCAL Late-Joiner Hardware Test

See `docs/transient_local/TEST_PLAN.md`.

### Step 5: Expose Status Callbacks

Files to modify:
- `mros2/include/mros2.h` — add status query functions
- `mros2/src/mros2.cpp` — implement status accessors

New API:
```cpp
// Deadline
uint32_t publisher_deadline_missed_count();  // already exists
uint32_t subscriber_deadline_missed_count(); // already exists

// Liveliness (new)
bool publisher_liveliness_alive();
bool subscriber_liveliness_alive();
uint32_t publisher_liveliness_lost_count();
uint32_t subscriber_liveliness_lost_count();

// Lifespan (new)
uint32_t publisher_lifespan_drop_count(); // already exists
```

## Testing Strategy

Each step should be validated with:

1. **Unit test** — add host-side tests in `tests/test_qos.cpp` for logic
2. **Static check** — add verification cases to `scripts/test/qos_static_checks.sh`
3. **Hardware test** — create dedicated firmware in `workspace/stepN_xxx/`
4. **Evidence update** — update `docs/qos/QOS_EVIDENCE_MATRIX.md` maturity levels

## Priority Order

1. TRANSIENT_LOCAL hardware test (Step 4) — lowest effort, highest evidence value
2. Deadline RTPS integration (Step 1) — moderate effort, closes major gap
3. Lifespan cache expiry (Step 2) — moderate effort, depends on StatefulWriter
4. Liveliness assertion (Step 3) — higher effort, requires timer infrastructure
5. Status callbacks (Step 5) — can be done incrementally with each step
