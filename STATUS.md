# Historical Status Snapshot

This file records a 2026-07-10 pre-ROUND4 session and is not the current
experiment status. Do not use it to select a firmware, run a formal condition,
or support a paper claim. The authoritative formal protocol is
docs/benchmark/ROUND4_TOP_TIER_PROTOCOL.md.

# mROS2-QoS Project Status

**Last Update**: 2026-07-10 01:20 JST
**Phase**: Round 3 Execution
**Status**: 🔄 IN PROGRESS

---

## Current Execution

**R4 (E1 Three-System)**: mROS2-QoS arm running (2/30 runs complete)
**Expected completion**: 01:50-02:00 JST
**Monitor**: Active

---

## Session Summary (2026-07-10 00:18-01:20)

### ✅ Completed
- **Zombie cleanup**: 11→0 processes cleared (WSL restart)
- **Root cause correction**: Board functional, firmware bug diagnosis was wrong
- **R1@15% efficacy**: 5/5 runs passed, E2 unfrozen
- **Baseline validation**: TX=40 RX=40 RTT=20ms

### 🔄 In Progress
- **R4 mROS2-QoS arm**: 2/30 runs (running)

### ⏸️ Ready
- **R2 (E2)**: 10 conditions × 30 runs, 4 hours
- **R4 remaining**: upstream + micro-ROS arms

### ❌ Skipped
- **R3 (E3)**: Memory pool exhaustion, lowest priority

---

## Next Session Actions

1. **If R4 completes**: Execute upstream + micro-ROS arms
2. **Then**: Execute R2 (E2) full collection
3. **Finally**: Commit results, tag experiment freeze

---

## Board Status

**Hardware**: ESP32-S3 functional ✅
**Firmware**: v0.3.1-round2-fixes (991df75)
**WSL IP**: 10.84.233.195
**Serial**: /dev/ttyUSB0

---

**Monitor command**: R4 progress via task besyd9shl
