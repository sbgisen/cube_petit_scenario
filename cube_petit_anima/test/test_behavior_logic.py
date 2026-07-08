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

from cube_petit_anima import behavior_logic as logic
import pytest


class TestComputeSwing:

    def test_phase_advances_by_dt_times_speed(self) -> None:
        new_phase, _ = logic.compute_swing(0.0)
        assert new_phase == pytest.approx(0.1 * 1.2)

    def test_value_is_amplitude_times_sin(self) -> None:
        phase = 1.0
        new_phase, value = logic.compute_swing(phase)
        assert value == pytest.approx(1.5 * math.sin(new_phase))

    def test_value_within_limit(self) -> None:
        # 位相を進めていっても指令値は ±1.5 を超えない
        phase = 0.0
        for _ in range(200):
            phase, value = logic.compute_swing(phase)
            assert -1.5 <= value <= 1.5

    def test_clamp_when_amplitude_exceeds_limit(self) -> None:
        # sin がほぼ 1 になる位相で振幅を大きくするとクランプされる
        phase = math.pi / 2 - 0.1 * 1.2  # 進めた後に pi/2 になる
        _, value = logic.compute_swing(phase, amplitude=3.0)
        assert value == pytest.approx(1.5)

    def test_clamp_negative_side(self) -> None:
        phase = -math.pi / 2 - 0.1 * 1.2
        _, value = logic.compute_swing(phase, amplitude=3.0)
        assert value == pytest.approx(-1.5)

    def test_defaults_match_original_parameters(self) -> None:
        assert logic.SWING_AMPLITUDE == pytest.approx(1.5)
        assert logic.SWING_SPEED == pytest.approx(1.2)
        assert logic.SWING_DT == pytest.approx(0.1)
        assert logic.ANGULAR_Z_LIMIT == pytest.approx(1.5)
