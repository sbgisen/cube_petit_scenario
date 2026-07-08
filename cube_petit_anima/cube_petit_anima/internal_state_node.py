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
import socket

from cube_petit_anima import internal_state_logic
from cube_petit_scenario_msgs.msg import InternalState
from cube_petit_scenario_msgs.msg import InternalStateDelta
import rclpy
from rclpy.node import Node


class InternalStateNode(Node):

    def __init__(self) -> None:
        super().__init__('internal_state_node')

        # Publisher
        self.pub = self.create_publisher(InternalState, 'internal_state', 10)

        # Delta subscriber
        self.delta_sub = self.create_subscription(InternalStateDelta, 'internal_state_delta', self.delta_callback, 10)

        # Hostname → namespace
        raw_hostname = socket.gethostname()
        self.namespace = internal_state_logic.hostname_to_namespace(raw_hostname)

        self.state_file = internal_state_logic.default_state_file(self.namespace)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self.state = InternalState()
        self.load_state()

        # Delta buffer
        self.delta_buffer = []

        self.human_detect_timer = 0

        self.is_sleeping = False

        self.update_timer = self.create_timer(1.0, self.update_state)
        self.save_timer = self.create_timer(300.0, self.save_state)

        self.get_logger().info(f'Anima initialized for host: {self.namespace}')

    # ==================================
    # Delta input
    # ==================================
    def delta_callback(self, msg: InternalStateDelta) -> None:
        if msg.human_detected:
            self.human_detect_timer = 5
        self.delta_buffer.append(msg)

    # ==================================
    # State update loop (1Hz)
    # ==================================
    def update_state(self) -> None:
        if self.human_detect_timer > 0:
            self.human_detect_timer -= 1
            self.state.human_detected = True
        else:
            self.state.human_detected = False

        # --- Base drift ---
        base_d_curiosity = random.uniform(-0.05, 0.05)

        # msg → plain dict へ変換（計算は internal_state_logic に委譲）
        deltas = [{
            'd_curiosity': delta.d_curiosity,
            'd_boredom': delta.d_boredom,
            'd_energy': delta.d_energy,
            'd_silence_bias': delta.d_silence_bias,
            'weight': delta.weight,
            'human_detected': delta.human_detected,
            'petit_detected': delta.petit_detected,
            'sleep_request': delta.sleep_request,
        } for delta in self.delta_buffer]
        self.delta_buffer.clear()

        values = {
            'curiosity': self.state.curiosity,
            'boredom': self.state.boredom,
            'energy': self.state.energy,
            'silence_bias': self.state.silence_bias,
        }

        prev_sleeping = self.is_sleeping
        new_values, self.is_sleeping = internal_state_logic.update_state(values, deltas, self.is_sleeping,
                                                                         base_d_curiosity)

        if not prev_sleeping and self.is_sleeping:
            self.get_logger().info('Entering sleep mode')
        elif prev_sleeping and not self.is_sleeping:
            self.get_logger().info('Waking up')

        self.state.curiosity = new_values['curiosity']
        self.state.boredom = new_values['boredom']
        self.state.energy = new_values['energy']
        self.state.silence_bias = new_values['silence_bias']

        self.state.human_detected = new_values['human_detected']
        self.state.petit_detected = new_values['petit_detected']

        # Reflect sleep mode into state
        self.state.sleep_mode = self.is_sleeping

        self.pub.publish(self.state)

    # ==================================
    def load_state(self) -> None:
        try:
            values = internal_state_logic.load_state_file(self.state_file)
            if values is None:
                self.initialize_default_state()
                return

            self.state.curiosity = values['curiosity']
            self.state.boredom = values['boredom']
            self.state.energy = values['energy']
            self.state.silence_bias = values['silence_bias']
            self.state.body_generation = values['body_generation']
            self.state.human_detected = False
            self.state.petit_detected = False
            self.state.sleep_mode = False

            self.get_logger().info('Anima state restored.')

        except Exception as e:
            self.get_logger().warn(f'Failed to load state: {e}')
            self.initialize_default_state()

    # ==================================
    def initialize_default_state(self) -> None:
        self.state.curiosity = random.uniform(40, 70)
        self.state.boredom = 50.0
        self.state.energy = 80.0
        self.state.silence_bias = random.uniform(50, 80)
        self.state.body_generation = 1
        self.state.human_detected = False
        self.state.petit_detected = False
        self.state.sleep_mode = False

    # ==================================
    def save_state(self) -> None:
        data = {
            'curiosity': self.state.curiosity,
            'boredom': self.state.boredom,
            'energy': self.state.energy,
            'silence_bias': self.state.silence_bias,
            'body_generation': self.state.body_generation
        }

        try:
            internal_state_logic.save_state_file(self.state_file, data)
        except Exception as e:
            self.get_logger().error(f'Failed to save state: {e}')

    # ==================================
    def destroy_node(self) -> None:
        self.save_state()
        super().destroy_node()


def main() -> None:
    rclpy.init()
    node = InternalStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
