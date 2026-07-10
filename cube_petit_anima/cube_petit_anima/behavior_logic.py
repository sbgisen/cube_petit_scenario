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
# 実機フィードバック(2026-07-10): amplitude=1.5 では静止摩擦に負けてほぼ回らなかった
# (指令 angular.z≈1.35 に対し odom は±0.03程度)。
# teleop(ps4.config.yaml の scale_angular.yaw=5.0、turbo側の上書きなし＝実質的な上限)を
# 基準に、その上限を超えない範囲でamplitudeを引き上げる。
SWING_AMPLITUDE = 4.0
SWING_SPEED = 1.2
SWING_DT = 0.1
# teleopの scale_angular.yaw(5.0)を安全上限として採用（teleopで実際に到達している値のため）
ANGULAR_Z_LIMIT = 5.0

# スイング開始判定のしきい値（callback 由来）
ENERGY_LOW_THRESHOLD = 20
BOREDOM_HIGH_THRESHOLD = 80


# ==================================
def compute_swing_active(swing_enabled: bool,
                         energy: float,
                         boredom: float,
                         energy_threshold: float = ENERGY_LOW_THRESHOLD,
                         boredom_threshold: float = BOREDOM_HIGH_THRESHOLD) -> bool:
    """スイング動作を行うべきかの判定.

    swing_enabled が False なら常に False（従来どおりスイングしない）。
    True の場合、エネルギーが十分（energy >= energy_threshold）かつ
    退屈度が高い（boredom > boredom_threshold）ときにスイングする。
    """
    if not swing_enabled:
        return False
    if energy < energy_threshold:
        return False
    return boredom > boredom_threshold


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
