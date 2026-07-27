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
"""システム情報 API (/system/devices, /system/namespace, /action/exists, /ros/nodes, /ros/robot_pose)."""

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


@router.get('/system/namespace')
async def get_namespace() -> dict:
    """接続先ロボットの ROS 名前空間 (hostname 由来) をフロントエンドに返す."""
    return {'namespace': core.DEFAULT_NAMESPACE}


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
    # /dev/ttyCANableのudevルールはCANable2(idVendor=16d0, idProduct=117e)専用で、
    # 別機種のCANableボード(例: pinkのProtofusion Labs製、CANtactファーム、
    # idVendor=ad50)ではシンボリックリンクが作られず誤って「未検出」になる。
    # 実体はslcandプロセスの有無(ボード機種によらずCAN0を動かしていれば必ず居る)
    # で代替検出する。
    result['canable'] = os.path.exists('/dev/ttyCANable')
    if not result['canable']:
        try:
            r = await asyncio.to_thread(subprocess.run, ['pgrep', '-x', 'slcand'],
                                        capture_output=True,
                                        text=True,
                                        timeout=3)
            result['canable'] = r.returncode == 0
        except Exception:
            pass

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


@router.post('/system/can/restart')
async def restart_can() -> dict:
    """CAN0(slcand経由のCANable)を再起動する.

    can@ttyCANable.serviceの`startCan.sh`は自身のhealth-checkでslcandプロセスの
    生死とcan0インターフェースの有無しか見ておらず、slcandもcan0も生きたまま
    フレームを受信しなくなる("止まっているのに気づけない")ケースを検知できない。
    この手動リスタートはそのケースの救済用(操作タブのCAN0受信停止表示から呼ぶ)。
    """
    try:
        r = await asyncio.to_thread(subprocess.run, ['sudo', 'systemctl', 'restart', 'can@ttyCANable.service'],
                                    capture_output=True,
                                    text=True,
                                    timeout=15)
        if r.returncode == 0:
            return {'ok': True, 'message': 'CAN0を再起動しました'}
        return {'ok': False, 'message': (r.stderr or r.stdout).strip() or f'exit code {r.returncode}'}
    except Exception as e:
        return {'ok': False, 'message': str(e)}


_CONTROLLER_NAME_PATTERNS = ('wireless controller', 'dualshock', 'dualsense', 'xbox', 'joy-con')


def _is_controller_name(name: str) -> bool:
    lname = name.lower()
    return any(p in lname for p in _CONTROLLER_NAME_PATTERNS)


def _parse_bluetoothctl_devices(stdout: str) -> list[dict]:
    """`bluetoothctl devices` 系コマンドの `Device <MAC> <Name>` 形式を解析する."""
    devices = []
    for line in stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) == 3 and parts[0] == 'Device':
            devices.append({'mac': parts[1], 'name': parts[2]})
    return devices


async def _get_battery_percentage(mac: str) -> int | None:
    """`bluetoothctl info <mac>`のBattery Percentage行を読む.

    BlueZのBattery Service(GATT)経由の値で、機種によっては公開されない
    (例: PS4 Wireless Controllerはクラシック接続のみだと出ないことが多い)。
    その場合はNoneを返す(フロントエンドは残量欄を単に表示しない)。
    """
    try:
        r = await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'info', mac],
                                    capture_output=True,
                                    text=True,
                                    timeout=5)
        m = re.search(r'Battery Percentage:.*\((\d+)%\)', r.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


@router.get('/system/bluetooth/controllers')
async def get_bluetooth_controllers() -> dict:
    """接続中のコントローラ(PS4/PS5/Xbox等)一覧を返す(取得できればバッテリー残量も)."""
    try:
        r = await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'devices', 'Connected'],
                                    capture_output=True,
                                    text=True,
                                    timeout=5)
        connected = [d for d in _parse_bluetoothctl_devices(r.stdout) if _is_controller_name(d['name'])]
        for dev in connected:
            dev['battery'] = await _get_battery_percentage(dev['mac'])
        return {'connected': connected}
    except Exception as e:
        return {'connected': [], 'error': str(e)}


@router.post('/system/bluetooth/disconnect')
async def disconnect_bluetooth_controller(mac: str) -> dict:
    """指定したコントローラをBluetooth切断する(ペア情報は保持、再接続はペアリングボタンから)."""
    try:
        r = await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'disconnect', mac],
                                    capture_output=True,
                                    text=True,
                                    timeout=10)
        ok = 'Successful disconnected' in r.stdout or r.returncode == 0
        return {'ok': ok, 'message': (r.stdout or r.stderr).strip()}
    except Exception as e:
        return {'ok': False, 'message': str(e)}


@router.post('/system/bluetooth/pair')
async def pair_bluetooth_controller() -> dict:
    """コントローラのペアリングモード(PS+SHAREボタン長押し等)中にスキャンして自動ペア接続する.

    bluetoothctlの非対話CLI(BlueZ 5.5x以降)で power on → scan(タイムアウト付き)
    → 新規に見つかったコントローラらしき機器を pair/trust/connect する。
    見つからなければその旨を返す(呼び出し元でユーザーに再試行を促す)。
    """
    try:
        # agentを登録しないと pair は「見た目はPaired」でも正しくボンディングされず、
        # bluetoothdがHID接続を "Rejected connection from !bonded device" で拒否する
        # (実機で確認: Paired: yes だが Bonded: no のまま接続が通らないケースがあった)。
        await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'agent', 'NoInputNoOutput'],
                                capture_output=True,
                                text=True,
                                timeout=5)
        await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'default-agent'],
                                capture_output=True,
                                text=True,
                                timeout=5)
        await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'power', 'on'],
                                capture_output=True,
                                text=True,
                                timeout=5)
        await asyncio.to_thread(subprocess.run, ['bluetoothctl', '--timeout', '12', 'scan', 'on'],
                                capture_output=True,
                                text=True,
                                timeout=20)
        r = await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'devices'],
                                    capture_output=True,
                                    text=True,
                                    timeout=5)
        candidates = [d for d in _parse_bluetoothctl_devices(r.stdout) if _is_controller_name(d['name'])]
        if not candidates:
            return {
                'ok': False,
                'message': 'コントローラが見つかりませんでした。ペアリングモード'
                           '(PSボタン+SHAREボタン長押し)にしてから再試行してください',
            }

        connected = []
        for dev in candidates:
            mac = dev['mac']
            # ボンディングされないまま残った古いペア情報があると再ペアがno-opになるため、
            # 一度removeしてから作り直す(接続済みの場合は無害にスキップされる)。
            await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'remove', mac],
                                    capture_output=True,
                                    text=True,
                                    timeout=5)
            await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'pair', mac],
                                    capture_output=True,
                                    text=True,
                                    timeout=10)
            await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'trust', mac],
                                    capture_output=True,
                                    text=True,
                                    timeout=10)
            r_conn = await asyncio.to_thread(subprocess.run, ['bluetoothctl', 'connect', mac],
                                             capture_output=True,
                                             text=True,
                                             timeout=10)
            if 'Connection successful' in r_conn.stdout or 'already connected' in r_conn.stdout.lower():
                connected.append(dev)

        if connected:
            names = '、'.join(d['name'] for d in connected)
            return {'ok': True, 'message': f'{names} に接続しました', 'connected': connected}
        return {'ok': False, 'message': 'コントローラは見つかりましたが接続できませんでした'}
    except Exception as e:
        return {'ok': False, 'message': str(e)}


@router.get('/ros/nodes')
async def get_ros_nodes() -> dict:
    try:
        node_output = await core.get_node_list_output()
        nodes = [n.strip() for n in node_output.splitlines() if n.strip()]
        return {'nodes': nodes}
    except Exception as e:
        return {'nodes': [], 'error': str(e)}


@router.get('/ros/robot_pose')
async def get_robot_pose_endpoint(namespace: str = core.DEFAULT_NAMESPACE) -> dict:
    pose = core.get_robot_pose(namespace)
    if pose is None:
        return {'ok': False}
    return {'ok': True, 'x': pose[0], 'y': pose[1], 'yaw': pose[2]}
