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

from rclpy.action import ActionClient
from rclpy.node import Node
from sbgisen_speech_msgs.action import Speech


class CubeSpeechUtil(Node):
    """CubeSpeechUtil class."""

    def __init__(self) -> None:
        """Init."""
        super().__init__('cube_speech_util')
        self.get_logger().info("CubeSpeechUtil->wait_for_speech_service")
        self.__action_client = ActionClient(self, Speech, '/speech_action_server')
        self.emotion = 'happiness'
        self.pitch = 130
        self.speed = 100
        self.volume = 100
        self.speech_method = 'jtalk'

    def text_to_jtalk(self, phrase: str) -> None:
        """Text to Jtalk."""
        talk_msg = Speech.Goal()
        talk_msg.text = phrase
        talk_msg.method = "jtalk"
        talk_msg.emotion = "happiness"
        talk_msg.emotion_level = 2
        talk_msg.pitch = 130
        talk_msg.speed = 100
        talk_msg.volume = 30

        self.__action_client.wait_for_server()
        self.get_logger().info("Robot say: [%s]" % (talk_msg.text))
        return self.__action_client.send_goal_async(talk_msg)
