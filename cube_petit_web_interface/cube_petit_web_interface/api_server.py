import asyncio
import base64
import math
import os
import re
import subprocess
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import rclpy
import yaml
from rclpy.node import Node
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROS_ENV = {**os.environ, 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'}

MAP_BASE_DIR = Path('/home/cube-petit/ros/src/cube_petit_ros/cube_petit_navigation/map')
PLACES_FILE = Path('/home/cube-petit/ros/src/cube_petit_ros/cube_petit_navigation/config/places.yaml')
PROMPT_FILE = Path('/home/cube-petit/ros/src/cube_petit_interaction/cube_petit_chat/config/realtime_chat_setting.txt')

# rclpy 常駐ノード
WATCHED_NAMESPACES = ['cube_petit_orange']
_status_cache: dict[str, dict] = {ns: {'is_active': False, 'can_receive_message': False} for ns in WATCHED_NAMESPACES}
_node: Optional[Node] = None


def _start_ros():
    global _node
    from cube_petit_chat_msgs.msg import RealtimeState
    from tf2_ros import Buffer, TransformListener
    rclpy.init()
    _node = Node('web_interface_watcher')
    _node._tf_buffer = Buffer()
    _node._tf_listener = TransformListener(_node._tf_buffer, _node)
    for ns in WATCHED_NAMESPACES:
        def make_cb(n):
            def cb(msg):
                _status_cache[n]['is_active'] = msg.is_active
                _status_cache[n]['can_receive_message'] = msg.can_receive_message
            return cb
        _node.create_subscription(RealtimeState, f'/{ns}/realtime_conversation_status', make_cb(ns), 10)
    rclpy.spin(_node)

_ros_thread = threading.Thread(target=_start_ros, daemon=True)
_ros_thread.start()

processes: dict[str, Optional[subprocess.Popen]] = {
    'bringup': None,
    'demo': None,
}

LAUNCH_COMMANDS = {
    'bringup': ['ros2', 'launch', 'cube_petit_bringup', 'cube_petit_bringup.launch.py'],
    'demo': ['ros2', 'launch', 'cube_petit_scenario', 'cube_petit_talk_demo.launch.py'],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
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
async def start_launch(target: str):
    if target not in LAUNCH_COMMANDS:
        return LaunchResponse(ok=False, message=f'Unknown target: {target}')
    if processes[target] and processes[target].poll() is None:
        return LaunchResponse(ok=False, message=f'{target} is already running')
    processes[target] = subprocess.Popen(LAUNCH_COMMANDS[target])
    return LaunchResponse(ok=True, message=f'{target} started')


@app.post('/launch/{target}/stop', response_model=LaunchResponse)
async def stop_launch(target: str):
    if target not in processes:
        return LaunchResponse(ok=False, message=f'Unknown target: {target}')
    proc = processes[target]
    if not proc or proc.poll() is not None:
        return LaunchResponse(ok=False, message=f'{target} is not running')
    proc.terminate()
    processes[target] = None
    return LaunchResponse(ok=True, message=f'{target} stopped')


@app.get('/action/exists')
async def action_exists(name: str):
    try:
        result = subprocess.run(['ros2', 'action', 'list'], capture_output=True, text=True, timeout=3)
        found = any(name in line for line in result.stdout.splitlines())
        return {'exists': found}
    except Exception:
        return {'exists': False}


@app.get('/launch/status')
async def get_status():
    return {target: proc is not None and proc.poll() is None for target, proc in processes.items()}


# --- 会話ステータス ---

@app.get('/ros/conversation/status')
async def get_conversation_status(namespace: str = 'cube_petit_orange'):
    try:
        subprocess.run(
            ['ros2', 'service', 'call', f'/{namespace}/get_realtime_conversation_status',
             'std_srvs/srv/Trigger', '{}'],
            capture_output=True, text=True, timeout=3, env=ROS_ENV,
        )
        await asyncio.sleep(0.3)
    except Exception:
        pass
    return _status_cache.get(namespace, {'is_active': False, 'can_receive_message': False})


@app.post('/ros/conversation/enable')
async def enable_conversation(namespace: str = 'cube_petit_orange', enable: bool = True):
    try:
        val = 'True' if enable else 'False'
        result = subprocess.run(
            ['ros2', 'service', 'call', f'/{namespace}/enable_realtime_conversation',
             'std_srvs/srv/SetBool', f'{{data: {val}}}'],
            capture_output=True, text=True, timeout=5, env=ROS_ENV,
        )
        return {'ok': 'success: True' in result.stdout or result.returncode == 0}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _call_add_context_sync(namespace: str, req_body: ContextRequest) -> bool:
    from cube_petit_chat_msgs.srv import AddContext
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

    def done_cb(future):
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
async def add_context(namespace: str = 'cube_petit_orange', body: ContextRequest = ContextRequest()):
    try:
        ok = await asyncio.get_event_loop().run_in_executor(None, _call_add_context_sync, namespace, body)
        return {'ok': ok}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- 音量制御 ---

def _parse_amixer_volume(output: str) -> int:
    m = re.search(r'\[(\d+)%\]', output)
    return int(m.group(1)) if m else -1


@app.get('/audio/volume')
async def get_audio_volume():
    try:
        r_speaker = subprocess.run(['amixer', 'sget', 'Master'], capture_output=True, text=True)
        r_mic = subprocess.run(['amixer', 'sget', 'Capture'], capture_output=True, text=True)
        return {'speaker': _parse_amixer_volume(r_speaker.stdout), 'mic': _parse_amixer_volume(r_mic.stdout)}
    except Exception as e:
        return {'speaker': -1, 'mic': -1, 'error': str(e)}


@app.post('/audio/volume')
async def set_audio_volume(type: str, value: int):
    control = 'Master' if type == 'speaker' else 'Capture'
    try:
        subprocess.run(['amixer', 'sset', control, f'{value}%'], capture_output=True)
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- マップ ---

@app.get('/map/list')
async def list_maps():
    maps = sorted([d.name for d in MAP_BASE_DIR.iterdir() if d.is_dir()])
    return {'maps': maps}


@app.post('/map/load')
async def load_map(namespace: str, map_name: str):
    yaml_path = MAP_BASE_DIR / map_name / f'{map_name}.yaml'
    if not yaml_path.exists():
        return {'ok': False, 'error': f'Map file not found: {yaml_path}'}
    try:
        result = subprocess.run(
            ['ros2', 'service', 'call',
             f'/{namespace}/navigation/map_server/load_map',
             'nav2_msgs/srv/LoadMap',
             f"{{map_url: 'file://{yaml_path}'}}"],
            capture_output=True, text=True, timeout=10, env=ROS_ENV,
        )
        return {'ok': 'result: 0' in result.stdout or result.returncode == 0}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# --- ポイント (places.yaml) ---

def _load_places() -> dict:
    if PLACES_FILE.exists():
        with PLACES_FILE.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_places(data: dict) -> None:
    with PLACES_FILE.open('w') as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _get_robot_pose(namespace: str) -> Optional[list[float]]:
    if _node is None:
        return None
    try:
        t = _node._tf_buffer.lookup_transform('map', f'{namespace}/base_link', rclpy.time.Time())
        x = t.transform.translation.x
        y = t.transform.translation.y
        q = t.transform.rotation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        return [round(x, 3), round(y, 3), round(yaw, 3)]
    except Exception:
        return None


@app.get('/places')
async def get_places():
    data = _load_places()
    result = []
    for category, section in data.items():
        if category == 'rooms' or not isinstance(section, dict):
            continue
        for name, info in section.get('places', {}).items():
            result.append({'category': category, 'name': name, 'pose': info.get('pose', [])})
    return {'places': result}


@app.post('/places/add')
async def add_place(namespace: str, name: str, category: str = 'patrol'):
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
async def remove_place(category: str, name: str):
    data = _load_places()
    section = data.get(category, {})
    if name in section.get('places', {}):
        del section['places'][name]
    if name in section.get('order', []):
        section['order'].remove(name)
    _save_places(data)
    return {'ok': True}


# --- プロンプト ---

@app.get('/prompt')
async def get_prompt():
    content = PROMPT_FILE.read_text(encoding='utf-8') if PROMPT_FILE.exists() else ''
    return {'content': content, 'file': str(PROMPT_FILE)}


@app.post('/prompt')
async def set_prompt(body: PromptBody):
    PROMPT_FILE.write_text(body.content, encoding='utf-8')
    return {'ok': True}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
