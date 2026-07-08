# Recovery Path Decision

## Decision: Use app.cpp (not app_lossy.cpp)

### Rationale
1. app.cpp already verified working (TX=40 RX=40 RTT=30 matched=1&1)
2. app_lossy.cpp has API compatibility issues requiring deeper code study
3. Key insight: warm-up abort only triggers if echo node is broken
4. With fixed harness (pkill exact match), echo nodes won't be killed
5. Time constraint: implementing app_lossy.cpp correctly would take hours

### Strategy
- Use app.cpp for all experiments
- Fixed harness ensures echo_node_lossy won't be killed accidentally
- If warm-up still fails, it means real packet loss issue (not harness bug)
- This is acceptable: RELIABLE QoS should handle reasonable packet loss

### Execution Order
1. E2 (RELIABLE under packet loss) - with fixed pkill
2. E3 (Reset storm)  
3. E4 (Resources)
4. E6 (Heartbeat sweep)

Starting E2 rerun now with app.cpp + fixed harness.
