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

    def test_includes_default_venue_context_when_omitted(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_script_prompt(['orange', 'pink'], personalities)
        assert logic.DEFAULT_VENUE_CONTEXT in prompt
        assert 'ROSCon JP 2026' in prompt

    def test_includes_custom_context_instead_of_default(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        custom_context = 'テスト用会場コンテキスト'
        prompt = logic.build_script_prompt(['orange', 'pink'], personalities, context=custom_context)
        assert custom_context in prompt
        assert logic.DEFAULT_VENUE_CONTEXT not in prompt


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

    def test_interactive_mode_total_turns_mirrors_current_turn(self) -> None:
        # 掛け合いモードは台本を事前生成しないので総ターン数が不明 -- 「わかっている
        # 総数」として current_turn をそのまま返す(進捗バーではなく経過秒で見せる想定)。
        state = {
            'running': True,
            'mode': 'interactive',
            'participants': ['orange', 'pink'],
            'script': [],
            'current_turn': 3,
            'log': [],
            'started_at': 10.0,
            'now': 15.0,
        }
        payload = logic.build_status_payload(state)
        assert payload['total_turns'] == 3


class TestParseTurnResponse:

    PARTICIPANTS = ['orange', 'pink', 'violet']

    def test_accepts_valid_json_object_string(self) -> None:
        raw = json.dumps({'speaker': 'pink', 'text': 'こんにちは', 'face': 'happy'})
        turn = logic.parse_turn_response(raw, self.PARTICIPANTS)
        assert turn == {'speaker': 'pink', 'text': 'こんにちは', 'face': 'happy'}

    def test_accepts_pre_parsed_dict(self) -> None:
        turn = logic.parse_turn_response({'speaker': 'orange', 'text': 'やあ'}, self.PARTICIPANTS)
        assert turn['speaker'] == 'orange'
        assert turn['face'] == logic.DEFAULT_FACE

    def test_tolerates_single_element_array_wrapping(self) -> None:
        raw = json.dumps([{'speaker': 'violet', 'text': 'ねー'}])
        turn = logic.parse_turn_response(raw, self.PARTICIPANTS)
        assert turn['speaker'] == 'violet'

    def test_strips_markdown_code_fence(self) -> None:
        raw = '```json\n' + json.dumps({'speaker': 'orange', 'text': 'やあ'}) + '\n```'
        turn = logic.parse_turn_response(raw, self.PARTICIPANTS)
        assert turn['speaker'] == 'orange'

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_turn_response('not json', self.PARTICIPANTS)

    def test_rejects_empty_array(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_turn_response('[]', self.PARTICIPANTS)

    def test_rejects_unknown_speaker(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_turn_response({'speaker': 'yellow', 'text': 'やあ'}, self.PARTICIPANTS)

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(logic.ScriptError):
            logic.parse_turn_response({'speaker': 'orange', 'text': '   '}, self.PARTICIPANTS)

    def test_truncates_overlong_text(self) -> None:
        long_text = 'あ' * (logic.MAX_TURN_TEXT_CHARS + 50)
        turn = logic.parse_turn_response({'speaker': 'orange', 'text': long_text}, self.PARTICIPANTS)
        assert len(turn['text']) == logic.MAX_TURN_TEXT_CHARS


class TestBuildTurnPrompt:

    def test_mentions_every_participant_nickname(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 0.0)
        assert 'オレンジプチ' in prompt
        assert 'ピンクプチ' in prompt

    def test_includes_history_lines(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        history = [{'speaker': 'orange', 'text': 'やっほー'}, {'speaker': logic.HUMAN_SPEAKER, 'text': 'こんにちは'}]
        prompt = logic.build_turn_prompt(['orange', 'pink'], personalities, history, 5.0)
        assert 'やっほー' in prompt
        assert 'こんにちは' in prompt

    def test_no_history_uses_placeholder(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 0.0)
        assert 'まだ発言はありません' in prompt

    def test_closing_hint_adds_wrap_up_instruction(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        without_hint = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 46.0, closing_hint=False)
        with_hint = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 46.0, closing_hint=True)
        assert '締めくく' in with_hint
        assert '締めくく' not in without_hint

    def test_asks_for_single_json_object(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 0.0)
        assert 'JSONオブジェクト1つ' in prompt

    def test_includes_default_venue_context_when_omitted(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        prompt = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 0.0)
        assert logic.DEFAULT_VENUE_CONTEXT in prompt
        assert 'ROSCon JP 2026' in prompt

    def test_includes_custom_context_instead_of_default(self) -> None:
        personalities = logic.load_personalities(['orange', 'pink'], Path('/nonexistent'))
        custom_context = 'テスト用会場コンテキスト'
        prompt = logic.build_turn_prompt(['orange', 'pink'], personalities, [], 0.0, context=custom_context)
        assert custom_context in prompt
        assert logic.DEFAULT_VENUE_CONTEXT not in prompt


class TestNormalizeHumanUtterance:

    def test_strips_whitespace(self) -> None:
        assert logic.normalize_human_utterance('  こんにちは  ') == 'こんにちは'

    def test_empty_or_whitespace_only_becomes_empty_string(self) -> None:
        assert logic.normalize_human_utterance('   ') == ''
        assert logic.normalize_human_utterance('') == ''

    def test_clips_to_max_length(self) -> None:
        long_text = 'あ' * (logic.MAX_HUMAN_TEXT_CHARS + 20)
        assert len(logic.normalize_human_utterance(long_text)) == logic.MAX_HUMAN_TEXT_CHARS

    def test_non_string_input_returns_empty(self) -> None:
        assert logic.normalize_human_utterance(None) == ''  # type: ignore[arg-type]


class TestLastRobotSpeaker:

    def test_finds_most_recent_robot_entry(self) -> None:
        history = [
            {
                'speaker': 'orange',
                'text': 'a'
            },
            {
                'speaker': logic.HUMAN_SPEAKER,
                'text': 'b'
            },
            {
                'speaker': 'pink',
                'text': 'c'
            },
        ]
        assert logic.last_robot_speaker(history, ['orange', 'pink', 'violet']) == 'pink'

    def test_defaults_to_first_participant_when_no_history(self) -> None:
        assert logic.last_robot_speaker([], ['orange', 'pink', 'violet']) == 'orange'

    def test_ignores_human_entries(self) -> None:
        history = [{'speaker': logic.HUMAN_SPEAKER, 'text': 'hi'}]
        assert logic.last_robot_speaker(history, ['orange', 'pink']) == 'orange'


class TestForcedClosingAndTiming:

    def test_build_forced_closing_turn_uses_given_speaker(self) -> None:
        personalities = logic.load_personalities(['orange'], Path('/nonexistent'))
        turn = logic.build_forced_closing_turn('orange', personalities)
        assert turn['speaker'] == 'orange'
        assert turn['text']
        assert turn['face'] in logic.VALID_FACES

    def test_should_inject_closing_hint_threshold(self) -> None:
        assert logic.should_inject_closing_hint(logic.INTERACTIVE_SOFT_CLOSE_SEC) is True
        assert logic.should_inject_closing_hint(logic.INTERACTIVE_SOFT_CLOSE_SEC - 1) is False

    def test_should_force_close_threshold(self) -> None:
        assert logic.should_force_close(logic.INTERACTIVE_HARD_CLOSE_SEC) is True
        assert logic.should_force_close(logic.INTERACTIVE_HARD_CLOSE_SEC - 1) is False
