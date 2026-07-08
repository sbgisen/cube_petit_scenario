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
"""sensor_influence_logic のテスト."""

from cube_petit_anima import sensor_influence_logic as logic
import pytest


class TestCalcMicVolume:

    def test_average_of_absolute_values(self) -> None:
        # 1000 サンプル全て 10 → 平均 10
        audio = [10] * 1000
        assert logic.calc_mic_volume(audio) == pytest.approx(10.0)

    def test_negative_samples_use_absolute_value(self) -> None:
        audio = [-10] * 1000
        assert logic.calc_mic_volume(audio) == pytest.approx(10.0)

    def test_only_first_1000_samples_used(self) -> None:
        # 先頭 1000 サンプルは 10、以降の大音量は無視される
        audio = [10] * 1000 + [127] * 1000
        assert logic.calc_mic_volume(audio) == pytest.approx(10.0)

    def test_short_audio_divided_by_sample_count(self) -> None:
        # サンプル数が 1000 未満でも 1000 で割る（元実装と同じ）
        audio = [100] * 500
        assert logic.calc_mic_volume(audio) == pytest.approx(50.0)

    def test_threshold_constant(self) -> None:
        assert logic.MIC_VOLUME_THRESHOLD == 20


class TestCalcOdomDistance:

    def test_pythagorean_distance(self) -> None:
        assert logic.calc_odom_distance(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)

    def test_zero_distance(self) -> None:
        assert logic.calc_odom_distance(1.5, -2.0, 1.5, -2.0) == pytest.approx(0.0)

    def test_negative_direction(self) -> None:
        assert logic.calc_odom_distance(1.0, 1.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_move_threshold_constant(self) -> None:
        assert logic.ODOM_MOVE_THRESHOLD == pytest.approx(0.01)
