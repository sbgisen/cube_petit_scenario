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
"""フリート(複数ロボット)監視 API (/fleet/robots).

Tier 2「複数ロボット同時閲覧」: cube_petit_fleet_bridge (別リポジトリ cube_petit_ros)
が zenoh 経由で配信する各ロボットの pose/battery/map_name を集約して返す。
どのロボットの web_interface を開いても同じ全体像が見える対称設計
(単一の「ハブ」インスタンスは存在しない)。詳細は core.py / fleet_zenoh.py 参照。
"""

from fastapi import APIRouter

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


@router.get('/fleet/robots')
async def get_fleet_robots() -> dict:
    """Zenoh フリートネットワーク上で見えている全ロボットの最新状態を返す.

    `available=False` は zenoh 監視が起動できていないことを示す（例:
    `eclipse-zenoh` pip パッケージ未インストール、または `ZENOH_ROUTER_ENDPOINT`
    のルーターに到達できない）。フロントエンドはこの場合ピッカー自体を隠す
    （空リストとして表示しない）。
    """
    error = core.get_fleet_error()
    return {
        'available': error is None,
        'error': error,
        'robots': core.get_fleet_state(),
    }
