# RTPS Parameter Experiment: Wire-Level Effects of Heartbeat and SPDP Periods

> **Naming note (2026-07-07):** the validation app and topics were renamed
> `step7_full_qos` → `qos_eval` after these experiments; captures and names
> below are historical.

**Date:** 2026-07-06
**Setup:** ESP32-S3 (mROS2 + embeddedRTPS, Wi-Fi) ⇄ ROS2 Humble echo host (WSL2 mirrored networking, FastDDS)
**Capture point:** WSL `eth1` (`tshark -f "udp portrange 7400-7620"`), 60 s per run
**Firmware:** `workspace/step7_full_qos` at current tree (all QoS validation phases enabled)

## Objective

Measure, on the wire, how two `platform/rtps/config.h` parameters shape RTPS traffic:

| Parameter | Used by | Baseline |
|---|---|---|
| `SF_WRITER_HB_PERIOD_MS` | StatefulWriter heartbeat thread (`StatefulWriter.tpp:631`) | 4000 |
| `SPDP_RESEND_PERIOD_MS` | SPDP participant announcer (`SPDPAgent.cpp:90`) | 1000 |

## Method

Single-variable design. Per run: start ROS2 echo host → start capture → hard-reset the
ESP32 via serial DTR/RTS → capture 60 s and log serial 50 s → functional check
(endpoint match, warm-up echo, RX count, phase completion). One parameter changed
per condition; firmware re-flashed between conditions; configuration and firmware
restored to baseline afterward (verified by a final passing run and empty `git diff`).

## Results

| Metric (60 s window) | Baseline | Exp‑A `HB=1000` | Exp‑B `SPDP=3000` (run 2) |
|---|---|---|---|
| Total RTPS packets | 655 | **1057 (+61 %)** | 841 |
| ESP32 HEARTBEAT packets | 93 | **366 (×3.9)** | 143 |
| ESP32 HB burst interval | ≈3.6 s | **≈0.9 s** | ≈3.6 s |
| ESP32 SPDP DATA(p) mean interval | 1.03 s | 1.04 s | **3.17 s (×3.1)** |
| Endpoint match wait | 10.0 s | 9.2 s | 10.1 s |
| Echo replies delivered | 43 | 43 | 43 |

Notes:
- Measured intervals run ≈10 % below nominal in both conditions (3.6 s vs 4000 ms,
  0.9 s vs 1000 ms); the 4:1 ratio is preserved exactly, so the offset is a systematic
  clock/tick effect, not parameter noise.
- ESP32 = vendorId `0d.25` (embeddedRTPS 13.37), GUID prefix `01:02:03:…`;
  ROS2 = vendorId `01.0f` (eProsima FastDDS). Display filter: `rtps`.

### Finding 1 — Heartbeat period is a direct bandwidth/reactivity dial

Quartering `SF_WRITER_HB_PERIOD_MS` (4000→1000) multiplied ESP32 HEARTBEAT traffic
by 3.9 and total RTPS packets by 1.6, with **no functional difference** (same match
time, same 43/43 echo delivery). On a healthy link the extra heartbeats buy faster
loss detection but cost airtime/energy; at this message rate the baseline 4 s is ample.

### Finding 2 — SPDP period shapes discovery traffic, not steady-state matching

Tripling `SPDP_RESEND_PERIOD_MS` (1000→3000) stretched DATA(p) announcements
×3.1 as expected. Successful-path match latency was unchanged (~10 s in all
conditions — dominated by the SEDP exchange cadence, not SPDP). Side effect to
remember: participant-liveliness checks run every `SPDP_CYCLECOUNT_HEARTBEAT`
(=2) SPDP rounds, so slowing SPDP also slows remote-participant timeout detection.

### Finding 3 (serendipitous) — Sporadic post-reset SEDP re-sync deadlock

2 of 7 hardware runs (once at SPDP=1000, once at SPDP=3000 → **parameter-independent**)
stalled: the rebooted board never matched within its 70 s window. The capture shows a
textbook signature:

```
pre-reset  t≈0.6s  ESP32 SEDP ACKNACK count=6          (board mid-life, prefix a3ee…)
reset      t≈2s    the SAME prefix a3ee… reappears      (see root cause below)
post-reset t≈7s+   ESP32 SEDP ACKNACK count=1,2,3,…     (protocol counters restarted)
           t→67s   FastDDS: HEARTBEATs only — never retransmits SEDP DATA(r)/DATA(w)
```

**Root cause (corrected after wire-level falsification).** Our first hypothesis —
"the GUID prefix is a compile-time constant" — is wrong: `Domain::generateGuidPrefix()`
already randomizes the whole prefix. But on FreeRTOS it seeds `rand()` with
`xTaskGetTickCount()`, and the boot sequence is deterministic enough that the seed
(and therefore the entire "random" prefix) is drawn from a **tiny pool** and repeats
across boots. Wire evidence: boots at 18:38, 18:58, and 19:00 all drew the identical
prefix `a3eee366…`, while four other boots drew distinct values. When a reborn node
collides with a prefix for which the peer still holds reliable-stream state (the SPDP
lease announced by this node was 100 s), the restarted ACKNACK counts look like stale
duplicates, FastDDS never re-serves the SEDP endpoint data, and matching deadlocks.
`scripts/validation/qos_preflight.sh` retries up to 3 attempts, which had been
masking exactly this failure mode (a second reset re-rolls the seed).

### Fixes implemented and hardware-verified (2026-07-06/07)

| Fix | Where | Effect |
|---|---|---|
| GUID prefix from hardware RNG (`esp_random()` per byte) | `Domain.cpp: generateGuidPrefix()` | prefix pool 2^88 — cross-boot collision eliminated |
| Announced SPDP lease 100 s → 12 s | `platform/rtps/config.h` | peer drops a rebooted node's ghost in ~12 s instead of 100 s |
| Wi-Fi reconnect-forever after first association + `WIFI_PS_NONE` | `platform/wifi/wifi.c` | node no longer goes permanently dark after AP hiccups; idle reachability restored |

Verification on hardware:

```
8/8 consecutive reset→match cycles (echo host running throughout; pre-fix: 5/7)
9 boots → 9 distinct GUID prefixes on the wire
endpoint match wait: 8.7 s cold start; 0.4–0.9 s warm re-match
  (pre-fix: ~9–10 s in every condition — the 12 s lease removes ghost interference)
official 22-check bidirectional verification: PASS
idle ICMP loss: 10 % (pre-fix: 50–66 %); DDS RTT avg 20.7 ms, min 11.7 ms (pre-fix 21.9/15.0)
memory: 202,520 B free — no regression
```

## Run ledger

| # | Condition | Outcome |
|---|---|---|
| 1 | baseline (official `qos_verify`) | PASS, wait 9.3 s |
| 2 | baseline capture | PASS, wait 10.0 s |
| 3 | Exp‑A HB=1000 | PASS, wait 9.2 s |
| 4 | Exp‑B SPDP=3000 run 1 | **STALL** (no match ≥46 s) |
| 5 | Exp‑B SPDP=3000 run 2 | PASS, wait 10.1 s |
| 6 | restored baseline run 1 | **STALL** (no match ≥48 s) |
| 7 | restored baseline run 2 | PASS (restoration verified) |

## Artifacts (in `results/wireshark/`, kept out of version control — raw captures contain local IPs/MACs)

- `rtps_bidirectional_20260706_183830.pcapng` — baseline
- `expA_hb1000_20260706_184841.pcapng` — HB=1000
- `expB_spdp3000_20260706_185105.pcapng` — SPDP=3000, stalled run (deadlock evidence)
- `expB_run2_spdp3000_20260706_185546.pcapng` — SPDP=3000, passing run
- `restored_baseline_20260706_190021.pcapng` — baseline, stalled run
- `restored_baseline2_20260706_190324.pcapng` — baseline, passing (restoration proof)
- matching `*_serial.log` / `*_host.log` per run

## Reproduce

```bash
# 1. edit platform/rtps/config.h (one parameter)
# 2. QOS_VALIDATION_MONITOR=0 ./scripts/validation/qos_flash.sh all /dev/ttyUSB0
# 3. start echo host + tshark on eth1 + reset board (see scripts/validation/qos_verify.sh)
# 4. compare: tshark -r <pcap> -Y "ip.src==<esp32> && rtps.sm.id==0x07"   # heartbeats
#             tshark -r <pcap> -Y "rtps.sm.wrEntityId==0x000100c2"        # SPDP DATA(p)
```
