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
"""フリート(複数ロボット)監視・操作 API (/fleet/robots, /fleet/command).

Tier 2「複数ロボット同時閲覧」: cube_petit_fleet_bridge (別リポジトリ cube_petit_ros)
が zenoh 経由で配信する各ロボットの pose/battery/map_name を集約して返す。
どのロボットの web_interface を開いても同じ全体像が見える対称設計
(単一の「ハブ」インスタンスは存在しない)。詳細は core.py / fleet_zenoh.py 参照。

/fleet/command は「フリート運用」ダッシュボード(集合・追いかけっこモード)から
自分以外のロボットへ move_to_pose を送るための書き込みAPI。ROSConJP 2026デモの
「追いかけっこ・すれ違い挨拶」用に追加(plans/cube_petit_fleet_adapter_plan.md参照)。
"""

from fastapi import APIRouter
from pydantic import BaseModel

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


class FleetCommandRequest(BaseModel):
    robot_name: str
    method: str
    args: dict = {}


class FleetCommandResponse(BaseModel):
    ok: bool
    command_id: str = ''
    error: str = ''


class ChaseStartRequest(BaseModel):
    chaser: str
    target: str


class ChaseStartResponse(BaseModel):
    ok: bool
    id: str = ''
    error: str = ''


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


@router.post('/fleet/command', response_model=FleetCommandResponse)
async def post_fleet_command(req: FleetCommandRequest) -> FleetCommandResponse:
    """フリート内のロボットへコマンド(主にmove_to_pose)を送る.

    完了は待たない(fire-and-forget)。フロントエンドは対象ロボットの
    /fleet/robots の pose が実際に動くのを見て進捗を判断する。
    """
    try:
        command_id = core.send_fleet_command(req.robot_name, req.method, req.args)
    except RuntimeError as error:
        return FleetCommandResponse(ok=False, error=str(error))
    return FleetCommandResponse(ok=True, command_id=command_id)


@router.post('/fleet/chase/start', response_model=ChaseStartResponse)
async def start_chase(req: ChaseStartRequest) -> ChaseStartResponse:
    """追いかけっこペアを開始する.

    このAPIサーバー常駐プロセス内のループで実行され、ダッシュボードの
    タブ切替/クローズに影響されない。
    """
    try:
        pair_id = core.start_fleet_chase(req.chaser, req.target)
    except (RuntimeError, ValueError) as error:
        return ChaseStartResponse(ok=False, error=str(error))
    return ChaseStartResponse(ok=True, id=pair_id)


@router.post('/fleet/chase/stop')
async def stop_chase(pair_id: str) -> dict:
    """追いかけっこペアを停止する."""
    return {'ok': core.stop_fleet_chase(pair_id)}


@router.get('/fleet/chase/list')
async def list_chase() -> dict:
    """現在アクティブな追いかけっこペア一覧を返す."""
    return {'pairs': core.list_fleet_chase()}
