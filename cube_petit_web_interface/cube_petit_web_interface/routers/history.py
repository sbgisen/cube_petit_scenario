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
"""会話履歴管理 API (/history/*)."""

import subprocess

from fastapi import APIRouter

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


@router.get('/history/list')
async def list_history() -> dict:
    core.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in core.HISTORY_DIR.glob('*.jsonl'))
    active = ''
    if core.HISTORY_ACTIVE_MARKER.exists():
        candidate = core.HISTORY_ACTIVE_MARKER.read_text(encoding='utf-8').strip()
        if (core.HISTORY_DIR / candidate).exists():
            active = candidate
    if not active and files:
        active = files[0]
    return {'files': files, 'active': active}


@router.post('/history/activate')
async def activate_history(file: str, namespace: str = core.DEFAULT_NAMESPACE) -> dict:
    path = core.HISTORY_DIR / file
    if not path.exists():
        core.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path.touch()
    core.HISTORY_ACTIVE_MARKER.write_text(file, encoding='utf-8')
    subprocess.run(
        ['ros2', 'param', 'set', f'/{namespace}/realtime_gpt_chat', 'history_file',
         str(path)],
        capture_output=True,
        timeout=5,
        env=core.ROS_ENV,
    )
    return {'ok': True}


@router.post('/history/new')
async def new_history(name: str) -> dict:
    if not name.endswith('.jsonl'):
        name += '.jsonl'
    path = core.HISTORY_DIR / name
    if path.exists():
        return {'ok': False, 'error': 'Already exists'}
    core.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path.touch()
    return {'ok': True, 'file': name}


@router.delete('/history')
async def delete_history(file: str) -> dict:
    if file in core.PROTECTED_HISTORY:
        return {'ok': False, 'error': 'Protected file'}
    path = core.HISTORY_DIR / file
    if path.exists():
        path.unlink()
    if core.HISTORY_ACTIVE_MARKER.exists() and core.HISTORY_ACTIVE_MARKER.read_text().strip() == file:
        core.HISTORY_ACTIVE_MARKER.unlink()
    return {'ok': True}
