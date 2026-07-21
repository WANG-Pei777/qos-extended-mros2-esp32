# Telemetry Runtime-Overhead Pilot Amendment 02

Recorded: 2026-07-17T05:32:27Z

Status: FROZEN HARNESS AMENDMENT, VALIDATION SMOKE PENDING

## Trigger

The first two scheduled micro-ROS/off attempts were not accepted. In both cases,
the micro-ROS Agent created its XRCE session, participant, writer, and reader in
less than four seconds. The host immediately received board warmup samples and
published replies, but the board did not receive a reply until 65,473 ms in
attempt 01 and 162,891 ms in attempt 02. The outer capture then expired before the
fixed measurement could complete.

The logs show asymmetric late DDS discovery: the host node and publisher were
started before the Agent-created DDS reader existed. They show no firmware crash,
watchdog, delivery-window failure, CRC fault, or CPU-control arithmetic fault.

## Amendment

For micro-ROS only, startup order becomes:

1. flash the exact scheduled firmware;
2. start the exact micro-ROS Agent;
3. open UART capture and reset the board;
4. wait until the Agent log confirms both datawriter and datareader creation;
5. start the exact host echo node;
6. proceed through board `COMPARE_READY`, the unchanged 1 s settle, and the
   unchanged 20 s measurement window.

Current mROS2-QoS and upstream startup order remains host first, then board reset.
The 180 s outer capture bound from Amendment 01 remains in force.

No workload, firmware, Agent binary, host binary, measurement-window, GPIO,
validator, estimator, schedule, random seed, or statistical gate changes.

## Consistency Action

The previously accepted `trop-006` micro-ROS/on attempt 01 used the old startup
order. It remains immutable and retained, but is classified
`SUPERSEDED_PROTOCOL_AMENDMENT` and excluded from the 60-run accepted set. A
replacement under the frozen schedule and new startup order is required. This
decision is based on harness consistency and was recorded without using its CPU or
RTT value to choose the action.

The two failed `trop-005` attempts remain failed attempts. Before consuming its
third and final scheduled attempt, the amended startup order must pass a separate
engineering smoke that is excluded from all pilot estimators.

The original schedule SHA-256 remains
`20849d0e044f9021eaba8ec037f9180d677dac9fe2f8cea07cad4e6fdb21e399`.
