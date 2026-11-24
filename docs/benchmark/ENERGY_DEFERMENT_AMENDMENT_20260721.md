# Energy Measurement Deferral Amendment

**Frozen at:** 2026-07-21 Asia/Tokyo

## Change

Energy consumption is deferred as a secondary metric. It is not a blocking gate
for the non-energy Seven-QoS deterministic cases or performance outcomes.

## Reason

No external calibrated power monitor and GPIO marker alignment are currently
available. Starting formal collection without those instruments would prevent
energy traces from being collected, but it would not invalidate the independent
functional, delivery, latency, CPU, heap, or stack outcomes.

## Boundary

The current campaign may collect delivery, RTT, CPU utilization, heap, stack
high-watermark, wire, and state-transition outcomes. No energy conclusion or
energy advantage claim is permitted for these runs.

After a calibrated monitor and GPIO alignment are available, energy will be
measured in a separate supplementary campaign focused on resource pressure,
payload size, publish rate, and selected matched-system conditions.

The amendment does not modify the frozen P4 or three-system result trees.
