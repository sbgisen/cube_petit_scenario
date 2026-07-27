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
"""launch 制御 API (/launch/*)."""

import os
import signal
import subprocess
import time
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


class LaunchResponse(BaseModel):
    ok: bool
    message: str


@router.post('/launch/{target}/start', response_model=LaunchResponse)
async def start_launch(
        target: str,
        map: Optional[str] = None,  # noqa: A002
        keepout: Optional[str] = None) -> LaunchResponse:
    if target not in core.LAUNCH_COMMANDS:
        return LaunchResponse(ok=False, message=f'Unknown target: {target}')
    # このAPI自身が起動したプロセスだけでなく、systemdサービス等で外部起動されている
    # 場合も検知する(でないと二重起動して同名ノードが衝突し、片方が不安定になる)
    status = await core.get_launch_status()
    if status.get(target):
        return LaunchResponse(ok=False, message=f'{target} is already running (別プロセス/systemdサービス含む)')
    if target in ('bringup', 'rosbridge'):
        subprocess.run(['fuser', '-k', '9090/tcp'], capture_output=True)
        time.sleep(0.5)
    cmd = list(core.LAUNCH_COMMANDS[target])
    log_msg = ' '.join(cmd)
    if target == 'navigation':
        if map:
            map_dir = core.helpers.find_map_dir(map, core.MAP_DIRS)
            map_yaml = str(map_dir / 'map.yaml') if map_dir else map
            cmd.append(f'map:={map_yaml}')
            log_msg += f' map:={map_yaml}'
        if keepout:
            kp_dir = core.helpers.find_map_dir(keepout, core.MAP_DIRS)
            kp_yaml = str(kp_dir / 'map_keepout.yaml') if kp_dir else keepout
            cmd.append(f'keepout:={kp_yaml}')
            log_msg += f' keepout:={kp_yaml}'
    core.processes[target] = subprocess.Popen(cmd, env=core.ROS_ENV, preexec_fn=os.setsid)
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


@router.post('/launch/{target}/stop', response_model=LaunchResponse)
async def stop_launch(target: str) -> LaunchResponse:
    if target not in core.processes:
        return LaunchResponse(ok=False, message=f'Unknown target: {target}')

    killed = False

    # 自前で起動したプロセスグループを停止
    proc = core.processes[target]
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            killed = True
        except Exception:
            proc.terminate()
            killed = True
    core.processes[target] = None

    # 外部起動のプロセスも探して停止
    launch_file = core.LAUNCH_COMMANDS[target][-1]
    if _kill_by_launch_file(launch_file):
        killed = True

    if killed:
        return LaunchResponse(ok=True, message=f'{target} stopped')
    return LaunchResponse(ok=False, message=f'{target} is not running')


@router.post('/launch/kill_all')
async def kill_all_ros() -> dict:
    subprocess.run(['pkill', 'ros'], capture_output=True)
    subprocess.run(['pkill', 'ros2'], capture_output=True)
    for k in core.processes:
        core.processes[k] = None
    return {'ok': True}


@router.get('/launch/status')
async def get_status() -> dict:
    # ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET のため、同じサブネット上の他機のノードも
    # ros2 node list に出てくる。名前空間で絞らないと、例えば pink の
    # rosbridge_websocket ノードを orange 側の判定が誤って拾ってしまう
    # (rosbridgeが実際は落ちてるのに「起動中」と表示され続けるバグの原因)。
    # 実装は core.get_launch_status() に共通化済み（start_launch の二重起動防止チェックと
    # 同じロジックを共有する）。
    return await core.get_launch_status()
