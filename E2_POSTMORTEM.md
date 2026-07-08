## E2 Post-Mortem

**Root Cause**: Trap累积修复未生效，僵尸进程导致端口冲突

**Evidence**:
- 6个 echo_node_lossy 进程同时运行
- QoS不兼容警告（DEADLINE policy）
- 所有验证 TX=0 RX=0 matched=0&0

**Next Action**: 
1. 简化 E2 脚本，手动管理进程生命周期
2. 移除复杂的 trap 累积逻辑
3. 使用简单的 kill $PID 清理

重跑 E2 with simplified cleanup.
