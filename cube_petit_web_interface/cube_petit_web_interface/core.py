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
"""API サーバーの共有基盤.

rclpy 常駐ノード・TF・launch プロセス管理・共有定数・lifespan を持つ。
rclpy の import はすべて関数内で行い、ROS 環境なしでもこのモジュール自体は
import できる（テストで app を import 可能にするため）。
"""

from contextlib import asynccontextmanager
import math
import os
from pathlib import Path
import subprocess
import threading
from typing import AsyncIterator, Callable, Optional, TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from rclpy.node import Node

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import helpers
except ImportError:
    # python api_server.py で直接実行した場合
    import helpers  # noqa: F401  (routers から core.helpers として参照される)

ROS_ENV = {**os.environ, 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'}

MAP_BASE_DIR = Path('/home/cube-petit/ros/src/cube_petit_ros/cube_petit_navigation/map')
MAP_EXTRA_DIR = Path('/home/cube-petit/map')
MAP_DIRS = [MAP_BASE_DIR, MAP_EXTRA_DIR]
PLACES_FILE = Path('/home/cube-petit/ros/src/cube_petit_ros/cube_petit_navigation/config/places.yaml')
PROMPT_FILE = Path('/home/cube-petit/ros/src/cube_petit_interaction/cube_petit_chat/config/realtime_chat_setting.txt')

PROMPT_DIR = PROMPT_FILE.parent
ACTIVE_MARKER = PROMPT_DIR / '.active_prompt'
PROTECTED_PROMPTS = {'realtime_chat_setting.txt', 'gpt_chat_setting.txt'}

HISTORY_DIR = Path('/home/cube-petit/ros/src/cube_petit_interaction/cube_petit_chat/resource/history')
HISTORY_ACTIVE_MARKER = HISTORY_DIR / '.active_history'
PROTECTED_HISTORY = {'history.jsonl'}

# rclpy 常駐ノード
WATCHED_NAMESPACES = ['cube_petit_orange']
status_cache: dict[str, dict] = {ns: {'is_active': False, 'can_receive_message': False} for ns in WATCHED_NAMESPACES}
_node: Optional['Node'] = None
_tf_buffer = None
_tf_listener = None
_ros_thread: Optional[threading.Thread] = None

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
    # demo: 02_DEMO_VISION 相当。プロンプトは PROMPT_DIR の .active_prompt が指すファイル
    # (lt_demo_prompt.txt は slides 側へのsymlink)。表情(change_expression)+
    # 視覚(infer_object)+Web検索(gpt_chat)を有効化
    'demo': [
        'ros2',
        'launch',
        'cube_petit_scenario',
        'cube_petit_talk_demo.launch.py',
        f'setting_file:={PROMPT_DIR}/lt_demo_prompt.txt',
        "tool_names:=['change_expression']",
        "gpt_tool_names:=['gpt_chat', 'infer_object']",
        ('gpt_tools.infer_object.setting_path:=/home/cube-petit/ros/install/cube_petit_chat/'
         'share/cube_petit_chat/config/gpt_tools/infer_object/infer_object.txt'),
    ],
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


def get_node() -> Optional['Node']:
    """常駐ノードを返す（未起動なら None）."""
    return _node


def _start_ros() -> None:
    global _node, _tf_buffer, _tf_listener
    from cube_petit_chat_msgs.msg import RealtimeState
    import rclpy
    from rclpy.node import Node
    from tf2_ros import Buffer
    from tf2_ros import TransformListener
    rclpy.init()
    _node = Node('web_interface_watcher')
    _tf_buffer = Buffer()
    _tf_listener = TransformListener(_tf_buffer, _node)
    for ns in WATCHED_NAMESPACES:

        def make_cb(n: str) -> Callable:

            def cb(msg: RealtimeState) -> None:
                status_cache[n]['is_active'] = msg.is_active
                status_cache[n]['can_receive_message'] = msg.can_receive_message

            return cb

        _node.create_subscription(RealtimeState, f'/{ns}/realtime_conversation_status', make_cb(ns), 10)
    rclpy.spin(_node)


def start_ros_thread() -> None:
    """常駐 rclpy ノードのスレッドを起動する（多重起動はしない）."""
    global _ros_thread
    if _ros_thread is not None:
        return
    _ros_thread = threading.Thread(target=_start_ros, daemon=True)
    _ros_thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_ros_thread()
    yield
    for proc in processes.values():
        if proc and proc.poll() is None:
            proc.terminate()


def get_robot_pose(namespace: str) -> Optional[list[float]]:
    """TF から map フレーム上のロボット位置 [x, y, yaw] を返す."""
    from rclpy.time import Time
    if _node is None:
        return None
    try:
        t = _tf_buffer.lookup_transform('map', f'{namespace}/base_link', Time())
        x = t.transform.translation.x
        y = t.transform.translation.y
        q = t.transform.rotation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        return [round(x, 3), round(y, 3), round(yaw, 3)]
    except Exception:
        return None
