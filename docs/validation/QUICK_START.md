# Hardware Validation Quick Start

This file contains the shortest path for checking the mROS2-ESP32 QoS hardware workflow.

## Preconditions

```text
Windows 11 with WSL2 Ubuntu-22.04
ROS2 Humble installed in WSL
ESP-IDF installed in WSL
usbipd-win installed on Windows
ESP32-S3 connected over USB
ESP32-S3 and ROS2 host on the same WiFi/LAN
```

Create local WiFi credentials:

```bash
cp platform/wifi/wifi_secrets.example.h platform/wifi/wifi_secrets.h
```

Edit `platform/wifi/wifi_secrets.h` for the local network. This file is ignored by git.

## Windows USB/IP

In Windows PowerShell:

```powershell
Start-Process -FilePath wsl.exe -ArgumentList '-d Ubuntu-22.04 -- sleep 900' -WindowStyle Hidden
usbipd list
```

Attach the CP2102N USB-UART device to WSL:

```powershell
usbipd attach --wsl Ubuntu-22.04 --busid X-Y
usbipd list
```

Replace `X-Y` with the real BUSID shown by `usbipd list`.

## WSL Validation

In WSL:

```bash
cd /home/your-user/mROS2-QoS
ls -l /dev/ttyUSB0
test -f /opt/ros/humble/setup.bash && echo "ROS2 OK" || echo "ROS2 missing"
test -f ~/esp-idf/export.sh && echo "ESP-IDF OK" || echo "ESP-IDF missing"
./scripts/validation/qos_ready.sh /dev/ttyUSB0 all
```

Accept the run only when the output includes:

```text
[verify] RESULT: PASS
[ready] RESULT: ALL PASS
```

Optional reset stress check:

```bash
./scripts/validation/qos_reset_stress.sh 3 /dev/ttyUSB0 140
```

Accept the stress check only when the output includes:

```text
[stress] RESULT: PASS
```
