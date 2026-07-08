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
"""internal_state_logic のテスト."""

import json
from pathlib import Path

import pytest

from cube_petit_anima import internal_state_logic as logic


def make_delta(d_curiosity: float = 0.0,
               d_boredom: float = 0.0,
               d_energy: float = 0.0,
               d_silence_bias: float = 0.0,
               weight: float = 1.0,
               human_detected: bool = False,
               petit_detected: bool = False,
               sleep_request: bool = False) -> dict:
    return {
        'd_curiosity': d_curiosity,
        'd_boredom': d_boredom,
        'd_energy': d_energy,
        'd_silence_bias': d_silence_bias,
        'weight': weight,
        'human_detected': human_detected,
        'petit_detected': petit_detected,
        'sleep_request': sleep_request,
    }


def make_values(curiosity: float = 50.0,
                boredom: float = 50.0,
                energy: float = 50.0,
                silence_bias: float = 50.0) -> dict:
    return {
        'curiosity': curiosity,
        'boredom': boredom,
        'energy': energy,
        'silence_bias': silence_bias,
    }


# ==================================
# clamp
# ==================================
class TestClamp:

    def test_within_range(self) -> None:
        assert logic.clamp(42.5) == 42.5

    def test_below_lower_bound(self) -> None:
        assert logic.clamp(-3.0) == 0.0

    def test_above_upper_bound(self) -> None:
        assert logic.clamp(120.0) == 100.0

    def test_exact_bounds(self) -> None:
        assert logic.clamp(0.0) == 0.0
        assert logic.clamp(100.0) == 100.0


# ==================================
# aggregate_deltas
# ==================================
class TestAggregateDeltas:

    def test_empty_deltas_returns_base_drift(self) -> None:
        agg = logic.aggregate_deltas([], base_d_curiosity=0.03, base_d_boredom=0.05)
        assert agg['d_curiosity'] == pytest.approx(0.03)
        assert agg['d_boredom'] == pytest.approx(0.05)
        assert agg['d_energy'] == 0.0
        assert agg['d_silence_bias'] == 0.0
        assert agg['human_detected'] is False
        assert agg['petit_detected'] is False
        assert agg['sleep_request'] is False

    def test_multiple_deltas_weighted_sum(self) -> None:
        deltas = [
            make_delta(d_curiosity=0.2, d_boredom=-0.1, weight=0.5),
            make_delta(d_curiosity=0.4, d_energy=-0.1, weight=1.0),
        ]
        agg = logic.aggregate_deltas(deltas, base_d_curiosity=0.0, base_d_boredom=0.05)
        assert agg['d_curiosity'] == pytest.approx(0.2 * 0.5 + 0.4 * 1.0)
        assert agg['d_boredom'] == pytest.approx(0.05 + (-0.1) * 0.5)
        assert agg['d_energy'] == pytest.approx(-0.1)

    def test_weight_clamped_to_one(self) -> None:
        deltas = [make_delta(d_curiosity=1.0, weight=5.0)]
        agg = logic.aggregate_deltas(deltas, base_d_curiosity=0.0, base_d_boredom=0.0)
        assert agg['d_curiosity'] == pytest.approx(1.0)

    def test_negative_weight_clamped_to_zero(self) -> None:
        deltas = [make_delta(d_curiosity=1.0, weight=-1.0)]
        agg = logic.aggregate_deltas(deltas, base_d_curiosity=0.0, base_d_boredom=0.0)
        assert agg['d_curiosity'] == pytest.approx(0.0)

    def test_boolean_flags_or(self) -> None:
        deltas = [
            make_delta(human_detected=True),
            make_delta(petit_detected=True),
            make_delta(sleep_request=True),
        ]
        agg = logic.aggregate_deltas(deltas, base_d_curiosity=0.0, base_d_boredom=0.0)
        assert agg['human_detected'] is True
        assert agg['petit_detected'] is True
        assert agg['sleep_request'] is True


# ==================================
# update_sleep_mode (hysteresis)
# ==================================
class TestSleepHysteresis:

    def test_enter_sleep_at_exactly_20(self) -> None:
        # energy <= 20 で入眠（境界値ちょうど）
        assert logic.update_sleep_mode(False, 20.0, sleep_request=False) is True

    def test_no_sleep_just_above_20(self) -> None:
        assert logic.update_sleep_mode(False, 20.01, sleep_request=False) is False

    def test_enter_sleep_by_request(self) -> None:
        assert logic.update_sleep_mode(False, 100.0, sleep_request=True) is True

    def test_wake_at_exactly_60(self) -> None:
        # energy >= 60 で覚醒（境界値ちょうど）
        assert logic.update_sleep_mode(True, 60.0, sleep_request=False) is False

    def test_stay_sleeping_just_below_60(self) -> None:
        assert logic.update_sleep_mode(True, 59.99, sleep_request=False) is True

    def test_hysteresis_band_keeps_state(self) -> None:
        # 20 < energy < 60 の帯域では現状維持
        assert logic.update_sleep_mode(False, 40.0, sleep_request=False) is False
        assert logic.update_sleep_mode(True, 40.0, sleep_request=False) is True


# ==================================
# update_state
# ==================================
class TestUpdateState:

    def test_awake_drift_direction(self) -> None:
        # 覚醒中: boredom はベースドリフトで上昇、energy は -0.05
        values = make_values()
        new, sleeping = logic.update_state(values, [], False, base_d_curiosity=0.0)
        assert sleeping is False
        assert new['boredom'] == pytest.approx(50.05)
        assert new['energy'] == pytest.approx(49.95)
        assert new['curiosity'] == pytest.approx(50.0)
        assert new['silence_bias'] == pytest.approx(50.0)

    def test_sleeping_recovers_energy(self) -> None:
        # スリープ中: energy +0.4 / boredom -0.2
        values = make_values(energy=30.0)
        new, sleeping = logic.update_state(values, [], True, base_d_curiosity=0.0)
        assert sleeping is True
        assert new['energy'] == pytest.approx(30.4)
        assert new['boredom'] == pytest.approx(50.05 - 0.2)

    def test_enter_sleep_when_energy_drops(self) -> None:
        # デルタで energy が 20 以下になった場合、入眠して +0.4 が適用される
        values = make_values(energy=21.0)
        deltas = [make_delta(d_energy=-1.0, weight=1.0)]
        new, sleeping = logic.update_state(values, deltas, False, base_d_curiosity=0.0)
        assert sleeping is True
        assert new['energy'] == pytest.approx(20.0 + 0.4)

    def test_wake_when_energy_recovered(self) -> None:
        values = make_values(energy=59.7)
        new, sleeping = logic.update_state(values, [], True, base_d_curiosity=0.0)
        # 59.7 < 60 なのでまだスリープ継続
        assert sleeping is True
        values = make_values(energy=60.0)
        new, sleeping = logic.update_state(values, [], True, base_d_curiosity=0.0)
        # ちょうど 60 で覚醒 → 覚醒側の -0.05 が適用される
        assert sleeping is False
        assert new['energy'] == pytest.approx(59.95)

    def test_deltas_applied_and_clamped(self) -> None:
        values = make_values(curiosity=99.9, boredom=0.1, silence_bias=99.9)
        deltas = [make_delta(d_curiosity=10.0, d_boredom=-10.0, d_silence_bias=10.0, weight=1.0)]
        new, _ = logic.update_state(values, deltas, False, base_d_curiosity=0.0)
        assert new['curiosity'] == 100.0
        assert new['boredom'] == 0.0
        assert new['silence_bias'] == 100.0

    def test_detection_flags_forwarded(self) -> None:
        deltas = [make_delta(human_detected=True, petit_detected=True)]
        new, _ = logic.update_state(make_values(), deltas, False, base_d_curiosity=0.0)
        assert new['human_detected'] is True
        assert new['petit_detected'] is True

    def test_input_values_not_mutated(self) -> None:
        values = make_values()
        original = dict(values)
        logic.update_state(values, [], False, base_d_curiosity=0.0)
        assert values == original


# ==================================
# 永続化 (JSON)
# ==================================
class TestPersistence:

    def test_round_trip(self, tmp_path: Path) -> None:
        state_file = tmp_path / 'anima_state.json'
        values = {
            'curiosity': 61.5,
            'boredom': 42.0,
            'energy': 83.3,
            'silence_bias': 71.0,
            'body_generation': 2,
        }
        logic.save_state_file(state_file, values)
        loaded = logic.load_state_file(state_file)
        assert loaded == values

    def test_load_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert logic.load_state_file(tmp_path / 'no_such_file.json') is None

    def test_load_corrupt_file_raises(self, tmp_path: Path) -> None:
        state_file = tmp_path / 'anima_state.json'
        state_file.write_text('{ this is not json !!')
        with pytest.raises(Exception):
            logic.load_state_file(state_file)

    def test_load_missing_keys_uses_defaults(self, tmp_path: Path) -> None:
        state_file = tmp_path / 'anima_state.json'
        state_file.write_text(json.dumps({'curiosity': 10.0}))
        loaded = logic.load_state_file(state_file)
        assert loaded['curiosity'] == 10.0
        assert loaded['boredom'] == 40.0
        assert loaded['energy'] == 80.0
        assert loaded['silence_bias'] == 70.0
        assert loaded['body_generation'] == 1

    def test_default_state_file_path(self, tmp_path: Path) -> None:
        path = logic.default_state_file('cube_petit_orange', home_dir=tmp_path)
        assert path == tmp_path / '.cube_petit' / 'cube_petit_orange' / 'anima_state.json'

    def test_hostname_to_namespace(self) -> None:
        assert logic.hostname_to_namespace('cube-petit-orange') == 'cube_petit_orange'
        assert logic.hostname_to_namespace('nodash') == 'nodash'
