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

import asyncio
import base64
from contextlib import asynccontextmanager
import io
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
from typing import AsyncIterator, Callable, Optional

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel
import rclpy
from rclpy.node import Node
import yaml

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import helpers as _helpers
except ImportError:
    # python api_server.py で直接実行した場合
    import helpers as _helpers

ROS_ENV = {**os.environ, 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'}

MAP_BASE_DIR = Path('/home/cube-petit/ros/src/cube_petit_ros/cube_petit_navigation/map')
MAP_EXTRA_DIR = Path('/home/cube-petit/map')
PLACES_FILE = Path('/home/cube-petit/ros/src/cube_petit_ros/cube_petit_navigation/config/places.yaml')
PROMPT_FILE = Path('/home/cube-petit/ros/src/cube_petit_interaction/cube_petit_chat/config/realtime_chat_setting.txt')

# rclpy 常駐ノード
WATCHED_NAMESPACES = ['cube_petit_orange']
_status_cache: dict[str, dict] = {ns: {'is_active': False, 'can_receive_message': False} for ns in WATCHED_NAMESPACES}
_node: Optional[Node] = None
_tf_buffer = None
_tf_listener = None


def _start_ros() -> None:
    global _node, _tf_buffer, _tf_listener
    from cube_petit_chat_msgs.msg import RealtimeState
    from tf2_ros import Buffer
    from tf2_ros import TransformListener
    rclpy.init()
    _node = Node('web_interface_watcher')
    _tf_buffer = Buffer()
    _tf_listener = TransformListener(_tf_buffer, _node)
    for ns in WATCHED_NAMESPACES:

        def make_cb(n: str) -> Callable:

            def cb(msg: RealtimeState) -> None:
                _status_cache[n]['is_active'] = msg.is_active
                _status_cache[n]['can_receive_message'] = msg.can_receive_message

            return cb

        _node.create_subscription(RealtimeState, f'/{ns}/realtime_conversation_status', make_cb(ns), 10)
    rclpy.spin(_node)


_ros_thread = threading.Thread(target=_start_ros, daemon=True)
_ros_thread.start()

_can_prev_rx: int = -1
_can_stale: bool = False

processes: dict[str, Optional[subprocess.Popen]] = {
    'rosbridge': None,
    'bringup': None,
    'demo': None,
    'anima': None,
    'create_map': None,
    'navigation': None,
}

LAUNCH_COMMANDS = {
    'rosbridge': ['ros2', 'launch', 'rosbridge_server', 'rosbridge_websocket_launch.xml'],
    'bringup': ['ros2', 'launch', 'cube_petit_bringup', 'cube_petit_bringup.launch.py'],
    'demo': ['ros2', 'launch', 'cube_petit_scenario', 'cube_petit_talk_demo.launch.py'],
    'anima': ['ros2', 'launch', 'cube_petit_anima', 'anima.launch.py'],
    'create_map': ['ros2', 'launch', 'cube_petit_navigation', 'create_map_orange.launch.py'],
    'navigation': ['ros2', 'launch', 'cube_petit_navigation', 'navigation_orange.launch.py'],
}

# 各launchが起動中かを判定するノード名（部分一致）
LAUNCH_NODE_MARKERS = {
    'rosbridge': 'rosbridge_websocket',
    'bringup': 'robot_state_publisher',
    'demo': 'realtime_gpt_chat',
    'anima': 'behavior_node',
    'create_map': 'slam_toolbox',
    'navigation': 'emcl',
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    for proc in processes.values():
        if proc and proc.poll() is None:
            proc.terminate()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


class LaunchResponse(BaseModel):
    ok: bool
    message: str


class ContextRequest(BaseModel):
    context: str = ''
    role: int = 2
    images: list[str] = []


class PromptBody(BaseModel):
    content: str


@app.post('/launch/{target}/start', response_model=LaunchResponse)
async def start_launch(
        target: str,
        map: Optional[str] = None,  # noqa: A002
        keepout: Optional[str] = None) -> LaunchResponse:
    if target not in LAUNCH_COMMANDS:
        return LaunchResponse(ok=False, message=f'Unknown target: {target}')
    if processes[target] and processes[target].poll() is None:
        return LaunchResponse(ok=False, message=f'{target} is already running')
    if target in ('bringup', 'rosbridge'):
        subprocess.run(['fuser', '-k', '9090/tcp'], capture_output=True)
        import time
        time.sleep(0.5)
    cmd = list(LAUNCH_COMMANDS[target])
    log_msg = ' '.join(cmd)
    if target == 'navigation':
        if map:
            map_dir = _find_map_dir(map)
            map_yaml = str(map_dir / 'map.yaml') if map_dir else map
            cmd.append(f'map:={map_yaml}')
            log_msg += f' map:={map_yaml}'
        if keepout:
            kp_dir = _find_map_dir(keepout)
            kp_yaml = str(kp_dir / 'map_keepout.yaml') if kp_dir else keepout
            cmd.append(f'keepout:={kp_yaml}')
            log_msg += f' keepout:={kp_yaml}'
    processes[target] = subprocess.Popen(cmd, env=ROS_ENV, preexec_fn=os.setsid)
    return LaunchResponse(ok=True, message=log_msg)


def _kill_by_launch_file(launch_file: str) -> bool:
    """ランチファイル名でプロセスを探してプロセスグループごと停止する."""
    result = subprocess.run(['pgrep', '-f', launch_file], capture_output=True, text=True)
    killed = False
    for pid_str in result.stdout.strip().split():
        try:
            os.killpg(os.getpgid(int(pid_str)), signal.SIGTERM)
            killed = True
        except Exception:
            pass
    return killed


@app.post('/launch/{target}/stop', response_model=LaunchResponse)
async def stop_launch(target: str) -> LaunchResponse:
    if target not in processes:
        return LaunchResponse(ok=False, message=f'Unknown target: {target}')

    killed = False

    # 自前で起動したプロセスグループを停止
    proc = processes[target]
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            killed = True
        except Exception:
            proc.terminate()
            killed = True
    processes[target] = None

    # 外部起動のプロセスも探して停止
    launch_file = LAUNCH_COMMANDS[target][-1]
    if _kill_by_launch_file(launch_file):
        killed = True

    if killed:
        return LaunchResponse(ok=True, message=f'{target} stopped')
    return LaunchResponse(ok=False, message=f'{target} is not running')


@app.get('/action/exists')
async def action_exists(name: str) -> dict:
    try:
        result = subprocess.run(['ros2', 'action', 'list'], capture_output=True, text=True, timeout=3)
        found = any(name in line for line in result.stdout.splitlines())
        return {'exists': found}
    except Exception:
        return {'exists': False}


@app.get('/system/devices')
async def get_system_devices() -> dict:
    import os as _os
    result: dict = {}

    # IP (IPv4のみ)
    try:
        r = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=3)
        result['ip'] = [ip for ip in r.stdout.strip().split() if ':' not in ip]
    except Exception:
        result['ip'] = []

    # CAN0 ネットワークインターフェース + 受信統計
    global _can_prev_rx, _can_stale
    try:
        r = subprocess.run(['ip', '-s', 'link', 'show', 'can0'], capture_output=True, text=True, timeout=3)
        up = r.returncode == 0 and 'UP' in r.stdout
        result['can0'] = up
        if up:
            m = re.search(r'RX:.*?\n\s+(\d+)\s+(\d+)\s+(\d+)', r.stdout)
            if m:
                rx_packets = int(m.group(2))
                rx_errors = int(m.group(3))
                if _can_prev_rx < 0:
                    _can_stale = False
                else:
                    _can_stale = (rx_packets == _can_prev_rx)
                _can_prev_rx = rx_packets
                result['can_rx'] = rx_packets
                result['can_errors'] = rx_errors
                result['can_stale'] = _can_stale
    except Exception:
        result['can0'] = False

    # シリアルデバイス（udevシンボリックリンク）
    result['lidar'] = _os.path.exists('/dev/ttyLD06-19')
    result['imu'] = _os.path.exists('/dev/ttyWitMotion')
    result['canable'] = _os.path.exists('/dev/ttyCANable')

    # USB接続（lsusb）
    try:
        r = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
        lines = r.stdout.splitlines()
        result['realsense'] = any('8086:0b' in line or 'RealSense' in line for line in lines)
        result['oak'] = any('03e7:' in line or 'Movidius' in line or 'Myriad' in line for line in lines)
    except Exception:
        result['realsense'] = False
        result['oak'] = False

    return result


@app.post('/launch/kill_all')
async def kill_all_ros() -> dict:
    subprocess.run(['pkill', 'ros'], capture_output=True)
    subprocess.run(['pkill', 'ros2'], capture_output=True)
    for k in processes:
        processes[k] = None
    return {'ok': True}


@app.get('/ros/nodes')
async def get_ros_nodes() -> dict:
    try:
        result = subprocess.run(['ros2', 'node', 'list'], capture_output=True, text=True, timeout=5, env=ROS_ENV)
        nodes = [n.strip() for n in result.stdout.splitlines() if n.strip()]
        return {'nodes': nodes}
    except Exception as e:
        return {'nodes': [], 'error': str(e)}


@app.get('/launch/status')
async def get_status() -> dict:
    try:
        result = subprocess.run(['ros2', 'node', 'list'], capture_output=True, text=True, timeout=5, env=ROS_ENV)
        node_output = result.stdout
        status = {}
        for target, marker in LAUNCH_NODE_MARKERS.items():
            proc_alive = processes[target] is not None and processes[target].poll() is None
            status[target] = proc_alive or (marker in node_output)
        return status
    except Exception:
        return {target: proc is not None and proc.poll() is None for target, proc in processes.items()}


# --- 会話ステータス ---


@app.get('/ros/conversation/status')
async def get_conversation_status(namespace: str = 'cube_petit_orange') -> dict:
    try:
        subprocess.run(
            [
                'ros2', 'service', 'call', f'/{namespace}/get_realtime_conversation_status', 'std_srvs/srv/Trigger',
                '{}'
            ],
            capture_output=True,
            text=True,
            timeout=3,
            env=ROS_ENV,
        )
        await asyncio.sleep(0.3)
    except Exception:
        pass
    return _status_cache.get(namespace, {'is_active': False, 'can_receive_message': False})


@app.post('/ros/conversation/enable')
async def enable_conversation(namespace: str = 'cube_petit_orange', enable: bool = True) -> dict:
    try:
        val = 'True' if enable else 'False'
        result = subprocess.run(
            [
                'ros2', 'service', 'call', f'/{namespace}/enable_realtime_conversation', 'std_srvs/srv/SetBool',
                f'{{data: {val}}}'
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=ROS_ENV,
        )
        return {'ok': 'success: True' in result.stdout or result.returncode == 0}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _call_add_context_sync(namespace: str, req_body: ContextRequest) -> bool:
    from cube_petit_chat_msgs.srv import AddContext
    from rclpy.task import Future
    from sensor_msgs.msg import Image as SensorImage

    if _node is None:
        return False

    client = _node.create_client(AddContext, f'/{namespace}/add_realtime_context')
    if not client.wait_for_service(timeout_sec=3.0):
        return False

    req = AddContext.Request()
    req.role = req_body.role
    req.context = req_body.context
    req.images = []
    for data_url in req_body.images:
        b64 = data_url.split(',', 1)[-1]
        img_bytes = base64.b64decode(b64)
        img = SensorImage()
        img.encoding = 'jpeg'
        img.data = list(img_bytes)
        req.images.append(img)

    event = threading.Event()
    result = [None]

    def done_cb(future: Future) -> None:
        try:
            result[0] = future.result()
        except Exception:
            pass
        event.set()

    future = client.call_async(req)
    future.add_done_callback(done_cb)
    event.wait(timeout=5.0)
    return result[0] is not None and result[0].success


@app.post('/ros/conversation/context')
async def add_context(namespace: str = 'cube_petit_orange', body: ContextRequest = ContextRequest()) -> dict:
    try:
        ok = await asyncio.get_event_loop().run_in_executor(None, _call_add_context_sync, namespace, body)
        return {'ok': ok}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- 音量制御 ---


def _parse_amixer_volume(output: str) -> int:
    return _helpers.parse_amixer_volume(output)


@app.get('/audio/volume')
async def get_audio_volume() -> dict:
    try:
        r_speaker = subprocess.run(['amixer', 'sget', 'Master'], capture_output=True, text=True)
        r_mic = subprocess.run(['amixer', 'sget', 'Capture'], capture_output=True, text=True)
        return {'speaker': _parse_amixer_volume(r_speaker.stdout), 'mic': _parse_amixer_volume(r_mic.stdout)}
    except Exception as e:
        return {'speaker': -1, 'mic': -1, 'error': str(e)}


@app.post('/audio/volume')
async def set_audio_volume(type: str, value: int) -> dict:  # noqa: A002
    control = 'Master' if type == 'speaker' else 'Capture'
    try:
        subprocess.run(['amixer', 'sset', control, f'{value}%'], capture_output=True)
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- マップ ---


@app.get('/map/list')
async def list_maps() -> dict:
    dirs = [MAP_BASE_DIR, MAP_EXTRA_DIR]
    names = sorted({d.name for base in dirs if base.exists() for d in base.iterdir() if d.is_dir()})
    return {'maps': names}


@app.post('/map/load')
async def load_map(namespace: str, map_name: str) -> dict:
    yaml_path = MAP_BASE_DIR / map_name / f'{map_name}.yaml'
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
            env=ROS_ENV,
        )
        return {'ok': 'result: 0' in result.stdout or result.returncode == 0}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- ポイント (places.yaml) ---


def _load_places() -> dict:
    return _helpers.load_places(PLACES_FILE)


def _save_places(data: dict) -> None:
    _helpers.save_places(PLACES_FILE, data)


def _get_robot_pose(namespace: str) -> Optional[list[float]]:
    if _node is None:
        return None
    try:
        t = _tf_buffer.lookup_transform('map', f'{namespace}/base_link', rclpy.time.Time())
        x = t.transform.translation.x
        y = t.transform.translation.y
        q = t.transform.rotation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        return [round(x, 3), round(y, 3), round(yaw, 3)]
    except Exception:
        return None


@app.get('/ros/robot_pose')
async def get_robot_pose_endpoint(namespace: str = 'cube_petit_orange') -> dict:
    pose = _get_robot_pose(namespace)
    if pose is None:
        return {'ok': False}
    return {'ok': True, 'x': pose[0], 'y': pose[1], 'yaw': pose[2]}


@app.get('/places')
async def get_places() -> dict:
    data = _load_places()
    result = []
    for category, section in data.items():
        if category == 'rooms' or not isinstance(section, dict):
            continue
        for name, info in section.get('places', {}).items():
            result.append({'category': category, 'name': name, 'pose': info.get('pose', [])})
    return {'places': result}


@app.post('/places/add')
async def add_place(namespace: str, name: str, category: str = 'patrol') -> dict:
    pose = _get_robot_pose(namespace)
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


@app.delete('/places/remove')
async def remove_place(category: str, name: str) -> dict:
    data = _load_places()
    section = data.get(category, {})
    if name in section.get('places', {}):
        del section['places'][name]
    if name in section.get('order', []):
        section['order'].remove(name)
    _save_places(data)
    return {'ok': True}


# --- プロンプト / ヒストリー ---

PROMPT_DIR = PROMPT_FILE.parent
ACTIVE_MARKER = PROMPT_DIR / '.active_prompt'
PROTECTED_PROMPTS = {'realtime_chat_setting.txt', 'gpt_chat_setting.txt'}

HISTORY_DIR = Path('/home/cube-petit/ros/src/cube_petit_interaction/cube_petit_chat/resource/history')
HISTORY_ACTIVE_MARKER = HISTORY_DIR / '.active_history'
PROTECTED_HISTORY = {'history.jsonl'}


def _active_prompt_name() -> str:
    return _helpers.active_prompt_name(PROMPT_DIR, ACTIVE_MARKER, PROMPT_FILE.name)


@app.get('/prompt/list')
async def list_prompts() -> dict:
    files = sorted(p.name for p in PROMPT_DIR.glob('*.txt'))
    return {'files': files, 'active': _active_prompt_name()}


@app.get('/prompt')
async def get_prompt(file: Optional[str] = None) -> dict:
    path = PROMPT_DIR / file if file else PROMPT_FILE
    content = path.read_text(encoding='utf-8') if path.exists() else ''
    return {'content': content, 'file': path.name}


@app.post('/prompt')
async def set_prompt(body: PromptBody, file: Optional[str] = None) -> dict:
    name = file or PROMPT_FILE.name
    if name in PROTECTED_PROMPTS:
        return {'ok': False, 'error': 'Protected file'}
    path = PROMPT_DIR / name
    path.write_text(body.content, encoding='utf-8')
    return {'ok': True}


@app.post('/prompt/activate')
async def activate_prompt(file: str, namespace: str = 'cube_petit_orange') -> dict:
    src = PROMPT_DIR / file
    if not src.exists():
        return {'ok': False, 'error': 'File not found'}
    ACTIVE_MARKER.write_text(file, encoding='utf-8')
    subprocess.run(
        ['ros2', 'param', 'set', f'/{namespace}/realtime_gpt_chat', 'setting_file',
         str(src)],
        capture_output=True,
        timeout=5,
        env=ROS_ENV,
    )
    return {'ok': True}


@app.post('/prompt/new')
async def new_prompt(name: str) -> dict:
    if not name.endswith('.txt'):
        name += '.txt'
    path = PROMPT_DIR / name
    if path.exists():
        return {'ok': False, 'error': 'Already exists'}
    path.write_text('', encoding='utf-8')
    return {'ok': True, 'file': name}


@app.delete('/prompt')
async def delete_prompt(file: str) -> dict:
    if file in PROTECTED_PROMPTS:
        return {'ok': False, 'error': 'Protected file'}
    path = PROMPT_DIR / file
    if path.exists():
        path.unlink()
    if ACTIVE_MARKER.exists() and ACTIVE_MARKER.read_text().strip() == file:
        ACTIVE_MARKER.unlink()
    return {'ok': True}


@app.get('/history/list')
async def list_history() -> dict:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in HISTORY_DIR.glob('*.jsonl'))
    active = ''
    if HISTORY_ACTIVE_MARKER.exists():
        candidate = HISTORY_ACTIVE_MARKER.read_text(encoding='utf-8').strip()
        if (HISTORY_DIR / candidate).exists():
            active = candidate
    if not active and files:
        active = files[0]
    return {'files': files, 'active': active}


@app.post('/history/activate')
async def activate_history(file: str, namespace: str = 'cube_petit_orange') -> dict:
    path = HISTORY_DIR / file
    if not path.exists():
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path.touch()
    HISTORY_ACTIVE_MARKER.write_text(file, encoding='utf-8')
    subprocess.run(
        ['ros2', 'param', 'set', f'/{namespace}/realtime_gpt_chat', 'history_file',
         str(path)],
        capture_output=True,
        timeout=5,
        env=ROS_ENV,
    )
    return {'ok': True}


@app.post('/history/new')
async def new_history(name: str) -> dict:
    if not name.endswith('.jsonl'):
        name += '.jsonl'
    path = HISTORY_DIR / name
    if path.exists():
        return {'ok': False, 'error': 'Already exists'}
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path.touch()
    return {'ok': True, 'file': name}


@app.delete('/history')
async def delete_history(file: str) -> dict:
    if file in PROTECTED_HISTORY:
        return {'ok': False, 'error': 'Protected file'}
    path = HISTORY_DIR / file
    if path.exists():
        path.unlink()
    if HISTORY_ACTIVE_MARKER.exists() and HISTORY_ACTIVE_MARKER.read_text().strip() == file:
        HISTORY_ACTIVE_MARKER.unlink()
    return {'ok': True}


# --- マップ別 places.yaml ---


def _map_places_path(map_name: str) -> Optional[Path]:
    return _helpers.map_places_path(map_name, [MAP_BASE_DIR, MAP_EXTRA_DIR])


def _load_map_places(map_name: str) -> list:
    return _helpers.load_map_places(map_name, [MAP_BASE_DIR, MAP_EXTRA_DIR])


def _save_map_places(map_name: str, places: list) -> None:
    _helpers.save_map_places(map_name, places, [MAP_BASE_DIR, MAP_EXTRA_DIR])


@app.get('/map/places')
async def get_map_places(map_name: str) -> dict:
    return {'places': _load_map_places(map_name)}


class MapPlaceBody(BaseModel):
    map_name: str
    name: str
    category: str = 'patrol'
    x: float
    y: float
    yaw: float = 0.0


@app.post('/map/places/add')
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


@app.post('/map/places/add_current')
async def add_map_place_current(map_name: str,
                                name: str,
                                category: str = 'patrol',
                                namespace: str = 'cube_petit_orange') -> dict:
    pose = _get_robot_pose(namespace)
    if pose is None:
        return {'ok': False, 'error': 'Cannot get robot position from TF'}
    places = _load_map_places(map_name)
    places = [p for p in places if p.get('name') != name]
    places.append({'name': name, 'category': category, 'pose': pose})
    _save_map_places(map_name, places)
    return {'ok': True, 'pose': pose}


@app.delete('/map/places/remove')
async def remove_map_place(map_name: str, name: str) -> dict:
    places = _load_map_places(map_name)
    places = [p for p in places if p.get('name') != name]
    _save_map_places(map_name, places)
    return {'ok': True}


class PlaceManualBody(BaseModel):
    name: str
    category: str = 'patrol'
    x: float
    y: float
    yaw: float = 0.0


@app.post('/places/add_manual')
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


def _find_map_dir(map_name: str) -> Optional[Path]:
    return _helpers.find_map_dir(map_name, [MAP_BASE_DIR, MAP_EXTRA_DIR])


def _pgm_to_png_bytes(pgm_path: Path) -> bytes:
    return _helpers.pgm_to_png_bytes(pgm_path)


def _png_bytes_to_pgm(png_data: bytes, pgm_path: Path) -> None:
    _helpers.png_bytes_to_pgm(png_data, pgm_path)


def _pil_to_pgm_bytes(img: Image.Image) -> bytes:
    return _helpers.pil_to_pgm_bytes(img)


@app.get('/map/image')
async def get_map_image(map_name: str, type: str = 'map') -> Response:  # noqa: A002
    d = _find_map_dir(map_name)
    if d is None:
        raise HTTPException(404, 'Map not found')
    suffix = '_keepout' if type == 'keepout' else ''
    pgm = d / f'map{suffix}.pgm'
    if not pgm.exists():
        raise HTTPException(404, f'{pgm.name} not found')
    png_bytes = _pgm_to_png_bytes(pgm)
    return Response(content=png_bytes, media_type='image/png')


@app.get('/map/meta')
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


@app.post('/map/keepout/save')
async def save_keepout(body: KeepoutSaveBody) -> dict:
    d = _find_map_dir(body.map_name)
    if d is None:
        raise HTTPException(404, 'Map not found')
    png_data = base64.b64decode(body.png_base64)
    img = Image.open(io.BytesIO(png_data)).convert('L')
    pgm_path = d / 'map_keepout.pgm'
    pgm_path.write_bytes(_pil_to_pgm_bytes(img))
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


@app.get('/map/preview')
async def preview_map() -> dict:
    """現在のSLAMマップをPNGで返す（保存しない）."""
    import tempfile
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
            'map:=/cube_petit_orange/navigation/map',
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=ROS_ENV)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, 'map_saver timeout')
        pgm = Path(tmp) / 'map.pgm'
        if not pgm.exists():
            raise HTTPException(503, 'Map not available (SLAM running?)')
        png_bytes = _pgm_to_png_bytes(pgm)
        yml = Path(tmp) / 'map.yaml'
        meta = {}
        if yml.exists():
            with yml.open() as f:
                meta = yaml.safe_load(f) or {}
    b64 = base64.b64encode(png_bytes).decode()
    return {'png_base64': b64, 'meta': meta}


@app.post('/map/save')
async def save_map(body: MapSaveBody) -> dict:
    base = MAP_EXTRA_DIR if body.dest == 'extra' else MAP_BASE_DIR
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
        'map:=/cube_petit_orange/navigation/map',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=ROS_ENV)
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


@app.post('/map/rotate')
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
        pgm.write_bytes(_pil_to_pgm_bytes(rotated))
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


def _map_rooms_path(map_name: str) -> Optional[Path]:
    return _helpers.map_rooms_path(map_name, [MAP_BASE_DIR, MAP_EXTRA_DIR])


def _load_map_rooms(map_name: str) -> list:
    return _helpers.load_map_rooms(map_name, [MAP_BASE_DIR, MAP_EXTRA_DIR])


def _save_map_rooms(map_name: str, rooms: list) -> None:
    _helpers.save_map_rooms(map_name, rooms, [MAP_BASE_DIR, MAP_EXTRA_DIR])


@app.get('/map/rooms')
async def get_map_rooms(map_name: str) -> dict:
    return {'rooms': _load_map_rooms(map_name)}


class RoomBody(BaseModel):
    map_name: str
    name: str
    points: list  # [[x,y], ...] world coords


@app.post('/map/rooms/add')
async def add_map_room(body: RoomBody) -> dict:
    rooms = _load_map_rooms(body.map_name)
    rooms = [r for r in rooms if r.get('name') != body.name]
    pts = [[round(p[0], 3), round(p[1], 3)] for p in body.points]
    rooms.append({'name': body.name, 'points': pts})
    _save_map_rooms(body.map_name, rooms)
    return {'ok': True}


@app.delete('/map/rooms/remove')
async def remove_map_room(map_name: str, name: str) -> dict:
    rooms = _load_map_rooms(map_name)
    rooms = [r for r in rooms if r.get('name') != name]
    _save_map_rooms(map_name, rooms)
    return {'ok': True}


# --- places 順序変更 ---


class PlacesReorderBody(BaseModel):
    map_name: str
    places: list  # full ordered list


@app.post('/map/places/reorder')
async def reorder_map_places(body: PlacesReorderBody) -> dict:
    _save_map_places(body.map_name, body.places)
    return {'ok': True}


# --- 初期位置設定 ---


@app.post('/map/initial_pose')
async def set_initial_pose(x: float, y: float, yaw: float, namespace: str = 'cube_petit_orange') -> dict:
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
    subprocess.Popen(cmd, env=ROS_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'ok': True}


@app.post('/map/places/rename')
async def rename_map_place(map_name: str, old_name: str, new_name: str) -> dict:
    places = _load_map_places(map_name)
    for p in places:
        if p.get('name') == old_name:
            p['name'] = new_name
            break
    _save_map_places(map_name, places)
    return {'ok': True}


@app.post('/map/rooms/rename')
async def rename_map_room(map_name: str, old_name: str, new_name: str) -> dict:
    rooms = _load_map_rooms(map_name)
    for r in rooms:
        if r.get('name') == old_name:
            r['name'] = new_name
            break
    _save_map_rooms(map_name, rooms)
    return {'ok': True}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
