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

from rclpy.node import Node
from cube_petit_state_machine.scripts.utils.cube_speech_util import CubeSpeechUtil


class HotwordDetected:
    """Hotword detected action (FSM version)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== HotwordDetected Init ==\033[0m")

    def execute(self) -> str:
        """Say response for hotword detection."""
        self.node.get_logger().info("---------------------------------")

        cube_speech = CubeSpeechUtil()
        cube_speech.text_to_jtalk("はい")

        self.node.get_logger().info("---------------------------------")
        self.node.get_logger().info("Hotword detected!")

        return 'success'


if __name__ == '__main__':
    rclpy.init_node('test')
    state = HotwordDetected('test')
    state()
