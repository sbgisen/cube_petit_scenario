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
"""プロンプト管理 API (/prompt/*)."""

import subprocess
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


class PromptBody(BaseModel):
    content: str


def _active_prompt_name() -> str:
    return core.helpers.active_prompt_name(core.PROMPT_DIR, core.ACTIVE_MARKER, core.PROMPT_FILE.name)


@router.get('/prompt/list')
async def list_prompts() -> dict:
    files = sorted(p.name for p in core.PROMPT_DIR.glob('*.txt'))
    return {'files': files, 'active': _active_prompt_name()}


@router.get('/prompt')
async def get_prompt(file: Optional[str] = None) -> dict:
    path = core.PROMPT_DIR / file if file else core.PROMPT_FILE
    content = path.read_text(encoding='utf-8') if path.exists() else ''
    return {'content': content, 'file': path.name}


@router.post('/prompt')
async def set_prompt(body: PromptBody, file: Optional[str] = None) -> dict:
    name = file or core.PROMPT_FILE.name
    if name in core.PROTECTED_PROMPTS:
        return {'ok': False, 'error': 'Protected file'}
    path = core.PROMPT_DIR / name
    path.write_text(body.content, encoding='utf-8')
    return {'ok': True}


@router.post('/prompt/activate')
async def activate_prompt(file: str, namespace: str = 'cube_petit_orange') -> dict:
    src = core.PROMPT_DIR / file
    if not src.exists():
        return {'ok': False, 'error': 'File not found'}
    core.ACTIVE_MARKER.write_text(file, encoding='utf-8')
    subprocess.run(
        ['ros2', 'param', 'set', f'/{namespace}/realtime_gpt_chat', 'setting_file',
         str(src)],
        capture_output=True,
        timeout=5,
        env=core.ROS_ENV,
    )
    return {'ok': True}


@router.post('/prompt/new')
async def new_prompt(name: str) -> dict:
    if not name.endswith('.txt'):
        name += '.txt'
    path = core.PROMPT_DIR / name
    if path.exists():
        return {'ok': False, 'error': 'Already exists'}
    path.write_text('', encoding='utf-8')
    return {'ok': True, 'file': name}


@router.delete('/prompt')
async def delete_prompt(file: str) -> dict:
    if file in core.PROTECTED_PROMPTS:
        return {'ok': False, 'error': 'Protected file'}
    path = core.PROMPT_DIR / file
    if path.exists():
        path.unlink()
    if core.ACTIVE_MARKER.exists() and core.ACTIVE_MARKER.read_text().strip() == file:
        core.ACTIVE_MARKER.unlink()
    return {'ok': True}
