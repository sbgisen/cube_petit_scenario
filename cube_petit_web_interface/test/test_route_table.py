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
"""ルートテーブルのスナップショットテスト（api_server.py 分割の等価性検証）.

route_table_snapshot.txt は分割前の api_server.py（単一ファイル版）から
生成したもの。分割後も (methods, path, name) の集合が完全一致することを保証する。

rclpy は不要（core.py が rclpy を関数内 import にしているため）。
fastapi が無い環境では skip する。
"""

from pathlib import Path
import sys

import pytest

pytest.importorskip('fastapi')

SNAPSHOT_FILE = Path(__file__).resolve().parent / 'route_table_snapshot.txt'


def _iter_routes(routes: list) -> list:
    """include_router がルートをコピーせず内包する FastAPI 版にも対応して平坦化する."""
    flat = []
    for route in routes:
        if hasattr(route, 'path'):
            flat.append(route)
            continue
        # FastAPI >= 0.129 の _IncludedRouter は original_router 経由でルートを持つ
        sub = getattr(route, 'routes', None)
        if sub is None:
            sub = getattr(getattr(route, 'original_router', None), 'routes', None)
        if sub is not None:
            flat.extend(_iter_routes(sub))
    return flat


def _dump_route_table() -> list[str]:
    from cube_petit_web_interface.api_server import app
    lines = []
    for route in _iter_routes(app.routes):
        methods = ','.join(sorted(getattr(route, 'methods', None) or []))
        lines.append(f'{methods} {route.path} {route.name}')
    return sorted(lines)


def test_route_table_matches_snapshot() -> None:
    expected = SNAPSHOT_FILE.read_text(encoding='utf-8').strip().splitlines()
    assert _dump_route_table() == expected


def test_import_does_not_start_ros() -> None:
    """App の import 時に rclpy が読み込まれない（import-safe である）こと."""
    import cube_petit_web_interface.api_server  # noqa: F401
    assert 'rclpy' not in sys.modules
