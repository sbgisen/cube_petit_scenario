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
"""マップ管理 API (/map/*) — マップ一覧・画像・places/rooms・保存・回転・初期位置."""

import base64
import io
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Optional

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel
import yaml

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


def _find_map_dir(map_name: str) -> Optional[Path]:
    return core.helpers.find_map_dir(map_name, core.MAP_DIRS)


def _load_map_places(map_name: str) -> list:
    return core.helpers.load_map_places(map_name, core.MAP_DIRS)


def _save_map_places(map_name: str, places: list) -> None:
    core.helpers.save_map_places(map_name, places, core.MAP_DIRS)


def _load_map_rooms(map_name: str) -> list:
    return core.helpers.load_map_rooms(map_name, core.MAP_DIRS)


def _save_map_rooms(map_name: str, rooms: list) -> None:
    core.helpers.save_map_rooms(map_name, rooms, core.MAP_DIRS)


@router.get('/map/list')
async def list_maps() -> dict:
    names = sorted({d.name for base in core.MAP_DIRS if base.exists() for d in base.iterdir() if d.is_dir()})
    return {'maps': names}


@router.post('/map/load')
async def load_map(namespace: str, map_name: str) -> dict:
    yaml_path = core.MAP_BASE_DIR / map_name / f'{map_name}.yaml'
    if not yaml_path.exists():
        return {'ok': False, 'error': f'Map file not found: {yaml_path}'}
    try:
        result = subprocess.run(
            [
                'ros2', 'service', 'call', f'/{namespace}/navigation/map_server/load_map', 'nav2_msgs/srv/LoadMap',
                f"{{map_url: 'file://{yaml_path}'}}"
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=core.ROS_ENV,
        )
        return {'ok': 'result: 0' in result.stdout or result.returncode == 0}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- マップ別 places.yaml ---


@router.get('/map/places')
async def get_map_places(map_name: str) -> dict:
    return {'places': _load_map_places(map_name)}


class MapPlaceBody(BaseModel):
    map_name: str
    name: str
    category: str = 'patrol'
    x: float
    y: float
    yaw: float = 0.0


@router.post('/map/places/add')
async def add_map_place(body: MapPlaceBody) -> dict:
    places = _load_map_places(body.map_name)
    places = [p for p in places if p.get('name') != body.name]
    places.append({
        'name': body.name,
        'category': body.category,
        'pose': [round(body.x, 3), round(body.y, 3), round(body.yaw, 3)]
    })
    _save_map_places(body.map_name, places)
    return {'ok': True}


@router.post('/map/places/add_current')
async def add_map_place_current(map_name: str,
                                name: str,
                                category: str = 'patrol',
                                namespace: str = core.DEFAULT_NAMESPACE) -> dict:
    pose = core.get_robot_pose(namespace)
    if pose is None:
        return {'ok': False, 'error': 'Cannot get robot position from TF'}
    places = _load_map_places(map_name)
    places = [p for p in places if p.get('name') != name]
    places.append({'name': name, 'category': category, 'pose': pose})
    _save_map_places(map_name, places)
    return {'ok': True, 'pose': pose}


@router.delete('/map/places/remove')
async def remove_map_place(map_name: str, name: str) -> dict:
    places = _load_map_places(map_name)
    places = [p for p in places if p.get('name') != name]
    _save_map_places(map_name, places)
    return {'ok': True}


# --- マップ画像・メタ情報 ---


@router.get('/map/image')
async def get_map_image(map_name: str, type: str = 'map') -> Response:  # noqa: A002
    d = _find_map_dir(map_name)
    if d is None:
        raise HTTPException(404, 'Map not found')
    suffix = '_keepout' if type == 'keepout' else ''
    pgm = d / f'map{suffix}.pgm'
    if not pgm.exists():
        raise HTTPException(404, f'{pgm.name} not found')
    png_bytes = core.helpers.pgm_to_png_bytes(pgm)
    return Response(content=png_bytes, media_type='image/png')


@router.get('/map/meta')
async def get_map_meta(map_name: str) -> dict:
    d = _find_map_dir(map_name)
    if d is None:
        raise HTTPException(404, 'Map not found')
    yaml_path = d / 'map.yaml'
    if not yaml_path.exists():
        raise HTTPException(404, 'map.yaml not found')
    with yaml_path.open() as f:
        meta = yaml.safe_load(f)
    return meta


class KeepoutSaveBody(BaseModel):
    map_name: str
    png_base64: str


@router.post('/map/keepout/save')
async def save_keepout(body: KeepoutSaveBody) -> dict:
    d = _find_map_dir(body.map_name)
    if d is None:
        raise HTTPException(404, 'Map not found')
    png_data = base64.b64decode(body.png_base64)
    img = Image.open(io.BytesIO(png_data)).convert('L')
    pgm_path = d / 'map_keepout.pgm'
    pgm_path.write_bytes(core.helpers.pil_to_pgm_bytes(img))
    # update keepout yaml image field
    yaml_path = d / 'map_keepout.yaml'
    if yaml_path.exists():
        with yaml_path.open() as f:
            meta = yaml.safe_load(f)
        meta['image'] = 'map_keepout.pgm'
        with yaml_path.open('w') as f:
            yaml.safe_dump(meta, f, sort_keys=False)
    return {'ok': True}


class MapSaveBody(BaseModel):
    map_name: str
    dest: str = 'extra'  # 'extra' = /home/cube-petit/map, 'base' = nav pkg map dir


@router.get('/map/preview')
async def preview_map() -> dict:
    """現在のSLAMマップをPNGで返す（保存しない）."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / 'map'
        cmd = [
            'ros2',
            'run',
            'nav2_map_server',
            'map_saver_cli',
            '-f',
            str(dest),
            '--ros-args',
            '-r',
            f'map:=/{core.DEFAULT_NAMESPACE}/navigation/map',
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=core.ROS_ENV)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, 'map_saver timeout')
        pgm = Path(tmp) / 'map.pgm'
        if not pgm.exists():
            raise HTTPException(503, 'Map not available (SLAM running?)')
        png_bytes = core.helpers.pgm_to_png_bytes(pgm)
        yml = Path(tmp) / 'map.yaml'
        meta = {}
        if yml.exists():
            with yml.open() as f:
                meta = yaml.safe_load(f) or {}
    b64 = base64.b64encode(png_bytes).decode()
    return {'png_base64': b64, 'meta': meta}


@router.post('/map/save')
async def save_map(body: MapSaveBody) -> dict:
    base = core.MAP_EXTRA_DIR if body.dest == 'extra' else core.MAP_BASE_DIR
    dest_dir = base / body.map_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_stem = str(dest_dir / 'map')
    cmd = [
        'ros2',
        'run',
        'nav2_map_server',
        'map_saver_cli',
        '-f',
        dest_stem,
        '--ros-args',
        '-r',
        f'map:=/{core.DEFAULT_NAMESPACE}/navigation/map',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=core.ROS_ENV)
        if result.returncode != 0:
            return {'ok': False, 'error': result.stderr.strip() or 'map_saver failed'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'timeout'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

    # auto-generate keepout copy
    pgm_src = dest_dir / 'map.pgm'
    pgm_kp = dest_dir / 'map_keepout.pgm'
    yaml_src = dest_dir / 'map.yaml'
    yaml_kp = dest_dir / 'map_keepout.yaml'
    if pgm_src.exists():
        shutil.copy2(pgm_src, pgm_kp)
    if yaml_src.exists():
        with yaml_src.open() as f:
            meta = yaml.safe_load(f)
        meta['image'] = 'map_keepout.pgm'
        with yaml_kp.open('w') as f:
            yaml.safe_dump(meta, f, sort_keys=False)
    return {'ok': True, 'dir': str(dest_dir)}


class RotateBody(BaseModel):
    map_name: str
    degrees: float  # any angle


@router.post('/map/rotate')
async def rotate_map(body: RotateBody) -> dict:
    d = _find_map_dir(body.map_name)
    if d is None:
        raise HTTPException(404, 'Map not found')
    angle = body.degrees % 360

    fill_values = {'': 205, '_keepout': 254}
    for suffix, fill in fill_values.items():
        pgm = d / f'map{suffix}.pgm'
        yml = d / f'map{suffix}.yaml'
        if not pgm.exists():
            continue
        img = Image.open(pgm).convert('L')
        rotated = img.rotate(-angle, expand=True, fillcolor=fill)
        pgm.write_bytes(core.helpers.pil_to_pgm_bytes(rotated))
        if yml.exists():
            with yml.open() as f:
                meta = yaml.safe_load(f)
            res = meta.get('resolution', 0.05)
            ox, oy = meta.get('origin', [0, 0, 0])[:2]
            w, h = img.size
            rw, rh = rotated.size
            # preserve world center
            cx = ox + w * res / 2
            cy = oy + h * res / 2
            meta['origin'] = [round(cx - rw * res / 2, 4), round(cy - rh * res / 2, 4), 0]
            with yml.open('w') as f:
                yaml.safe_dump(meta, f, sort_keys=False)
    return {'ok': True}


# --- マップ別 rooms.yaml ---


@router.get('/map/rooms')
async def get_map_rooms(map_name: str) -> dict:
    return {'rooms': _load_map_rooms(map_name)}


class RoomBody(BaseModel):
    map_name: str
    name: str
    points: list  # [[x,y], ...] world coords


@router.post('/map/rooms/add')
async def add_map_room(body: RoomBody) -> dict:
    rooms = _load_map_rooms(body.map_name)
    rooms = [r for r in rooms if r.get('name') != body.name]
    pts = [[round(p[0], 3), round(p[1], 3)] for p in body.points]
    rooms.append({'name': body.name, 'points': pts})
    _save_map_rooms(body.map_name, rooms)
    return {'ok': True}


@router.delete('/map/rooms/remove')
async def remove_map_room(map_name: str, name: str) -> dict:
    rooms = _load_map_rooms(map_name)
    rooms = [r for r in rooms if r.get('name') != name]
    _save_map_rooms(map_name, rooms)
    return {'ok': True}


# --- places 順序変更 ---


class PlacesReorderBody(BaseModel):
    map_name: str
    places: list  # full ordered list


@router.post('/map/places/reorder')
async def reorder_map_places(body: PlacesReorderBody) -> dict:
    _save_map_places(body.map_name, body.places)
    return {'ok': True}


# --- 初期位置設定 ---


@router.post('/map/initial_pose')
async def set_initial_pose(x: float, y: float, yaw: float, namespace: str = core.DEFAULT_NAMESPACE) -> dict:
    qz = math.sin(yaw / 2)
    qw = math.cos(yaw / 2)
    msg = (f'{{header: {{frame_id: map}}, pose: {{pose: {{'
           f'position: {{x: {x}, y: {y}, z: 0.0}}, '
           f'orientation: {{x: 0.0, y: 0.0, z: {qz:.6f}, w: {qw:.6f}}}'
           f'}}}}}}')
    cmd = [
        'ros2',
        'topic',
        'pub',
        '--once',
        f'/{namespace}/initialpose',
        'geometry_msgs/PoseWithCovarianceStamped',
        msg,
    ]
    subprocess.Popen(cmd, env=core.ROS_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'ok': True}


@router.post('/map/places/rename')
async def rename_map_place(map_name: str, old_name: str, new_name: str) -> dict:
    places = _load_map_places(map_name)
    for p in places:
        if p.get('name') == old_name:
            p['name'] = new_name
            break
    _save_map_places(map_name, places)
    return {'ok': True}


@router.post('/map/rooms/rename')
async def rename_map_room(map_name: str, old_name: str, new_name: str) -> dict:
    rooms = _load_map_rooms(map_name)
    for r in rooms:
        if r.get('name') == old_name:
            r['name'] = new_name
            break
    _save_map_rooms(map_name, rooms)
    return {'ok': True}
