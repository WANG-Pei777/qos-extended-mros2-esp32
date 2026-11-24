# Telemetry Runtime-Overhead Pilot Amendment 01

Recorded: 2026-07-17T05:27:17Z

Status: FROZEN OPERATIONAL AMENDMENT

## Trigger

Scheduled run `trop-005` (micro-ROS, telemetry off) reached
`COMPARE_READY` at 65,473 ms after boot. Its fixed 85 s UART capture expired after
150 echo replies and before `COMPARE_FINAL`. Flash, Wi-Fi, XRCE session creation,
and firmware-hash checks passed. The retained serial, host, and Agent logs contain
no crash, watchdog, telemetry fault, CRC failure, or control-probe arithmetic
failure.

This was the first micro-ROS/off scheduled attempt. It was not accepted and remains
in the attempt ledger as `runs/005_trop-005/attempt_01`.

## Amendment

The UART capture timeout changes from 85 s to 180 s for every subsequent attempt
in all six cells. The 20 s measurement window, 5 s reply grace, 6 s post-terminal
watchdog observation, workload, binaries, schedule, randomization, acceptance
validator, estimands, and statistical gate do not change.

The timeout is an outer observation bound, not a measured-window parameter. It is
extended because micro-ROS DDS discovery can consume most of the former bound
before the measurement window begins. The board still starts measurement only
after `COMPARE_READY` and the fixed 1 s settle interval.

## Bias Boundary

No previously accepted run is reclassified or removed. The amendment was recorded
before any micro-ROS/off run entered the accepted set. Ready time remains reported
as a secondary outcome; the amendment prevents right-censoring it at an implicit
approximately 60 s readiness limit.

The original schedule SHA-256 remains
`20849d0e044f9021eaba8ec037f9180d677dac9fe2f8cea07cad4e6fdb21e399`.
