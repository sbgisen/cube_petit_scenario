import rclpy
from rclpy.node import Node
from cube_petit_scenario_msgs.msg import InternalState
from geometry_msgs.msg import TwistStamped

import random
import math
import time
from rclpy.action import ActionClient
from cube_petit_speech_msgs.action import Speech
from cube_petit_anima.utils.sound_effect_play import SEPlayer

class BehaviorNode(Node):

    def __init__(self):
        super().__init__('behavior_node')

        # Subscribe to anima state
        self.sub = self.create_subscription(
            InternalState,
            'internal_state',
            self.callback,
            10
        )

        # Publisher (TwistStamped!!)
        self.motion_pub = self.create_publisher(
            TwistStamped,
            'diff_drive_controller/cmd_vel',
            10
        )
        
        self.speech_client = ActionClient(
            self,
            Speech,
            'speech_action_server'
        )

        # Swing control
        self.swing_active = False
        self.swing_phase = 0.0
        self.last_speak_time = 0.0
        self.speak_cooldown = 180.0  # 3分
        self.se_cooldown = 60.0
        self.last_se_time = 0.0

        self.motion_timer = self.create_timer(0.1, self.update_motion)

        
        config_se_path = (
            self.declare_parameter("config_se_path", "")
                .get_parameter_value()
                .string_value
        )
        if not config_se_path:
            raise RuntimeError("config_se_path parameter not set")
        self.se = SEPlayer(config_se_path)

    # ==================================
    # State Callback
    # ==================================
    def callback(self, state):

        now = time.time()

        prev_swing = self.swing_active

        if state.energy < 20:
            self.swing_active = False

        elif state.boredom > 80:
            self.swing_active = True
            if (now - self.last_se_time) > self.se_cooldown:
                self.get_logger().info("play SE: 喜び")
                self.se.play("感情：興味")
                self.last_se_time = now

        else:
            self.swing_active = False

        # --- 状態変化検出 ---
        if not prev_swing and self.swing_active:
            self.get_logger().info("Wake up")
            # 起きた音
            self.get_logger().info("play SE: スリープ解除")
            self.se.play("スリープ解除")
            self.last_speak_time = now

        if prev_swing and not self.swing_active:
            self.get_logger().info("Sleep")
            self.get_logger().info("play SE: スリープ移行")
            self.se.play("スリープ移行")
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
    def update_motion(self):

        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"

        if self.swing_active:

            amplitude = 1.5
            speed = 1.2

            self.swing_phase += 0.1 * speed

            value = amplitude * math.sin(self.swing_phase)
            msg.twist.angular.z = max(-1.5, min(1.5, value))
        else:
            msg.twist.angular.z = 0.0

        self.motion_pub.publish(msg)

    # ==================================
    # Sleep
    # ==================================
    def sleep_mode(self):
        self.swing_active = False
        self.last_swing_active = True

    # ==================================
    # Speak
    # ==================================
    def trigger_speak(self):
        self.get_logger().info("trigger_speak")

        if not self.speech_client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warn("Speech action server not available")
            return

        goal_msg = Speech.Goal()
        goal_msg.text = random.choice([
            "いる。",
            "すこし、ちがう。",
            "まだ、みてる。",
            "きょう、しずか。",
            "わからない。"
        ])
        goal_msg.emotion = "normal"
        goal_msg.emotion_level = 1
        goal_msg.pitch = 100
        goal_msg.speed = 100
        goal_msg.volume = 80

        self.speech_client.send_goal_async(goal_msg)


def main():
    rclpy.init()
    node = BehaviorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
