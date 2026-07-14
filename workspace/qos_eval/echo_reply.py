#!/usr/bin/env python3
"""ROS2 echo reply node for step7 QoS latency measurement.

Subscribes to /qos_eval, extracts timestamp, replies to
/qos_eval_reply with "[ECHO] #N <timestamp_us>" format.
"""

import os

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.qos import (
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
    HistoryPolicy,
)
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import String
import time


class EchoReplyNode(Node):
    def __init__(self):
        super().__init__('echo_reply_node')

        reliability_label = os.environ.get(
            'QOS_REPLY_RELIABILITY', 'RELIABLE'
        ).upper()
        reliability_by_label = {
            'RELIABLE': ReliabilityPolicy.RELIABLE,
            'BEST_EFFORT': ReliabilityPolicy.BEST_EFFORT,
        }
        try:
            reliability = reliability_by_label[reliability_label]
        except KeyError as exc:
            raise ValueError(
                'QOS_REPLY_RELIABILITY must be RELIABLE or BEST_EFFORT'
            ) from exc

        # Use one mode for both directions so endpoint compatibility is explicit.
        sub_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=reliability,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.sub = self.create_subscription(
            String, '/qos_eval', self.callback, sub_qos)

        # Publish echo reply with the ESP32 reply subscriber QoS.
        pub_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=reliability,
            durability=DurabilityPolicy.VOLATILE,
            deadline=Duration(seconds=0, nanoseconds=23_283_064),
            lifespan=Duration(seconds=2),
        )
        self.pub = self.create_publisher(String, '/qos_eval_reply', pub_qos)

        self.count = 0
        self.get_logger().info(
            'Echo reply node started, listening on /qos_eval, '
            f'reply={reliability_label}')

    def callback(self, msg):
        # Echo back the original message content (ESP32 measures RTT internally)
        reply = String()
        reply.data = f'[ECHO] #{self.count} {msg.data}'
        self.pub.publish(reply)
        self.count += 1

        if self.count <= 3 or self.count % 10 == 0:
            self.get_logger().info(f'Echo replies sent: {self.count}')


def main():
    rclpy.init()
    node = EchoReplyNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
