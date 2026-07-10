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
"""behavior_logic のテスト."""

import math

import pytest

from cube_petit_anima import behavior_logic as logic


class TestComputeSwing:

    def test_phase_advances_by_dt_times_speed(self) -> None:
        new_phase, _ = logic.compute_swing(0.0)
        assert new_phase == pytest.approx(0.1 * 1.2)

    def test_value_is_amplitude_times_sin(self) -> None:
        phase = 1.0
        new_phase, value = logic.compute_swing(phase)
        assert value == pytest.approx(logic.SWING_AMPLITUDE * math.sin(new_phase))

    def test_value_within_limit(self) -> None:
        # 位相を進めていっても指令値は ±ANGULAR_Z_LIMIT を超えない
        phase = 0.0
        for _ in range(200):
            phase, value = logic.compute_swing(phase)
            assert -logic.ANGULAR_Z_LIMIT <= value <= logic.ANGULAR_Z_LIMIT

    def test_value_is_amplitude_argument_times_sin(self) -> None:
        # amplitude を明示的に渡した場合、その値が使われる（ノード側の
        # swing_amplitude パラメータ配線が正しく動くことの前提となる挙動）
        phase = 1.0
        new_phase, value = logic.compute_swing(phase, amplitude=2.0)
        assert value == pytest.approx(2.0 * math.sin(new_phase))

    def test_clamp_when_amplitude_exceeds_limit(self) -> None:
        # sin がほぼ 1 になる位相で振幅を limit 超えまで大きくするとクランプされる
        phase = math.pi / 2 - 0.1 * 1.2  # 進めた後に pi/2 になる
        _, value = logic.compute_swing(phase, amplitude=logic.ANGULAR_Z_LIMIT + 1.0)
        assert value == pytest.approx(logic.ANGULAR_Z_LIMIT)

    def test_clamp_negative_side(self) -> None:
        phase = -math.pi / 2 - 0.1 * 1.2
        _, value = logic.compute_swing(phase, amplitude=logic.ANGULAR_Z_LIMIT + 1.0)
        assert value == pytest.approx(-logic.ANGULAR_Z_LIMIT)

    def test_defaults_match_updated_parameters(self) -> None:
        # 2026-07-10 実機フィードバック対応: amplitude/limit を引き上げ
        # (teleopの scale_angular.yaw=5.0 を安全上限として採用)
        assert logic.SWING_AMPLITUDE == pytest.approx(4.0)
        assert logic.SWING_SPEED == pytest.approx(1.2)
        assert logic.SWING_DT == pytest.approx(0.1)
        assert logic.ANGULAR_Z_LIMIT == pytest.approx(5.0)


class TestComputeSwingActive:

    def test_disabled_never_swings(self) -> None:
        # swing_enabled=False なら条件を満たしても常に False（従来の挙動）
        assert logic.compute_swing_active(False, energy=100.0, boredom=100.0) is False
        assert logic.compute_swing_active(False, energy=0.0, boredom=0.0) is False

    def test_enabled_swings_when_bored_and_energetic(self) -> None:
        assert logic.compute_swing_active(True, energy=50.0, boredom=90.0) is True

    def test_enabled_no_swing_when_energy_low(self) -> None:
        assert logic.compute_swing_active(True, energy=19.99, boredom=90.0) is False

    def test_enabled_no_swing_when_not_bored(self) -> None:
        assert logic.compute_swing_active(True, energy=50.0, boredom=50.0) is False

    def test_energy_threshold_boundary(self) -> None:
        # energy はしきい値ちょうどで許可（元コードは energy < 20 で除外）
        assert logic.compute_swing_active(True, energy=20.0, boredom=90.0) is True

    def test_boredom_threshold_boundary(self) -> None:
        # boredom はしきい値ちょうどでは発動しない（元コードは boredom > 80）
        assert logic.compute_swing_active(True, energy=50.0, boredom=80.0) is False

    def test_thresholds_match_original_parameters(self) -> None:
        assert logic.ENERGY_LOW_THRESHOLD == 20
        assert logic.BOREDOM_HIGH_THRESHOLD == 80
