#!/usr/bin/env python

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

from cube_petit_interaction_msgs.srv import CreateUser
from cube_petit_interaction_msgs.srv import UpdateInteraction
import rclpy
from rclpy.node import Node
from rclpy.task import Future
from std_msgs.msg import Float32
from std_msgs.msg import String


class MemoryTalkDemoNode(Node):

    def __init__(self) -> None:
        """Init."""
        super().__init__('memory_talk_demo_node')

        self.create_user_client = self.create_client(CreateUser, 'create_user')
        self.update_interaction_client = self.create_client(UpdateInteraction, 'update_interaction')
        self.current_identity = 'new'
        self.speaker_confidence = 0.0

        self.create_subscription(
            String,
            'speaker_identity',
            self.on_identity,
            10,
        )

        self.create_subscription(
            Float32,
            'speaker_confidence',
            self.on_confidence,
            10,
        )

        self.get_logger().info('Waiting for services...')
        self.create_user_client.wait_for_service()
        self.update_interaction_client.wait_for_service()
        self.get_logger().info('Services are available')

        self.current_user_id = None

        self.get_logger().info('MemoryTalkDemoNode started')

        # self.timer = self.create_timer(3.0, self.on_trigger)

    def on_identity(self, msg: String) -> None:
        self.current_identity = msg.data

    def on_confidence(self, msg: Float32) -> None:
        self.speaker_confidence = msg.data

    def on_trigger(self) -> None:
        if self.current_identity == 'new':
            self.create_user()
        else:
            self.current_user_id = self.current_identity
            self.update_interaction()

    def create_user(self) -> None:
        req = CreateUser.Request()
        future = self.create_user_client.call_async(req)
        future.add_done_callback(self.on_create_user_response)

    def on_create_user_response(self, future: Future) -> None:
        """Handle CreateUser service response."""
        res = future.result()
        self.current_user_id = res.user_id

        self.get_logger().info(f'New user created: {res.user_id}, count={res.interaction_count}')

        self.say_greeting(res.confidence)

    def update_interaction(self) -> None:
        if self.current_user_id is None:
            return
        req = UpdateInteraction.Request()
        req.user_id = self.current_user_id

        future = self.update_interaction_client.call_async(req)
        future.add_done_callback(self.on_update_interaction_response)

    def on_update_interaction_response(self, future: Future) -> None:
        res = future.result()
        self.get_logger().info(f'Update: count={res.interaction_count}, conf={res.confidence}')

        self.say_greeting(res.confidence)

    def say_greeting(self, confidence: float) -> None:
        if confidence < 0.3:
            self.get_logger().info('はじめまして')
        elif confidence < 0.6:
            self.get_logger().info('また会えたね')
        else:
            self.get_logger().info('いつもありがとう')

        # for demonstration
        # self.timer.cancel()


def main() -> None:
    rclpy.init()
    node = MemoryTalkDemoNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
