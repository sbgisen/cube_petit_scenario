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

import random
from enum import Enum, auto
from typing import Optional

from rclpy.node import Node
from std_msgs.msg import String

from cube_petit_state_machine.scripts.utils.cube_speech_util import CubeSpeechUtil


class _JankenState(Enum):
    IDLE = auto()
    START = auto()
    WAIT_HAND = auto()
    RESULT = auto()
    DONE = auto()


class RockPaperScissors:
    """Rock Paper Scissors (FSM-safe version)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== RockPaperScissors Init ==\033[0m")

        self._state = _JankenState.IDLE

        # ---------- ROS ----------
        self._subscription = self.node.create_subscription(
            String,
            '/hand_gesture',
            self._handgesture_callback,
            10
        )

        # ---------- Timer ----------
        self._timeout_timer = None

        # ---------- Game state ----------
        self._hand_gesture: Optional[str] = None
        self._robot_hand: Optional[str] = None

        self._cube_speech = CubeSpeechUtil()

    # ==========================
    # ROS callback
    # ==========================

    def _handgesture_callback(self, msg: String) -> None:
        if self._state != _JankenState.WAIT_HAND:
            return

        mapping = {
            "FI



if __name__ == '__main__':
    rclpy.init_node('test')
    state = RockPaperScissors('test')
    state()
