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
"""ポイント管理 API (/places/*) — グローバル places.yaml を扱う."""

from fastapi import APIRouter
from pydantic import BaseModel

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


def _load_places() -> dict:
    return core.helpers.load_places(core.PLACES_FILE)


def _save_places(data: dict) -> None:
    core.helpers.save_places(core.PLACES_FILE, data)


@router.get('/places')
async def get_places() -> dict:
    data = _load_places()
    result = []
    for category, section in data.items():
        if category == 'rooms' or not isinstance(section, dict):
            continue
        for name, info in section.get('places', {}).items():
            result.append({'category': category, 'name': name, 'pose': info.get('pose', [])})
    return {'places': result}


@router.post('/places/add')
async def add_place(namespace: str, name: str, category: str = 'patrol') -> dict:
    pose = core.get_robot_pose(namespace)
    if pose is None:
        return {'ok': False, 'error': 'Cannot get robot position from TF'}
    data = _load_places()
    section = data.setdefault(category, {'order': [], 'places': {}})
    section.setdefault('order', [])
    section.setdefault('places', {})
    section['places'][name] = {'pose': pose, 'room': None}
    if name not in section['order']:
        section['order'].append(name)
    _save_places(data)
    return {'ok': True, 'pose': pose}


@router.delete('/places/remove')
async def remove_place(category: str, name: str) -> dict:
    data = _load_places()
    section = data.get(category, {})
    if name in section.get('places', {}):
        del section['places'][name]
    if name in section.get('order', []):
        section['order'].remove(name)
    _save_places(data)
    return {'ok': True}


class PlaceManualBody(BaseModel):
    name: str
    category: str = 'patrol'
    x: float
    y: float
    yaw: float = 0.0


@router.post('/places/add_manual')
async def add_place_manual(body: PlaceManualBody) -> dict:
    pose = [round(body.x, 3), round(body.y, 3), round(body.yaw, 3)]
    data = _load_places()
    section = data.setdefault(body.category, {'order': [], 'places': {}})
    section.setdefault('order', [])
    section.setdefault('places', {})
    section['places'][body.name] = {'pose': pose, 'room': None}
    if body.name not in section['order']:
        section['order'].append(body.name)
    _save_places(data)
    return {'ok': True, 'pose': pose}
