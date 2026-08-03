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
"""Pure (I/O-light, LLM/zenoh-free) helpers for the conversation "conductor" demo.

ROSConJP 2026 booth demo: orange/pink/violet take turns speaking a ~1 minute
LLM-generated script ("script mode", see plans/conversation_demo_plan.md in
the orange_petit_claude repo for the full design). This module owns:

  * short/full robot name conversion (matches cube_petit_fleet_bridge's
    ``robots/<robot_name>/...`` convention, e.g. ``cube_petit_pink``)
  * personality loading (``~/.cube_petit/<robot>/personality.yaml``, same
    file the setup wizard writes -- see cube_petit_orange's own copy) with a
    built-in fallback for robots whose file isn't present on this machine
  * the LLM prompt text for one-shot script generation
  * validating/normalizing the LLM's JSON script response
  * estimating a turn's spoken duration (fallback timing when
    ``command_is_completed`` doesn't arrive in time)
  * building the JSON-serializable ``GET /fleet/conversation/status`` payload

Kept free of ``openai``/``zenoh``/``rclpy`` imports (only ``yaml`` and the
stdlib) so it can be unit tested with plain pytest, mirroring
fleet_zenoh_logic.py / fleet_bridge_logic.py's split between "pure logic" and
"I/O glue" modules in this codebase.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import time
import typing

import yaml

#: Robots this demo is scoped to (2026-08-02 ありさん決定: デモ機体3台).
#: Not enforced as a hard allowlist here (a future 4th robot should "just
#: work"), only used as the default personality-fallback key set.
DEFAULT_PARTICIPANTS: typing.Tuple[str, ...] = ('orange', 'pink', 'violet')

#: Default venue context injected into both script-mode and interactive-mode
#: prompts (ROSConJP 2026 booth demo, 2026-08-03 ありさん依頼). Callers can
#: override this per run via the optional `context` argument to
#: build_script_prompt()/build_turn_prompt() (wired from
#: `/fleet/conversation/start`'s optional `context` field, see
#: routers/conversation_router.py), e.g. to swap topics live at the booth.
# NOTE: deliberately written with katakana readings only (ロスコンジェーピー etc.,
# no Latin spellings like "ROSCon JP") -- the LLM mirrors whatever spelling the
# context uses, and Latin text comes out garbled through jtalk TTS.
DEFAULT_VENUE_CONTEXT: str = ('ここはロスコンジェーピー2026(2026年8月4日・5日、'
                              '茨城県つくば市の「つくばカピオ」)の会場です。'
                              'ロス(ロボットの共通ソフト基盤)のコミュニティの年次イベントで、'
                              '来場者はロボット開発者や研究者、学生が中心です。'
                              'ブースの前で会話を聞いている人にも届くように、ロスやロボット開発、つくば、'
                              'このイベント自体の話題を好んで話してください。\n'
                              'わたしたちキューブプチは22センチ角・約6.3キロの立方体型パーソナルロボットです。'
                              'ロスツー ジャジーで動いていて、ライダーとデプスカメラで自律ナビゲーションをし、'
                              'エルエルエムでおしゃべりをして、ディスプレイの顔で表情を出します。'
                              '研究・開発のプラットフォームとして使われていて、'
                              '今日はオレンジプチ・ピンクプチ・バイオレットプチの3台で来ています。'
                              'バイオレットプチは今日は移動せずおしゃべり担当、'
                              'オレンジプチとピンクプチは追いかけっこが得意です。\n'
                              '技術的な話も交えつつ、かわいらしく短い言葉で話してください。誇張したり、'
                              '実際にはできないことをできると言ったりしないでください。\n'
                              'セリフは音声合成でそのまま読み上げられます。英字の固有名詞・略語は絶対に'
                              '英字のまま書かず、必ずカタカナの読みで書いてください'
                              '(ロスコンジェーピー、ロスツー ジャジー、ライダー、エルエルエムのように)。')

#: Facial expressions cube_petit_facial_animation actually supports (see
#: frontend/src/components/ExpressionGrid.tsx's EXPRESSIONS list in this
#: package). The zenoh `speak` command has no `face` argument yet (checked
#: cube_petit_fleet_bridge's SUPPORTED_METHODS in the cube_petit_ros repo --
#: only `text` is accepted), so `face` is validated/logged/shown in the UI
#: today but not yet sent to the robot. See conversation_conductor.py's
#: module docstring TODO.
VALID_FACES: typing.FrozenSet[str] = frozenset({
    'normal', 'happy', 'excited', 'love', 'wink', 'shy', 'surprised', 'curious', 'thinking', 'puzzled', 'dizzy',
    'sleepy', 'sad', 'angry'
})
DEFAULT_FACE = 'normal'

#: Fallback per-robot personality, used when
#: ``~/.cube_petit/cube_petit_<name>/personality.yaml`` isn't present on this
#: machine (only cube_petit_orange's own file exists on the orange host --
#: pink/violet's files live on their own machines). TODO(personality-sync):
#: pull pink/violet's real personality.yaml (e.g. via the fleet or a shared
#: config sync) instead of hardcoding placeholders here.
DEFAULT_PERSONALITIES: typing.Dict[str, dict] = {
    'orange': {
        'color': 'オレンジ',
        'personality': '元気いっぱいで前向き',
        'nick_name': 'オレンジプチ',
        'first_person_pronoun': 'ぼく',
        'favorite': 'みんなで遊ぶこと',
        'friends': ['ピンク色のピンクプチ', 'バイオレット色のバイオレットプチ'],
    },
    'pink': {
        'color': 'ピンク',
        'personality': 'おっとりしていてマイペース',
        'nick_name': 'ピンクプチ',
        'first_person_pronoun': 'わたし',
        'favorite': 'ひなたぼっこ',
        'friends': ['オレンジ色のオレンジプチ', 'バイオレット色のバイオレットプチ'],
    },
    'violet': {
        'color': 'バイオレット',
        'personality': 'クールで落ち着いている',
        'nick_name': 'バイオレットプチ',
        'first_person_pronoun': '私',
        'favorite': '静かな時間',
        'friends': ['オレンジ色のオレンジプチ', 'ピンク色のピンクプチ'],
    },
}
_GENERIC_FALLBACK_PERSONALITY: dict = {
    'color': '',
    'personality': '元気で人懐っこい',
    'nick_name': 'プチ',
    'first_person_pronoun': 'ぼく',
    'favorite': 'おしゃべり',
    'friends': [],
}

#: Speech duration estimate: chars/sec for jtalk-generated Japanese speech at
#: the fleet_bridge default speed (100). Rough booth-tested figure, not a
#: precise TTS-duration model -- this is only ever a *fallback* for when
#: `command_is_completed` doesn't arrive within the estimate-derived timeout.
CHARS_PER_SEC = 6.0
#: Fixed per-utterance overhead (TTS synthesis + a short breath before/after).
FIXED_OVERHEAD_SEC = 1.5
MIN_TURN_SEC = 2.0
MAX_TURN_SEC = 20.0

#: Extra buffer added on top of the estimate when using it as the
#: `wait_for_completion` timeout ceiling (gives `command_is_completed` a
#: realistic chance to arrive before falling back).
COMPLETION_TIMEOUT_BUFFER_SEC = 3.0

#: Target script shape handed to the LLM (a *target*, not a hard limit --
#: validate_script() only rejects scripts that are empty or malformed).
TARGET_TOTAL_SEC = 60
TARGET_MIN_TURNS = 8
TARGET_MAX_TURNS = 12

#: Hard bounds validate_script() enforces on top of the LLM's own judgement,
#: so a pathological response (1 turn, or 200 turns) can't wedge the demo.
MIN_SCRIPT_TURNS = 2
MAX_SCRIPT_TURNS = 24
MAX_TURN_TEXT_CHARS = 200

# =================================================
# 掛け合いモード (interactive): 1ターン1回LLM呼び出し + 人間発話の織り込み
# =================================================

#: 会話ログの中で人間の発話を表す speaker 値 (personalities / VALID robot names
#: とは別の予約語)。conversation_conductor.py の submit_human_utterance() が
#: この値でログに積む。
HUMAN_SPEAKER = 'human'

#: 1分制御(plans/conversation_demo_plan.md「1分制御」節): 45秒でプロンプトに
#: 締め指示を注入し、60秒でLLMを介さず締めセリフを強制する。
INTERACTIVE_SOFT_CLOSE_SEC = 45.0
INTERACTIVE_HARD_CLOSE_SEC = 60.0

#: 各ロボット発話後に人間の発話を待つ「間」のデフォルト長さ(2〜3秒、設定可能 --
#: ConversationConductor.start() の human_window_sec で上書きできる)。
DEFAULT_HUMAN_WINDOW_SEC = 2.5

#: 人間発話(ASRテキスト)の長さ上限。ロボットのセリフよりやや長めに許容する。
MAX_HUMAN_TEXT_CHARS = 300

#: プロンプトに含める直近の会話履歴の件数上限(トークン節約・低レイテンシ優先)。
HISTORY_PROMPT_MAX_ENTRIES = 12


class ScriptError(ValueError):
    """The LLM's script response was missing, malformed, or failed validation."""


# =================================================
# Robot name conversion
# =================================================


def short_name(robot_name: str) -> str:
    """``cube_petit_pink`` -> ``pink`` (pass through names without the prefix)."""
    return re.sub(r'^cube_petit_', '', robot_name)


def full_robot_name(short: str) -> str:
    """``pink`` -> ``cube_petit_pink`` (pass through names that already have the prefix)."""
    return short if short.startswith('cube_petit_') else f'cube_petit_{short}'


# =================================================
# Personality loading
# =================================================


def personality_file_path(short: str, base_dir: Path) -> Path:
    """Path the setup wizard writes personality.yaml to for a given robot.

    Args:
        short: Robot short name, e.g. ``'pink'``.
        base_dir: Usually ``Path.home() / '.cube_petit'``.
    """
    return base_dir / full_robot_name(short) / 'personality.yaml'


def load_personality(short: str, base_dir: Path) -> dict:
    """Load one robot's personality.yaml, falling back to built-in data.

    Args:
        short: Robot short name, e.g. ``'pink'``.
        base_dir: Usually ``Path.home() / '.cube_petit'`` (see
            personality_file_path).

    Returns:
        The parsed YAML dict, or DEFAULT_PERSONALITIES[short] (or a generic
        placeholder for unknown robots) if the file is absent/unreadable.
    """
    path = personality_file_path(short, base_dir)
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and data:
                return data
        except (yaml.YAMLError, OSError):
            pass
    return dict(DEFAULT_PERSONALITIES.get(short, _GENERIC_FALLBACK_PERSONALITY))


def load_personalities(participants: typing.Sequence[str], base_dir: Path) -> typing.Dict[str, dict]:
    """load_personality() for every participant, keyed by short name."""
    return {p: load_personality(p, base_dir) for p in participants}


# =================================================
# LLM prompt building
# =================================================


def build_script_prompt(participants: typing.Sequence[str],
                        personalities: typing.Dict[str, dict],
                        context: str = DEFAULT_VENUE_CONTEXT) -> str:
    """Build the one-shot prompt asking the LLM for a full ~1 minute script.

    Args:
        participants: Robot short names taking part, e.g. ``['orange',
            'pink', 'violet']``.
        personalities: ``{short_name: personality_dict}`` as returned by
            load_personalities().
        context: Venue/booth context to ground the conversation in (defaults
            to DEFAULT_VENUE_CONTEXT, the ROSConJP 2026 booth description).
            Overridable per run -- see DEFAULT_VENUE_CONTEXT's docstring.

    Returns:
        The full prompt text (system + task instructions in one string --
        conversation_conductor.py sends this as a single user/system message,
        no multi-turn chat needed for one-shot generation).
    """
    lines = [
        'あなたは複数台のコミュニケーションロボット「キューブプチ」の掛け合い台本作家です。',
        '以下のロボットたちが、来場者の前で自然に盛り上がる約60秒の会話劇を演じます。',
        '',
        '会場の状況:',
        context,
        '',
        '各ロボットの性格設定:',
    ]
    for name in participants:
        p = personalities.get(name, _GENERIC_FALLBACK_PERSONALITY)
        friends = '、'.join(p.get('friends', []) or []) or '(記載なし)'
        lines.append(f'- {name}({p.get("nick_name", name)}): 性格={p.get("personality", "")} / '
                     f'一人称={p.get("first_person_pronoun", "")} / 好きなもの={p.get("favorite", "")} / '
                     f'友達={friends}')
    lines += [
        '',
        f'{TARGET_MIN_TURNS}〜{TARGET_MAX_TURNS}ターンのセリフで構成し、'
        f'合計で読み上げて約{TARGET_TOTAL_SEC}秒(1分)に収まる分量にしてください。',
        '各セリフは1〜2文の短い日本語にし、ロボット同士がお互いのニックネームで呼び合ってください。',
        '最初は挨拶や近況の掛け合いから始め、最後は来場者に向けた明るい締めの一言で終えてください。',
        '出力は次のJSON配列だけを返してください(説明文やコードブロック記号は不要):',
        '[{"speaker": "<参加ロボットのnameのいずれか>", "text": "<セリフ>", '
        f'"face": "<{"|".join(sorted(VALID_FACES))}のいずれか>"}}, ...]',
    ]
    return '\n'.join(lines)


# =================================================
# Script validation
# =================================================


def parse_script_response(raw: typing.Union[str, list], participants: typing.Sequence[str]) -> typing.List[dict]:
    """Parse and validate the LLM's script response into a clean turn list.

    Args:
        raw: Either the raw JSON text the LLM returned, or an already
            ``json.loads``-ed list (for tests / non-string LLM clients).
        participants: Robot short names allowed as `speaker`.

    Returns:
        ``[{"speaker": str, "text": str, "face": str}, ...]``, `face`
        normalized to one of VALID_FACES (DEFAULT_FACE if missing/invalid).

    Raises:
        ScriptError: If `raw` isn't valid JSON, isn't a list, is out of the
            [MIN_SCRIPT_TURNS, MAX_SCRIPT_TURNS] bounds, or any turn is
            missing a non-empty `text` / has a `speaker` not in
            `participants`.
    """
    if isinstance(raw, str):
        text = _strip_code_fence(raw)
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as error:
            raise ScriptError(f'LLM response is not valid JSON: {error}') from None
    else:
        data = raw

    if not isinstance(data, list):
        raise ScriptError(f'Expected a JSON array of turns, got {type(data).__name__}')
    if not (MIN_SCRIPT_TURNS <= len(data) <= MAX_SCRIPT_TURNS):
        raise ScriptError(f'Script has {len(data)} turns, expected {MIN_SCRIPT_TURNS}-{MAX_SCRIPT_TURNS}')

    participant_set = set(participants)
    return [_normalize_turn_item(item, i, participant_set) for i, item in enumerate(data)]


def _normalize_turn_item(item: object, index: int, participant_set: typing.Set[str]) -> dict:
    """Validate/normalize one ``{"speaker", "text", "face"}`` turn object.

    Shared by parse_script_response() (a whole array of these) and
    parse_turn_response() (a single one, 掛け合いモード's per-turn LLM call).

    Raises:
        ScriptError: Same conditions as parse_script_response()'s per-turn checks.
    """
    if not isinstance(item, dict):
        raise ScriptError(f'Turn {index} is not a JSON object: {item!r}')
    speaker = item.get('speaker')
    if not isinstance(speaker, str) or speaker not in participant_set:
        raise ScriptError(f'Turn {index} has speaker {speaker!r}, expected one of {sorted(participant_set)}')
    text = item.get('text')
    if not isinstance(text, str) or not text.strip():
        raise ScriptError(f'Turn {index} is missing non-empty text: {item!r}')
    text = text.strip()[:MAX_TURN_TEXT_CHARS]
    face = item.get('face')
    if not isinstance(face, str) or face not in VALID_FACES:
        face = DEFAULT_FACE
    return {'speaker': speaker, 'text': text, 'face': face}


def parse_turn_response(raw: typing.Union[str, dict, list], participants: typing.Sequence[str]) -> dict:
    """Parse and validate a single turn from 掛け合いモード's per-turn LLM call.

    Mirrors parse_script_response() but expects one JSON object (not an
    array). Tolerates the LLM wrapping the object in a 1-element array
    anyway (some models do this even when asked for a bare object).

    Args:
        raw: Raw JSON text, or an already-parsed dict/list.
        participants: Robot short names allowed as `speaker`.

    Returns:
        ``{"speaker": str, "text": str, "face": str}``.

    Raises:
        ScriptError: If `raw` isn't valid JSON/an object, or the turn fails
            the same checks as parse_script_response()'s per-item validation.
    """
    if isinstance(raw, str):
        text = _strip_code_fence(raw)
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as error:
            raise ScriptError(f'LLM response is not valid JSON: {error}') from None
    else:
        data = raw

    if isinstance(data, list):
        if not data:
            raise ScriptError('Expected a JSON object, got an empty array')
        data = data[0]

    return _normalize_turn_item(data, 0, set(participants))


def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing ```json ... ``` fence if the LLM added one anyway."""
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = re.sub(r'^```[a-zA-Z]*\n?', '', stripped)
        stripped = re.sub(r'```\s*$', '', stripped)
    return stripped.strip()


# =================================================
# 掛け合いモード: 単ターンのプロンプト構築・人間発話の正規化・締め処理
# =================================================


def _speaker_label(short: str, personalities: typing.Dict[str, dict]) -> str:
    """Human-readable label for a history line's speaker (nickname, or 来場者 for humans)."""
    if short == HUMAN_SPEAKER:
        return '来場者(人間)'
    p = personalities.get(short, _GENERIC_FALLBACK_PERSONALITY)
    return p.get('nick_name', short)


def format_history_for_prompt(history: typing.Sequence[dict],
                              personalities: typing.Dict[str, dict],
                              max_entries: int = HISTORY_PROMPT_MAX_ENTRIES) -> str:
    """Render recent ``{"speaker", "text", ...}`` log entries as ``label: text`` lines.

    Args:
        history: Conductor log entries so far (only `speaker`/`text` are
            read; extra keys like `face`/`success` are ignored).
        personalities: ``{short_name: personality_dict}`` for nickname lookup.
        max_entries: Only the most recent this-many entries are included
            (keeps the per-turn prompt small -- low latency is the point of
            掛け合いモード's one-call-per-turn design).

    Returns:
        Newline-joined ``"label: text"`` lines, or a placeholder if `history`
        has no entries with non-empty text yet.
    """
    lines = []
    for entry in list(history)[-max_entries:]:
        text = (entry.get('text') or '').strip()
        if not text:
            continue
        label = _speaker_label(entry.get('speaker', ''), personalities)
        lines.append(f'{label}: {text}')
    return '\n'.join(lines) if lines else '(まだ発言はありません)'


def build_turn_prompt(participants: typing.Sequence[str],
                      personalities: typing.Dict[str, dict],
                      history: typing.Sequence[dict],
                      elapsed_sec: float,
                      closing_hint: bool = False,
                      context: str = DEFAULT_VENUE_CONTEXT) -> str:
    """Build the one-shot prompt asking the LLM for just the *next* turn.

    Unlike build_script_prompt() (whole ~1 minute script in one call),
    掛け合いモード calls the LLM once per turn so a human utterance captured
    in `history` since the last turn can steer who speaks next (destination/
    宛先 inference is entirely the LLM's job -- see the addressing instruction
    below -- this module has no name-matching logic of its own).

    Args:
        participants: Robot short names taking part.
        personalities: ``{short_name: personality_dict}``.
        history: Conductor log so far (``{"speaker", "text", ...}``), human
            turns included with `speaker` == HUMAN_SPEAKER.
        elapsed_sec: Seconds since the conversation started (only used to
            decide whether to mention `closing_hint` isn't already covering
            it -- kept as an explicit arg so callers/tests don't need to
            reconstruct timing).
        closing_hint: If True, ask the LLM to start wrapping the
            conversation up (see INTERACTIVE_SOFT_CLOSE_SEC).
        context: Venue/booth context to ground the conversation in (defaults
            to DEFAULT_VENUE_CONTEXT, the ROSConJP 2026 booth description).
            Overridable per run -- see DEFAULT_VENUE_CONTEXT's docstring.

    Returns:
        The full prompt text.
    """
    lines = [
        'あなたは複数台のコミュニケーションロボット「キューブプチ」の会話進行役です。',
        '来場者(人間)とロボットたちが掛け合う対話デモの、次の1ターン分だけを考えます。',
        '',
        '会場の状況:',
        context,
        '',
        '各ロボットの性格設定:',
    ]
    for name in participants:
        p = personalities.get(name, _GENERIC_FALLBACK_PERSONALITY)
        friends = '、'.join(p.get('friends', []) or []) or '(記載なし)'
        lines.append(f'- {name}({p.get("nick_name", name)}): 性格={p.get("personality", "")} / '
                     f'一人称={p.get("first_person_pronoun", "")} / 好きなもの={p.get("favorite", "")} / '
                     f'友達={friends}')
    lines += [
        '',
        'これまでの会話:',
        format_history_for_prompt(history, personalities),
        '',
        '次に話すロボットを1体選び、そのセリフを1〜2文の短い日本語で考えてください。',
        '直前の発言(特に来場者の発言)で名前を呼びかけられていたら、呼ばれたロボットを次の話者にしてください。'
        '呼びかけがなければ、まだあまり話していないロボットや自然な会話の流れを優先してください。',
        '来場者に一方的に説明するのではなく、ロボット同士・来場者との掛け合いとして返してください。',
    ]
    if closing_hint:
        lines.append('そろそろ会話を締めくくる時間です。来場者に向けた明るい一言を交えて、'
                     '自然に締めに向かうセリフにしてください。')
    lines += [
        '出力は次のJSONオブジェクト1つだけを返してください(説明文やコードブロック記号は不要):',
        '{"speaker": "<参加ロボットのnameのいずれか>", "text": "<セリフ>", '
        f'"face": "<{"|".join(sorted(VALID_FACES))}のいずれか>"}}',
    ]
    return '\n'.join(lines)


def normalize_human_utterance(raw_text: str) -> str:
    """Trim/clip a raw ASR transcript for use as a history entry / prompt input.

    Returns:
        The stripped text (empty string if `raw_text` is empty/whitespace-only),
        clipped to MAX_HUMAN_TEXT_CHARS.
    """
    if not isinstance(raw_text, str):
        return ''
    return raw_text.strip()[:MAX_HUMAN_TEXT_CHARS]


def last_robot_speaker(history: typing.Sequence[dict], participants: typing.Sequence[str]) -> str:
    """Return the most recent non-human speaker in `history`, or participants[0] if none yet."""
    for entry in reversed(list(history)):
        speaker = entry.get('speaker')
        if speaker and speaker != HUMAN_SPEAKER and speaker in participants:
            return speaker
    return participants[0]


#: Canned (LLM-free) closing lines used once INTERACTIVE_HARD_CLOSE_SEC is
#: reached, so the demo has a guaranteed, low-latency way to end even if the
#: LLM is slow/flaky right when the clock runs out (see
#: build_forced_closing_turn() -- 1分制御の「60秒で締めのセリフを強制」).
FORCED_CLOSING_TEMPLATES: typing.Tuple[str, ...] = (
    'そろそろ時間だね、みんな聞いてくれてありがとう!またね!',
    '今日はここまで!また遊びに来てね、ばいばーい!',
)


def build_forced_closing_turn(speaker: str, personalities: typing.Dict[str, dict]) -> dict:
    """Build a deterministic (no LLM call) closing turn for `speaker`.

    Args:
        speaker: Short robot name to say the closing line (usually the last
            robot to have spoken, see last_robot_speaker()).
        personalities: ``{short_name: personality_dict}`` (unused today, kept
            for symmetry/future personalization -- the line is generic on
            purpose so it never fails validation).

    Returns:
        A single ``{"speaker", "text", "face"}`` turn.
    """
    text = FORCED_CLOSING_TEMPLATES[0]
    return {'speaker': speaker, 'text': text, 'face': 'happy'}


def should_inject_closing_hint(elapsed_sec: float) -> bool:
    """Return True once elapsed_sec has crossed INTERACTIVE_SOFT_CLOSE_SEC (45s)."""
    return elapsed_sec >= INTERACTIVE_SOFT_CLOSE_SEC


def should_force_close(elapsed_sec: float) -> bool:
    """Return True once elapsed_sec has crossed INTERACTIVE_HARD_CLOSE_SEC (60s)."""
    return elapsed_sec >= INTERACTIVE_HARD_CLOSE_SEC


# =================================================
# Speech duration estimate (fallback timing)
# =================================================


def estimate_speech_duration_sec(text: str) -> float:
    """Estimate how long `text` takes to speak, for the completion-wait timeout ceiling.

    Only ever used as a *fallback*: the conductor waits for the real
    ``command_is_completed`` notice first, up to this estimate (+ buffer) as
    the timeout, so a genuinely long/short utterance doesn't stall the demo
    if the notice is lost.
    """
    raw = len(text) / CHARS_PER_SEC + FIXED_OVERHEAD_SEC
    return max(MIN_TURN_SEC, min(MAX_TURN_SEC, raw))


def completion_timeout_sec(text: str) -> float:
    """Return the timeout to pass to wait_for_completion() for one turn's speak command."""
    return estimate_speech_duration_sec(text) + COMPLETION_TIMEOUT_BUFFER_SEC


# =================================================
# Status payload (GET /fleet/conversation/status)
# =================================================


def build_status_payload(state: dict) -> dict:
    """Build the JSON-serializable status payload from the conductor's internal state dict.

    Args:
        state: The conductor's internal state (see conversation_conductor.py's
            ConversationConductor._state for the exact shape). Kept as a
            plain dict (not a dataclass) so the impure module can mutate it
            freely under its lock; this function just reshapes/copies it for
            the API response.

    Returns:
        ``{running, mode, participants, current_turn, total_turns, log,
        elapsed_sec, error}``.
    """
    started_at = state.get('started_at')
    running = bool(state.get('running'))
    mode = state.get('mode', 'script')
    now = state.get('now', time.monotonic())
    elapsed = round(now - started_at, 1) if running and started_at is not None else state.get('elapsed_sec', 0.0)
    # 台本モードは開始時点で総ターン数が確定している(script配列の長さ)。掛け合い
    # モードは1ターン1回LLM呼び出しで総数が事前に決まらないため、現在ターン数を
    # そのまま「わかっている総数」として返す(フロントは進捗バーではなく経過秒/
    # 締切秒で残り時間を見せる想定)。
    if mode == 'script':
        total_turns = len(state.get('script', []) or [])
    else:
        total_turns = state.get('current_turn', 0)
    return {
        'running': running,
        'mode': mode,
        'participants': list(state.get('participants', [])),
        'current_turn': state.get('current_turn', 0),
        'total_turns': total_turns,
        'log': list(state.get('log', [])),
        'elapsed_sec': elapsed,
        'error': state.get('error', ''),
    }
