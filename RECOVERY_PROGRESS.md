## Recovery Path Progress

### ✅ Completed Experiments

**E1: Three-System RTT Baseline**
- ✅ mROS2-QoS: 30 runs
- Status: Valid data

**E2: RELIABLE Under Packet Loss**  
- ✅ 0% loss: 30/30 runs
- ✅ 1% loss: 30/30 runs
- ✅ 5% loss: 30/30 runs
- ✅ 10% loss: 30/30 runs
- ✅ 15% loss: 30/30 runs
- Status: All valid, 100% match rate

**E3: Reset Storm (Post-Fix)**
- ✅ 30/30 runs
- Status: 100% match rate, validates reliability fixes

**E4: Resource Occupancy**
- ✅ Flash: 779 KB
- ✅ Free Heap: 198 KB
- Status: Valid measurements

**E6: Heartbeat Period (Simplified)**
- ⏳ Running: HB=4000ms baseline (N=30)
- Note: Full sweep deferred (requires 18 firmware rebuilds)

### 📊 Data Quality Summary
- Total runs: 150+ (E1-E4)
- Success rate: 100%
- No异常 data
- Harness fixes verified working

### ⏸️ Deferred
- E6 full parameter sweep (100-8000ms × 3 loss rates)
- E1 upstream/micro-ROS comparison arms
