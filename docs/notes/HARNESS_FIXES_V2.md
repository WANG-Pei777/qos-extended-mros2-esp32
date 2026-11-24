## Harness Fixes Applied

### Fix 1: Trap累积问题 → 改用显式清理
**Before**: 复杂的trap累积逻辑，未生效
**After**: 
- 每轮开始前 pkill 清理所有 echo_node_lossy
- 循环结束后显式 kill $ECHO_PID
- 双重保险：再次 pkill 清理

### Fix 2: E2验证逻辑 regex bug
**Before**: `grep -oP 'matched_pub,\K\d+'` 匹配表头，总是失败
**After**: `tail -1 ... | awk -F, '{print $11}'` 提取数据行第11列

### Testing
Run: `bash scripts/experiment/run_e2_rerun.sh` 验证修复
