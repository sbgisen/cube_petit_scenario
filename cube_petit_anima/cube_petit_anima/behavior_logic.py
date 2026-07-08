"""behavior_node の純粋ロジック部分。

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
def compute_swing(phase, amplitude=SWING_AMPLITUDE, speed=SWING_SPEED, dt=SWING_DT,
                  limit=ANGULAR_Z_LIMIT):
    """スイング動作の正弦波計算。

    位相を dt * speed だけ進め、angular.z の指令値を返す。
    戻り値: (new_phase, angular_z)
    """
    new_phase = phase + dt * speed
    value = amplitude * math.sin(new_phase)
    return new_phase, max(-limit, min(limit, value))
