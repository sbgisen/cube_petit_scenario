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

import time

import rclpy
from rclpy.node import Node
import smach
from smach import State
from std_msgs.msg import String


class Idolng(State):
    """Idolng state."""

    def __init__(self, node: Node) -> None:
        """Init."""
        State.__init__(self, outcomes=['success', 'round_and_round'], input_keys=['voice_cmd_text'])

        self.node = node
        self.logger = node.get_logger()
        self.voice_cmd_text = None
        self.actor_pose = None

        # Subscriber
        self.voice_cmd_sub = self.node.create_subscription(String, '/voice_cmd', self.voice_cmd_callback, 10)
        self.node.get_logger().info('\033[96m==Idolng Init==\033[0m')

    def voice_cmd_callback(self, data: String) -> None:
        self.voice_cmd_text = data.data
        self.logger.debug('Voice cmd Subscriber ----------')
        self.logger.debug(data.data)
        self.logger.debug('-------------------------------')

    def execute(self, userdata: smach.user_data) -> str:
        """Execute."""
        self.logger.info('Idolng state.')
        # return 'success'
        self.logger.info('Waiting for /voice_cmd...')
        self.voice_cmd_text = ''
        while not self.voice_cmd_text:
            rclpy.spin_once(self.node, timeout_sec=1.0)

        if self.voice_cmd_text == 'round_and_round':
            return 'round_and_round'

        else:
            time.sleep(3)
            return 'success'


if __name__ == '__main__':
    rclpy.init_node('test')
    state = Idolng('test')
    state()
