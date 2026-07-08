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
"""SEPlayer の設定パースのテスト（play() は aplay に依存するため対象外）."""

import json
from pathlib import Path
from typing import Callable

from cube_petit_anima.utils.sound_effect_play import SEPlayer
import pytest
import yaml


@pytest.fixture
def make_config(tmp_path: Path) -> Callable:
    """一時ディレクトリに se.yaml + mapping json を作る."""

    def _make(mapping: list) -> Path:
        mapping_path = tmp_path / 'mapping.json'
        mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding='utf-8')

        config_path = tmp_path / 'se.yaml'
        config = {
            'se_parent_dir': str(tmp_path / 'assets'),
            'mapping_file_path': str(mapping_path),
        }
        config_path.write_text(yaml.dump(config), encoding='utf-8')
        return config_path

    return _make


class TestSEPlayerConfig:

    def test_state_map_grouping(self, make_config: Callable) -> None:
        mapping = [
            {
                'state': '起動',
                'path': 'a.wav',
                'volume': 100
            },
            {
                'state': '起動',
                'path': 'b.wav',
                'volume': 80
            },
            {
                'state': 'スリープ移行',
                'path': 'c.wav',
                'volume': 50
            },
        ]
        player = SEPlayer(make_config(mapping))

        assert set(player.state_map.keys()) == {'起動', 'スリープ移行'}
        assert len(player.state_map['起動']) == 2
        assert len(player.state_map['スリープ移行']) == 1
        assert player.state_map['起動'][0]['path'] == 'a.wav'
        assert player.state_map['スリープ移行'][0]['volume'] == 50

    def test_base_dir_from_config(self, make_config: Callable, tmp_path: Path) -> None:
        player = SEPlayer(make_config([]))
        assert player.base_dir == tmp_path / 'assets'

    def test_empty_mapping(self, make_config: Callable) -> None:
        player = SEPlayer(make_config([]))
        assert player.state_map == {}

    def test_mapping_items_preserved(self, make_config: Callable) -> None:
        # volume / seconds 等の付随情報も item として保持される
        mapping = [
            {
                'state': '感情：興味',
                'path': 'x.wav',
                'volume': 70,
                'seconds': 1.2,
                'notes': 'テスト'
            },
        ]
        player = SEPlayer(make_config(mapping))
        item = player.state_map['感情：興味'][0]
        assert item['seconds'] == 1.2
        assert item['notes'] == 'テスト'

    def test_missing_config_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            SEPlayer(tmp_path / 'no_such_config.yaml')
