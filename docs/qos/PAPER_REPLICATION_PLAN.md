# Paper Replication Plan
## "Optimizing Communication in ROS 2 With QoS Parameters for System Advantages"

**Date Created**: 2026-06-17  
**Paper Authors**: Utpal Kumar et al., Dayananda Sagar University  
**Conference**: 2025 IEEE Space, Aerospace and Defence Conference

---

## Executive Summary

This document outlines a practical replication plan for the paper's core concepts using the existing mROS2-QoS infrastructure. The paper demonstrates QoS parameter optimization in a Mars rover control system (Project Makardhwaj). We will adapt the key findings to validate QoS behavior on ESP32 hardware.

**Key Insight from Paper**: Different subsystems require different QoS configurations - no "one-size-fits-all" approach.

---

## Paper's System Architecture

### Nodes Defined in Paper

| Node Name | Function | Critical QoS Needs |
|-----------|----------|-------------------|
| DriveSystem | Controls driving motors | Reliable, latest data only |
| Manipulator | Controls arm joints | Reliable commands, best-effort feedback |
| ABEx | Scientific experiments | Reliable commands & data storage |
| CamFeedTransmitor | Transmits camera feed | Low latency, best-effort |
| Telemetry | GNSS/IMU data | Reliable, latest data |
| AutonomousDrive | Autonomous navigation | Reliable sensor data |
| CentralUX | Command center | Mixed requirements |

---

## QoS Configuration Matrix from Paper

### Critical Configurations

#### High-Priority Reliable (Drive Control Pattern)
```
Topic: /Drive, /TestActuate, /TestActuateFeedback
Reliability: RELIABLE
Durability: VOLATILE
History: KEEP_LAST(10)
Liveliness: MANUAL_BY_TOPIC
```
**Rationale**: Commands must arrive, but only latest matters. Prevents old commands from executing after network recovery.

#### Persistent Data Storage Pattern
```
Topic: /TestData
Reliability: RELIABLE
Durability: TRANSIENT_LOCAL
History: KEEP_ALL
Liveliness: MANUAL_BY_TOPIC
```
**Rationale**: Experimental data is the mission's core purpose - must be complete and persistent.

#### Low-Latency Stream Pattern
```
Topic: /CamFeed
Reliability: BEST_EFFORT
Durability: VOLATILE
History: KEEP_LAST
Liveliness: AUTOMATIC
```
**Rationale**: Video streaming prioritizes low latency over completeness. Dropped frames acceptable.

#### Observable Feedback Pattern
```
Topic: /ArmFeedback
Reliability: BEST_EFFORT
Durability: VOLATILE
History: KEEP_LAST(10)
Liveliness: AUTOMATIC
```
**Rationale**: Visual confirmation available via camera, so unreliable transport acceptable.

---

## Mapping to mROS2-QoS Project

### Current mROS2-QoS Capabilities

**Already Validated** (from QOS_IMPLEMENTATION_STATUS.md):
- ✅ Reliability: RELIABLE uplink ESP32→ROS2
- ✅ Durability: VOLATILE + TRANSIENT_LOCAL with late-joiner
- ✅ History: KEEP_LAST(depth) enforcement
- ✅ Liveliness: AUTOMATIC mode with lease tracking
- ⚠️ Liveliness: MANUAL_BY_TOPIC not yet supported
- ✅ Resource Limits: Basic enforcement

**Gap Analysis**:
- Paper uses MANUAL_BY_TOPIC extensively
- Paper requires bidirectional scenarios (command + feedback)
- Paper claims performance improvements (latency, packet loss) - we need metrics

---

## Replication Strategy

### Phase 1: Baseline QoS Patterns (3 days)

**Objective**: Implement and validate the 4 core QoS patterns from the paper

#### Test 1: Drive Control Pattern
- **Setup**: ESP32 subscriber (motor controller) + ROS2 publisher (control station)
- **QoS**: RELIABLE + VOLATILE + KEEP_LAST(10)
- **Validation**: 
  - Verify all commands arrive
  - Verify old commands discarded when queue full
  - Measure latency

#### Test 2: Persistent Data Pattern
- **Setup**: ESP32 publisher (sensor) + ROS2 subscriber (data logger)
- **QoS**: RELIABLE + TRANSIENT_LOCAL + KEEP_ALL
- **Validation**:
  - Late-joining subscriber receives all historical data
  - Data survives network interruption
  - Memory usage monitoring

#### Test 3: Low-Latency Stream Pattern
- **Setup**: ESP32 publisher (camera sim) + ROS2 subscriber (viewer)
- **QoS**: BEST_EFFORT + VOLATILE + KEEP_LAST
- **Validation**:
  - Measure end-to-end latency
  - Compare with RELIABLE configuration
  - Frame drop rate under load

#### Test 4: Observable Feedback Pattern
- **Setup**: ESP32 publisher (actuator status) + ROS2 subscriber (monitor)
- **QoS**: BEST_EFFORT + VOLATILE + KEEP_LAST(10)
- **Validation**:
  - Measure bandwidth usage vs RELIABLE
  - Acceptable data loss rate

### Phase 2: Multi-Node Architecture (1 week)

**Objective**: Create simplified rover-like system with multiple subsystems

#### Simulated Rover System
```
[ROS2 Control Station]
    ↓ /drive_cmd (RELIABLE, VOLATILE, KEEP_LAST 10)
[ESP32 Drive Controller]
    ↓ /drive_feedback (RELIABLE, VOLATILE, KEEP_LAST 10)
[ROS2 Control Station]

[ROS2 Control Station]
    ↓ /experiment_cmd (RELIABLE, VOLATILE, KEEP_LAST 10)
[ESP32 Experiment Module]
    ↓ /experiment_data (RELIABLE, TRANSIENT_LOCAL, KEEP_ALL)
[ROS2 Data Logger]

[ESP32 Telemetry]
    ↓ /telemetry (RELIABLE, VOLATILE, KEEP_LAST)
[ROS2 Monitor]

[ESP32 Camera Simulator]
    ↓ /camera_feed (BEST_EFFORT, VOLATILE, KEEP_LAST)
[ROS2 Viewer]
```

#### Success Metrics
- All 4 subsystems operating concurrently
- Network bandwidth < sum of individual streams (multiplexing benefit)
- No interference between subsystems
- Each subsystem maintains its QoS guarantees

### Phase 3: Performance Characterization (1 week)

**Objective**: Quantify the benefits claimed in the paper

#### Metrics to Measure

1. **Latency Reduction**
   - BEST_EFFORT vs RELIABLE for video stream
   - Expected: 20-50% reduction

2. **Bandwidth Utilization**
   - Optimized QoS vs default (all RELIABLE)
   - Expected: 15-30% reduction

3. **Packet Loss**
   - RELIABLE critical data: 0% loss
   - BEST_EFFORT streams: <5% loss acceptable

4. **CPU/Memory Usage**
   - KEEP_LAST(10) vs KEEP_ALL
   - VOLATILE vs TRANSIENT_LOCAL

#### Test Scenarios

**Scenario A: Normal Operation**
- Baseline performance under ideal conditions

**Scenario B: Network Congestion**
- Introduce artificial delay/packet loss
- Verify QoS priorities maintained

**Scenario C: Late Joiner**
- Subscriber joins after data transmission starts
- TRANSIENT_LOCAL delivers history

**Scenario D: Network Interruption**
- Temporary disconnect/reconnect
- RELIABLE ensures recovery
- KEEP_LAST prevents buffer overflow

---

## Implementation Plan

### Directory Structure
```
workspace/
├── paper_replication/
│   ├── README.md                    # Overview and quick start
│   ├── test1_drive_control/         # Drive control pattern
│   │   ├── esp32/
│   │   │   └── main.cpp
│   │   └── ros2/
│   │       └── control_station.py
│   ├── test2_persistent_data/       # Data storage pattern
│   │   ├── esp32/
│   │   │   └── main.cpp
│   │   └── ros2/
│   │       └── data_logger.py
│   ├── test3_lowlatency_stream/     # Video stream pattern
│   │   ├── esp32/
│   │   │   └── main.cpp
│   │   └── ros2/
│   │       └── viewer.py
│   ├── test4_observable_feedback/   # Feedback pattern
│   │   ├── esp32/
│   │   │   └── main.cpp
│   │   └── ros2/
│   │       └── monitor.py
│   └── integrated_rover/            # Multi-node system
│       ├── esp32_drive/
│       ├── esp32_experiment/
│       ├── esp32_telemetry/
│       ├── esp32_camera/
│       └── ros2_station/
├── scripts/
│   └── paper_replication/
│       ├── benchmark_patterns.sh    # Run all benchmarks
│       ├── measure_latency.py       # Latency measurement tool
│       ├── measure_bandwidth.py     # Bandwidth measurement tool
│       └── network_stress.sh        # Introduce artificial issues
└── docs/
    └── qos/
        ├── PAPER_REPLICATION_PLAN.md         # This file
        ├── PAPER_REPLICATION_RESULTS.md      # Results and findings
        └── PAPER_COMPARISON.md               # Paper claims vs our results
```

### Code Template: Drive Control Pattern

#### ESP32 Side (Subscriber)
```cpp
// workspace/paper_replication/test1_drive_control/esp32/main.cpp
#include "mros2.h"

void app_main() {
    mros2_init(0, NULL);
    
    // Paper's Drive Control QoS Profile
    mROS2QoSProfile qos;
    qos.reliability = MROS2_RELIABILITY_RELIABLE;
    qos.durability = MROS2_DURABILITY_VOLATILE;
    qos.history = MROS2_HISTORY_KEEP_LAST;
    qos.depth = 10;  // Paper uses depth 10
    // Note: MANUAL_BY_TOPIC not yet supported, use AUTOMATIC
    qos.liveliness = MROS2_LIVELINESS_AUTOMATIC;
    qos.liveliness_lease_duration = {5, 0};
    
    auto sub = mros2_create_subscriber_qos(
        "drive_cmd",
        MROS2_MSG_TYPE_GEOMETRY_MSGS__TWIST,
        qos
    );
    
    while (1) {
        Twist msg;
        if (mros2_take(sub, &msg)) {
            // Execute drive command
            ESP_LOGI("DRIVE", "Command: linear=%.2f, angular=%.2f",
                     msg.linear.x, msg.angular.z);
            
            // Simulate motor control
            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }
}
```

#### ROS2 Side (Publisher)
```python
# workspace/paper_replication/test1_drive_control/ros2/control_station.py
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Twist

class ControlStation(Node):
    def __init__(self):
        super().__init__('control_station')
        
        # Paper's Drive Control QoS Profile
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        self.publisher = self.create_publisher(Twist, 'drive_cmd', qos)
        self.timer = self.create_timer(0.1, self.publish_command)
        self.count = 0
        
    def publish_command(self):
        msg = Twist()
        msg.linear.x = 1.0
        msg.angular.z = 0.5
        self.publisher.publish(msg)
        self.count += 1
        if self.count % 10 == 0:
            self.get_logger().info(f'Published {self.count} commands')

def main():
    rclpy.init()
    node = ControlStation()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
```

---

## Expected Outcomes

### Quantitative Goals

1. **Latency**:
   - BEST_EFFORT stream: <100ms end-to-end
   - RELIABLE command: <200ms end-to-end

2. **Reliability**:
   - RELIABLE topics: 100% delivery
   - BEST_EFFORT topics: >95% delivery under normal conditions

3. **Bandwidth**:
   - Optimized QoS: 20-30% reduction vs all-RELIABLE
   - Per the paper's claim

4. **Scalability**:
   - 4+ concurrent subsystems without degradation

### Qualitative Goals

1. Demonstrate clear use cases for each QoS pattern
2. Provide reusable templates for future development
3. Document trade-offs for each configuration
4. Validate paper's architectural principles

---

## Known Limitations

### Hardware Constraints
- ESP32 memory limits KEEP_ALL scenarios
- WiFi latency higher than wired Ethernet in paper
- Single ESP32 vs distributed rover in paper

### Software Gaps
- MANUAL_BY_TOPIC liveliness not yet supported
- Need to use AUTOMATIC as substitute
- May affect some test scenarios

### Scope Differences
- Paper: Real Mars rover with multiple hardware modules
- Our replication: Simulated subsystems on single ESP32
- Focus on QoS behavior validation, not robotics control

---

## Success Criteria

### Minimum Viable Replication (Phase 1)
- ✅ All 4 QoS patterns implemented
- ✅ Basic validation passed
- ✅ Documentation complete

### Full Replication (Phase 2)
- ✅ Multi-subsystem integration working
- ✅ Performance measurements collected
- ✅ Results compared with paper's claims

### Research Contribution (Phase 3)
- ✅ Extended to embedded ESP32 context
- ✅ Identified embedded-specific considerations
- ✅ Published results or technical report

---

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1: Basic Patterns | 3 days | 4 test cases validated |
| Phase 2: Integration | 1 week | Multi-node rover simulation |
| Phase 3: Performance | 1 week | Benchmark results document |
| **Total** | **~2.5 weeks** | **Complete replication** |

---

## Next Steps

1. **Immediate**: Create workspace structure
2. **Day 1**: Implement Test 1 (Drive Control)
3. **Day 2**: Implement Tests 2-4
4. **Day 3**: Baseline validation
5. **Week 2**: Multi-node integration
6. **Week 3**: Performance characterization

---

## References

- Paper: "Optimizing Communication in ROS 2 With QoS Parameters for System Advantages" (2025)
- Location: `docs/papers/related-work/`
- Project Status: `docs/qos/QOS_IMPLEMENTATION_STATUS.md`
- Existing Tests: `workspace/`
