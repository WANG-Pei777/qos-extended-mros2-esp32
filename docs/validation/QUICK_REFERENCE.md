# Hardware Validation Command Reference

## USB/IP Status

Windows PowerShell:

```powershell
usbipd list
```

The ESP32-S3 CP2102N USB-UART bridge should be attached to WSL.

## ROS2 Host

WSL terminal A:

```bash
cd /home/your-user/mROS2-QoS
./scripts/validation/qos_host.sh all
```

Keep this process running while the ESP32 firmware is monitored.

## ESP32 Serial Monitor

WSL terminal B:

```bash
cd /home/your-user/mROS2-QoS/workspace/qos_eval
source ~/esp-idf/export.sh
idf.py -p /dev/ttyUSB0 monitor
```

After the monitor starts, reset the ESP32-S3 board.

Important hardware evidence:

```text
publisher matched with remote subscriber
subscriber matched with remote publisher
Warm-up reply confirmed
[ROS2 -> ESP32] Echo reply received
Deadline missed: YES
Lifespan check PASSED
Liveliness lease check PASSED
History cache: 5/5 samples
History KEEP_LAST enforcement PASSED
Rejected during burst
TX: 40 msgs
RX: nonzero
Packets Dropped:  0
All phases complete.
```

Exit the ESP-IDF monitor with:

```text
Ctrl + ]
```

## ROS2 QoS Discovery Evidence

WSL terminal C:

```bash
source /opt/ros/humble/setup.bash
ros2 topic info /qos_eval --verbose
ros2 topic info /qos_eval_reply --verbose
```

Expected QoS fields include:

```text
Reliability: RELIABLE
Durability: VOLATILE
History (Depth): UNKNOWN
Deadline: 23283064 nanoseconds
Lifespan: 2000000000 nanoseconds
Liveliness: AUTOMATIC
```

`Deadline` and `Lifespan` are expected on the reply path.
