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
"""behavior_node の純粋ロジック部分.

ROS に依存しない（rclpy / msgs を import しない）ため、
素の Python 環境で単体テストできる。
"""

import math

# スイング動作のデフォルトパラメータ（update_motion 由来）
SWING_AMPLITUDE = 1.5
SWING_SPEED = 1.2
SWING_DT = 0.1
ANGULAR_Z_LIMIT = 1.5


# ==================================
def compute_swing(phase: float,
                  amplitude: float = SWING_AMPLITUDE,
                  speed: float = SWING_SPEED,
                  dt: float = SWING_DT,
                  limit: float = ANGULAR_Z_LIMIT) -> tuple:
    """スイング動作の正弦波計算.

    位相を dt * speed だけ進め、angular.z の指令値を返す。
    戻り値: (new_phase, angular_z)
    """
    new_phase = phase + dt * speed
    value = amplitude * math.sin(new_phase)
    return new_phase, max(-limit, min(limit, value))
