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

import random
import time

from cube_petit_speech_msgs.action import Speech
from geometry_msgs.msg import TwistStamped
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from cube_petit_anima import behavior_logic
from cube_petit_anima.utils.sound_effect_play import SEPlayer
from cube_petit_scenario_msgs.msg import InternalState


class BehaviorNode(Node):

    def __init__(self) -> None:
        super().__init__('behavior_node')

        # Subscribe to anima state
        self.sub = self.create_subscription(InternalState, 'internal_state', self.callback, 10)

        # Publisher (TwistStamped!!)
        self.motion_pub = self.create_publisher(TwistStamped, 'diff_drive_controller/cmd_vel', 10)

        self.speech_client = ActionClient(self, Speech, 'speech_action_server')

        # Swing control
        self.swing_enabled = (self.declare_parameter('swing_enabled', False).get_parameter_value().bool_value)
        self.swing_active = False
        self.swing_phase = 0.0
        self.last_speak_time = 0.0
        self.speak_cooldown = 180.0  # 3分
        self.se_cooldown = 60.0
        self.last_se_time = 0.0

        self.motion_timer = self.create_timer(0.1, self.update_motion)

        config_se_path = (self.declare_parameter('config_se_path', '').get_parameter_value().string_value)
        if not config_se_path:
            raise RuntimeError('config_se_path parameter not set')
        self.se = SEPlayer(config_se_path)

    # ==================================
    # State Callback
    # ==================================
    def callback(self, state: InternalState) -> None:

        now = time.time()

        prev_swing = self.swing_active

        self.swing_active = behavior_logic.compute_swing_active(self.swing_enabled, state.energy, state.boredom)

        if (state.energy >= behavior_logic.ENERGY_LOW_THRESHOLD and
                state.boredom > behavior_logic.BOREDOM_HIGH_THRESHOLD):
            if (now - self.last_se_time) > self.se_cooldown:
                self.get_logger().info('play SE: 喜び')
                self.se.play('感情：興味')
                self.last_se_time = now

        # --- 状態変化検出 ---
        if not prev_swing and self.swing_active:
            self.get_logger().info('Wake up')
            # 起きた音
            self.get_logger().info('play SE: スリープ解除')
            self.se.play('スリープ解除')
            self.last_speak_time = now

        if prev_swing and not self.swing_active:
            self.get_logger().info('Sleep')
            self.get_logger().info('play SE: スリープ移行')
            self.se.play('スリープ移行')
            self.last_speak_time = now

        # --- Speak ---
        if self.swing_active:
            if state.curiosity > 40 and state.human_detected:
                if (now - self.last_speak_time) > self.speak_cooldown:
                    if random.random() < 0.2:
                        self.trigger_speak()
                        self.last_speak_time = now

    # ==================================
    # Motion Update (10Hz)
    # ==================================
    def update_motion(self) -> None:

        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'

        if self.swing_active:
            self.swing_phase, msg.twist.angular.z = behavior_logic.compute_swing(self.swing_phase)
        else:
            msg.twist.angular.z = 0.0

        self.motion_pub.publish(msg)

    # ==================================
    # Speak
    # ==================================
    def trigger_speak(self) -> None:
        self.get_logger().info('trigger_speak')

        if not self.speech_client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warn('Speech action server not available')
            return

        goal_msg = Speech.Goal()
        texts = ['いる。', 'すこし、ちがう。', 'まだ、みてる。', 'きょう、しずか。', 'わからない。']
        goal_msg.text = random.choice(texts)
        goal_msg.emotion = 'normal'
        goal_msg.emotion_level = 1
        goal_msg.pitch = 100
        goal_msg.speed = 100
        goal_msg.volume = 80

        self.speech_client.send_goal_async(goal_msg)


def main() -> None:
    rclpy.init()
    node = BehaviorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
