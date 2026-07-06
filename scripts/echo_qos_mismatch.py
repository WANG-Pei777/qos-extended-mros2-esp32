#!/usr/bin/env python3
"""ROS2 node for step11 QoS mismatch testing.

This node acts as the counterpart for ESP32's QoS mismatch tests.
It does NOT subscribe or publish - the ESP32 tests itself using
internal pub/sub on different topics.

This node is just for monitoring and validation.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import String
import sys


class QoSMismatchMonitor(Node):
    def __init__(self):
        super().__init__('qos_mismatch_monitor')

        self.get_logger().info('QoS Mismatch Test Monitor started')
        self.get_logger().info('Monitoring ESP32 step11 QoS mismatch tests...')
        self.get_logger().info('')
        self.get_logger().info('Expected tests on ESP32:')
        self.get_logger().info('  Test 1: RELIABLE pub + BEST_EFFORT sub → MATCH ✅')
        self.get_logger().info('  Test 2: BEST_EFFORT pub + RELIABLE sub → REJECT ❌')
        self.get_logger().info('  Test 3: VOLATILE pub + TRANSIENT_LOCAL sub → MATCH ⚠️')
        self.get_logger().info('  Test 4: TRANSIENT_LOCAL pub + VOLATILE sub → MATCH ⚠️')
        self.get_logger().info('')
        self.get_logger().info('Check ESP32 serial output for test results.')


def main():
    rclpy.init()
    node = QoSMismatchMonitor()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
