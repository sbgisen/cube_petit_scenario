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
import random
from rcl_interfaces.msg import ParameterDescriptor

class CreateResponse:
    """Create response (FSM version)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== CreateResponse Init ==\033[0m")

        self._input_cmd: str | None = None


        self._conversations = (
            self.node.get_parameter('conversations').value or {}
        )

    # -------------------------
    # FSM からコマンドを渡す
    # -------------------------
    def set_input_cmd(self, cmd: str) -> None:
        self._input_cmd = cmd

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

    # -------------------------
    # FSM 用 execute
    # -------------------------
    def execute(self) -> str:
        self.node.get_logger().info("CreateResponse state")

        if self._input_cmd is None:
            self.node.get_logger().warn("CreateResponse: input_cmd is None")
            return 'success'

        cube_speech = CubeSpeechUtil()
        conversations = self.load_conversations()

        data = conversations.get(self._input_cmd)
        if not data:
            self.node.get_logger().warn(
                f"No conversation for [{self._input_cmd}]"
            )
            self._input_cmd = None
            return 'success'

        responses = data.get('response', [])
        if responses:
            text = random.choice(responses)
            cube_speech.text_to_jtalk(text)


        if self._input_cmd == "hello":
            self.node.get_logger().info("---------------------------------")
            self.node.get_logger().info("Create Resp: Hello World")
            cube_speech.text_to_jtalk("こんにちは")
            self.node.get_logger().info("---------------------------------")

        elif self._input_cmd == "introduce":
            self.node.get_logger().info("---------------------------------")
            self.node.get_logger().info("Create Resp: Introduce")
            cube_speech.text_to_jtalk("僕の名前はキューブプチです！")
            self.node.get_logger().info("---------------------------------")

        else:
            self.node.get_logger().info(
                f"CreateResponse: unknown cmd [{self._input_cmd}]"
            )

        # 一回喋ったらクリア
        self._input_cmd = None
        return 'success'

if __name__ == '__main__':
    rclpy.init_node('test')
    state = CreateResponse('test')
    state()
