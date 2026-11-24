#!/usr/bin/env python3
"""ROS2 echo subscriber for step9 KEEP_ALL verification.

Subscribes to /step9_keep_all with KEEP_ALL history to verify
ESP32's KEEP_ALL implementation.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
    HistoryPolicy,
)
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import String


class KeepAllEchoNode(Node):
    def __init__(self):
        super().__init__('keep_all_echo_node')

        # Match ESP32's KEEP_ALL QoS
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_ALL,
            depth=10,  # Ignored for KEEP_ALL but set for compatibility
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.sub = self.create_subscription(
            String, '/step9_keep_all', self.callback, qos)

        self.rx_count = 0
        self.get_logger().info('KEEP_ALL echo node started')
        self.get_logger().info('  Subscribing: /step9_keep_all (KEEP_ALL, RELIABLE)')

    def callback(self, msg):
        self.rx_count += 1
        content = msg.data[:60] + '...' if len(msg.data) > 60 else msg.data

        if self.rx_count <= 5 or self.rx_count % 5 == 0:
            self.get_logger().info(f'RX [{self.rx_count:3d}]: {content}')


def main():
    rclpy.init()
    node = KeepAllEchoNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.get_logger().info(f'Total messages received: {node.rx_count}')
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
