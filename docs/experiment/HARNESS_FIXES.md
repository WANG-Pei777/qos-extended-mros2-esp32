# Harness Bug Fixes - Completed

## Fixed Issues (5/5)

### ✅ 1. CSV Append Protection
- **File**: `scripts/experiment/run_matrix.sh`
- **Fix**: Changed CSV initialization from overwrite (`>`) to conditional creation
- **Before**: `echo "header" > ${OUTPUT_CSV}`
- **After**: `if [ ! -f "${OUTPUT_CSV}" ]; then echo "header" > "${OUTPUT_CSV}"; fi`

### ✅ 2. pkill Exact Match
- **File**: `scripts/experiment/run_matrix.sh`
- **Fix**: Use `-fx` flag for exact process matching
- **Before**: `pgrep -f "echo_reply.py\|echo_node"`
- **After**: `pgrep -fx "python3 .*echo_reply.py"` and `pgrep -fx ".*/echo_node"`
- **Impact**: Prevents killing `echo_node_lossy` when cleaning up `echo_node`

### ✅ 3. Trap Accumulation
- **File**: `scripts/experiment/run_e2_rerun.sh`
- **Fix**: Accumulate trap handlers instead of overwriting
- **Before**: `trap "kill ${ECHO_PID} ..." EXIT` (每轮覆盖)
- **After**: `TRAP_CLEANUP="kill ${ECHO_PID} ...; ${TRAP_CLEANUP:-true}"`

### ✅ 4. Statistics N=1 Support
- **File**: `scripts/experiment/run_matrix.sh`
- **Fix**: Check data length before calculating stdev
- **Before**: Always called `stdev()` → crashed on N=1
- **After**: `if len(rtt_avgs) > 1: stdev() else: "n=1, no stdev"`

### ✅ 5. Loss-Tolerant App
- **File**: `workspace/qos_eval/main/app_lossy.cpp`
- **Fix**: Created new application without validation abort
- **Purpose**: For E2/E6 where packet loss is expected
- **Key difference**: No warm-up validation → continues even if packets drop

## E4 Flash Size Parsing - Deferred
- **Issue**: `idf.py size` output format varies
- **Workaround**: Use binary file size from build output
- **Command**: `ls -l build/qos_eval.bin | awk '{print $5}'`

##废弃数据标记
All CSV files in `results/experiments/20260708/` except:
- ✅ `mros2qos_reliable_baseline.csv` (E1 baseline, 30 runs, valid)
- ✅ `mros2qos_verify_recovery.csv` (post-fix verification)

## Ready for Re-run
- **Priority**: E2 → E3 → E4 → E6
- **Strategy**: Validate N=1 before each N=30 batch
- **New tool**: `app_lossy.cpp` for loss-tolerant experiments
