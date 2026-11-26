# Measurement data

Processed results of the loss and late-join campaigns: per-run values,
per-condition statistics, and the series plotted in each figure. Every
condition has 30 runs; loss runs send 200 requests at 10 Hz.

Raw packet captures and board logs are not included (about 17 GB, and they
contain local network addresses).

## statistics/

`verified_statistics.csv` has one row per condition: runs, transmitted and
lost requests, aggregate loss (%), and the median, quartile deviation, min,
and max of the run-level p95 RTT (ms).

`computed_cells.json` holds the per-run values behind those rows. Each
condition maps to a list of 30 runs with `tx`, `rx`, `p95` (ms), and, for
the embedded systems, `cpu` (%), `heap` (KB), and `stack` (bytes). The
late-join conditions (`P0LJ_mros2_vol_ctl`, `P2_mros2_tl_kl1`,
`P3_mros2_tl_kl10`) instead record, per run, the history depth, the 40
pre-join samples, how many were retained, and how many were replayed.

Condition names read `<profile>_<system>_<link>`:

| part | values |
|------|--------|
| profile | P0 Reliable, P1 Best Effort, P4 upstream mros2-esp32 |
| system | `mros2` (this work), `microros`, `native` (two-host ROS 2), `upstream` |
| link | `clean`, `loss5`/`loss15` = injected one-way loss in % |
| direction | `h2b` host to board, `b2h` board to host; `a2b`/`b2a` for the two-host setup |

## figures/

| file | content |
|------|---------|
| `fig3_*` | P0 loss sweep (0, 5, 15 %): `*_loss` application loss, `*_latency` median run p95 RTT, per direction. Columns: x offset, value, and spread for each system. |
| `fig4_*` | Reliable vs Best Effort at 15 % loss, `fwd`/`rev`. Rows P0 and P1; columns: mROS 2 value and spread, then ROS 2 value and spread. |
| `fig5_*` | QoS-extended vs upstream mros2-esp32 at 15 % loss, per direction. |
| `table3_*` | Board CPU (%), heap (KB), and wire bytes under P0: mean and SD per system. |
| `table4_recovered.csv` | Late-join samples recovered for P0, P2, P3: mean and SD over 30 runs (40 pre-join samples). |
