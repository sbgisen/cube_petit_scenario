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
"""会話ステータス API (/ros/conversation/*)."""

import asyncio
import base64
import subprocess
import threading

from fastapi import APIRouter
from pydantic import BaseModel

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import core
except ImportError:
    # python api_server.py で直接実行した場合
    import core

router = APIRouter()


class ContextRequest(BaseModel):
    context: str = ''
    role: int = 2
    images: list[str] = []


@router.get('/ros/conversation/status')
async def get_conversation_status(namespace: str = 'cube_petit_orange') -> dict:
    try:
        await asyncio.to_thread(
            subprocess.run,
            [
                'ros2', 'service', 'call', f'/{namespace}/get_realtime_conversation_status', 'std_srvs/srv/Trigger',
                '{}'
            ],
            capture_output=True,
            text=True,
            timeout=3,
            env=core.ROS_ENV,
        )
        await asyncio.sleep(0.3)
    except Exception:
        pass
    return core.status_cache.get(namespace, {'is_active': False, 'can_receive_message': False})


@router.post('/ros/conversation/enable')
async def enable_conversation(namespace: str = 'cube_petit_orange', enable: bool = True) -> dict:
    try:
        val = 'True' if enable else 'False'
        result = await asyncio.to_thread(
            subprocess.run,
            [
                'ros2', 'service', 'call', f'/{namespace}/enable_realtime_conversation', 'std_srvs/srv/SetBool',
                f'{{data: {val}}}'
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=core.ROS_ENV,
        )
        return {'ok': 'success: True' in result.stdout or result.returncode == 0}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _call_add_context_sync(namespace: str, req_body: ContextRequest) -> bool:
    from cube_petit_chat_msgs.srv import AddContext
    from rclpy.task import Future
    from sensor_msgs.msg import Image as SensorImage

    node = core.get_node()
    if node is None:
        return False

    client = node.create_client(AddContext, f'/{namespace}/add_realtime_context')
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


@router.post('/ros/conversation/context')
async def add_context(namespace: str = 'cube_petit_orange', body: ContextRequest = ContextRequest()) -> dict:
    try:
        ok = await asyncio.get_event_loop().run_in_executor(None, _call_add_context_sync, namespace, body)
        return {'ok': ok}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
