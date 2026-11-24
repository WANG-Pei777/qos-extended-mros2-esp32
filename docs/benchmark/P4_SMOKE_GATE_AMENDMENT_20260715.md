# P4 Precollection Amendment: Mode-Aware History Smoke Gate

**Frozen at:** 2026-07-15 03:28 Asia/Tokyo

**Data status at freeze:** No P4 formal design manifest, acceptance ledger, or
formal run existed. The first exact-binary smoke attempt had three passing
RELIABLE runs and one failed BEST_EFFORT run. The failed run is retained in the
precollection diagnostic archive.

## Trigger

The BEST_EFFORT smoke run passed network, bidirectional DDS, endpoint QoS,
deadline, lifespan, liveliness, resource, serial-provenance, and PCAP checks.
Its only failed assertion required `History KEEP_LAST enforcement PASSED`.
That assertion came from the all-RELIABLE Round 6 gate.

The implementation selects a StatefulWriter for RELIABLE and a StatelessWriter
for BEST_EFFORT. Stateful history introspection therefore reports the frozen
depth for RELIABLE and correctly reports `0/0` for BEST_EFFORT. Treating the
BEST_EFFORT `0/0` result as a failure tests an inapplicable mechanism.

## Frozen Change

Only the smoke instrumentation assertion becomes mode-aware:

- RELIABLE still requires the frozen KEEP_LAST and mechanism lines plus
  `History KEEP_LAST enforcement PASSED`.
- BEST_EFFORT requires the same frozen configuration lines plus
  `History cache: 0/0 samples, 0 bytes`, confirming the expected stateless
  cache bypass.

All other 21 smoke assertions are unchanged. The hypotheses, firmware
binaries, schedule, outcomes, acceptance rules for formal runs, impairment,
and frozen analysis are unchanged. No failed smoke run may be reused; a new
machine-recorded window and all six smoke runs are required under the amended
harness.
