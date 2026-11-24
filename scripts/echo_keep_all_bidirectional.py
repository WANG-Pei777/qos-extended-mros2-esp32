#!/usr/bin/env python3
"""ROS2 echo node for step9b KEEP_ALL bidirectional test.

This node:
1. Subscribes to /from_esp32 to receive ESP32's KEEP_ALL messages
2. Publishes messages to /to_esp32 for ESP32 to receive with KEEP_ALL

Tests full bidirectional KEEP_ALL history behavior.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import String
import time


class KeepAllBidirectional(Node):
    def __init__(self):
        super().__init__('keep_all_bidirectional')

        # KEEP_ALL QoS for both pub and sub
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_ALL,
            depth=10,  # Ignored for KEEP_ALL but set for compatibility
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        # Create publisher
        self.pub = self.create_publisher(String, '/to_esp32', qos)

        # Create subscriber
        self.sub = self.create_subscription(
            String, '/from_esp32', self.callback, qos)

        self.rx_count = 0
        self.tx_count = 0

        self.get_logger().info('KEEP_ALL bidirectional test started')
        self.get_logger().info('  Subscribing: /from_esp32 (KEEP_ALL)')
        self.get_logger().info('  Publishing:  /to_esp32 (KEEP_ALL)')
        self.get_logger().info('')

        # Start publishing thread
        self.timer = self.create_timer(0.5, self.publish_callback)

    def callback(self, msg):
        self.rx_count += 1
        content = msg.data[:60] + '...' if len(msg.data) > 60 else msg.data

        if self.rx_count <= 5 or self.rx_count % 5 == 0:
            self.get_logger().info(f'RX from ESP32 [{self.rx_count:3d}]: {content}')

        # Report if we see resource rejection indicators
        if 'rejected' in msg.data.lower() or 'reject' in msg.data.lower():
            self.get_logger().warn(f'ESP32 reported resource rejection: {content}')

    def publish_callback(self):
        if self.tx_count < 20:  # Publish 20 messages
            msg = String()
            msg.data = f'[ROS2] KEEP_ALL test message #{self.tx_count} at {time.time()}'
            self.pub.publish(msg)
            self.tx_count += 1

            if self.tx_count <= 5 or self.tx_count % 5 == 0:
                self.get_logger().info(f'TX to ESP32 [{self.tx_count:3d}]')

        elif self.tx_count == 20:
            self.tx_count += 1  # Prevent repeated logging
            self.get_logger().info('')
            self.get_logger().info('Finished publishing 20 messages to ESP32')
            self.get_logger().info('Waiting for ESP32 responses...')


def main():
    rclpy.init()
    node = KeepAllBidirectional()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('')
        node.get_logger().info('=== Final Statistics ===')
        node.get_logger().info(f'  TX to ESP32: {node.tx_count - 1}')
        node.get_logger().info(f'  RX from ESP32: {node.rx_count}')
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
