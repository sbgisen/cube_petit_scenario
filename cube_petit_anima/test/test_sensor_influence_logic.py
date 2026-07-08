"""sensor_influence_logic のテスト"""

import pytest

from cube_petit_anima import sensor_influence_logic as logic


class TestCalcMicVolume:

    def test_average_of_absolute_values(self):
        # 1000 サンプル全て 10 → 平均 10
        audio = [10] * 1000
        assert logic.calc_mic_volume(audio) == pytest.approx(10.0)

    def test_negative_samples_use_absolute_value(self):
        audio = [-10] * 1000
        assert logic.calc_mic_volume(audio) == pytest.approx(10.0)

    def test_only_first_1000_samples_used(self):
        # 先頭 1000 サンプルは 10、以降の大音量は無視される
        audio = [10] * 1000 + [127] * 1000
        assert logic.calc_mic_volume(audio) == pytest.approx(10.0)

    def test_short_audio_divided_by_sample_count(self):
        # サンプル数が 1000 未満でも 1000 で割る（元実装と同じ）
        audio = [100] * 500
        assert logic.calc_mic_volume(audio) == pytest.approx(50.0)

    def test_threshold_constant(self):
        assert logic.MIC_VOLUME_THRESHOLD == 20


class TestCalcOdomDistance:

    def test_pythagorean_distance(self):
        assert logic.calc_odom_distance(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)

    def test_zero_distance(self):
        assert logic.calc_odom_distance(1.5, -2.0, 1.5, -2.0) == pytest.approx(0.0)

    def test_negative_direction(self):
        assert logic.calc_odom_distance(1.0, 1.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_move_threshold_constant(self):
        assert logic.ODOM_MOVE_THRESHOLD == pytest.approx(0.01)
