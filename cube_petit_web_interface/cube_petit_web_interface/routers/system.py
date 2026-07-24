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
"""システム情報 API (/system/devices, /action/exists, /ros/nodes, /ros/robot_pose)."""

import asyncio
import os
import re
import subprocess

from fastapi import APIRouter

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()

_can_prev_rx: int = -1
_can_stale: bool = False


@router.get('/action/exists')
async def action_exists(name: str) -> dict:
    try:
        result = await asyncio.to_thread(subprocess.run, ['ros2', 'action', 'list'],
                                         capture_output=True,
                                         text=True,
                                         timeout=3)
        found = any(name in line for line in result.stdout.splitlines())
        return {'exists': found}
    except Exception:
        return {'exists': False}


@router.get('/system/devices')
async def get_system_devices() -> dict:
    result: dict = {}

    # IP (IPv4のみ)
    try:
        r = await asyncio.to_thread(subprocess.run, ['hostname', '-I'], capture_output=True, text=True, timeout=3)
        result['ip'] = [ip for ip in r.stdout.strip().split() if ':' not in ip]
    except Exception:
        result['ip'] = []

    # CAN0 ネットワークインターフェース + 受信統計
    global _can_prev_rx, _can_stale
    try:
        r = await asyncio.to_thread(subprocess.run, ['ip', '-s', 'link', 'show', 'can0'],
                                    capture_output=True,
                                    text=True,
                                    timeout=3)
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
    result['lidar'] = os.path.exists('/dev/ttyLD06-19')
    result['imu'] = os.path.exists('/dev/ttyWitMotion')
    result['canable'] = os.path.exists('/dev/ttyCANable')

    # USB接続（lsusb）
    try:
        r = await asyncio.to_thread(subprocess.run, ['lsusb'], capture_output=True, text=True, timeout=5)
        lines = r.stdout.splitlines()
        result['realsense'] = any('8086:0b' in line or 'RealSense' in line for line in lines)
        result['oak'] = any('03e7:' in line or 'Movidius' in line or 'Myriad' in line for line in lines)
    except Exception:
        result['realsense'] = False
        result['oak'] = False

    return result


@router.get('/ros/nodes')
async def get_ros_nodes() -> dict:
    try:
        node_output = await core.get_node_list_output()
        nodes = [n.strip() for n in node_output.splitlines() if n.strip()]
        return {'nodes': nodes}
    except Exception as e:
        return {'nodes': [], 'error': str(e)}


@router.get('/ros/robot_pose')
async def get_robot_pose_endpoint(namespace: str = 'cube_petit_orange') -> dict:
    pose = core.get_robot_pose(namespace)
    if pose is None:
        return {'ok': False}
    return {'ok': True, 'x': pose[0], 'y': pose[1], 'yaw': pose[2]}
