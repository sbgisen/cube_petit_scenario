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
"""Tests for ConversationConductor's turn-playback orchestration.

send_command / wait_for_completion / llm_call are all dependency-injected
stubs here (see conversation_conductor.py's module docstring) -- no real
zenoh session and no OpenAI call happen in this file, so it runs in the
plain-Python CI job.
"""

import json
import threading
import time

import pytest

from cube_petit_web_interface import conversation_conductor
from cube_petit_web_interface import conversation_conductor_logic as logic


def _script_json(turns: list) -> str:
    return json.dumps(turns)


def _wait_until_idle(conductor: conversation_conductor.ConversationConductor, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not conductor.status()['running']:
            return
        time.sleep(0.01)
    raise AssertionError('Conductor did not finish within timeout')


@pytest.fixture(autouse=True)
def _fast_inter_turn_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real INTER_TURN_GAP_SEC (0.6s) would make every test slow for no benefit;
    # the gap's existence isn't what these tests are checking.
    monkeypatch.setattr(conversation_conductor, 'INTER_TURN_GAP_SEC', 0.0)


class _StubZenoh:
    """Minimal stand-in for FleetZenohWatcher's two methods the conductor uses."""

    def __init__(self, completion_success: bool = True, block_completion: bool = False) -> None:
        self.sent: list = []
        self._completion_success = completion_success
        self._block_event = threading.Event() if block_completion else None
        self._next_id = 0

    def send_command(self, robot_name: str, method: str, args: dict) -> str:
        self._next_id += 1
        command_id = f'cmd-{self._next_id}'
        self.sent.append((robot_name, method, args, command_id))
        return command_id

    def wait_for_completion(self, command_id: str, timeout: float) -> bool | None:
        if self._block_event is not None:
            self._block_event.wait(timeout)
            return None
        return self._completion_success

    def release(self) -> None:
        if self._block_event is not None:
            self._block_event.set()


VALID_SCRIPT = [
    {
        'speaker': 'orange',
        'text': 'やっほー!',
        'face': 'happy'
    },
    {
        'speaker': 'pink',
        'text': 'こんにちはー',
        'face': 'normal'
    },
    {
        'speaker': 'violet',
        'text': 'またね',
        'face': 'normal'
    },
]


class TestStartValidation:

    def test_rejects_non_script_mode(self) -> None:
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        with pytest.raises(conversation_conductor.ConductorError):
            conductor.start(['orange', 'pink'], mode='banter')

    def test_rejects_too_few_participants(self) -> None:
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        with pytest.raises(conversation_conductor.ConductorError):
            conductor.start(['orange'])

    def test_rejects_double_start(self) -> None:
        zenoh = _StubZenoh(block_completion=True)
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        conductor.start(['orange', 'pink', 'violet'])
        try:
            with pytest.raises(conversation_conductor.ConductorError):
                conductor.start(['orange', 'pink', 'violet'])
        finally:
            conductor.stop()
            zenoh.release()
            _wait_until_idle(conductor)


class TestFullRun:

    def test_plays_every_turn_in_order_and_marks_done(self) -> None:
        zenoh = _StubZenoh(completion_success=True)
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        conductor.start(['orange', 'pink', 'violet'])
        _wait_until_idle(conductor)

        status = conductor.status()
        assert status['error'] == ''
        assert status['total_turns'] == 3
        assert status['current_turn'] == 3
        assert [entry['speaker'] for entry in status['log']] == ['orange', 'pink', 'violet']
        assert all(entry['success'] is True for entry in status['log'])

        # cube_petit_fleet_bridge's speak command only accepts `text` today
        # (see conversation_conductor.py's TODO(face)) -- args sent must not
        # include anything speak's validate_speak_args would reject.
        assert zenoh.sent[0][1] == 'speak'
        assert zenoh.sent[0][2] == {'text': 'やっほー!'}
        assert zenoh.sent[0][0] == 'cube_petit_orange'

    def test_status_while_idle_before_any_start(self) -> None:
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        status = conductor.status()
        assert status['running'] is False
        assert status['total_turns'] == 0


class TestStop:

    def test_stop_mid_run_halts_without_error(self) -> None:
        zenoh = _StubZenoh(block_completion=True)
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        conductor.start(['orange', 'pink', 'violet'])
        # Let the first turn's send_command fire, then stop before it "finishes" speaking.
        deadline = time.monotonic() + 2.0
        while not zenoh.sent and time.monotonic() < deadline:
            time.sleep(0.01)
        conductor.stop()
        zenoh.release()
        _wait_until_idle(conductor)

        status = conductor.status()
        assert status['running'] is False
        assert status['error'] == ''
        assert status['current_turn'] < status['total_turns']


class TestErrorHandling:

    def test_invalid_llm_response_is_recorded_as_error(self) -> None:
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: 'not valid json')
        conductor.start(['orange', 'pink'])
        _wait_until_idle(conductor)
        status = conductor.status()
        assert status['running'] is False
        assert 'Script generation failed' in status['error']
        assert zenoh.sent == []

    def test_send_command_failure_on_one_turn_does_not_abort_script(self) -> None:
        calls = {'n': 0}

        def flaky_send(robot_name: str, method: str, args: dict) -> str:
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('zenoh session not open')
            return f'cmd-{calls["n"]}'

        def always_success(command_id: str, timeout: float) -> bool:
            return True

        conductor = conversation_conductor.ConversationConductor(flaky_send,
                                                                 always_success,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        conductor.start(['orange', 'pink', 'violet'])
        _wait_until_idle(conductor)

        status = conductor.status()
        assert status['current_turn'] == 3
        assert status['log'][0]['success'] is False
        assert 'zenoh session not open' in status['log'][0]['error']
        assert status['log'][1]['success'] is True
        assert status['log'][2]['success'] is True


class TestPersonalitySourcing:

    def test_uses_orange_pink_violet_short_names_end_to_end(self) -> None:
        # Full-name participants (as the frontend might send) must be accepted too.
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        conductor.start(['cube_petit_orange', 'cube_petit_pink', 'cube_petit_violet'])
        _wait_until_idle(conductor)
        assert conductor.status()['participants'] == ['orange', 'pink', 'violet']


class TestDefaultLlmCallGuards:

    def test_raises_conductor_error_without_openai_or_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Whichever guard fires first (the 'openai' package missing, or
        # OPENAI_API_KEY unset -- see _default_llm_call), the caller-facing
        # contract is the same: a ConductorError, never a raw ImportError/KeyError.
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command, zenoh.wait_for_completion)
        with pytest.raises(conversation_conductor.ConductorError):
            conductor._default_llm_call('prompt')  # noqa: SLF001 - testing the guard directly


def test_logic_full_robot_name_matches_fleet_bridge_convention() -> None:
    # Sanity check the two modules agree on the wire convention
    # (cube_petit_fleet_bridge.fleet_bridge_logic.robot_key expects this shape).
    assert logic.full_robot_name('orange') == 'cube_petit_orange'


def _turn_json(speaker: str, text: str = 'セリフ') -> str:
    return json.dumps({'speaker': speaker, 'text': text, 'face': 'happy'})


class _CyclingTurnLlm:
    """Stub turn_llm_call that cycles through participants each call."""

    def __init__(self, participants: list) -> None:
        self._participants = participants
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        speaker = self._participants[self.calls % len(self._participants)]
        self.calls += 1
        return _turn_json(speaker)


@pytest.fixture(autouse=True)
def _fast_interactive_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real 45s/60s 1分制御 + 2.5s human window would make tests slow for no
    # benefit -- shrink to something a test can hit deterministically and fast.
    monkeypatch.setattr(logic, 'INTERACTIVE_SOFT_CLOSE_SEC', 1000.0)
    monkeypatch.setattr(logic, 'INTERACTIVE_HARD_CLOSE_SEC', 1000.0)
    monkeypatch.setattr(conversation_conductor, 'TURN_RETRY_BACKOFF_SEC', 0.0)


class TestInteractiveMode:

    def test_runs_turns_until_stopped_and_records_them(self) -> None:
        zenoh = _StubZenoh()
        turn_llm = _CyclingTurnLlm(['orange', 'pink', 'violet'])
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 turn_llm_call=turn_llm)
        conductor.start(['orange', 'pink', 'violet'], mode='interactive', human_window_sec=0.01)
        deadline = time.monotonic() + 2.0
        while turn_llm.calls < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        conductor.stop()
        _wait_until_idle(conductor)

        status = conductor.status()
        assert status['mode'] == 'interactive'
        assert status['error'] == ''
        assert len(status['log']) >= 3
        assert all(entry['speaker'] in ('orange', 'pink', 'violet') for entry in status['log'])

    def test_human_utterance_is_recorded_in_log_and_broadcast(self) -> None:
        zenoh = _StubZenoh()
        turn_llm = _CyclingTurnLlm(['orange', 'pink'])
        broadcast: list = []
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 turn_llm_call=turn_llm,
                                                                 publish_transcript=lambda s, t: broadcast.append(
                                                                     (s, t)))
        # Long human window so the injected utterance is reliably captured within it.
        conductor.start(['orange', 'pink'], mode='interactive', human_window_sec=1.0)
        deadline = time.monotonic() + 2.0
        while turn_llm.calls < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        conductor.submit_human_utterance('ピンクちゃん、こんにちは')
        deadline = time.monotonic() + 2.0
        while not any(e['speaker'] == logic.HUMAN_SPEAKER for e in conductor.status()['log']) \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        conductor.stop()
        _wait_until_idle(conductor)

        status = conductor.status()
        human_entries = [e for e in status['log'] if e['speaker'] == logic.HUMAN_SPEAKER]
        assert len(human_entries) == 1
        assert human_entries[0]['text'] == 'ピンクちゃん、こんにちは'
        assert broadcast == [(logic.HUMAN_SPEAKER, 'ピンクちゃん、こんにちは')]

    def test_submit_human_utterance_ignored_when_not_running(self) -> None:
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command, zenoh.wait_for_completion)
        conductor.submit_human_utterance('誰も聞いていない')
        assert conductor.status()['log'] == []

    def test_submit_human_utterance_ignored_during_script_mode(self) -> None:
        zenoh = _StubZenoh(block_completion=True)
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=lambda p: _script_json(VALID_SCRIPT))
        conductor.start(['orange', 'pink', 'violet'], mode='script')
        try:
            conductor.submit_human_utterance('台本モード中の発話')
            assert not any(e['speaker'] == logic.HUMAN_SPEAKER for e in conductor.status()['log'])
        finally:
            conductor.stop()
            zenoh.release()
            _wait_until_idle(conductor)

    def test_forces_closing_turn_once_hard_close_elapses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(logic, 'INTERACTIVE_HARD_CLOSE_SEC', 0.0)
        zenoh = _StubZenoh()
        turn_llm = _CyclingTurnLlm(['orange', 'pink'])
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 turn_llm_call=turn_llm)
        conductor.start(['orange', 'pink'], mode='interactive', human_window_sec=0.01)
        _wait_until_idle(conductor)

        status = conductor.status()
        assert status['error'] == ''
        # The forced closing turn never calls the (stubbed) LLM.
        assert turn_llm.calls == 0
        assert len(status['log']) == 1
        assert status['log'][0]['text'] in logic.FORCED_CLOSING_TEMPLATES

    def test_persistent_turn_generation_failure_ends_run_with_error(self) -> None:
        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 turn_llm_call=lambda p: 'not valid json')
        conductor.start(['orange', 'pink'], mode='interactive', human_window_sec=0.01)
        _wait_until_idle(conductor, timeout=5.0)

        status = conductor.status()
        assert status['running'] is False
        assert 'consecutive' in status['error'].lower()
        assert zenoh.sent == []


class TestVenueContext:
    """ConversationConductor.start()'s optional `context` flows into the LLM prompt.

    See conversation_conductor_logic.DEFAULT_VENUE_CONTEXT / build_script_prompt /
    build_turn_prompt -- covers ROSConJP 2026 booth context wiring (2026-08-03).
    """

    def test_script_mode_uses_default_context_when_omitted(self) -> None:
        captured = {}

        def llm_call(prompt: str) -> str:
            captured['prompt'] = prompt
            return _script_json(VALID_SCRIPT)

        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=llm_call)
        conductor.start(['orange', 'pink', 'violet'])
        _wait_until_idle(conductor)
        assert logic.DEFAULT_VENUE_CONTEXT in captured['prompt']

    def test_script_mode_uses_custom_context_when_given(self) -> None:
        captured = {}
        custom_context = 'カスタムテスト用会場コンテキスト'

        def llm_call(prompt: str) -> str:
            captured['prompt'] = prompt
            return _script_json(VALID_SCRIPT)

        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=llm_call)
        conductor.start(['orange', 'pink', 'violet'], context=custom_context)
        _wait_until_idle(conductor)
        assert custom_context in captured['prompt']
        assert logic.DEFAULT_VENUE_CONTEXT not in captured['prompt']

    def test_blank_context_falls_back_to_default(self) -> None:
        captured = {}

        def llm_call(prompt: str) -> str:
            captured['prompt'] = prompt
            return _script_json(VALID_SCRIPT)

        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 llm_call=llm_call)
        conductor.start(['orange', 'pink', 'violet'], context='   ')
        _wait_until_idle(conductor)
        assert logic.DEFAULT_VENUE_CONTEXT in captured['prompt']

    def test_interactive_mode_uses_custom_context_in_turn_prompt(self) -> None:
        captured: list = []

        def turn_llm(prompt: str) -> str:
            captured.append(prompt)
            return _turn_json('orange')

        zenoh = _StubZenoh()
        conductor = conversation_conductor.ConversationConductor(zenoh.send_command,
                                                                 zenoh.wait_for_completion,
                                                                 turn_llm_call=turn_llm)
        custom_context = 'テスト用掛け合い会場コンテキスト'
        conductor.start(['orange', 'pink'], mode='interactive', human_window_sec=0.01, context=custom_context)
        deadline = time.monotonic() + 2.0
        while not captured and time.monotonic() < deadline:
            time.sleep(0.01)
        conductor.stop()
        _wait_until_idle(conductor)
        assert captured
        assert 'テスト用掛け合い会場コンテキスト' in captured[0]
