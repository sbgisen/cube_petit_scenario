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

from typing import Optional

from rclpy.node import Node
from std_msgs.msg import String
from rclpy.parameter import Parameter
from cube_petit_state_machine.scripts.utils.cube_speech_util import CubeSpeechUtil
from rcl_interfaces.msg import ParameterDescriptor

class JuliusSearch:
    """Julius Search (FSM-safe, non-blocking)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== JuliusSearch Init ==\033[0m")

        # ---------- internal state ----------
        self._latest_text: Optional[str] = None

        # ---------- ROS I/O ----------
        topic = self.node.get_parameter('julius_result_topic').value


        self._subscriber = self.node.create_subscription(
            String,
            topic,
            self._julius_callback,
            10
        )

        self._publisher = self.node.create_publisher(
            String,
            'voice_cmd',
            10
        )
        self.node.declare_parameter(
            'conversations',
            descriptor=ParameterDescriptor(
                dynamic_typing=True
            )
        )


        self._conversations = self.load_conversations()

        self.node.get_logger().info(
            f"Loaded conversations: {list(self._conversations.keys())}"
        )

    def load_conversations(self):
        conversations = {}

        for name, param in self.node.get_parameters_by_prefix('conversations').items():
            # name 例: "hello.julius"
            parts = name.split('.')
            if len(parts) != 2:
                continue

            intent, key = parts
            conversations.setdefault(intent, {})[key] = param.value

        return conversations
        
    def _declare_topic(self, name, default):
        return self.node.declare_parameter(name, default).get_parameter_value().string_value

    def _param(self, name, default):
        return self.node.declare_parameter(name, default).value

    # ==========================
    # ROS callback
    # ==========================

    def _julius_callback(self, msg: String) -> None:
        text = msg.data.strip()
        if not text:
            return

        self.node.get_logger().debug(f"Julius received: {text}")
        self._latest_text = text

    # ==========================
    # FSM execute (non-blocking)
    # ==========================

    def execute(self) -> Optional[tuple[str, Optional[str]]]:
        """
        Returns:
            None
                : waiting for julius result
            (outcome, input_cmd)
                : transition decision
        """

        if self._latest_text is None:
            return None

        text = self._latest_text
        self._latest_text = None  # consume

        cube_speech = CubeSpeechUtil()

        self.node.get_logger().info(f"Julius recognized: {text}")
        self._publisher.publish(String(data="idling"))

        for intent, data in self._conversations.items():
            for keyword in data.get('julius', []):
                if keyword in text:
                    self.node.get_logger().info(f"Response intent: {intent}")
                    return ('response', intent)

        # ---------- routing ----------
        if text == "キューブプチ":
            return ('julius', None)

        if text == "こんにちは":
            return ('response', 'hello')

        if text == "自己紹介して":
            return ('response', 'introduce')

        if text == "会話して":
            return ('gpt_conversation', 'gpt')

        if text == "ジャンケンしよう":
            return ('rock_paper_scissors', 'rock_paper_scissors')

        if text == "何歳に見える":
            return ('how_old_you_are', 'how_old')

        if text == "くるくるして":
            self.node.get_logger().info('Published /voice_cmd "round_and_round"')
            self._publisher.publish(String(data="round_and_round"))
            cube_speech.text_to_jtalk("くるくるします")
            return ('hotword', None)

        if text in ("キャンセル", "ストップ"):
            self.node.get_logger().info("Julius Cancelled")
            self._publisher.publish(String(data="cancel"))
            cube_speech.text_to_jtalk("わかりました")
            return ('hotword', None)

        # ---------- fallback ----------
        self.node.get_logger().info("Julius: cannot understand")
        cube_speech.text_to_jtalk("よくわかりませんでした")
        return ('hotword', None)


if __name__ == '__main__':
    rclpy.init_node('test')
    state = JuliusSearch('test')
    state()
