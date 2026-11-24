#!/usr/bin/env python3
"""ROS2 echo reply node for step10 BEST_EFFORT performance test.

Bidirectional communication:
- Subscribes: /step10_best_effort (BEST_EFFORT)
- Publishes: /step10_best_effort_reply (BEST_EFFORT)
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


class BestEffortEchoNode(Node):
    def __init__(self):
        super().__init__('best_effort_echo_node')

        # BEST_EFFORT QoS for both pub and sub
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.sub = self.create_subscription(
            String, '/step10_best_effort', self.callback, qos)

        self.pub = self.create_publisher(
            String, '/step10_best_effort_reply', qos)

        self.rx_count = 0
        self.tx_count = 0
        self.get_logger().info('BEST_EFFORT echo node started')
        self.get_logger().info('  Subscribing: /step10_best_effort (BEST_EFFORT)')
        self.get_logger().info('  Publishing:  /step10_best_effort_reply (BEST_EFFORT)')

    def callback(self, msg):
        self.rx_count += 1

        # Echo back the message
        reply = String()
        reply.data = f'[ECHO] #{self.tx_count} {msg.data}'
        self.pub.publish(reply)
        self.tx_count += 1

        if self.rx_count <= 3 or self.rx_count % 10 == 0:
            content = msg.data[:50] + '...' if len(msg.data) > 50 else msg.data
            self.get_logger().info(f'RX [{self.rx_count:3d}] TX [{self.tx_count:3d}]: {content}')


def main():
    rclpy.init()
    node = BestEffortEchoNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.get_logger().info(f'Total RX: {node.rx_count}, TX: {node.tx_count}')
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
