import subprocess
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
        result = subprocess.run(
            ['ros2', 'action', 'list'],
            capture_output=True, text=True, timeout=3
        )
        found = any(name in line for line in result.stdout.splitlines())
        return {'exists': found}
    except Exception:
        return {'exists': False}


@app.get('/launch/status')
async def get_status():
    return {
        target: proc is not None and proc.poll() is None
        for target, proc in processes.items()
    }
