#!/usr/bin/env python3
"""ROS2 echo node for step8b TRANSIENT_LOCAL bidirectional test.

This node:
1. Publishes 8 cached messages to /to_esp32 BEFORE ESP32 connects
2. Subscribes to /from_esp32 to receive ESP32's cached messages

Tests full bidirectional TRANSIENT_LOCAL durability.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import String
import time


class TransientLocalBidirectional(Node):
    def __init__(self):
        super().__init__('transient_local_bidirectional')

        # TRANSIENT_LOCAL QoS for both pub and sub
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        # Create publisher FIRST and publish cached messages
        self.pub = self.create_publisher(String, '/to_esp32', qos)
        self.get_logger().info('TRANSIENT_LOCAL bidirectional test started')
        self.get_logger().info('')

        # Wait for publisher to establish
        time.sleep(2)

        # Publish 8 cached messages BEFORE ESP32 starts
        self.get_logger().info('Publishing 8 cached messages (BEFORE ESP32 connects)...')
        for i in range(8):
            msg = String()
            msg.data = f'[CACHED] ROS2 message #{i} published at {time.time()}'
            self.pub.publish(msg)
            self.get_logger().info(f'  Published cached message {i+1}/8')
            time.sleep(0.1)

        self.get_logger().info('All cached messages published')
        self.get_logger().info('')
        self.get_logger().info('Waiting for ESP32 to start and receive cached messages...')
        self.get_logger().info('Also subscribing to ESP32\'s cached messages on /from_esp32')
        self.get_logger().info('')

        # Create subscriber to receive ESP32's cached messages
        self.sub = self.create_subscription(
            String, '/from_esp32', self.callback, qos)

        self.rx_count = 0
        self.cached_count = 0
        self.post_match_count = 0

    def callback(self, msg):
        self.rx_count += 1

        if '[CACHED]' in msg.data:
            self.cached_count += 1
            self.get_logger().info(f'RX CACHED from ESP32 [{self.cached_count}]: {msg.data[:60]}')
        elif '[POST_MATCH]' in msg.data:
            self.post_match_count += 1
            if self.post_match_count <= 3:
                self.get_logger().info(f'RX POST_MATCH from ESP32 [{self.post_match_count}]: {msg.data[:60]}')

        # Report summary after receiving several messages
        if self.rx_count == 10:
            self.get_logger().info('')
            self.get_logger().info('=== ROS2 Reception Summary ===')
            self.get_logger().info(f'  Total RX: {self.rx_count}')
            self.get_logger().info(f'  Cached RX: {self.cached_count}')
            self.get_logger().info(f'  Post-match RX: {self.post_match_count}')
            if self.cached_count >= 8:
                self.get_logger().info('  ✅ Received all cached messages from ESP32!')
            else:
                self.get_logger().warn(f'  ⚠️  Only received {self.cached_count}/8 cached messages')


def main():
    rclpy.init()
    node = TransientLocalBidirectional()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('')
        node.get_logger().info('=== Final Statistics ===')
        node.get_logger().info(f'  Total messages from ESP32: {node.rx_count}')
        node.get_logger().info(f'  Cached messages from ESP32: {node.cached_count}')
        node.get_logger().info(f'  Post-match messages: {node.post_match_count}')
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
