"""sensor_influence_node の純粋ロジック部分。

ROS に依存しない（rclpy / msgs を import しない）ため、
素の Python 環境で単体テストできる。
"""

import math

# mic_callback で使う音量の仮閾値
MIC_VOLUME_THRESHOLD = 20

# odom_callback で「移動あり」とみなす距離閾値 [m]
ODOM_MOVE_THRESHOLD = 0.01


# ==================================
def calc_mic_volume(audio, sample_count=1000):
    """音量変化を見る（簡易）: 先頭 sample_count サンプルの絶対値平均"""
    return sum(abs(b) for b in audio[:sample_count]) / float(sample_count)


# ==================================
def calc_odom_distance(prev_x, prev_y, cur_x, cur_y):
    """前回位置からの移動距離 [m]"""
    dx = cur_x - prev_x
    dy = cur_y - prev_y
    return math.sqrt(dx * dx + dy * dy)
