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
"""helpers.py（api_server.py から抽出した純粋ヘルパー）のテスト.

api_server.py 本体は import 時に rclpy.init() が走るため import しない。
"""

import io
from pathlib import Path

from cube_petit_web_interface import helpers
import numpy as np
from PIL import Image
import pytest
import yaml

# --- amixer 出力パース ---

AMIXER_OUTPUT = """Simple mixer control 'Master',0
  Capabilities: pvolume pswitch pswitch-joined
  Playback channels: Front Left - Front Right
  Limits: Playback 0 - 65536
  Mono:
  Front Left: Playback 43690 [67%] [on]
  Front Right: Playback 43690 [67%] [on]
"""


class TestParseAmixerVolume:

    def test_parses_percentage(self) -> None:
        assert helpers.parse_amixer_volume(AMIXER_OUTPUT) == 67

    def test_returns_first_match(self) -> None:
        assert helpers.parse_amixer_volume('[12%] then [99%]') == 12

    def test_no_match_returns_minus_one(self) -> None:
        assert helpers.parse_amixer_volume('no percentage here') == -1

    def test_empty_string(self) -> None:
        assert helpers.parse_amixer_volume('') == -1

    def test_zero_and_hundred(self) -> None:
        assert helpers.parse_amixer_volume('[0%]') == 0
        assert helpers.parse_amixer_volume('[100%]') == 100


# --- places.yaml ---


class TestPlaces:

    def test_round_trip(self, tmp_path: Path) -> None:
        places_file = tmp_path / 'places.yaml'
        data = {
            'patrol': {
                'order': ['キッチン', 'リビング'],
                'places': {
                    'キッチン': {
                        'pose': [1.0, 2.0, 0.5],
                        'room': None
                    },
                    'リビング': {
                        'pose': [-1.0, 0.0, 3.14],
                        'room': None
                    },
                },
            },
        }
        helpers.save_places(places_file, data)
        assert helpers.load_places(places_file) == data

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert helpers.load_places(tmp_path / 'no_such.yaml') == {}

    def test_load_empty_file_returns_empty(self, tmp_path: Path) -> None:
        places_file = tmp_path / 'places.yaml'
        places_file.write_text('')
        assert helpers.load_places(places_file) == {}

    def test_save_preserves_key_order(self, tmp_path: Path) -> None:
        places_file = tmp_path / 'places.yaml'
        data = {'z_first': {}, 'a_second': {}}
        helpers.save_places(places_file, data)
        text = places_file.read_text()
        assert text.index('z_first') < text.index('a_second')


# --- マップディレクトリ探索 / パス導出 ---


@pytest.fixture
def map_dirs(tmp_path: Path) -> list:
    base = tmp_path / 'base'
    extra = tmp_path / 'extra'
    (base / 'office').mkdir(parents=True)
    (extra / 'home').mkdir(parents=True)
    return [base, extra]


class TestMapDirs:

    def test_find_in_base_dir(self, map_dirs: list) -> None:
        assert helpers.find_map_dir('office', map_dirs) == map_dirs[0] / 'office'

    def test_find_in_extra_dir(self, map_dirs: list) -> None:
        assert helpers.find_map_dir('home', map_dirs) == map_dirs[1] / 'home'

    def test_base_dir_has_priority(self, map_dirs: list) -> None:
        (map_dirs[1] / 'office').mkdir()
        assert helpers.find_map_dir('office', map_dirs) == map_dirs[0] / 'office'

    def test_not_found_returns_none(self, map_dirs: list) -> None:
        assert helpers.find_map_dir('nowhere', map_dirs) is None

    def test_map_places_path(self, map_dirs: list) -> None:
        assert helpers.map_places_path('office', map_dirs) == \
            map_dirs[0] / 'office' / 'places.yaml'
        assert helpers.map_places_path('nowhere', map_dirs) is None

    def test_map_rooms_path(self, map_dirs: list) -> None:
        assert helpers.map_rooms_path('home', map_dirs) == \
            map_dirs[1] / 'home' / 'rooms.yaml'
        assert helpers.map_rooms_path('nowhere', map_dirs) is None


# --- マップ別 places.yaml / rooms.yaml ---


class TestMapPlaces:

    def test_round_trip(self, map_dirs: list) -> None:
        places = [
            {
                'name': '充電スポット',
                'category': 'patrol',
                'pose': [0.5, 1.5, 0.0]
            },
            {
                'name': '窓際',
                'category': 'patrol',
                'pose': [2.0, -1.0, 1.57]
            },
        ]
        helpers.save_map_places('office', places, map_dirs)
        assert helpers.load_map_places('office', map_dirs) == places

    def test_load_missing_returns_empty_list(self, map_dirs: list) -> None:
        assert helpers.load_map_places('office', map_dirs) == []
        assert helpers.load_map_places('nowhere', map_dirs) == []

    def test_save_unknown_map_is_noop(self, map_dirs: list) -> None:
        helpers.save_map_places('nowhere', [{'name': 'x'}], map_dirs)
        assert helpers.load_map_places('nowhere', map_dirs) == []

    def test_yaml_structure(self, map_dirs: list) -> None:
        helpers.save_map_places('office', [{'name': 'a', 'pose': [0, 0, 0]}], map_dirs)
        data = yaml.safe_load((map_dirs[0] / 'office' / 'places.yaml').read_text())
        assert 'places' in data


class TestMapRooms:

    def test_round_trip(self, map_dirs: list) -> None:
        rooms = [
            {
                'name': '会議室',
                'points': [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
            },
        ]
        helpers.save_map_rooms('home', rooms, map_dirs)
        assert helpers.load_map_rooms('home', map_dirs) == rooms

    def test_load_missing_returns_empty_list(self, map_dirs: list) -> None:
        assert helpers.load_map_rooms('home', map_dirs) == []

    def test_save_unknown_map_is_noop(self, map_dirs: list) -> None:
        helpers.save_map_rooms('nowhere', [{'name': 'x'}], map_dirs)
        assert helpers.load_map_rooms('nowhere', map_dirs) == []


# --- プロンプト ---


class TestActivePromptName:

    def test_no_marker_returns_default(self, tmp_path: Path) -> None:
        marker = tmp_path / '.active_prompt'
        assert helpers.active_prompt_name(tmp_path, marker, 'default.txt') == 'default.txt'

    def test_marker_points_to_existing_file(self, tmp_path: Path) -> None:
        (tmp_path / 'custom.txt').write_text('hello')
        marker = tmp_path / '.active_prompt'
        marker.write_text('custom.txt\n')
        assert helpers.active_prompt_name(tmp_path, marker, 'default.txt') == 'custom.txt'

    def test_marker_points_to_missing_file(self, tmp_path: Path) -> None:
        marker = tmp_path / '.active_prompt'
        marker.write_text('gone.txt')
        assert helpers.active_prompt_name(tmp_path, marker, 'default.txt') == 'default.txt'


# --- 画像変換 (PGM <-> PNG) ---


def make_gray_image(w: int = 8, h: int = 6, seed: int = 42) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(h, w), dtype=np.uint8)
    return Image.fromarray(arr, mode='L')


class TestImageConversion:

    def test_pil_to_pgm_bytes_header(self) -> None:
        img = make_gray_image(8, 6)
        data = helpers.pil_to_pgm_bytes(img)
        assert data.startswith(b'P5\n8 6\n255\n')
        assert data == b'P5\n8 6\n255\n' + img.tobytes()

    def test_pgm_to_png_round_trip(self, tmp_path: Path) -> None:
        img = make_gray_image()
        pgm_path = tmp_path / 'map.pgm'
        pgm_path.write_bytes(helpers.pil_to_pgm_bytes(img))

        png_bytes = helpers.pgm_to_png_bytes(pgm_path)
        decoded = Image.open(io.BytesIO(png_bytes))
        assert decoded.format == 'PNG'
        assert np.array_equal(np.array(decoded.convert('L')), np.array(img))

    def test_png_bytes_to_pgm_round_trip(self, tmp_path: Path) -> None:
        img = make_gray_image(16, 4, seed=7)
        buf = io.BytesIO()
        img.save(buf, format='PNG')

        pgm_path = tmp_path / 'map_keepout.pgm'
        helpers.png_bytes_to_pgm(buf.getvalue(), pgm_path)

        restored = Image.open(pgm_path).convert('L')
        assert np.array_equal(np.array(restored), np.array(img))
        # 出力は PGM (P5) ヘッダを持つ
        assert pgm_path.read_bytes().startswith(b'P5\n16 4\n255\n')
