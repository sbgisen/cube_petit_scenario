#!/usr/bin/env python3
"""
InternalState を std_msgs/String (JSON) に変換して rosbridge 経由で配信するリレーノード
"""
import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from cube_petit_scenario_msgs.msg import InternalState


class InternalStateRelay(Node):
    def __init__(self):
        super().__init__('internal_state_relay')
        ns = self.get_namespace().lstrip('/')
        self.pub = self.create_publisher(String, f'/{ns}/internal_state_json', 10)
        self.sub = self.create_subscription(
            InternalState,
            f'/{ns}/internal_state',
            self.callback,
            10,
        )

    def callback(self, msg: InternalState):
        data = {
            'curiosity':     msg.curiosity,
            'boredom':       msg.boredom,
            'energy':        msg.energy,
            'silence_bias':  msg.silence_bias,
            'body_generation': msg.body_generation,
            'human_detected':  msg.human_detected,
            'petit_detected':  msg.petit_detected,
            'sleep_mode':      msg.sleep_mode,
        }
        self.pub.publish(String(data=json.dumps(data)))


def main():
    rclpy.init()
    node = InternalStateRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
