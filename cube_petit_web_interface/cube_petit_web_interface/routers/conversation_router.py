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
"""フリート会話デモ「指揮者」API (/fleet/conversation/*).

ROSConJP 2026ブースデモ用。参加機体(orange/pink/violet)の掛け合い台本を
LLMで1回生成し、zenoh speak commandで順に発話させる「台本モード」の
開始/停止/状況取得。詳細は conversation_conductor.py / plans/conversation_demo_plan.md
(orange_petit_claudeリポジトリ)参照。

/fleet/command や /fleet/chase/* (routers/fleet.py) と同じくフリート zenoh
watcher前提の機能なので、命名は既存の `/ros/conversation/*`
(routers/conversation.py、単一機体のrealtime会話ON/OFF)とは独立させている。
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


class ConversationStartRequest(BaseModel):
    participants: list[str]
    mode: str = 'script'
    # interactive(掛け合い)モードのみ有効。各ロボット発話後に人間の発話を
    # 待つ「間」の秒数(省略時はconversation_conductor_logic.
    # DEFAULT_HUMAN_WINDOW_SEC=2.5秒)。フロントに直接のUIは無いが、将来
    # の調整用にAPIとしては受けておく。
    human_window_sec: float | None = None
    # 会場コンテキスト(台本/掛け合い両モードのLLMプロンプトに差し込む)。
    # 省略/空文字ならconversation_conductor_logic.DEFAULT_VENUE_CONTEXT
    # (ROSConJP 2026ブース想定の既定文)を使う。フロントの「会場コンテキスト」
    # 折りたたみテキストエリアから当日ブースで話題を差し替えられるようにする。
    context: str | None = None


class ConversationStartResponse(BaseModel):
    ok: bool
    error: str = ''


@router.post('/fleet/conversation/start', response_model=ConversationStartResponse)
async def start_fleet_conversation(req: ConversationStartRequest) -> ConversationStartResponse:
    """会話デモを開始する(mode='script'(台本)/'interactive'(掛け合い))."""
    try:
        core.start_fleet_conversation(req.participants, req.mode, req.human_window_sec, req.context)
    except (RuntimeError, core.conversation_conductor.ConductorError) as error:
        return ConversationStartResponse(ok=False, error=str(error))
    return ConversationStartResponse(ok=True)


@router.post('/fleet/conversation/stop')
async def stop_fleet_conversation() -> dict:
    """会話デモを停止する(実行中でなければ何もしない)."""
    core.stop_fleet_conversation()
    return {'ok': True}


@router.get('/fleet/conversation/status')
async def get_fleet_conversation_status() -> dict:
    """会話デモの現在状態(実行中か・現在ターン・会話ログ・経過秒)を返す."""
    return core.get_fleet_conversation_status()
