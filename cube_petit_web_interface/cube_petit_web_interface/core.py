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

import asyncio
from contextlib import asynccontextmanager
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import AsyncIterator, Callable, Optional, TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from rclpy.node import Node

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import conversation_conductor
    from cube_petit_web_interface import conversation_conductor_logic
    from cube_petit_web_interface import fleet_zenoh
    from cube_petit_web_interface import helpers
except ImportError:
    # python api_server.py で直接実行した場合
    import conversation_conductor  # noqa: F401  (routers から core.conversation_conductor として参照される)
    import conversation_conductor_logic  # noqa: F401  (会話デモ未起動時のstatusペイロード組み立てに使う)
    import fleet_zenoh  # noqa: F401  (routers から core.fleet_zenoh として参照される)
    import helpers  # noqa: F401  (routers から core.helpers として参照される)

ROS_ENV = {**os.environ, 'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp'}

# `ros2 node list` は数秒かかることがあるためイベントループ上で実行してはならない。
# 複数タブ/接続からのポーリングが同時に来ても CLI 呼び出しを1本に共有する。
# (`ros2 node list` can take seconds; never run it on the event loop, and share
# one CLI invocation across concurrent polls.)
_node_list_lock: Optional[asyncio.Lock] = None
_node_list_cache: tuple[float, str] = (0.0, '')
NODE_LIST_TTL = 3.0


async def get_node_list_output() -> str:
    """Return `ros2 node list` stdout, cached for NODE_LIST_TTL seconds."""
    global _node_list_lock, _node_list_cache
    if _node_list_lock is None:
        _node_list_lock = asyncio.Lock()
    async with _node_list_lock:
        if time.monotonic() - _node_list_cache[0] < NODE_LIST_TTL:
            return _node_list_cache[1]
        # ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET だと同じサブネット上の他機のノードも
        # 探索対象になり、機体が増える/ネットワークが混むと`ros2 node list`自体が
        # 5秒では終わらないことがある(yellowで実際に5秒超で"bringup: false"の
        # 誤判定を引き起こした。プロセス自体はCPUを使って動いており固まってはいない)。
        result = await asyncio.to_thread(subprocess.run, ['ros2', 'node', 'list'],
                                         capture_output=True,
                                         text=True,
                                         timeout=15,
                                         env=ROS_ENV)
        _node_list_cache = (time.monotonic(), result.stdout)
        return result.stdout


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
# hostname (cube_petit_<color>) から動的に導出する。cube_petit_bringup.launch.py の
# face_color 導出と同じ発想（PR #102参照）。routers 側のデフォルト値もここから参照する。
DEFAULT_NAMESPACE = helpers.resolve_namespace()
WATCHED_NAMESPACES = [DEFAULT_NAMESPACE]
status_cache: dict[str, dict] = {ns: {'is_active': False, 'can_receive_message': False} for ns in WATCHED_NAMESPACES}
_node: Optional['Node'] = None
_tf_buffer = None
_tf_listener = None
_ros_thread: Optional[threading.Thread] = None

# Tier 2: fleet-wide multi-robot picker (see fleet_zenoh.py). Independent of
# the rclpy watcher above -- a plain eclipse-zenoh client session, not a ROS node.
ZENOH_ROUTER_ENDPOINT = os.environ.get('ZENOH_ROUTER_ENDPOINT', fleet_zenoh.DEFAULT_ZENOH_ENDPOINT)
ZENOH_MODE = os.environ.get('ZENOH_MODE', fleet_zenoh.DEFAULT_ZENOH_MODE)
_fleet_watcher: Optional['fleet_zenoh.FleetZenohWatcher'] = None
_fleet_error: Optional[str] = None
_fleet_zenoh_thread: Optional[threading.Thread] = None

processes: dict[str, Optional[subprocess.Popen]] = {
    'rosbridge': None,
    'bringup': None,
    'demo': None,
    'anima': None,
    'create_map': None,
    'navigation': None,
    'shared_controller_hub': None,
}

LAUNCH_COMMANDS = {
    'rosbridge': ['ros2', 'launch', 'rosbridge_server', 'rosbridge_websocket_launch.xml'],
    'bringup': ['ros2', 'launch', 'cube_petit_bringup', 'cube_petit_bringup.launch.py'],
    # demo: 02_DEMO_VISION 相当(ターミナルのaliasと引数を一致させること)。プロンプトは
    # PROMPT_DIR の .active_prompt が指すファイル (lt_demo_prompt.txt は slides 側へのsymlink)。
    # tool_names は launch デフォルトに change_expression を足したもの。視覚(infer_object)+
    # Web検索(gpt_chat)を有効化 (Keep args in sync with the 02_DEMO_VISION shell alias.)
    'demo': [
        'ros2',
        'launch',
        'cube_petit_scenario',
        'cube_petit_talk_demo.launch.py',
        f'setting_file:={PROMPT_DIR}/lt_demo_prompt.txt',
        "tool_names:=['horoscope', 'weather', 'memory_voice', 'memory_name', 'change_expression']",
        "gpt_tool_names:=['gpt_chat', 'infer_object']",
        ('gpt_tools.infer_object.setting_path:=/home/cube-petit/ros/install/cube_petit_chat/'
         'share/cube_petit_chat/config/gpt_tools/infer_object/infer_object.txt'),
    ],
    'anima': ['ros2', 'launch', 'cube_petit_anima', 'anima.launch.py'],
    # create_map.launch.py / navigation.launch.py は自身のhostnameからrobot名前空間を
    # 自動導出する(cube_petit_ros側、2026-07-27)。以前は機体別の薄いラッパー
    # (create_map_orange.launch.py等)を機体色で動的に選んでいたが、hostname自動導出に
    # 一本化してラッパーファイル自体を廃止した。
    # create_map.launch.py / navigation.launch.py auto-derive their robot namespace from
    # hostname (see cube_petit_ros, 2026-07-27); the per-robot wrapper launch files this
    # used to select dynamically (create_map_orange.launch.py, etc.) have been removed.
    'create_map': ['ros2', 'launch', 'cube_petit_navigation', 'create_map.launch.py'],
    'navigation': ['ros2', 'launch', 'cube_petit_navigation', 'navigation.launch.py'],
    # 1台のPS4/PS5コントローラを複数ロボットで使い回す仕組み(共有コントローラ)の
    # hub役。物理接続したこの機体からのコントローラ入力を他機(receiver役、bringupに
    # 統合済みで常時起動中)へ配信する。role/robot_names/toggle_buttonsはstart_launch内で
    # 動的に付与する(navigationのmap:=/keepout:=と同じパターン)。
    # ベースコマンドの末尾(launch file名)は _kill_by_launch_file の検索キーに
    # 使われるため変更しないこと。
    'shared_controller_hub': ['ros2', 'launch', 'cube_petit_shared_controller', 'shared_controller.launch.py'],
}

# 各launchが起動中かを判定するノード名（部分一致）
LAUNCH_NODE_MARKERS = {
    'rosbridge': 'rosbridge_websocket',
    'bringup': 'robot_state_publisher',
    'demo': 'realtime_gpt_chat',
    'anima': 'behavior_node',
    'create_map': 'slam_toolbox',
    'navigation': 'emcl',
    'shared_controller_hub': 'controller_hub_node',
}


async def get_launch_status() -> dict:
    """各launchターゲットが実際に起動中かを返す.

    自プロセス管理下か、systemdサービス等の外部起動かを問わない。
    `/launch/status` と `start_launch` の「既に起動中か」判定を共通化するために切り出した。
    以前は `start_launch` が `processes[target]` （このAPIサーバー自身が起動したものだけ）
    しか見ておらず、systemd の `cube-petit-bringup.service` 等で外部起動されている状態を
    検知できずに二重起動してしまうバグがあった（同名ノードの重複でロボットが不安定になる）。
    """
    try:
        node_output = await get_node_list_output()
        own_ns_prefix = f'/{DEFAULT_NAMESPACE}/'
        own_nodes = [line for line in node_output.splitlines() if line.startswith(own_ns_prefix)]
        status = {}
        for target, marker in LAUNCH_NODE_MARKERS.items():
            proc_alive = processes[target] is not None and processes[target].poll() is None
            status[target] = proc_alive or any(marker in line for line in own_nodes)
        return status
    except Exception:
        return {target: proc is not None and proc.poll() is None for target, proc in processes.items()}


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


def _start_fleet_zenoh() -> None:
    """Open the fleet zenoh watcher (runs in its own thread; see start_fleet_zenoh_thread)."""
    global _fleet_watcher, _fleet_error
    watcher = fleet_zenoh.FleetZenohWatcher(ZENOH_ROUTER_ENDPOINT, ZENOH_MODE)
    try:
        watcher.start()
    except Exception as error:  # noqa: BLE001 - Tier 2 must degrade gracefully, never break Tier 1
        _fleet_error = str(error)
        return
    _fleet_watcher = watcher


def start_fleet_zenoh_thread() -> None:
    """Tier 2 のフリート監視スレッドを起動する（多重起動はしない・失敗しても例外を投げない）."""
    global _fleet_zenoh_thread, _fleet_error
    if _fleet_zenoh_thread is not None:
        return
    if fleet_zenoh.zenoh is None:
        _fleet_error = ("The 'eclipse-zenoh' pip package is not installed; the multi-robot picker "
                        '(Tier 2) is disabled. See cube_petit_web_interface/requirements.txt.')
        return
    _fleet_zenoh_thread = threading.Thread(target=_start_fleet_zenoh, daemon=True)
    _fleet_zenoh_thread.start()


def get_fleet_state() -> dict:
    """フリート監視の最新スナップショットを返す（未起動/利用不可なら空 dict）."""
    if _fleet_watcher is None:
        return {}
    return _fleet_watcher.snapshot()


def get_fleet_error() -> Optional[str]:
    """フリート監視が使えない理由（正常なら None）."""
    return _fleet_error


def send_fleet_command(robot_name: str, method: str, args: dict) -> str:
    """フリート内の(自分以外でもよい)ロボットへコマンドを送る（例: move_to_pose）.

    Raises:
        RuntimeError: フリート監視(zenoh)が起動していない場合。
    """
    if _fleet_watcher is None:
        raise RuntimeError('Fleet zenoh watcher is not running (Tier 2 unavailable)')
    return _fleet_watcher.send_command(robot_name, method, args)


def start_fleet_chase(chaser: str, target: str) -> str:
    """追いかけっこペアを開始する(このAPIサーバープロセス内の常駐ループで実行される).

    Raises:
        RuntimeError: フリート監視(zenoh)が起動していない場合。
        ValueError: chaser == target の場合。
    """
    if _fleet_watcher is None:
        raise RuntimeError('Fleet zenoh watcher is not running (Tier 2 unavailable)')
    return _fleet_watcher.start_chase(chaser, target)


def stop_fleet_chase(pair_id: str) -> bool:
    """追いかけっこペアを停止する。存在しなければFalse."""
    if _fleet_watcher is None:
        return False
    return _fleet_watcher.stop_chase(pair_id)


def list_fleet_chase() -> list:
    """現在アクティブな追いかけっこペア一覧を返す."""
    if _fleet_watcher is None:
        return []
    return _fleet_watcher.list_chase()


# ================= 会話デモ「指揮者」(conversation_conductor.py) =================
# fleet zenoh watcher(_fleet_watcher)の send_command/wait_for_completion を
# そのまま指揮者に渡す(zenohセッションを二重に開かない)。フリート監視スレッド
# 起動前にstartが呼ばれた場合はエラーにする(chase系のRuntimeErrorパターンと同じ)。
_conversation_conductor: Optional['conversation_conductor.ConversationConductor'] = None


def _get_conversation_conductor() -> 'conversation_conductor.ConversationConductor':
    global _conversation_conductor
    if _conversation_conductor is None:
        if _fleet_watcher is None:
            raise RuntimeError('Fleet zenoh watcher is not running (Tier 2 unavailable); '
                               'the conversation demo needs it to send speak commands')
        _conversation_conductor = conversation_conductor.ConversationConductor(
            send_command=_fleet_watcher.send_command,
            wait_for_completion=_fleet_watcher.wait_for_completion,
        )
    return _conversation_conductor


def start_fleet_conversation(participants: list, mode: str = 'script') -> None:
    """会話デモ(指揮者)を開始する.

    Raises:
        RuntimeError: フリート監視(zenoh)が起動していない場合。
        conversation_conductor.ConductorError: 既に実行中/参加機体不足/未対応モード。
    """
    _get_conversation_conductor().start(participants, mode)


def stop_fleet_conversation() -> None:
    """会話デモ(指揮者)を停止する(実行中でなければ何もしない)."""
    if _conversation_conductor is not None:
        _conversation_conductor.stop()


def get_fleet_conversation_status() -> dict:
    """会話デモ(指揮者)の現在状態を返す(未起動なら停止中として扱う)."""
    if _conversation_conductor is None:
        return conversation_conductor_logic.build_status_payload({})
    return _conversation_conductor.status()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_ros_thread()
    start_fleet_zenoh_thread()
    yield
    for proc in processes.values():
        if proc and proc.poll() is None:
            proc.terminate()
    if _conversation_conductor is not None:
        _conversation_conductor.stop()
    if _fleet_watcher is not None:
        _fleet_watcher.close()


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
