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
"""sensor_influence_node の純粋ロジック部分.

ROS に依存しない（rclpy / msgs を import しない）ため、
素の Python 環境で単体テストできる。
"""

import math
from typing import Sequence

# mic_callback で使う音量の仮閾値
MIC_VOLUME_THRESHOLD = 20

# odom_callback で「移動あり」とみなす距離閾値 [m]
ODOM_MOVE_THRESHOLD = 0.01


# ==================================
def calc_mic_volume(audio: Sequence[int], sample_count: int = 1000) -> float:
    """音量変化を見る（簡易）: 先頭 sample_count サンプルの絶対値平均."""
    return sum(abs(b) for b in audio[:sample_count]) / float(sample_count)


# ==================================
def calc_odom_distance(prev_x: float, prev_y: float, cur_x: float, cur_y: float) -> float:
    """前回位置からの移動距離 [m]."""
    dx = cur_x - prev_x
    dy = cur_y - prev_y
    return math.sqrt(dx * dx + dy * dy)
