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

import json
from typing import Optional

from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node

from cube_petit_python_api.commanders.gpt_chat import GPTChatCommander


class GPTConversation:
    """GPT conversation (FSM version)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== GPTConversation Init ==\033[0m")

        self._gpt_chat = GPTChatCommander(self.node)

        # ---------- setting file ----------
        package_path = get_package_share_directory('cube_petit_smach_ros')
        default_setting_file_path = f"{package_path}/config/add_gpt_setting.txt"

        self._setting_file = self.node.declare_parameter(
            'add_setting_file',
            default_setting_file_path
        ).get_parameter_value().string_value

        try:
            with open(self._setting_file, 'r') as file:
                self._add_gpt_setting_text = file.read()
        except Exception as e:
            self.node.get_logger().error(
                f"Failed to load GPT setting file: {e}"
            )
            self._add_gpt_setting_text = ""

        # ---------- FSM shared data ----------
        self._input_cmd: Optional[str] = None
        self._chat_history: Optional[list] = None

    # ==========================
    # FSM からデータを渡す
    # ==========================

    def set_input_cmd(self, cmd: str) -> None:
        self._input_cmd = cmd

    def set_chat_history(self, history: list) -> None:
        self._chat_history = history

    def get_chat_history(self) -> list:
        return self._gpt_chat.get_chat_history()

    def clear_chat_history(self) -> None:
        self._gpt_chat.clear_chat_history()

    # ==========================
    # FSM 用 execute
    # ==========================

    def execute(self) -> str:
        self.node.get_logger().info("\033[96m== GPTConversation Execute ==\033[0m")

        try:
            # ※ 今は固定。後で input_cmd を使ってもOK
            result_json = self._gpt_chat.chat(
                input_robot_text="こんにちは",
                add_setting_text=self._add_gpt_setting_text
            )

            response_data = json.loads(result_json)

            # ---------- 遷移判定 ----------
            transitions = response_data.get('transitions')
            end_conversation = response_data.get('end_conversation', False)

            if transitions == "janken":
                self.clear_chat_history()
                return 'rock_paper_scissors'

            if transitions == "how_old":
                return 'how_old_you_are'

            if end_conversation:
                self.clear_chat_history()
                return 'success'

        except json.JSONDecodeError:
            self.node.get_logger().error("GPTConversation: JSON decode error")

        except Exception as e:
            self.node.get_logger().error(
                f"GPTConversation: unexpected error: {str(e)}"
            )

        return 'success'


if __name__ == '__main__':
    rclpy.init_node('test')
    state = GPTConversation('test')
    state()
