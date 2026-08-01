#!/usr/bin/env python

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
"""ROSConJP 2026 booth "conversation demo" conductor (指揮者): script mode.

Generates a ~1 minute orange/pink/violet script with a single LLM call, then
plays it back turn by turn over the existing fleet zenoh `speak` command
(cube_petit_fleet_bridge, already fully implemented -- see
plans/conversation_demo_plan.md in orange_petit_claude for the full design
and cube_petit_fleet_bridge/cube_petit_fleet_bridge/zenoh_connector.py's
`_handle_speak` in the cube_petit_ros repo for the wire format this drives).

Runs as a single background thread inside this always-on FastAPI process
(same pattern as fleet_zenoh.py's chase loop), so the demo isn't affected by
the operator's browser tab switching/closing. `stop()` is cooperative: it
sets an Event the loop checks between turns and while waiting for a speak
command to complete.

Two seams are deliberately dependency-injected so this class stays testable
without real zenoh/OpenAI, and so "掛け合いモード" (turn-by-turn, human
参加) can reuse the same LLM call / robot-speak plumbing later:

  * `send_command` / `wait_for_completion`: bound to a FleetZenohWatcher's
    methods by core.py in production; a stub pair in tests.
  * `llm_call`: `str -> str` (prompt -> raw script JSON text). Defaults to
    `_default_llm_call`, a thin OpenAI wrapper mirroring
    cube_petit_interaction/cube_petit_chat's realtime_gpt_chat.py /
    gpt_api_chat.py OPENAI_API_KEY convention (see that repo's launch files:
    `api_key` launch arg defaults to the `OPENAI_API_KEY` env var). Tests
    inject a canned `llm_call` instead.

TODO(face): the LLM script includes a `face` per turn
(conversation_conductor_logic.VALID_FACES), but cube_petit_fleet_bridge's
`speak` command has no facial-expression argument yet (only `text`) --
see that module's SUPPORTED_METHODS/validate_speak_args in the cube_petit_ros
repo. `face` is logged/shown in the UI today but not sent to the robot.
Wiring this needs a cube_petit_ros change (new zenoh method, or extending
`speak`'s args) -- out of scope for this skeleton.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
import time
import typing

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import conversation_conductor_logic as logic
except ImportError:
    # python api_server.py で直接実行した場合
    import conversation_conductor_logic as logic

try:
    from openai import OpenAI
except ImportError as _openai_import_error:  # pragma: no cover - exercised only without the pip dep
    OpenAI = None
    _OPENAI_IMPORT_ERROR = _openai_import_error
else:
    _OPENAI_IMPORT_ERROR = None

#: Same default model realtime_gpt_chat / gpt_api_chat use for one-shot text
#: generation (see cube_petit_interaction/cube_petit_chat's gpt_api_chat.py).
DEFAULT_MODEL = 'gpt-4o'

#: Gap between turns (lets the previous utterance's audio tail off and gives
#: a human-conversation-like beat before the next robot starts).
INTER_TURN_GAP_SEC = 0.6

#: Default location of the setup wizard's per-robot personality.yaml files
#: (see conversation_conductor_logic.personality_file_path).
DEFAULT_PERSONALITY_BASE_DIR = Path.home() / '.cube_petit'

SendCommand = typing.Callable[[str, str, dict], str]
WaitForCompletion = typing.Callable[[str, float], typing.Optional[bool]]
LlmCall = typing.Callable[[str], str]


class ConductorError(RuntimeError):
    """Raised by start()/stop() for user-facing failures (already running, bad mode, etc.)."""


class ConversationConductor:
    """Owns one background "script mode" playback run at a time."""

    def __init__(self,
                 send_command: SendCommand,
                 wait_for_completion: WaitForCompletion,
                 llm_call: typing.Optional[LlmCall] = None,
                 personality_base_dir: Path = DEFAULT_PERSONALITY_BASE_DIR) -> None:
        """Build a conductor bound to the given zenoh send/wait and (optional) LLM callables.

        Args:
            send_command: ``(full_robot_name, method, args) -> command_id``,
                e.g. `FleetZenohWatcher.send_command`.
            wait_for_completion: ``(command_id, timeout_sec) ->
                success_or_None``, e.g. `FleetZenohWatcher.wait_for_completion`.
            llm_call: ``prompt -> raw_json_text``. Defaults to
                `_default_llm_call` (OpenAI). Inject a stub in tests.
            personality_base_dir: Where to look for
                ``<robot>/personality.yaml`` (see conversation_conductor_logic).
        """
        self._send_command = send_command
        self._wait_for_completion = wait_for_completion
        self._llm_call = llm_call or self._default_llm_call
        self._personality_base_dir = personality_base_dir

        self._lock = threading.Lock()
        self._thread: typing.Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._state: dict = {
            'running': False,
            'mode': 'script',
            'participants': [],
            'script': [],
            'current_turn': 0,
            'log': [],
            'started_at': None,
            'elapsed_sec': 0.0,
            'error': '',
        }

    # =================================================
    # Public API (routers/conversation_router.py -> core.py -> here)
    # =================================================

    def start(self, participants: typing.Sequence[str], mode: str = 'script') -> None:
        """Start a new script-mode run.

        Raises:
            ConductorError: If a run is already active, `mode` isn't
                'script' (掛け合いモード is future work, see the plan doc),
                or fewer than 2 participants were given.
        """
        if mode != 'script':
            raise ConductorError(f"Unsupported mode {mode!r}: only 'script' is implemented so far "
                                 '(掛け合いモード is future work, see plans/conversation_demo_plan.md)')
        participants = [logic.short_name(p) for p in participants]
        if len(participants) < 2:
            raise ConductorError('Need at least 2 participants for a conversation')

        with self._lock:
            if self._state['running']:
                raise ConductorError('A conversation is already running; stop it first')
            self._state = {
                'running': True,
                'mode': mode,
                'participants': participants,
                'script': [],
                'current_turn': 0,
                'log': [],
                'started_at': time.monotonic(),
                'elapsed_sec': 0.0,
                'error': '',
            }
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_script, args=(participants,), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Request the current run to stop (no-op if nothing is running).

        Cooperative: the running thread notices `_stop_event` between turns
        and while waiting for a speak command to complete, so this returns
        immediately without blocking on the thread.
        """
        self._stop_event.set()

    def status(self) -> dict:
        """Return the JSON-serializable status payload (thread-safe snapshot)."""
        with self._lock:
            state_copy = dict(self._state)
            state_copy['now'] = time.monotonic()
        return logic.build_status_payload(state_copy)

    # =================================================
    # Background thread
    # =================================================

    def _run_script(self, participants: typing.List[str]) -> None:
        try:
            personalities = logic.load_personalities(participants, self._personality_base_dir)
            prompt = logic.build_script_prompt(participants, personalities)
            raw = self._llm_call(prompt)
            script = logic.parse_script_response(raw, participants)
        except logic.ScriptError as error:
            self._finish(error=f'Script generation failed: {error}')
            return
        except Exception as error:  # noqa: BLE001 - must never crash the background thread
            self._finish(error=f'Script generation failed: {error}')
            return

        with self._lock:
            self._state['script'] = script

        for i, turn in enumerate(script):
            if self._stop_event.is_set():
                self._finish(stopped=True)
                return
            self._speak_turn(i, turn)
            if self._stop_event.wait(INTER_TURN_GAP_SEC):
                self._finish(stopped=True)
                return

        self._finish()

    def _speak_turn(self, index: int, turn: dict) -> None:
        full_name = logic.full_robot_name(turn['speaker'])
        args = {'text': turn['text']}
        try:
            command_id = self._send_command(full_name, 'speak', args)
            timeout = logic.completion_timeout_sec(turn['text'])
            success = self._wait_for_completion(command_id, timeout)
        except Exception as error:  # noqa: BLE001 - one bad turn must not abort the whole script
            success = None
            command_id = ''
            self._append_log_entry(index, turn, success=False, error=str(error))
            return
        self._append_log_entry(index, turn, success=success)

    def _append_log_entry(self, index: int, turn: dict, success: typing.Optional[bool], error: str = '') -> None:
        entry = {
            'speaker': turn['speaker'],
            'text': turn['text'],
            'face': turn['face'],
            'success': success,
            'error': error,
        }
        with self._lock:
            self._state['log'].append(entry)
            self._state['current_turn'] = index + 1

    def _finish(self, error: str = '', stopped: bool = False) -> None:
        with self._lock:
            started_at = self._state.get('started_at')
            self._state['running'] = False
            self._state['elapsed_sec'] = round(time.monotonic() - started_at, 1) if started_at else 0.0
            if error:
                self._state['error'] = error
            elif stopped:
                self._state['error'] = ''  # 停止は正常系(エラー扱いしない)

    # =================================================
    # Default LLM backend (OpenAI, same OPENAI_API_KEY convention as
    # cube_petit_interaction/cube_petit_chat's realtime_gpt_chat.py / gpt_api_chat.py)
    # =================================================

    def _default_llm_call(self, prompt: str) -> str:
        if OpenAI is None:
            raise ConductorError("The 'openai' pip package is not installed. Install it with "
                                 '`uv pip install --system openai` (see '
                                 f'cube_petit_web_interface/requirements.txt). Original error: {_OPENAI_IMPORT_ERROR}')
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            raise ConductorError('OPENAI_API_KEY is not set (same env var cube_petit_chat.launch.py reads for '
                                 'the realtime/gpt chat nodes)')
        client = OpenAI(api_key=api_key)
        response = client.responses.create(model=DEFAULT_MODEL, input=prompt)
        return response.output_text
