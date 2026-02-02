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

from enum import Enum, auto
from typing import Optional

import numpy as np
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image

from cube_petit_python_api.commanders.gpt_chat import GPTChatCommander
from cube_petit_state_machine.scripts.utils.cube_speech_util import CubeSpeechUtil


class _InternalState(Enum):
    INIT = auto()
    WAIT_IMAGE = auto()
    PROCESS = auto()
    DONE = auto()


class HowOldYouAre:
    """How old you are (FSM-safe version)."""

    def __init__(self, node: Node) -> None:
        self.node = node
        self.node.get_logger().info("\033[96m== HowOldYouAre Init ==\033[0m")

        # ---------- GPT ----------
        self._gpt_client = GPTChatCommander(self.node)

        package_path = get_package_share_directory('cube_petit_smach_ros')
        setting_file = f"{package_path}/config/add_gpt_setting.txt"
        try:
            with open(setting_file, 'r') as f:
                self._add_gpt_setting_text = f.read()
        except Exception as e:
            self.node.get_logger().error(f"Failed to load GPT setting file: {e}")
            self._add_gpt_setting_text = ""

        # ---------- Image ----------
        self._bridge = CvBridge()
        self._image: Optional[np.ndarray]()_



if __name__ == '__main__':
    rclpy.init_node('test')
    state = HowOldYouAre('test')
    state()
