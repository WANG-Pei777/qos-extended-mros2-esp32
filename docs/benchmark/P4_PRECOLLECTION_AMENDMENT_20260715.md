# P4 Precollection Amendment: Wi-Fi Startup Recovery

**Frozen at:** 2026-07-15 01:52 Asia/Tokyo

**Data status at freeze:** No P4 result directory, smoke result, formal run, or
outcome data existed.

## Reason

The independent-window gate exposed a startup fault before data collection.
The ESP32-S3 booted normally and esptool completed non-writing hard resets, but
the WPA3-SAE association intermittently returned disconnect reason 205. The
platform firmware stopped permanently after five initial retries. Restarting
the AP and increasing reset cadence did not pass the precollection recovery
qualification.

## Frozen Change

Only bootstrap behavior changes. Initial Wi-Fi association now retries until a
180,000 ms monotonic timeout, records each disconnect reason, retry count, and
elapsed time, and then fails closed. Reconnection after the first acquired IP
is unchanged. P4 measurement timing cannot start until the board has an IP,
matches both DDS endpoints, and passes the smoke acceptance checks.

The P4 harness waits at most 210 seconds for post-reset or post-flash network
recovery, leaving a 30-second observation margin after the firmware timeout.

Both QoS variants must be rebuilt from one clean source commit with
`MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS=180000`, reproducibility-checked, and
sealed. The original `20260714_p4_firmware_set_c9489da` remains immutable as
superseded pre-amendment evidence and must not be used for P4 collection.

## Unchanged Design

The hypotheses, six cells, random seed and schedule, 30 accepted runs per cell,
QoS/history/resource controls, impairment mechanism, outcomes, acceptance
rules, exclusion ledger, and frozen analysis are unchanged. No observed RTT,
delivery, packet-count, or other outcome informed this amendment.

## Qualification Gate

Before opening the P4 window, the amended firmware must pass ten consecutive
non-writing hard-reset and network-recovery cycles at 75-second cadence, then
the two exact archived binaries must each pass three smoke runs. Any failure
blocks formal collection and remains in the precollection diagnostic record.
The ten-cycle report must hash the exact sealed firmware and the immediately
preceding three-segment-verified flash log.
