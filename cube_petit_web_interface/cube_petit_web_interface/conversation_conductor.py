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
"""ROSConJP 2026 booth "conversation demo" conductor (指揮者): script + interactive modes.

**Script mode**: generates a ~1 minute orange/pink/violet script with a
single LLM call, then plays it back turn by turn over the existing fleet
zenoh `speak` command (cube_petit_fleet_bridge, already fully implemented --
see plans/conversation_demo_plan.md in orange_petit_claude for the full
design and cube_petit_fleet_bridge/cube_petit_fleet_bridge/zenoh_connector.py's
`_handle_speak` in the cube_petit_ros repo for the wire format this drives).

**Interactive mode (掛け合いモード)**: one LLM call *per turn* instead of
one call for the whole script, so a human's ASR transcript (orange's mic
only, see plans/conversation_demo_plan.md) can steer the conversation
turn-by-turn. After each robot turn, the loop waits a short "human の間"
window (`human_window_sec`, default `conversation_conductor_logic.
DEFAULT_HUMAN_WINDOW_SEC`) for `submit_human_utterance()` to be called (by
core.py's rclpy subscription to `realtime_conversation_content`, filtering
`user: ` lines -- see that module for the ASR wiring and its exclusivity
caveat with the normal chat pipeline). If a human utterance arrives it's
appended to history (and echoed to the caller-supplied
`publish_transcript`, e.g. a fleet zenoh key) so the *next* turn's prompt
can react to it -- destination/宛先 inference ("ピンクちゃん、〜" ->
next speaker = pink) is left entirely to the LLM's prompt instructions
(conversation_conductor_logic.build_turn_prompt()), this class has no
name-matching logic of its own. The same 45s/60s "1分制御" as the plan
doc's script-mode section applies here too, just enforced live instead of
being baked into a single upfront script (see logic.should_inject_closing_hint
/ logic.should_force_close).

Runs as a single background thread inside this always-on FastAPI process
(same pattern as fleet_zenoh.py's chase loop), so the demo isn't affected by
the operator's browser tab switching/closing. `stop()` is cooperative: it
sets an Event the loop checks between turns and while waiting for a speak
command to complete.

Several seams are deliberately dependency-injected so this class stays
testable without real zenoh/OpenAI/ROS:

  * `send_command` / `wait_for_completion`: bound to a FleetZenohWatcher's
    methods by core.py in production; a stub pair in tests.
  * `llm_call`: `str -> str` (prompt -> raw script JSON text), used by script
    mode. Defaults to `_default_llm_call`, a thin OpenAI wrapper mirroring
    cube_petit_interaction/cube_petit_chat's realtime_gpt_chat.py /
    gpt_api_chat.py OPENAI_API_KEY convention (see that repo's launch files:
    `api_key` launch arg defaults to the `OPENAI_API_KEY` env var). Tests
    inject a canned `llm_call` instead.
  * `turn_llm_call`: `str -> str` (prompt -> raw single-turn JSON text), used
    by interactive mode. Defaults to `_default_turn_llm_call`, the same
    OpenAI wrapper but with a smaller/cheaper model and a tight
    `max_output_tokens` (low-latency priority per the plan doc -- a whole
    script's worth of tokens per turn would make every "間" feel laggy).
  * `publish_transcript`: `(speaker, text) -> None`, optional. Bound to
    FleetZenohWatcher.publish_transcript by core.py so other fleet peers /
    the webapp can see human utterances too. `None` in tests / if the fleet
    zenoh watcher isn't available (best-effort -- a demo shouldn't hard-fail
    just because this one broadcast couldn't go out).

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

#: 掛け合いモードの単ターンLLM呼び出し用モデル/上限トークン。1発話1〜2文しか
#: 要らないので、台本モード用の DEFAULT_MODEL より軽量・低レイテンシ優先にする
#: (plan doc: 「ターンごとのLLM呼び出しは低レイテンシ優先」)。
INTERACTIVE_TURN_MODEL = 'gpt-4o-mini'
INTERACTIVE_TURN_MAX_TOKENS = 150

#: Gap between turns (lets the previous utterance's audio tail off and gives
#: a human-conversation-like beat before the next robot starts).
INTER_TURN_GAP_SEC = 0.6

#: 単ターンLLM呼び出しが立て続けに失敗したときの上限。これを超えたら掛け合い
#: モードを異常終了させる(無限リトライでデモが固まったままにしない)。
MAX_CONSECUTIVE_TURN_ERRORS = 3
#: 失敗時のリトライ間隔(スタックした外部APIを連打しない)。
TURN_RETRY_BACKOFF_SEC = 1.0

#: Speaker-amp warm-up before the first real line. The robots' amps have a
#: signal-detect standby that swallows the first ~1s of audio after idle, and
#: digital silence padding cannot wake them (2026-08-03 booth finding; a
#: continuous sub-audible keep-alive tone was audible on these small speakers
#: and got rejected). So every run starts with a short throat-clear on all
#: participants -- losing (part of) it is harmless and it keeps each robot's
#: real first line intact. Turns then follow closely enough that the amps
#: stay awake for the rest of the run.
WARMUP_TEXT = 'こほんっ'
WARMUP_WAIT_SEC = 2.0

#: Default location of the setup wizard's per-robot personality.yaml files
#: (see conversation_conductor_logic.personality_file_path).
DEFAULT_PERSONALITY_BASE_DIR = Path.home() / '.cube_petit'

SendCommand = typing.Callable[[str, str, dict], str]
WaitForCompletion = typing.Callable[[str, float], typing.Optional[bool]]
LlmCall = typing.Callable[[str], str]
PublishTranscript = typing.Callable[[str, str], None]


class ConductorError(RuntimeError):
    """Raised by start()/stop() for user-facing failures (already running, bad mode, etc.)."""


class ConversationConductor:
    """Owns one background "script mode" playback run at a time."""

    def __init__(self,
                 send_command: SendCommand,
                 wait_for_completion: WaitForCompletion,
                 llm_call: typing.Optional[LlmCall] = None,
                 turn_llm_call: typing.Optional[LlmCall] = None,
                 publish_transcript: typing.Optional[PublishTranscript] = None,
                 personality_base_dir: Path = DEFAULT_PERSONALITY_BASE_DIR) -> None:
        """Build a conductor bound to the given zenoh send/wait and (optional) LLM callables.

        Args:
            send_command: ``(full_robot_name, method, args) -> command_id``,
                e.g. `FleetZenohWatcher.send_command`.
            wait_for_completion: ``(command_id, timeout_sec) ->
                success_or_None``, e.g. `FleetZenohWatcher.wait_for_completion`.
            llm_call: ``prompt -> raw_json_text`` for script mode's one whole-
                script call. Defaults to `_default_llm_call` (OpenAI). Inject
                a stub in tests.
            turn_llm_call: ``prompt -> raw_json_text`` for interactive mode's
                per-turn calls. Defaults to `_default_turn_llm_call` (OpenAI,
                smaller/cheaper model -- see INTERACTIVE_TURN_MODEL). Inject a
                stub in tests.
            publish_transcript: ``(speaker, text) -> None``, best-effort
                broadcast of human utterances (e.g.
                `FleetZenohWatcher.publish_transcript`). `None` to skip
                broadcasting (status()'s log still contains them either way).
            personality_base_dir: Where to look for
                ``<robot>/personality.yaml`` (see conversation_conductor_logic).
        """
        self._send_command = send_command
        self._wait_for_completion = wait_for_completion
        self._llm_call = llm_call or self._default_llm_call
        self._turn_llm_call = turn_llm_call or self._default_turn_llm_call
        self._publish_transcript = publish_transcript
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

        # 掛け合いモード専用: 人間の発話(ASRテキスト)を待ち受けるための単スロット
        # 「メールボックス」。core.py 側のrclpy購読コールバック(別スレッド)から
        # submit_human_utterance() で書き込まれ、_run_interactive() が各ターンの
        # 「人間の間」ウィンドウで _wait_for_human() から読み出す。最新の1件だけを
        # 保持する(キューにしない -- 間に合わなかった発話を後から消化して会話が
        # ずれるより、直近の発話だけ確実に拾う方がデモとして自然)。
        self._human_lock = threading.Lock()
        self._human_pending: typing.Optional[str] = None
        self._human_event = threading.Event()
        self._human_window_sec = logic.DEFAULT_HUMAN_WINDOW_SEC

    # =================================================
    # Public API (routers/conversation_router.py -> core.py -> here)
    # =================================================

    def start(self,
              participants: typing.Sequence[str],
              mode: str = 'script',
              human_window_sec: typing.Optional[float] = None,
              context: typing.Optional[str] = None) -> None:
        """Start a new run (script or interactive mode).

        Args:
            participants: Robot names (short or ``cube_petit_``-prefixed).
            mode: ``'script'`` (default, whole script generated up front) or
                ``'interactive'`` (掛け合いモード, one LLM call per turn +
                human ASR input -- see this module's docstring).
            human_window_sec: Interactive-mode-only override for how long to
                wait for a human utterance after each robot turn (default
                `conversation_conductor_logic.DEFAULT_HUMAN_WINDOW_SEC`).
                Ignored in script mode.
            context: Venue/booth context to ground the LLM prompt in (both
                modes). Falls back to
                `conversation_conductor_logic.DEFAULT_VENUE_CONTEXT` (the
                ROSConJP 2026 booth description) if omitted or blank -- lets
                the booth operator swap topics live via the frontend's
                collapsible "会場コンテキスト" textarea without a redeploy.

        Raises:
            ConductorError: If a run is already active, `mode` isn't one of
                'script'/'interactive', or fewer than 2 participants were given.
        """
        if mode not in ('script', 'interactive'):
            raise ConductorError(f"Unsupported mode {mode!r}: expected 'script' or 'interactive'")
        participants = [logic.short_name(p) for p in participants]
        if len(participants) < 2:
            raise ConductorError('Need at least 2 participants for a conversation')
        resolved_context = context.strip() if context and context.strip() else logic.DEFAULT_VENUE_CONTEXT

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
            with self._human_lock:
                self._human_pending = None
            self._human_event.clear()
            self._human_window_sec = (human_window_sec
                                      if human_window_sec and human_window_sec > 0 else logic.DEFAULT_HUMAN_WINDOW_SEC)
            target = self._run_script if mode == 'script' else self._run_interactive
            self._thread = threading.Thread(target=target, args=(participants, resolved_context), daemon=True)
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

    def submit_human_utterance(self, raw_text: str) -> None:
        """Feed one ASR transcript line into the running interactive-mode conversation.

        Called by core.py's rclpy subscription callback (a different thread
        than the conductor's own background thread) whenever a `user: ...`
        line arrives on `realtime_conversation_content` (see that module for
        the ASR wiring/exclusivity caveat). Silently dropped (no-op) if:

          * the text is empty after `conversation_conductor_logic.
            normalize_human_utterance()`, or
          * no interactive-mode run is currently active (script mode has no
            use for human input mid-run, and stray utterances while idle
            shouldn't leak into the next run's first turn).

        Only the most recent pending utterance is kept (single-slot
        mailbox, not a queue) -- see the constructor docstring/comment.
        """
        text = logic.normalize_human_utterance(raw_text)
        if not text:
            return
        with self._lock:
            active_interactive = self._state['running'] and self._state['mode'] == 'interactive'
        if not active_interactive:
            return
        with self._human_lock:
            self._human_pending = text
            self._human_event.set()

    def _wait_for_human(self, timeout: float) -> typing.Optional[str]:
        """Block up to `timeout` seconds for a submit_human_utterance() call; return its text or None."""
        fired = self._human_event.wait(timeout)
        if not fired:
            return None
        with self._human_lock:
            text = self._human_pending
            self._human_pending = None
            self._human_event.clear()
        return text

    # =================================================
    # Background thread
    # =================================================

    def _run_script(self, participants: typing.List[str], context: str) -> None:
        try:
            personalities = logic.load_personalities(participants, self._personality_base_dir)
            prompt = logic.build_script_prompt(participants, personalities, context)
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

        self._warm_up_amps(participants)
        for i, turn in enumerate(script):
            if self._stop_event.is_set():
                self._finish(stopped=True)
                return
            self._speak_turn(i, turn)
            if self._stop_event.wait(INTER_TURN_GAP_SEC):
                self._finish(stopped=True)
                return

        self._finish()

    def _run_interactive(self, participants: typing.List[str], context: str) -> None:
        """掛け合いモードのメインループ: 1ターン1回LLM呼び出し + 人間の間 + 1分制御."""
        try:
            personalities = logic.load_personalities(participants, self._personality_base_dir)
        except Exception as error:  # noqa: BLE001 - must never crash the background thread
            self._finish(error=f'Personality loading failed: {error}')
            return

        self._warm_up_amps(participants)
        consecutive_errors = 0
        while not self._stop_event.is_set():
            with self._lock:
                started_at = self._state['started_at']
                history = list(self._state['log'])
            elapsed = time.monotonic() - started_at

            if logic.should_force_close(elapsed):
                closer = logic.last_robot_speaker(history, participants)
                turn = logic.build_forced_closing_turn(closer, personalities)
                with self._lock:
                    index = self._state['current_turn']
                self._speak_turn(index, turn)
                self._finish()
                return

            prompt = logic.build_turn_prompt(participants,
                                             personalities,
                                             history,
                                             elapsed,
                                             closing_hint=logic.should_inject_closing_hint(elapsed),
                                             context=context)
            try:
                raw = self._turn_llm_call(prompt)
                turn = logic.parse_turn_response(raw, participants)
            except Exception as error:  # noqa: BLE001 - one bad turn must not abort the whole run
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_TURN_ERRORS:
                    self._finish(error=f'Too many consecutive turn-generation failures: {error}')
                    return
                if self._stop_event.wait(TURN_RETRY_BACKOFF_SEC):
                    self._finish(stopped=True)
                    return
                continue
            consecutive_errors = 0

            if self._stop_event.is_set():
                self._finish(stopped=True)
                return
            with self._lock:
                index = self._state['current_turn']
            self._speak_turn(index, turn)

            if self._stop_event.is_set():
                self._finish(stopped=True)
                return
            human_text = self._wait_for_human(self._human_window_sec)
            if human_text:
                self._append_human_log_entry(human_text)
                if self._publish_transcript is not None:
                    try:
                        self._publish_transcript(logic.HUMAN_SPEAKER, human_text)
                    except Exception:  # noqa: BLE001 - broadcast is best-effort
                        pass

        self._finish(stopped=True)

    def _append_human_log_entry(self, text: str) -> None:
        entry = {
            'speaker': logic.HUMAN_SPEAKER,
            'text': text,
            'face': '',
            'success': True,
            'error': '',
        }
        with self._lock:
            self._state['log'].append(entry)

    def _warm_up_amps(self, participants: typing.List[str]) -> None:
        """Fire a short throat-clear on every participant to wake their amps.

        Fire-and-forget (completion is not awaited; losing part of the warm-up
        audio is the whole point) -- see WARMUP_TEXT above. Skipped instantly
        when a stop was already requested.
        """
        if self._stop_event.is_set():
            return
        for name in participants:
            try:
                self._send_command(logic.full_robot_name(name), 'speak', {'text': WARMUP_TEXT})
            except Exception:  # noqa: BLE001 - warm-up must never abort the run
                continue
        self._stop_event.wait(WARMUP_WAIT_SEC)

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
        client = self._build_openai_client()
        response = client.responses.create(model=DEFAULT_MODEL, input=prompt)
        return response.output_text

    def _default_turn_llm_call(self, prompt: str) -> str:
        """掛け合いモードの単ターン呼び出し: 軽量モデル + max_output_tokensを絞って低レイテンシ優先."""
        client = self._build_openai_client()
        response = client.responses.create(model=INTERACTIVE_TURN_MODEL,
                                           input=prompt,
                                           max_output_tokens=INTERACTIVE_TURN_MAX_TOKENS)
        return response.output_text

    def _build_openai_client(self) -> 'OpenAI':
        if OpenAI is None:
            raise ConductorError("The 'openai' pip package is not installed. Install it with "
                                 '`uv pip install --system openai` (see '
                                 f'cube_petit_web_interface/requirements.txt). Original error: {_OPENAI_IMPORT_ERROR}')
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if not api_key:
            raise ConductorError('OPENAI_API_KEY is not set (same env var cube_petit_chat.launch.py reads for '
                                 'the realtime/gpt chat nodes)')
        return OpenAI(api_key=api_key)
