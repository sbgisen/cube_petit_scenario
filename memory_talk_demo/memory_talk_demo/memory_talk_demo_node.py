#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
#
# <<licensetext>>

from cube_petit_interaction_msgs.srv import CreateUser
from cube_petit_interaction_msgs.srv import UpdateInteraction
import rclpy
from rclpy.node import Node


class MemoryTalkDemoNode(Node):

    def __init__(self):
        super().__init__('memory_talk_demo_node')

        self.create_user_client = self.create_client(CreateUser, 'create_user')
        self.update_interaction_client = self.create_client(UpdateInteraction, 'update_interaction')

        self.get_logger().info('Waiting for services...')
        self.create_user_client.wait_for_service()
        self.update_interaction_client.wait_for_service()
        self.get_logger().info('Services are available')

        self.current_user_id = None

        self.get_logger().info('MemoryTalkDemoNode started')

        # 仮：起動時に1回呼ぶ
        self.timer = self.create_timer(3.0, self.on_trigger)

    def on_trigger(self):
        if self.current_user_id is None:
            self.create_user()
        else:
            self.update_interaction()

    def create_user(self):
        req = CreateUser.Request()
        future = self.create_user_client.call_async(req)
        future.add_done_callback(self.on_create_user_response)

    def on_create_user_response(self, future):
        res = future.result()
        self.current_user_id = res.user_id

        self.get_logger().info(f'New user: {res.user_id}, count={res.interaction_count}')

        self.say_greeting(res.confidence)

    def update_interaction(self):
        req = UpdateInteraction.Request()
        req.user_id = self.current_user_id

        future = self.update_interaction_client.call_async(req)
        future.add_done_callback(self.on_update_interaction_response)

    def on_update_interaction_response(self, future):
        res = future.result()

        self.get_logger().info(f'Update: count={res.interaction_count}, conf={res.confidence}')

        self.say_greeting(res.confidence)

    def say_greeting(self, confidence):
        if confidence < 0.3:
            self.get_logger().info('はじめまして')
        elif confidence < 0.6:
            self.get_logger().info('また会えたね')
        else:
            self.get_logger().info('いつもありがとう')

        # # デモ用：一度だけ
        # self.timer.cancel()


def main():
    rclpy.init()
    node = MemoryTalkDemoNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
