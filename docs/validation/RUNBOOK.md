# mROS2-ESP32 QoS Hardware Validation Runbook

This runbook describes how to reproduce the real-hardware QoS validation workflow on Windows + WSL2.

## Goal

```text
ROS2 Humble runs in WSL2.
ESP32-S3 runs mROS2 firmware.
ESP32-S3 and ROS2 communicate over WiFi using DDS/RTPS.
USB serial is used only for flashing and observing ESP32 logs.
The validation path checks bidirectional communication and QoS evidence.
```

## Repository Setup

```bash
git clone https://github.com/hal-lab-u-tokyo/mROS2-QoS.git
cd mROS2-QoS
cp platform/wifi/wifi_secrets.example.h platform/wifi/wifi_secrets.h
```

Edit `platform/wifi/wifi_secrets.h` for the local network.

## Windows Firewall For WSL2 Mirrored Mode

Run once from an elevated Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "\\wsl.localhost\Ubuntu-22.04\home\your-user\mROS2-QoS\scripts\validation\wsl_firewall_admin.ps1"
```

This allows DDS/RTPS UDP ports `7400-7420` into WSL.

## USB Attachment

Windows PowerShell:

```powershell
Start-Process -FilePath wsl.exe -ArgumentList '-d Ubuntu-22.04 -- sleep 900' -WindowStyle Hidden
usbipd list
usbipd attach --wsl Ubuntu-22.04 --busid X-Y
usbipd list
```

Replace `X-Y` with the CP2102N BUSID.

WSL check:

```bash
ls -l /dev/ttyUSB0
```

## Build, Flash, And Preflight

WSL:

```bash
cd /home/your-user/mROS2-QoS
./scripts/validation/qos_ready.sh /dev/ttyUSB0 all
```

Required result:

```text
[verify] RESULT: PASS
[ready] RESULT: ALL PASS
```

## Manual Validation Windows

Terminal A, ROS2 host:

```bash
cd /home/your-user/mROS2-QoS
./scripts/validation/qos_host.sh all
```

Terminal B, ESP32 monitor:

```bash
cd /home/your-user/mROS2-QoS/workspace/qos_eval
source ~/esp-idf/export.sh
idf.py -p /dev/ttyUSB0 monitor
```

Terminal C, ROS2 QoS discovery:

```bash
source /opt/ros/humble/setup.bash
ros2 topic info /qos_eval --verbose
ros2 topic info /qos_eval_reply --verbose
```

## Evidence Interpretation

```text
TX proves ESP32 -> ROS2 traffic.
RX proves ROS2 -> ESP32 reply traffic.
RELIABLE on both topics is shown by ROS2 QoS discovery.
KEEP_LAST behavior and Resource Limits are shown by ESP32 logs.
Deadline, Lifespan, and Liveliness are shown by both discovery and focused log evidence.
```

## Scope Boundary

This project is an mROS2-ESP32 QoS extension prototype with real-hardware validation evidence. It is not a complete product-grade DDS QoS implementation.
