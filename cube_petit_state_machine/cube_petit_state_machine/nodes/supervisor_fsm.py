#!/usr/bin/env python3
# -*- coding:utf-8 -*-

# Copyright (c) 2024 SoftBank Corp.
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

"""
Supervisor FSM for Cube petit
- Controls permission of TalkFSM and ActionFSM
"""

from enum import Enum, auto
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool


# ===============================
# Supervisor State
# ===============================

class SupervisorState(Enum):
    IDLE = auto()
    TALK_ACTIVE = auto()
    ACTION_ACTIVE = auto()
    EMERGENCY = auto()


# ===============================
# Supervisor FSM
# ===============================

class SupervisorFSM:
    def __init__(self, node: Node):
        self.node = node
        self.state = SupervisorState.IDLE

        # ---------- flags ----------
        self._talk_active = False
        self._action_active = False
        self._emergency = False

        # ---------- ROS I/O ----------
        emergency_topic = self.node.get_parameter(
            'emergency_stop_topic'
        ).value

        self._emergency_sub = self.node.create_subscription(
            Bool,
            emergency_topic,
            self._emergency_callback,
            10
        )

        # optional: log topic
        self._state_pub = self.node.create_publisher(
            String,
            self.node.get_parameter('supervisor_state_topic').value,
            10
        )

        self.node.get_logger().info("SupervisorFSM initialized")

    def _declare_topic(self, name, default):
        return self.node.declare_parameter(name, default)\
            .get_parameter_value().string_value

    # ==========================
    # Callbacks
    # ==========================

    def _emergency_callback(self, msg: Bool) -> None:
        if msg.data:
            self.node.get_logger().warn("Supervisor: EMERGENCY STOP")
            self._emergency = True
        else:
            self.node.get_logger().info("Supervisor: Emergency cleared")
            self._emergency = False

    # ==========================
    # Interface for sub FSMs
    # ==========================

    def set_talk_active(self, active: bool) -> None:
        self._talk_active = active

    def set_action_active(self, active: bool) -> None:
        self._action_active = active

    def is_talk_allowed(self) -> bool:
        return self.state in (SupervisorState.IDLE, SupervisorState.TALK_ACTIVE)

    def is_action_allowed(self) -> bool:
        return self.state in (SupervisorState.IDLE, SupervisorState.ACTION_ACTIVE)

    # ==========================
    # FSM step
    # ==========================

    def step(self) -> None:
        prev_state = self.state

        if self._emergency:
            self.state = SupervisorState.EMERGENCY

        elif self._action_active:
            self.state = SupervisorState.ACTION_ACTIVE

        elif self._talk_active:
            self.state = SupervisorState.TALK_ACTIVE

        else:
            self.state = SupervisorState.IDLE

        if self.state != prev_state:
            self.node.get_logger().info(
                f"[SupervisorFSM] {prev_state.name} -> {self.state.name}"
            )
            self._state_pub.publish(String(data=self.state.name))

