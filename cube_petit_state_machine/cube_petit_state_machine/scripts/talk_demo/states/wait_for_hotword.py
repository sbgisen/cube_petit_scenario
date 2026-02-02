#!/usr/bin/env python
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

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from typing import Optional

from rclpy.node import Node
from std_msgs.msg import String


class WaitForHotword:
    """Wait for hotword (FSM-safe, non-blocking)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== WaitForHotword Init ==\033[0m")

        # ---------- internal state ----------
        self._detected: Optional[bool] = None

        # ---------- ROS subscriber ----------
        topic = self.node.get_parameter('detect_word_topic').value
        self._subscriber = self.node.create_subscription(
            String,
            topic,
            self._hotword_callback,
            10
        )

    def _declare_topic(self, name, default):
        return self.node.declare_parameter(name, default).get_parameter_value().string_value


    # ==========================
    # ROS callback
    # ==========================

    def _hotword_callback(self, msg: String) -> None:
        word = msg.data.strip()
        self.node.get_logger().debug(f"Hotword received: {word}")

        if word == 'Cube-petit':
            self._detected = True
        else:
            self._detected = False

    # ==========================
    # FSM execute (non-blocking)
    # ==========================

    def execute(self) -> Optional[str]:
        """
        Returns:
            None                      : still waiting
            'hotword_detected'        : correct hotword
            'invalid_hotword_detected': other word
        """

        if self._detected is None:
            return None  # nothing received yet

        if self._detected:
            self.node.get_logger().info("Hotword detected!")
            self._detected = None
            return 'hotword_detected'

        # invalid word
        self.node.get_logger().info("Invalid hotword detected")
        self._detected = None
        return 'invalid_hotword_detected'


if __name__ == '__main__':
    rclpy.init_node('test')
    state = WaitForHotword('test')
    state()
