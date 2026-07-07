# Paper figures

Vector PDFs (camera-ready) + PNG previews, generated from the raw packet
captures in `results/wireshark/` (local-only evidence, not in git) by:

```bash
python3 scripts/figures/make_figures.py
```

Requires: tshark, matplotlib. Timelines are re-zeroed to the board reboot
instant (first >3 s gap in the board's SPDP announcements). No raw IP/MAC
addresses appear in the figures (roles are labeled "board"/"host").

## fig_discovery_timeline — draft caption

> **Post-reset discovery handshake between the ESP32 (embeddedRTPS) and a
> ROS 2 Humble host (Fast DDS), observed on the wire.** After the board
> reboots (t=0), it resumes SPDP participant announcements; the host re-serves
> SEDP endpoint data, the reliable-protocol HEARTBEAT/ACKNACK exchange
> synchronizes both SEDP readers, and the first user sample flows 13.7 s
> after reboot (10 s of which is the application-level match wait).
> Capture: `restored_baseline2_20260706_190324.pcapng`.

## fig_discovery_deadlock — draft caption

> **The sporadic post-reset SEDP deadlock (before the fix).** Both runs use
> identical firmware and hosts. (a) The rebooted board reuses a GUID prefix
> the host still holds reliable-stream state for (tick-seeded PRNG collision):
> its SEDP ACKNACK counter restarts at 1 and climbs for a full minute
> requesting endpoint data that the host never re-serves — matching deadlocks.
> (b) A boot that drew a fresh prefix: the host re-serves SEDP data within
> seconds and user data flows. Fixed by deriving the GUID prefix from the
> hardware RNG and shortening the announced SPDP lease from 100 s to 12 s
> (8/8 reset-stress cycles pass after the fix). Captures:
> `restored_baseline_20260706_190021.pcapng` (a),
> `restored_baseline2_20260706_190324.pcapng` (b).

## fig_heartbeat_period — draft caption

> **Wire effect of the stateful-writer HEARTBEAT period.** Cumulative
> HEARTBEAT submessages sent by the ESP32 for `SF_WRITER_HB_PERIOD_MS`
> = 4000 (default) vs. 1000: 70 vs. 295 in the first 50 s after reboot
> (×4.2), with no functional difference in delivery (40/40 samples in both
> conditions). The brief plateau near t=30 s in the 1000 ms trace is a
> Wi-Fi stall. Captures: `rtps_bidirectional_20260706_183830.pcapng`,
> `expA_hb1000_20260706_184841.pcapng`.

## Notes for the paper

- These are *qualitative/mechanism* figures; quantitative claims (RTT
  distributions, match-latency statistics) must come from the N≥30
  measurement campaign after the experimental configuration is frozen.
- The two deadlock captures are irreplaceable: the bug is fixed in firmware
  and cannot be re-recorded. Keep `results/wireshark/` backed up.
