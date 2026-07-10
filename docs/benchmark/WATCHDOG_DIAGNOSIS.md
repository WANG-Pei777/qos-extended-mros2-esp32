# Historical Watchdog Diagnosis

This diagnosis predates the verified host-process cleanup and the current
ROUND4 protocol. It is retained for audit history only and is not a current
root-cause finding or an instruction to change the formal firmware baseline.

# Watchdog Deadlock Diagnosis

**Date**: 2026-07-09
**Issue**: ReaderThread systematic deadlock after firmware reflash
**Severity**: 🔴 CRITICAL - Blocks all experiments

---

## Evidence Timeline

### Working State (096913c)
- **Time**: 2026-07-09 02:49-03:22 (before F2)
- **Firmware**: commit 096913c
- **Tests**: reliable 0/1/5/10/15% all passed
- **Results**: TX=40 RX=40, match rate 100%
- **Topics**: step7_full_qos, step7_full_qos_reply
- **QoS**: deadline/lifespan enabled

### Broken State (Current)
- **Time**: 2026-07-09 16:21+ (after F2)
- **Firmware**: commit 991df75 (includes F2 fix)
- **Tests**: All fail with watchdog
- **Error**: `task_wdt: IDLE1 (CPU 1)` ReaderThread deadlock @ 62s
- **Topics**: qos_eval, qos_eval_reply (renamed)
- **QoS**: deadline/lifespan commented out

---

## Root Cause Analysis

### Changes Between Working and Broken

**Code changes** (096913c → 991df75):
1. Topic rename: `step7_full_qos` → `qos_eval`
2. F2 QoS fix: deadline/lifespan commented out
3. F1 HOST_MODE: run_matrix.sh changes
4. F3 efficacy gate: E2 driver changes

**Host changes**:
- echo_cpp also had deadline/lifespan removed (F2)
- Topic name unchanged at `/qos_eval` (already current)

### Hypothesis

The watchdog is **NOT caused by F2 code changes** directly. Evidence:
1. F2 changes are minimal (2 lines commented)
2. DeadlineManager/LifespanManager still compile and run
3. Discovery succeeds ("Endpoint match confirmed")
4. Crash occurs **after** discovery, during data exchange

**Likely cause**:
- Topic rename introduced in 654a18a broke something
- Or: Network/environment changed between test sessions
- Or: Multiple rapid resets during R1/R3 corrupted flash/NVS

---

## Resolution Strategy

### Option A: Revert to Working Version (Fast, Low Risk)

```bash
cd /home/wsde-47/mROS2-QoS
git checkout 096913c workspace/qos_eval/main/app.cpp
cd workspace/qos_eval
source ~/esp-idf/export.sh
idf.py build flash
cd ../..
bash scripts/validation/qos_flash.sh all /dev/ttyUSB0
```

**Pros**: Known working state
**Cons**: Loses F2 fix (but F2 was to avoid warnings, not fix crashes)

### Option B: Bisect the Problem (Thorough, Slow)

```bash
# Test each commit between 096913c and current
git checkout 035070e  # First commit after 096913c
# rebuild, flash, test
# If works, move forward; if breaks, found culprit
```

### Option C: Disable Watchdog (Bypass, Diagnostic)

Requires manual sdkconfig edit:
```
CONFIG_ESP_TASK_WDT_EN=n
```
Then rebuild and flash.

**Pros**: Will complete tests even if ReaderThread hangs
**Cons**: Hides the root cause, may cause silent data corruption

---

## Recommended Action

**IMMEDIATE**: Option A (revert to 096913c version of app.cpp)

Why:
1. 096913c is proven working with current hardware/network
2. Restores all experiments immediately
3. F2 fix (deadline/lifespan removal) was for QoS warnings, not critical
4. Can re-apply F2 incrementally after baseline is stable

**AFTER** successful baseline:
1. Re-test F2 changes one at a time
2. Keep topic names as `qos_eval` (host side already updated)
3. Test deadline/lifespan removal separately

---

## Commit to Revert To

```
096913c Add experiment harness with audit fixes
```

This commit had:
- Working qos_eval firmware
- Topics: step7_full_qos, step7_full_qos_reply
- QoS: deadline/lifespan enabled
- All 0/1/5/10/15% tests passed

---

## Alternative Theory

If revert doesn't work, the issue may be:
1. **NVS corruption**: Erase flash completely
   ```bash
   idf.py erase-flash
   idf.py flash
   ```

2. **Hardware**: Power cycle ESP32 completely (unplug USB)

3. **Network**: WSL IP changed, check REMOTE_PARTICIPANT_IP in app.cpp

---

**Next Step**: Execute Option A and report results
