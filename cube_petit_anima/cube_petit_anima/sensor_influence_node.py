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

import time

from cube_petit_anima import sensor_influence_logic
from cube_petit_scenario_msgs.msg import InternalStateDelta
from cube_petit_speech_msgs.msg import AudioDataStamped
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from people_msgs.msg import PositionMeasurementArray
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
from std_msgs.msg import Empty


class SensorInfluenceNode(Node):

    def __init__(self) -> None:
        super().__init__('sensor_influence_node')

        # Publisher
        self.delta_pub = self.create_publisher(InternalStateDelta, 'internal_state_delta', 10)

        self.last_laser_time = 0.0
        self.last_leg_time = 0.0
        self.last_image_time = 0.0

        self.prev_image_stamp = None
        self.prev_position = None

        # Subscribers
        self.create_subscription(Bool, 'vad', self.vad_callback, 10)
        self.create_subscription(PoseStamped, '/doa', self.doa_callback, 10)
        self.create_subscription(Empty, 'detect', self.hotword_callback, 10)
        self.create_subscription(AudioDataStamped, 'mic_audio_stamped', self.mic_callback, 10)
        self.create_subscription(LaserScan, 'scan', self.laser_callback, 10)
        self.create_subscription(PositionMeasurementArray, '/object_detection/laser/pair_of_legs_position',
                                 self.leg_callback, 10)
        self.create_subscription(Image, 'camera/camera/color/image_raw', self.image_callback, 10)
        self.create_subscription(Odometry, 'diff_drive_controller/odom', self.odom_callback, 10)

    def publish_delta(self,
                      d_curiosity: float = 0.0,
                      d_boredom: float = 0.0,
                      d_energy: float = 0.0,
                      d_silence_bias: float = 0.0,
                      human_detected: bool = False,
                      petit_detected: bool = False,
                      sleep_request: bool = False,
                      weight: float = 1.0,
                      source: str = 'unknown') -> None:
        msg = InternalStateDelta()
        msg.d_curiosity = float(d_curiosity)
        msg.d_boredom = float(d_boredom)
        msg.d_energy = float(d_energy)
        msg.d_silence_bias = float(d_silence_bias)

        msg.human_detected = human_detected
        msg.petit_detected = petit_detected
        msg.sleep_request = sleep_request

        msg.weight = float(weight)
        msg.source = source

        self.delta_pub.publish(msg)

    def vad_callback(self, msg: Bool) -> None:
        """音声活動検出."""
        if msg.data:
            # 話しかけられた → curiosity 上昇 / boredom 低下
            self.publish_delta(d_curiosity=0.2, d_boredom=-0.1, human_detected=True, weight=0.9, source='mic_vad')
        else:
            # 無音 → silence_bias 上昇
            self.publish_delta(d_silence_bias=0.05, weight=0.5, source='mic_vad')

    def doa_callback(self, msg: PoseStamped) -> None:
        """音源方向検出."""
        self.publish_delta(d_curiosity=0.3, weight=0.8, source='mic_doa')

    def hotword_callback(self, msg: Empty) -> None:
        """ホットワード検出."""
        self.publish_delta(d_curiosity=0.5, human_detected=True, weight=1.0, source='hotword')

    def mic_callback(self, msg: AudioDataStamped) -> None:
        """音量変化を見る（簡易）."""
        audio = msg.audio.data
        if not audio:
            return

        volume = sensor_influence_logic.calc_mic_volume(audio)

        if volume > sensor_influence_logic.MIC_VOLUME_THRESHOLD:  # 仮閾値
            self.publish_delta(d_curiosity=0.1, weight=0.6, source='mic_volume')

    def laser_callback(self, msg: LaserScan) -> None:
        """30秒に1回だけ処理."""
        now = time.time()
        if now - self.last_laser_time < 30.0:
            return
        self.last_laser_time = now

        min_dist = min(msg.ranges)

        if min_dist < 0.5:
            self.publish_delta(d_curiosity=0.4, human_detected=True, weight=0.7, source='laser_proximity')

    def leg_callback(self, msg: PositionMeasurementArray) -> None:
        """5秒に1回."""
        now = time.time()
        if now - self.last_leg_time < 5.0:
            return
        self.last_leg_time = now

        if len(msg.people) > 0:
            self.publish_delta(d_curiosity=0.6, human_detected=True, weight=0.9, source='leg_detector')

    def image_callback(self, msg: Image) -> None:
        """10秒に1回（画像変化を仮検出）."""
        now = time.time()
        if now - self.last_image_time < 10.0:
            return
        self.last_image_time = now

        if self.prev_image_stamp is not None:
            self.publish_delta(d_curiosity=0.2, weight=0.6, source='image_motion')

        self.prev_image_stamp = msg.header.stamp

    def odom_callback(self, msg: Odometry) -> None:
        """移動量があれば energy 低下."""
        pos = msg.pose.pose.position

        if self.prev_position is not None:
            dist = sensor_influence_logic.calc_odom_distance(self.prev_position.x, self.prev_position.y, pos.x, pos.y)

            if dist > sensor_influence_logic.ODOM_MOVE_THRESHOLD:
                self.publish_delta(d_energy=-0.1, weight=0.8, source='self_motion')

        self.prev_position = pos


def main() -> None:
    rclpy.init()
    node = SensorInfluenceNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
