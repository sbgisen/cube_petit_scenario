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


def build_script_prompt(participants: typing.Sequence[str], personalities: typing.Dict[str, dict]) -> str:
    """Build the one-shot prompt asking the LLM for a full ~1 minute script.

    Args:
        participants: Robot short names taking part, e.g. ``['orange',
            'pink', 'violet']``.
        personalities: ``{short_name: personality_dict}`` as returned by
            load_personalities().

    Returns:
        The full prompt text (system + task instructions in one string --
        conversation_conductor.py sends this as a single user/system message,
        no multi-turn chat needed for one-shot generation).
    """
    lines = [
        'あなたは複数台のコミュニケーションロボット「キューブプチ」の掛け合い台本作家です。',
        '以下のロボットたちが、来場者の前で自然に盛り上がる約60秒の会話劇を演じます。',
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
    turns: typing.List[dict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ScriptError(f'Turn {i} is not a JSON object: {item!r}')
        speaker = item.get('speaker')
        if not isinstance(speaker, str) or speaker not in participant_set:
            raise ScriptError(f'Turn {i} has speaker {speaker!r}, expected one of {sorted(participant_set)}')
        text = item.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ScriptError(f'Turn {i} is missing non-empty text: {item!r}')
        text = text.strip()[:MAX_TURN_TEXT_CHARS]
        face = item.get('face')
        if not isinstance(face, str) or face not in VALID_FACES:
            face = DEFAULT_FACE
        turns.append({'speaker': speaker, 'text': text, 'face': face})
    return turns


def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing ```json ... ``` fence if the LLM added one anyway."""
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = re.sub(r'^```[a-zA-Z]*\n?', '', stripped)
        stripped = re.sub(r'```\s*$', '', stripped)
    return stripped.strip()


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
    now = state.get('now', time.monotonic())
    elapsed = round(now - started_at, 1) if running and started_at is not None else state.get('elapsed_sec', 0.0)
    return {
        'running': running,
        'mode': state.get('mode', 'script'),
        'participants': list(state.get('participants', [])),
        'current_turn': state.get('current_turn', 0),
        'total_turns': len(state.get('script', []) or []),
        'log': list(state.get('log', [])),
        'elapsed_sec': elapsed,
        'error': state.get('error', ''),
    }
