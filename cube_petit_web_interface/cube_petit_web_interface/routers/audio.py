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
"""音量制御 API (/audio/volume)."""

import subprocess

from fastapi import APIRouter

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


@router.get('/audio/volume')
async def get_audio_volume() -> dict:
    try:
        r_speaker = subprocess.run(['amixer', 'sget', 'Master'], capture_output=True, text=True)
        r_mic = subprocess.run(['amixer', 'sget', 'Capture'], capture_output=True, text=True)
        return {
            'speaker': core.helpers.parse_amixer_volume(r_speaker.stdout),
            'mic': core.helpers.parse_amixer_volume(r_mic.stdout),
        }
    except Exception as e:
        return {'speaker': -1, 'mic': -1, 'error': str(e)}


@router.post('/audio/volume')
async def set_audio_volume(type: str, value: int) -> dict:  # noqa: A002
    control = 'Master' if type == 'speaker' else 'Capture'
    try:
        subprocess.run(['amixer', 'sset', control, f'{value}%'], capture_output=True)
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
