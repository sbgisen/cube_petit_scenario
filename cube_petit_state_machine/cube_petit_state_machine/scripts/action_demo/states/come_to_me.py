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


class ComeToMe:
    def __init__(self, node: Node):
        self.node = node
        self._people = []
        self._actor_pose = None
        self._done = False

        self.node.create_subscription(
            PositionMeasurementArray,
            '/people_tracker_measurements',
            self._people_cb,
            10
        )

        self.node.create_subscription(
            PoseStamped,
            '/actor_pose_from_robot',
            self._pose_cb,
            10
        )

        self.cmd_vel_pub = self.node.create_publisher(
            Twist,
            '/cube_petit/diff_drive_controller/cmd_vel',
            10
        )

    def _people_cb(self, msg):
        self._people = msg.people

    def _pose_cb(self, msg):
        self._actor_pose = msg.pose

    def execute(self) -> str:
        if not self._people or self._actor_pose is None:
            return None  # waiting

        target = self._select_target()
        if target is None:
            return 'success'

        self._move_to(target)

        if self._arrived(target):
            CubeSpeechUtil().text_to_jtalk("つきました")
            self._done = True
            return 'success'

        return None

if __name__ == '__main__':
    rclpy.init_node('test')
    state = Idolng('test')
    state()
