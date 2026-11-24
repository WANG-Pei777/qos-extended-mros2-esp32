# Seven-QoS Performance Protocol Amendment 13

Status: ACTIVE PRE-DATA WORKLOAD BINDING
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment makes every workload constant required to build and execute the
51 Seven-QoS cells explicit before formal collection. No formal performance row
has been collected or accepted.

## Frozen Workload Constants

- Every measurement window is 20,000 ms.
- History/Depth uses 64-byte payloads at 50 Hz.
- Durability uses 64-byte payloads at 50 Hz and attempts 10 pre-join samples.
- Deadline uses 512-byte payloads; its publish rate is derived exactly from the
  cell's 20 ms or 100 ms publish period.
- Lifespan uses 512-byte payloads at 50 Hz.
- Liveliness uses 512-byte payloads at 50 Hz.
- Resource Limits uses its cell-specific payload and rate and a 1,000 ms
  host-to-board ACK-suppression episode.

The Durability pre-join attempt count is held at 10 for every cell. KEEP_LAST
cache depth therefore changes retained/replayed history rather than changing
the number of samples offered before the reader joins.

## Schedule Consequence

The constants are part of each cell's canonical fixed configuration. The
expanded schedule SHA-256 must therefore be regenerated and rebound before any
formal launch. The randomization seed, family order, cell IDs, factor levels,
10 visits, three accepted replicates per visit, 30 accepted runs per cell, and
1,530-run total are unchanged.

The superseded no-data draft schedule SHA-256 was
`3e76421e2c07869df73e76663c80084f875ab8cbbcabaf7d52fc7a46e4309abe`.
The corrected schedule SHA-256 is
`3326942f48098fc0adfb0fdee03a81574add6b34ad34c0b30337078aa9734d09`.

Amendment 12 remains controlling for the separation between the stable
per-cell firmware token and the unique per-attempt campaign identity.

## Evidence Boundary

This is a transparent pre-data protocol correction. Existing compatibility,
mechanism, smoke, and native single-host pilot evidence retains its original
classification and is not promoted into the formal performance campaign.
Energy remains `deferred_not_collected`.
