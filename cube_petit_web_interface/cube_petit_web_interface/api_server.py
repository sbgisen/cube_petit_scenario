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
"""FastAPI バックエンドのエントリポイント.

app の生成・CORS 設定・各ドメインの APIRouter の登録のみを行う。
共有状態（rclpy 常駐ノード・launch プロセス・定数）は core.py、
各エンドポイントの実装は routers/ 以下を参照。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface.routers import audio
    from cube_petit_web_interface.routers import conversation
    from cube_petit_web_interface.routers import conversation_router
    from cube_petit_web_interface.routers import fleet
    from cube_petit_web_interface.routers import history
    from cube_petit_web_interface.routers import launch
    from cube_petit_web_interface.routers import map_router
    from cube_petit_web_interface.routers import places
    from cube_petit_web_interface.routers import prompt
    from cube_petit_web_interface.routers import system

    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core
    from routers import audio
    from routers import conversation
    from routers import conversation_router
    from routers import fleet
    from routers import history
    from routers import launch
    from routers import map_router
    from routers import places
    from routers import prompt
    from routers import system

app = FastAPI(lifespan=core.lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

for module in (launch, system, conversation, conversation_router, audio, map_router, places, prompt, history, fleet):
    app.include_router(module.router)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
