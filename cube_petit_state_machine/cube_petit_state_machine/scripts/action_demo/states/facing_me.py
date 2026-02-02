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


import time
import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String


class FacingMe:
    """
    FacingMe action (FSM version, no SMACH)

    - Rotate robot toward a given direction
    - Keep facing for a while
    """

    def __init__(self, node: Node):
        self.node = node

        # ---------- ROS I/O ----------
        self.cmd_vel_pub = self.node.create_publisher(
            Twist,
            node.get_parameter('cmd_vel_topic').value,
            10
        )

        self.direction_sub = self.node.create_subscription(
            String,
            node.get_parameter('people_direction_topic').value,
            self._direction_callback,
            10
        )

        # ---------- internal state ----------
        self._target_yaw = None
        self._active = False
        self._start_time = None
        self._duration_sec = 5.0

        self.node.get_logger().info("== FacingMe (FSM) Init ==")

    # --------------------------
    # parameter helper
    # --------------------------
    def _declare_param(self, name: str, default):
        return self.node.declare_parameter(
            name, default
        ).get_parameter_value().string_value

    # ==========================
    # direction input
    # ==========================
    def _direction_callback(self, msg: String) -> None:
        direction = msg.data.strip()

        mapping = {
            'front': 0.0,
            'left': math.pi / 2,
            'right': -math.pi / 2,
            'back': math.pi,
        }

        if direction in mapping:
            self._target_yaw = mapping[direction]
            self._active = True
            self._start_time = time.time()
            self.node.get_logger().info(
                f"[FacingMe] start facing: {direction}"
            )

    # ==========================
    # FSM step
    # ==========================
    def step(self):
        """
        Returns:
            None      : still running
            'done'    : finished
        """
        if not self._active:
            return 'done'

        # ---- simple rotation (time-based) ----
        twist = Twist()
        twist.angular.z = 0.4
        self.cmd_vel_pub.publish(twist)

        # ---- timeout ----
        if time.time() - self._start_time > self._duration_sec:
            twist.angular.z = 0.0
            self.cmd_vel_pub.publish(twist)

            self._active = False
            self._target_yaw = None

            self.node.get_logger().info("[FacingMe] finished")
            return 'done'

        return None

    # ==========================
    # external cancel
    # ==========================
    def cancel(self):
        self.node.get_logger().warn("[FacingMe] canceled")

        twist = Twist()
        twist.angular.z = 0.0
        self.cmd_vel_pub.publish(twist)

        self._active = False
        self._target_yaw = None
