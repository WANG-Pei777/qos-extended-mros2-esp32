#!/usr/bin/env python3
"""
Echo host for upstream mros2-esp32
Topic: /step10_best_effort (per EXPERIMENT_REMEDIATION_GUIDE §3.⑥)
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String

class EchoBestEffort(Node):
    def __init__(self):
        super().__init__('echo_best_effort')

        # BEST_EFFORT QoS (upstream default)
        qos = QoSProfile(depth=10)
        qos.reliability = QoSReliabilityPolicy.BEST_EFFORT

        self.sub = self.create_subscription(
            String, '/step10_best_effort', self.callback, qos)
        self.pub = self.create_publisher(
            String, '/step10_best_effort_reply', qos)

        self.get_logger().info('Echo node started (BEST_EFFORT)')
        self.count = 0

    def callback(self, msg):
        self.count += 1
        reply = String()
        reply.data = msg.data  # Echo back
        self.pub.publish(reply)
        if self.count % 10 == 0:
            self.get_logger().info(f'Echoed: {self.count}')

def main():
    rclpy.init()
    node = EchoBestEffort()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
