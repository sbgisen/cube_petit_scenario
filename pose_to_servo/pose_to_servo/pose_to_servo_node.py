#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
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

import math
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import PoseStamped
from servo_action.action import SetServoAngle


def quat_to_yaw(q) -> float:
    """Quaternion -> yaw [rad] (-pi, pi]"""
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def unwrap_yaw(prev: Optional[float], curr: float) -> float:
    """
    Keep yaw continuous across -pi <-> +pi
    """
    if prev is None:
        return curr

    diff = curr - prev
    if diff > math.pi:
        curr -= 2.0 * math.pi
    elif diff < -math.pi:
        curr += 2.0 * math.pi

    return curr


class PoseToServo(Node):
    def __init__(self) -> None:
        super().__init__('pose_to_servo')

        # Parameters
        self.declare_parameter('topic_name', '/doa')
        self.declare_parameter('frame_id', 'respeaker_base')
        self.declare_parameter('offset_yaw', -3.141592653589793)
        self.declare_parameter('scale_yaw', 1.0)
        self.declare_parameter('center_deg', 90.0)
        self.declare_parameter('min_deg', 0.0)
        self.declare_parameter('max_deg', 180.0)
        self.declare_parameter('time_sec', 1)
        self.declare_parameter('deadband_rad', 0.01)
        self.declare_parameter('max_jump_deg', 90.0)
        self.max_jump_deg = float(self.get_parameter('max_jump_deg').value)

        self.topic_name = self.get_parameter('topic_name').value
        self.frame_id = self.get_parameter('frame_id').value

        self.offset_yaw = float(self.get_parameter('offset_yaw').value)
        self.scale_yaw = float(self.get_parameter('scale_yaw').value)
        self.center_deg = float(self.get_parameter('center_deg').value)
        self.min_deg = float(self.get_parameter('min_deg').value)
        self.max_deg = float(self.get_parameter('max_deg').value)
        self.time_sec = int(self.get_parameter('time_sec').value)
        self.deadband = float(self.get_parameter('deadband_rad').value)

        # yaw state
        self._last_raw_yaw: Optional[float] = None
        self._last_sent_angle: Optional[int] = None
        self._last_unwrapped_yaw: Optional[float] = None

        # Action client
        self._client = ActionClient(self, SetServoAngle, 'set_servo_angle')

        self.get_logger().info('Waiting for action server...')
        self._client.wait_for_server()
        self.get_logger().info('Action server available')

        self.create_subscription(
            PoseStamped,
            self.topic_name,
            self.cb_pose,
            10,
        )
        self.get_logger().info(f'Subscribing: {self.topic_name}')
        self.goal = SetServoAngle.Goal()

    def cb_pose(self, msg: PoseStamped) -> None:
        if self.frame_id and msg.header.frame_id != self.frame_id:
            return

        # --- yaw calculation ---
        raw_yaw = quat_to_yaw(msg.pose.orientation)
        raw_yaw += self.offset_yaw

        yaw = unwrap_yaw(self._last_raw_yaw, raw_yaw)

        # deadband (rad)
        if self._last_unwrapped_yaw is not None:
            if abs(yaw - self._last_unwrapped_yaw) < self.deadband:
                return

        self._last_raw_yaw = raw_yaw
        self._last_unwrapped_yaw = yaw

        # --- yaw -> servo angle ---
        angle = self.center_deg + math.degrees(yaw) * self.scale_yaw
        deg = math.degrees(yaw)
        if deg <= -90:
            angle = self.min_deg      # 0
        elif deg >= 90:
            angle = self.max_deg      # 180
        else:
            angle = self.center_deg + deg

        angle = int(round(angle))

        # ★ 大ジャンプ抑制（90度以上は無視）
        if self._last_sent_angle is not None:
            if abs(angle - self._last_sent_angle) >= self.max_jump_deg:
                self.goal.time_sec = 5
            else:
                self.goal.time_sec = self.time_sec

        self._last_sent_angle = angle

        self.get_logger().info(f"angle: {angle}")
        self.goal.angle = angle
        self._client.send_goal_async(self.goal)


def main() -> None:
    rclpy.init()
    node = PoseToServo()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
