# Seven-QoS Mechanism Protocol Amendment 01

Status: pre-data amendment for the replacement v2 campaign

## Trigger

The sealed v1 campaign stopped at `DUR-VOL-LATE` after three retained,
nonfatal failures. In every attempt, the late Volatile reader received the
three pre-join samples (`A`, `B`, and `C`) plus the post-join sample (`Z`).
The frozen oracle required exactly one delivery, `Z`.

This was a deterministic implementation defect, not an execution or network
failure. The v1 protocol, failed campaign, and failed audit remain immutable
and excluded from the replacement formal result.

## Amendment

The writer now discards history produced with no matched reader when its first
reader matches and the offered durability is Volatile. Transient Local history
is retained. History associated with an already active reader set is also
retained. A host-side policy test covers all three branches.

The campaign runner also writes a terminal `FAILED` campaign manifest before
stopping on a fatal attempt or attempt exhaustion. This changes bookkeeping
only; it does not change a case oracle or retry limit.

Two ACK-release harnesses (`HIST-PBUF-RELEASE` and `RES-RECOVERY`) now wait for
their reader before filling history. A board-side transmission hold makes the
fill and capacity rejection atomic; releasing the hold then exposes the same
ACK-driven release mechanism named by the original claims. This prevents the
correct Volatile first-reader cleanup from replacing the intended ACK oracle.

## Frozen Invariants

- The 36 claim statements and their levels are unchanged.
- The 27 unit-oracle bindings and 32 hardware-case IDs are unchanged.
- Case order, payloads, timeouts, host timing, retry limit, and PCAP policy are
  unchanged. Board sequencing changed only for the two ACK-release harnesses
  described above.
- No v1 observation is reused as a passing v2 observation.
- No deterministic observation is pooled as performance, latency, loss,
  energy, or resource data.

## Bound Evidence

- Frozen-flash execution-mode smoke tree: `84d08c2646bd21fbeb363d7e01a282f161bbe2f3725728d89aafa7a1d218e8d8`
- v1 protocol tree: `9bae25c05c26ffa349d3e26afd17d9a910284b51959a4532aae893ad480b2a3e`
- v1 failed campaign tree: `e97c557501adb180e2113606fbbda1a27cf9cb0b4a209efee69ec30b6d04e7f6`
- v1 failed audit tree: `ead35e84261edc8fd75a4653ae9f8b5e90272dd4d0bd4e402d6e88a850623f8a`
- Volatile fix smoke tree: `f21c6ce7c86206b7f9c39ab286cbfab99d688ebb2224d4919cea0c4696e6cf2e`
- Transient Local regression smoke tree: `e24f6b607cba65cc3e272ea40643fb9d44d3b4acd05277994b408947c97cb455`
- ACK-driven history/pbuf release smoke tree: `289f3bcb922eec9086f5cca8f8595ae458db7e7192d08d44f939faf6637fcdc6`
- ACK-driven resource recovery smoke tree: `6d16bf47a58edcc2ef1f0abd662fc6c8d515ce78a7e8ed6e098df55f15c171c1`

The replacement v2 protocol must bind the release-verification files for all
of these trees before collecting any v2 formal observation.
