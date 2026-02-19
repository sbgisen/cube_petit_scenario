import rclpy
from rclpy.node import Node
from cube_petit_scenario_msgs.msg import InternalState

import random
import json
from pathlib import Path
import socket
from cube_petit_scenario_msgs.msg import InternalStateDelta



class InternalStateNode(Node):

    def __init__(self):
        super().__init__('internal_state_node')

        # Publisher
        self.pub = self.create_publisher(
            InternalState,
            'internal_state',
            10
        )

        # Delta subscriber
        self.delta_sub = self.create_subscription(
            InternalStateDelta,
            'internal_state_delta',
            self.delta_callback,
            10
        )

        # Hostname → namespace
        raw_hostname = socket.gethostname()
        self.namespace = raw_hostname.replace('-', '_')

        base_dir = Path.home() / '.cube_petit' / self.namespace
        base_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = base_dir / 'anima_state.json'

        self.state = InternalState()
        self.load_state()

        # Delta buffer
        self.delta_buffer = []

        self.human_detect_timer = 0

        self.is_sleeping = False

        self.update_timer = self.create_timer(1.0, self.update_state)
        self.save_timer = self.create_timer(300.0, self.save_state)

        

        self.get_logger().info(
            f"Anima initialized for host: {self.namespace}"
        )

    # ==================================
    # Delta input
    # ==================================
    def delta_callback(self, msg):
        if msg.human_detected:
            self.human_detect_timer = 5
        self.delta_buffer.append(msg)

    # ==================================
    # State update loop (1Hz)
    # ==================================
    def update_state(self):
        if self.human_detect_timer > 0:
            self.human_detect_timer -= 1
            self.state.human_detected = True
        else:
            self.state.human_detected = False

        # --- Base drift ---
        base_d_curiosity = random.uniform(-0.05, 0.05)
        base_d_boredom = 0.05

        # --- Aggregate deltas ---
        d_curiosity = base_d_curiosity
        d_boredom = base_d_boredom
        d_energy = 0.0
        d_silence = 0.0

        human_detected = False
        petit_detected = False
        sleep_request = False

        for delta in self.delta_buffer:
            w = max(0.0, min(1.0, delta.weight))

            d_curiosity += delta.d_curiosity * w
            d_boredom += delta.d_boredom * w
            d_energy += delta.d_energy * w
            d_silence += delta.d_silence_bias * w

            human_detected = human_detected or delta.human_detected
            petit_detected = petit_detected or delta.petit_detected
            sleep_request = sleep_request or delta.sleep_request

        self.delta_buffer.clear()

        # --- Apply deltas ---
        self.state.curiosity += d_curiosity
        self.state.boredom += d_boredom
        self.state.energy += d_energy
        self.state.silence_bias += d_silence

        self.state.human_detected = human_detected
        self.state.petit_detected = petit_detected

        # ==================================
        # Sleep hysteresis
        # ==================================
        if not self.is_sleeping and (self.state.energy <= 20 or sleep_request):
            self.is_sleeping = True
            self.get_logger().info("Entering sleep mode")

        elif self.is_sleeping and self.state.energy >= 60:
            self.is_sleeping = False
            self.get_logger().info("Waking up")

        # Energy auto behavior
        if self.is_sleeping:
            self.state.energy += 0.4
            self.state.boredom -= 0.2
        else:
            self.state.energy -= 0.05

        # Clamp
        self.clamp()

        # Reflect sleep mode into state
        self.state.sleep_mode = self.is_sleeping

        self.pub.publish(self.state)

    # ==================================
    def clamp(self):
        for attr in ['curiosity', 'boredom', 'energy', 'silence_bias']:
            val = getattr(self.state, attr)
            setattr(self.state, attr, max(0.0, min(100.0, val)))

    # ==================================
    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                self.state.curiosity = data.get('curiosity', 60.0)
                self.state.boredom = data.get('boredom', 40.0)
                self.state.energy = data.get('energy', 80.0)
                self.state.silence_bias = data.get('silence_bias', 70.0)
                self.state.body_generation = data.get('body_generation', 1)
                self.state.human_detected = False
                self.state.petit_detected = False
                self.state.sleep_mode = False

                self.get_logger().info("Anima state restored.")

            except Exception as e:
                self.get_logger().warn(f"Failed to load state: {e}")
                self.initialize_default_state()
        else:
            self.initialize_default_state()

    # ==================================
    def initialize_default_state(self):
        self.state.curiosity = random.uniform(40, 70)
        self.state.boredom = 50.0
        self.state.energy = 80.0
        self.state.silence_bias = random.uniform(50, 80)
        self.state.body_generation = 1
        self.state.human_detected = False
        self.state.petit_detected = False
        self.state.sleep_mode = False

    # ==================================
    def save_state(self):
        data = {
            'curiosity': self.state.curiosity,
            'boredom': self.state.boredom,
            'energy': self.state.energy,
            'silence_bias': self.state.silence_bias,
            'body_generation': self.state.body_generation
        }

        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            self.get_logger().error(f"Failed to save state: {e}")

    # ==================================
    def destroy_node(self):
        self.save_state()
        super().destroy_node()


def main():
    rclpy.init()
    node = InternalStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
