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
"""internal_state_node の純粋ロジック部分.

ROS に依存しない（rclpy / msgs を import しない）ため、
素の Python 環境で単体テストできる。
ノード側は msg <-> plain dict の変換だけを行い、計算はここに委譲する。
"""

import json
from pathlib import Path
from typing import Optional, Union

# 状態値のキー（0〜100 にクランプされる連続値）
STATE_KEYS = ['curiosity', 'boredom', 'energy', 'silence_bias']

# スリープヒステリシスの閾値
SLEEP_ENERGY_THRESHOLD = 20
WAKE_ENERGY_THRESHOLD = 60


# ==================================
def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """値を [low, high] に収める."""
    return max(low, min(high, value))


# ==================================
def aggregate_deltas(deltas: list, base_d_curiosity: float, base_d_boredom: float) -> dict:
    """デルタ列を集約する.

    deltas: dict のリスト。各 dict は以下のキーを持つ:
        d_curiosity, d_boredom, d_energy, d_silence_bias (float),
        weight (float), human_detected, petit_detected, sleep_request (bool)
    base_d_curiosity / base_d_boredom: ベースドリフト量

    戻り値: 集約結果の dict
    """
    d_curiosity = base_d_curiosity
    d_boredom = base_d_boredom
    d_energy = 0.0
    d_silence = 0.0

    human_detected = False
    petit_detected = False
    sleep_request = False

    for delta in deltas:
        w = max(0.0, min(1.0, delta['weight']))

        d_curiosity += delta['d_curiosity'] * w
        d_boredom += delta['d_boredom'] * w
        d_energy += delta['d_energy'] * w
        d_silence += delta['d_silence_bias'] * w

        human_detected = human_detected or delta['human_detected']
        petit_detected = petit_detected or delta['petit_detected']
        sleep_request = sleep_request or delta['sleep_request']

    return {
        'd_curiosity': d_curiosity,
        'd_boredom': d_boredom,
        'd_energy': d_energy,
        'd_silence_bias': d_silence,
        'human_detected': human_detected,
        'petit_detected': petit_detected,
        'sleep_request': sleep_request,
    }


# ==================================
def update_sleep_mode(is_sleeping: bool, energy: float, sleep_request: bool) -> bool:
    """スリープヒステリシス（energy<=20 で入眠、>=60 で覚醒）."""
    if not is_sleeping and (energy <= SLEEP_ENERGY_THRESHOLD or sleep_request):
        return True
    elif is_sleeping and energy >= WAKE_ENERGY_THRESHOLD:
        return False
    return is_sleeping


# ==================================
def update_state(values: dict,
                 deltas: list,
                 is_sleeping: bool,
                 base_d_curiosity: float,
                 base_d_boredom: float = 0.05) -> tuple:
    """1ステップ分の状態更新を計算する.

    values: STATE_KEYS を持つ dict（現在の状態値）
    deltas: aggregate_deltas() に渡すデルタ dict のリスト
    is_sleeping: 現在スリープ中か
    base_d_curiosity: ベースドリフト（ノード側で乱数生成して渡す）

    戻り値: (new_values, new_is_sleeping)
        new_values は STATE_KEYS + human_detected / petit_detected を持つ dict
    """
    agg = aggregate_deltas(deltas, base_d_curiosity, base_d_boredom)

    new = {key: values[key] for key in STATE_KEYS}

    # --- Apply deltas ---
    new['curiosity'] += agg['d_curiosity']
    new['boredom'] += agg['d_boredom']
    new['energy'] += agg['d_energy']
    new['silence_bias'] += agg['d_silence_bias']

    new['human_detected'] = agg['human_detected']
    new['petit_detected'] = agg['petit_detected']

    # Sleep hysteresis
    new_is_sleeping = update_sleep_mode(is_sleeping, new['energy'], agg['sleep_request'])

    # Energy auto behavior
    if new_is_sleeping:
        new['energy'] += 0.4
        new['boredom'] -= 0.2
    else:
        new['energy'] -= 0.05

    # Clamp
    for key in STATE_KEYS:
        new[key] = clamp(new[key])

    return new, new_is_sleeping


# ==================================
# 永続化 (JSON)
# ==================================
def default_state_file(namespace: str, home_dir: Union[str, Path, None] = None) -> Path:
    """状態ファイルのデフォルトパス（home_dir 指定でテスト時に差し替え可能）."""
    base = Path(home_dir) if home_dir is not None else Path.home()
    return base / '.cube_petit' / namespace / 'anima_state.json'


def hostname_to_namespace(raw_hostname: str) -> str:
    """ホスト名 → namespace（'-' を '_' に置換）."""
    return raw_hostname.replace('-', '_')


def load_state_file(state_file: Union[str, Path]) -> Optional[dict]:
    """状態ファイルを読み込む.

    ファイルが無ければ None を返す。
    破損している場合は例外を送出する（呼び出し側でデフォルト初期化する）。
    """
    state_file = Path(state_file)
    if not state_file.exists():
        return None

    with open(state_file, 'r') as f:
        data = json.load(f)

    return {
        'curiosity': data.get('curiosity', 60.0),
        'boredom': data.get('boredom', 40.0),
        'energy': data.get('energy', 80.0),
        'silence_bias': data.get('silence_bias', 70.0),
        'body_generation': data.get('body_generation', 1),
    }


def save_state_file(state_file: Union[str, Path], values: dict) -> None:
    """状態値 dict を JSON として書き込む."""
    with open(state_file, 'w') as f:
        json.dump(values, f)
