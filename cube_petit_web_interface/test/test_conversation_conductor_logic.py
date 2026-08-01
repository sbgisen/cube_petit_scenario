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
"""Plain pytest tests for conversation_conductor_logic (no zenoh / no openai required)."""

import json
from pathlib import Path

import pytest

from cube_petit_web_interface import conversation_conductor_logic as logic


class TestRobotNames:

    def test_short_name_strips_prefix(self) -> None:
        assert logic.short_name('cube_petit_pink') == 'pink'
        assert logic.short_name('pink') == 'pink'

    def test_full_robot_name_adds_prefix(self) -> None:
        assert logic.full_robot_name('pink') == 'cube_petit_pink'
        assert logic.full_robot_name('cube_petit_pink') == 'cube_petit_pink'


class TestLoadPersonality:

    def test_loads_existing_yaml_file(self, tmp_path: Path) -> None:
        robot_dir = tmp_path / 'cube_petit_orange'
        robot_dir.mkdir()
        (robot_dir / 'personality.yaml').write_text('nick_name: テストプチ\npersonality: テスト用\n', encoding='utf-8')
        result = logic.load_personality('orange', tmp_path)
        assert result['nick_name'] == 'テストプチ'
        assert result['personality'] == 'テスト用'

    def test_falls_back_to_builtin_default_when_file_missing(self, tmp_path: Path) -> None:
        result = logic.load_personality('pink', tmp_path)
        assert result == logic.DEFAULT_PERSONALITIES['pink']

    def test_falls_back_to_generic_default_for_unknown_robot(self, tmp_path: Path) -> None:
        result = logic.load_personality('unknown_color', tmp_path)
        assert result['nick_name'] == 'プチ'

    def test_falls_back_when_file_is_malformed(self, tmp_path: Path) -> None:
        (tmp_path / 'cube_petit_violet').mkdir()
        (tmp_path / 'cube_petit_violet' / 'personality.yaml').write_text('not: [valid: yaml:', encoding='utf-8')
        result = logic.load_personality('violet', tmp_path)
        assert result == logic.DEFAULT_PERSONALITIES['violet']

    def test_load_personalities_covers_all_participants(self, tmp_path: Path) -> None:
        result = logic.load_personalities(['orange', 'pink', 'violet'], tmp_path)
        assert set(result.keys()) == {'orange', 'pink', 'violet'}


class TestBuildScriptPrompt:

    def test_mentions_every_participant_nickname(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_script_prompt(['orange', 'pink'], personalities)
        assert 'オレンジプチ' in prompt
        assert 'ピンクプチ' in prompt

    def test_mentions_target_duration_and_turn_range(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_script_prompt(['orange', 'pink'], personalities)
        assert str(logic.TARGET_TOTAL_SEC) in prompt
        assert str(logic.TARGET_MIN_TURNS) in prompt
        assert str(logic.TARGET_MAX_TURNS) in prompt


class TestParseScriptResponse:

    PARTICIPANTS = ['orange', 'pink', 'violet']

    def _script(self, n: int = 4) -> list:
        return [{'speaker': self.PARTICIPANTS[i % 3], 'text': f'セリフ{i}', 'face': 'happy'} for i in range(n)]

    def test_accepts_valid_json_string(self) -> None:
        raw = json.dumps(self._script())
        turns = logic.parse_script_response(raw, self.PARTICIPANTS)
        assert len(turns) == 4
        assert turns[0]['speaker'] == 'orange'
        assert turns[0]['face'] == 'happy'

    def test_accepts_pre_parsed_list(self) -> None:
        turns = logic.parse_script_response(self._script(3), self.PARTICIPANTS)
        assert len(turns) == 3

    def test_strips_markdown_code_fence(self) -> None:
        raw = '```json\n' + json.dumps(self._script()) + '\n```'
        turns = logic.parse_script_response(raw, self.PARTICIPANTS)
        assert len(turns) == 4

    def test_defaults_missing_or_invalid_face(self) -> None:
        script = [{'speaker': 'orange', 'text': 'やあ'}, {'speaker': 'pink', 'text': 'こんにちは', 'face': 'nonsense'}]
        turns = logic.parse_script_response(script, self.PARTICIPANTS)
        assert turns[0]['face'] == logic.DEFAULT_FACE
        assert turns[1]['face'] == logic.DEFAULT_FACE

    def test_rejects_invalid_json_string(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_script_response('not json', self.PARTICIPANTS)

    def test_rejects_non_list(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_script_response(json.dumps({'not': 'a list'}), self.PARTICIPANTS)

    def test_rejects_too_few_turns(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_script_response([{'speaker': 'orange', 'text': 'やあ'}], self.PARTICIPANTS)

    def test_rejects_too_many_turns(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_script_response(self._script(logic.MAX_SCRIPT_TURNS + 1), self.PARTICIPANTS)

    def test_rejects_unknown_speaker(self) -> None:
        script = [{'speaker': 'yellow', 'text': 'やあ'}, {'speaker': 'pink', 'text': 'こんにちは'}]
        with pytest.raises(logic.ScriptError):
            logic.parse_script_response(script, self.PARTICIPANTS)

    def test_rejects_empty_text(self) -> None:
        script = [{'speaker': 'orange', 'text': '   '}, {'speaker': 'pink', 'text': 'こんにちは'}]
        with pytest.raises(logic.ScriptError):
            logic.parse_script_response(script, self.PARTICIPANTS)

    def test_truncates_overlong_text(self) -> None:
        long_text = 'あ' * (logic.MAX_TURN_TEXT_CHARS + 50)
        script = [{'speaker': 'orange', 'text': long_text}, {'speaker': 'pink', 'text': 'こんにちは'}]
        turns = logic.parse_script_response(script, self.PARTICIPANTS)
        assert len(turns[0]['text']) == logic.MAX_TURN_TEXT_CHARS


class TestEstimateSpeechDuration:

    def test_longer_text_takes_longer(self) -> None:
        assert logic.estimate_speech_duration_sec('あ' * 50) > logic.estimate_speech_duration_sec('あ' * 5)

    def test_clamped_to_minimum(self) -> None:
        assert logic.estimate_speech_duration_sec('') >= logic.MIN_TURN_SEC

    def test_clamped_to_maximum(self) -> None:
        assert logic.estimate_speech_duration_sec('あ' * 10000) == logic.MAX_TURN_SEC

    def test_completion_timeout_adds_buffer(self) -> None:
        text = 'ちょうどいい長さのセリフです'
        assert logic.completion_timeout_sec(text) == pytest.approx(
            logic.estimate_speech_duration_sec(text) + logic.COMPLETION_TIMEOUT_BUFFER_SEC)


class TestBuildStatusPayload:

    def test_idle_state(self) -> None:
        payload = logic.build_status_payload({})
        assert payload['running'] is False
        assert payload['total_turns'] == 0
        assert payload['log'] == []

    def test_running_state_computes_elapsed_from_now(self) -> None:
        state = {
            'running': True,
            'mode': 'script',
            'participants': ['orange', 'pink'],
            'script': [{
                'speaker': 'orange',
                'text': 'a',
                'face': 'normal'
            }],
            'current_turn': 0,
            'log': [],
            'started_at': 10.0,
            'now': 12.5,
        }
        payload = logic.build_status_payload(state)
        assert payload['running'] is True
        assert payload['elapsed_sec'] == pytest.approx(2.5)
        assert payload['total_turns'] == 1

    def test_finished_state_uses_stored_elapsed(self) -> None:
        state = {'running': False, 'elapsed_sec': 42.0, 'started_at': 10.0, 'now': 999.0}
        payload = logic.build_status_payload(state)
        assert payload['elapsed_sec'] == 42.0
