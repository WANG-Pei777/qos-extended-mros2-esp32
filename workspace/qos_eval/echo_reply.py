#!/usr/bin/env python3
"""ROS2 echo reply node for step7 QoS latency measurement.

Subscribes to /step7_full_qos, extracts timestamp, replies to
/step7_full_qos_reply with "[ECHO] #N <timestamp_us>" format.
"""

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

        # Subscribe to the ESP32 publisher in the RELIABLE full-QoS validation path.
        sub_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.sub = self.create_subscription(
            String, '/step7_full_qos', self.callback, sub_qos)

        # Publish echo reply with the ESP32 reply subscriber QoS.
        pub_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            deadline=Duration(seconds=0, nanoseconds=23_283_064),
            lifespan=Duration(seconds=2),
        )
        self.pub = self.create_publisher(String, '/step7_full_qos_reply', pub_qos)

        self.count = 0
        self.get_logger().info(
            'Echo reply node started, listening on /step7_full_qos, reply=RELIABLE')

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
