# P4 Independent-Window Execution Runbook

This runbook executes the design frozen in
`P4_INDEPENDENT_WINDOW_PREREGISTRATION.md` and its 2026-07-15 precollection
Wi-Fi startup and mode-aware history smoke amendments. Do not collect before
2026-07-15 00:00 Asia/Tokyo, reuse the pre-gate WSL session, or change the
commands after inspecting P4 outcomes.

## 1. Open The New Window

After the earliest date, restart WSL from PowerShell with `wsl --shutdown`,
start Ubuntu again, and re-associate or restart the dedicated AP/board network
path. Then enter the repository and load ESP-IDF:

```bash
cd ~/mROS2-QoS
source "$HOME/esp-idf/export.sh"
```

Use one immutable result identifier for every subsequent command:

```bash
export P4_RESULTS_ID=20260715_p4_independent
export P4_FIRMWARE_SET="$PWD/results/experiments/20260715_p4_firmware_set_amended"
export P4_RESULTS="$PWD/results/experiments/$P4_RESULTS_ID"
```

The preferred unattended entry point executes every section below in order and
stops immediately on the first failure:

```bash
python3 scripts/experiment/run_p4_pipeline.py \
  --firmware-set "$P4_FIRMWARE_SET" \
  --results-id "$P4_RESULTS_ID" \
  --serial-port /dev/ttyUSB0 \
  --board-ip 192.0.2.1 \
  --interface eth1 \
  --new-window-ack \
  --network-reassociated-ack
```

The remaining commands document the same pipeline as separately restartable
stages for audit and recovery.

Open the window and run three exact-binary smoke repetitions per QoS mode:

```bash
python3 scripts/experiment/run_p4_smoke_gates.py \
  --firmware-set "$P4_FIRMWARE_SET" \
  --results-id "$P4_RESULTS_ID" \
  --serial-port /dev/ttyUSB0 \
  --board-ip 192.0.2.1 \
  --interface eth1 \
  --new-window-ack \
  --network-reassociated-ack
```

Expected time: approximately 10-15 minutes. Do not continue unless
`window_manifest.json` reports `PASS` and six passing smoke runs.

## 2. Formal Collection

```bash
python3 scripts/experiment/run_p4_formal.py \
  --firmware-set "$P4_FIRMWARE_SET" \
  --results-id "$P4_RESULTS_ID" \
  --window-manifest "$P4_RESULTS/window_manifest.json" \
  --serial-port /dev/ttyUSB0 \
  --board-ip 192.0.2.1 \
  --interface eth1
```

The frozen schedule contains 60 visits and 180 accepted runs. With a 75-second
serial window per attempt, host setup, link gates, captures, and 60 verified
flashes, expected wall time is approximately 4.5-5.5 hours. The executor is
restartable at completed visit boundaries. It retains rejected attempts and
never uses RTT or delivery values as acceptance criteria.

## 3. Audit

```bash
mkdir -p "$P4_RESULTS/analysis"
python3 scripts/experiment/audit_p4_formal.py "$P4_RESULTS" \
  --output "$P4_RESULTS/analysis/formal_audit_report.json"
```

Do not analyze unless the audit reports `PASS`, 180 accepted runs, 30 per cell,
60 passing visits, and 180 unique PCAP and `tc` hashes.

## 4. Confirmatory And Wire Analysis

```bash
python3 scripts/experiment/analyze_p4_complete.py "$P4_RESULTS" \
  --audit-report "$P4_RESULTS/analysis/formal_audit_report.json" \
  --output-dir "$P4_RESULTS/analysis/confirmatory_92e5218" \
  --bootstrap-samples 10000 \
  --seed 20260715

python3 scripts/experiment/analyze_p4_wire.py "$P4_RESULTS" \
  --audit-report "$P4_RESULTS/analysis/formal_audit_report.json" \
  --window-manifest "$P4_RESULTS/window_manifest.json" \
  --board-ip 192.0.2.1 \
  --output-dir "$P4_RESULTS/analysis/wire_92e5218"
```

The confirmatory family is exactly six contrasts. The wire output is secondary
packet-level evidence; ingress capture may precede `tc` drop and must not be
described as standalone proof of retransmission.

## 5. Seal The Result Tree

After audit and both analyses complete, seal the immutable release tree:

```bash
python3 scripts/experiment/seal_result_tree.py "$P4_RESULTS"
python3 scripts/experiment/verify_result_tree_seal.py "$P4_RESULTS"
```

Record the result-tree digest, file-manifest digest, acceptance-ledger digest,
design digest, firmware hashes, harness commit, and analysis commit in the paper
artifact appendix. Keep all captures; manual Wireshark inspection is optional,
while the scripted `tshark` extraction is the quantitative source of record.
