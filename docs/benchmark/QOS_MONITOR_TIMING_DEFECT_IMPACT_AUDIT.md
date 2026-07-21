# QoS Monitor Timing Defect Impact Audit

Date: 2026-07-17 (Asia/Tokyo)

Status: legacy formal evidence unaffected; one pre-fix diagnostic CPU result
superseded.

## Defect

The new `Domain::qosMonitorLoop` initially requested a 5 ms sleep. ESP-IDF 5.1
implements `sys_msleep(ms)` with integer conversion to FreeRTOS ticks. With the
project's 100 Hz tick, 5 ms converted to zero ticks. The priority-24 monitor could
therefore remain runnable, starve the idle tasks, inflate idle-counter CPU usage,
and trigger the task watchdog.

The corrected configuration rounds the requested period up to a scheduler tick.
The diagnostic build therefore reports a 5 ms requested period and a 10 ms
effective period. A six-second post-terminal observation window is also mandatory
for telemetry smokes so a late watchdog cannot be missed.

## Evidence Boundary

The defect requires `Domain::qosMonitorLoop` to exist and periodically call
`checkDeadlineMissed`. The presence of `checkDeadlineMissed` alone does not imply
the defect.

The following sealed formal evidence predates the monitor and is unaffected:

- P4 independent, 180 accepted runs. Both exact archived P4 ELFs lack
  `qosMonitorLoop`, `qosMonitorJumppad`, and `QoSMonitor`; source commit
  `43ab8a86233f3a00d86160c296e4bef0486a2375` also lacks the monitor.
- Three-system formal comparison, 300 accepted runs. The exact mROS2-QoS ELF is
  SHA-256 `ec77dbf731b39b92c8f2dabb608f90f91caf6ddf3496e80e0bec68efe15a6f0e`,
  paired with firmware SHA-256
  `59bd0011d9b3f905f3abc96eccddc1fd3f5a80abe5ab8431459d9ce0b4e627d1`.
  The ELF and frozen source commit
  `b8c8d84c2e3e37488af64bac0ea20436a8838661` lack the monitor.

The pre-fix mROS2-QoS telemetry-enabled smoke that reported approximately 51.9%
mean CPU is superseded and must not be cited. It remains retained as diagnostic
failure evidence. The corrected exact-binary N=1 engineering smoke reports 2.2408%
mean CPU, but that value is also not a publication result because runtime overhead
has not yet been estimated with randomized telemetry-on/off repetitions.

## Reproducible Gate

Run:

```bash
python3 scripts/experiment/audit_qos_monitor_timing_impact.py \
  --output results/audits/20260717_qos_monitor_timing_impact/audit_report.json
```

The gate recomputes the three archived ELF hashes, inspects their demangled symbol
tables, and reads both frozen source commits. A pass requires all expected hashes
to match and all monitor identifiers to be absent.

This audit is read-only with respect to every sealed evidence tree. Its generated
report is stored in a separate, unsealed `results/audits` directory.
