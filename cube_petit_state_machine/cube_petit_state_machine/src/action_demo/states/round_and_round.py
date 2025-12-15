#!/usr/bin/env python3
# -*- coding:utf-8 -*-

# Copyright (c) 2025 SoftBank Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""round_and_round."""

from geometry_msgs.msg import Twist
from geometry_msgs.msg import TwistStamped
import rclpy
from rclpy.node import Node
import smach
from smach import State
from std_msgs.msg import Header


class RoundAndRound(State):
    """RoundAndRound state."""

    def __init__(self, node: Node) -> None:
        """Init."""
        State.__init__(self, outcomes=['success'])
        self.node = node
        self.cmd_vel_pub = self.node.create_publisher(TwistStamped, '/diff_drive_controller/cmd_vel', 10)
        self.node.get_logger().info('\033[96m==RoundAndRound Init==\033[0m')

    def execute(self, userdata: smach.user_data) -> str:
        """Execute."""
        self.node.get_logger().info('RoundAndRound state.')
        twist_stamped_msg = TwistStamped()
        twist_stamped_msg.header = Header()
        twist_stamped_msg.header.stamp = self.node.get_clock().now().to_msg()
        twist_stamped_msg.header.frame_id = 'base_link'
        twist = Twist()
        # [TODO] param
        twist.angular.z = 1.8462
        twist_stamped_msg.twist = twist

        start_time = self.node.get_clock().now().to_msg().sec
        time_for_one_rotation = 2 * 3.141592653589793 / 0.4
        while rclpy.ok() and self.node.get_clock().now().to_msg().sec - start_time < time_for_one_rotation:
            self.cmd_vel_pub.publish(twist_stamped_msg)
            rclpy.spin_once(self.node, timeout_sec=0.1)

        twist_stamped_msg.header = Header()
        twist_stamped_msg.header.stamp = self.node.get_clock().now().to_msg()
        twist.angular.z = 0.0
        twist_stamped_msg.twist = twist
        self.cmd_vel_pub.publish(twist_stamped_msg)
        return 'success'


if __name__ == '__main__':
    rclpy.init_node('test')
    state = RoundAndRound('test')
    state()
