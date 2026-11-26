# Parameter sweeps

Unattended sweeps over embeddedRTPS build parameters. For each value the
scripts edit `config.h`, rebuild and flash the board, run N tests while
tshark captures the traffic, and write per-run and aggregate statistics.

```
config.json          parameters and the values to sweep
param_sweep.sh       sweep one parameter
batch_test.sh        N repeated runs at one setting
run_single_test.sh   one run with a tshark capture
modify_param.py      edit a value in config.h
run_all_sweeps.sh    sweep the four core parameters in sequence
```

## Usage

```bash
./scripts/automation/param_sweep.sh heartbeat_period /dev/ttyUSB0 30
./scripts/automation/param_sweep.sh history_size /dev/ttyUSB0 30
./scripts/automation/run_all_sweeps.sh
```

The last argument is the number of runs per value (default 30). One
heartbeat sweep takes about 3 hours; all four parameters take about 15.
Rerunning the same command after Ctrl+C continues from the next value.

Swept values are set in `config.json`, for example:

```json
"heartbeat_period": { "values": [100, 500, 1000, 2000, 4000, 8000], "default": 4000 },
"history_size":     { "values": [3, 5, 10, 20, 30, 50],             "default": 10 }
```

`test_config.capture_duration` sets the length of one run (default 75 s).

## Output

```
results/param_sweep/<parameter>/<value>/
  test_runK.pcapng        capture
  test_runK_serial.log    board serial log
  test_runK_stats.json    per-run statistics
  test_summary.csv        all runs
  test_aggregate.json     mean and standard deviation
```

Useful Wireshark filters: HEARTBEAT `rtps.sm.id == 0x07`, ACKNACK
`rtps.sm.id == 0x06`.

## Requirements

- ESP32-S3 on `/dev/ttyUSB0` (user in the `dialout` group)
- ESP-IDF environment loaded
- tshark with capture rights:
  `sudo setcap cap_net_raw,cap_net_admin=eip $(which tshark)`
- ROS 2 Humble sourced
- About 50 GB of free disk (one capture is roughly 100 MB)
