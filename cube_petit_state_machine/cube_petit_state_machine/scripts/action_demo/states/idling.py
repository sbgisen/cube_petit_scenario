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
"""WaitHotword states for SMACH state machines."""

from typing import Optional

from rclpy.node import Node
from std_msgs.msg import String


class Idolng:
    """Idolng action (FSM-safe, non-blocking)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.logger = node.get_logger()
        self.logger.info('\033[96m== Idolng Init ==\033[0m')

        # ---------- internal state ----------
        self._voice_cmd_text: Optional[str] = None

        # ---------- ROS subscriber ----------
        self._voice_cmd_sub = self.node.create_subscription(
            String,
            '/voice_cmd',
            self._voice_cmd_callback,
            10
        )

    # ==========================
    # ROS callback
    # ==========================

    def _voice_cmd_callback(self, msg: String) -> None:
        text = msg.data.strip()
        self.logger.debug(f"Voice cmd received: {text}")
        self._voice_cmd_text = text

    # ==========================
    # FSM execute (non-blocking)
    # ==========================

    def execute(self) -> Optional[str]:
        """
        Returns:
            None               : keep idling
            'round_and_round'  : start action
            'success'          : idle tick (optional)
        """

        if self._voice_cmd_text is None:
            return None  # nothing received yet

        cmd = self._voice_cmd_text
        self._voice_cmd_text = None  # consume

        if cmd == 'round_and_round':
            self.logger.info("Idolng: round_and_round command received")
            return 'round_and_round'

        # その他のコマンドは無視してアイドル継続
        self.logger.debug(f"Idolng: ignored cmd [{cmd}]")
        return None


if __name__ == '__main__':
    rclpy.init_node('test')
    state = Idolng('test')
    state()
