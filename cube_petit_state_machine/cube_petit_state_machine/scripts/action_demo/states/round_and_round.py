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

from enum import Enum, auto
from typing import Optional

from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node
from std_msgs.msg import Header


class _RotateState(Enum):
    INIT = auto()
    ROTATING = auto()
    STOP = auto()
    DONE = auto()


class RoundAndRound:
    """Round and round action (FSM-safe, non-blocking)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info('\033[96m== RoundAndRound Init ==\033[0m')

        # ---------- Publisher ----------
        topic = self.node.get_parameter('cmd_vel_topic').value
        self._cmd_vel_pub = self.node.create_publisher(
            TwistStamped,
            topic,
            10
        )

        # ---------- Internal FSM ----------
        self._state = _RotateState.INIT
        self._start_time = None

        # ---------- Params (後で parameter 化しても良い) ----------
        self._angular_z = 1.8462          # rad/s
        self._rotation_speed = 0.4        # rad/s (旧コード互換)
        self._rotation_time = 2 * 3.141592653589793 / self._rotation_speed

    def _declare_topic(self, name, default):
        return self.node.declare_parameter(name, default)\
            .get_parameter_value().string_value

    # ==========================
    # FSM execute (non-blocking)
    # ==========================

    def execute(self) -> Optional[str]:
        """
        Returns:
            None      : still running
            'success' : finished
        """

        now = self.node.get_clock().now()

        # ---------- INIT ----------
        if self._state == _RotateState.INIT:
            self.node.get_logger().info("RoundAndRound: start rotating")
            self._start_time = now
            self._publish_twist(self._angular_z)
            self._state = _RotateState.ROTATING
            return None

        # ---------- ROTATING ----------
        if self._state == _RotateState.ROTATING:
            elapsed = (now - self._start_time).nanoseconds * 1e-9
            if elapsed < self._rotation_time:
                self._publish_twist(self._angular_z)
                return None
            else:
                self._state = _RotateState.STOP
                return None

        # ---------- STOP ----------
        if self._state == _RotateState.STOP:
            self.node.get_logger().info("RoundAndRound: stop")
            self._publish_twist(0.0)
            self._state = _RotateState.DONE
            return None

        # ---------- DONE ----------
        if self._state == _RotateState.DONE:
            self._state = _RotateState.INIT
            self._start_time = None
            return 'success'

        return None

    # ==========================
    # Helper
    # ==========================

    def _publish_twist(self, angular_z: float) -> None:
        msg = TwistStamped()
        msg.header = Header()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'

        twist = Twist()
        twist.angular.z = angular_z
        msg.twist = twist

        self._cmd_vel_pub.publish(msg)

if __name__ == '__main__':
    rclpy.init_node('test')
    state = RoundAndRound('test')
    state()
