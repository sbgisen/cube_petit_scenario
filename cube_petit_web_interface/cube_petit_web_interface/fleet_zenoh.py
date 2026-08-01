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
"""Tier 2 "multi-robot picker": a fleet-wide status aggregator over plain zenoh.

Every CubePetit robot's `cube_petit_fleet_bridge.zenoh_connector` node (a
separate ROS2 package/repo, `cube_petit_ros`) publishes its own state over a
plain `eclipse-zenoh` session (independent of ROS_DOMAIN_ID / rmw_zenoh_cpp).
See `fleet_zenoh_logic.py`'s module docstring for the exact wire format this
watcher reads/writes.

This module opens its own plain zenoh client session -- symmetric with
zenoh_connector.py and cube_petit_shared_controller's hub/receiver nodes --
and subscribes to `robots/*/{pose,battery,map_name}`. Every
cube_petit_web_interface instance runs one of these, so opening any robot's
web interface shows the same fleet-wide picture: there is no single "hub"
instance (symmetric peer design).

`send_command()` additionally lets the dashboard *drive* another robot in the
fleet (move_to_pose, e.g. "everyone gather here" / chase mode), by writing to
`robots/<robot>/command` -- the same key `zenoh_connector.py` subscribes to.
This was deliberately read-only until the ROSConJP 2026 demo (chase-and-greet)
needed operator-triggered move_to_pose from the dashboard instead of having
each robot decide autonomously (see plans/cube_petit_fleet_adapter_plan.md).

Kept independent of the cube_petit_fleet_bridge package (different repo:
cube_petit_ros vs cube_petit_scenario) -- fleet_zenoh_logic.py re-implements
the small bits of wire-format knowledge it needs rather than taking a
cross-repo dependency.

Requires the `eclipse-zenoh` pip package (not resolvable via rosdep -- see
requirements.txt next to this file). Degrades gracefully when it is missing:
`FleetZenohWatcher.__init__` raises `RuntimeError`, which core.py catches so
the rest of the API server (Tier 1) keeps working without it.
"""

from __future__ import annotations

import functools
import json
import math
import threading
import time
import typing
import uuid

try:
    # uvicorn cube_petit_web_interface.api_server:app で起動した場合
    from cube_petit_web_interface import fleet_zenoh_logic as logic
except ImportError:
    # python api_server.py で直接実行した場合
    import fleet_zenoh_logic as logic

try:
    import zenoh
except ImportError as _zenoh_import_error:  # pragma: no cover - exercised only without the pip dep
    zenoh = None
    _ZENOH_IMPORT_ERROR = _zenoh_import_error
else:
    _ZENOH_IMPORT_ERROR = None

#: Matches cube_petit_fleet_bridge/launch/zenoh_connector.launch.py's
#: `zenoh_router_endpoint` default (router assumed to run on "orange" for now;
#: see sbgisen/cube_petit_setup#43 for the "make this selectable" follow-up).
DEFAULT_ZENOH_ENDPOINT = 'tcp/cube-petit-orange.local:7447'
DEFAULT_ZENOH_MODE = 'client'

#: 追いかけっこ(chase)ループの送信間隔。ブラウザのタブ切替/クローズに影響されない
#: よう、このFastAPIサーバー(常駐プロセス)側でループを回す。
#: Chase-loop send interval. Runs inside this always-on FastAPI server process
#: (not the browser) so it isn't affected by the operator switching tabs or
#: closing the dashboard.
CHASE_PERIOD_SEC = 3.0


class FleetZenohWatcher:
    """Aggregates ``robots/*/{pose,battery,map_name}`` into an in-memory snapshot."""

    def __init__(self, endpoint: str = DEFAULT_ZENOH_ENDPOINT, mode: str = DEFAULT_ZENOH_MODE) -> None:
        if zenoh is None:
            raise RuntimeError("The 'eclipse-zenoh' pip package is not installed. Install it with "
                               '`uv pip install --system eclipse-zenoh` (plain pip is unreliable here; '
                               'see cube_petit_web_interface/requirements.txt). '
                               f'Original error: {_ZENOH_IMPORT_ERROR}')
        self._endpoint = endpoint
        self._mode = mode
        self._lock = threading.Lock()
        self._state: typing.Dict[str, dict] = {}
        self._session: typing.Optional['zenoh.Session'] = None
        self._subs: list = []

        # ================= chase (追いかけっこ) =================
        # このプロセス(常駐FastAPIサーバー)内で完結するループ。ブラウザのタブ切替/
        # クローズの影響を受けない(cube_petit_scenario#<PR> 参照)。
        self._chase_lock = threading.Lock()
        self._chase_pairs: typing.Dict[str, typing.Dict[str, str]] = {}
        self._chase_stop = threading.Event()
        self._chase_thread: typing.Optional[threading.Thread] = None

    def start(self) -> None:
        """Open the zenoh session and declare one subscriber per field in `logic.FIELDS`.

        May block briefly while zenoh establishes the connection; call this
        from a background thread, never on an asyncio event loop (mirrors
        core.py's rationale for running `ros2 node list` off-thread).
        """
        config = zenoh.Config()
        config.insert_json5('mode', json.dumps(self._mode))
        config.insert_json5('connect/endpoints', json.dumps([self._endpoint]))
        self._session = zenoh.open(config)
        for field in logic.FIELDS:
            key = f'robots/*/{field}'
            sub = self._session.declare_subscriber(key, functools.partial(self._on_sample, field))
            self._subs.append(sub)
        self._chase_stop.clear()
        self._chase_thread = threading.Thread(target=self._chase_loop, daemon=True)
        self._chase_thread.start()

    def close(self) -> None:
        """Release the zenoh session. Safe to call multiple times / before `start()`."""
        self._chase_stop.set()
        if self._session is not None and not self._session.is_closed():
            self._session.close()

    def _on_sample(self, field: str, sample: 'zenoh.Sample') -> None:
        robot_name = logic.parse_robot_name(str(sample.key_expr), field)
        if robot_name is None:
            return
        try:
            value = logic.decode_field(sample.payload.to_bytes())
        except (ValueError, TypeError):
            return
        with self._lock:
            robot = self._state.setdefault(robot_name, {})
            robot[field] = value
            robot['last_seen'] = time.monotonic()

    def snapshot(self, stale_after: float = logic.STALE_AFTER_SEC) -> typing.Dict[str, dict]:
        """Return a JSON-serializable ``{robot_name: {pose, battery, map_name, online, ...}}`` snapshot."""
        with self._lock:
            # Copy while holding the lock; build_snapshot() itself needs no lock (pure).
            state_copy = {name: dict(robot) for name, robot in self._state.items()}
        return logic.build_snapshot(state_copy, time.monotonic(), stale_after)

    def send_command(self, robot_name: str, method: str, args: dict) -> str:
        """Publish a ``robots/<robot_name>/command`` message (fire-and-forget).

        Mirrors the wire format `cube_petit_fleet_bridge.zenoh_connector`'s
        `_on_zenoh_command` expects: ``{"method", "args", "id"}`` JSON (see
        `fleet_bridge_logic.parse_command` in the `cube_petit_ros` repo).
        Completion isn't awaited here -- the dashboard polls `snapshot()`
        (robot pose moving) rather than `command_is_completed`, since that
        key isn't part of this watcher's subscriptions.

        Args:
            robot_name: Target robot namespace, e.g. ``cube_petit_pink``.
            method: One of the fleet_bridge ``SUPPORTED_METHODS`` (only
                ``move_to_pose`` is exercised by the dashboard today).
            args: Method-specific args, e.g. ``{"x", "y", "yaw", "map_name"}``.

        Returns:
            The generated command id.

        Raises:
            RuntimeError: If the zenoh session isn't open (watcher not started).
        """
        if self._session is None:
            raise RuntimeError('Fleet zenoh session is not open (watcher not started)')
        command_id = uuid.uuid4().hex
        payload = json.dumps({'method': method, 'args': args, 'id': command_id})
        self._session.put(f'robots/{robot_name}/command', payload)
        return command_id

    # =================================================
    # chase (追いかけっこ): サーバー側常駐ループ
    # =================================================

    def start_chase(self, chaser: str, target: str) -> str:
        """Start (or return the existing id for) a chaser->target pair.

        Args:
            chaser: Robot that will be sent move_to_pose commands.
            target: Robot whose current pose the chaser follows.

        Returns:
            The pair's id (new, or the existing one if this exact pair was
            already active -- addChasePair-style de-duplication).

        Raises:
            ValueError: If chaser == target.
        """
        if chaser == target:
            raise ValueError('chaser and target must be different robots')
        with self._chase_lock:
            for pair_id, pair in self._chase_pairs.items():
                if pair['chaser'] == chaser and pair['target'] == target:
                    return pair_id
            pair_id = uuid.uuid4().hex
            self._chase_pairs[pair_id] = {'chaser': chaser, 'target': target}
        return pair_id

    def stop_chase(self, pair_id: str) -> bool:
        """Stop a chase pair by id. Returns False if it wasn't active."""
        with self._chase_lock:
            return self._chase_pairs.pop(pair_id, None) is not None

    def list_chase(self) -> typing.List[dict]:
        """Return the currently active chase pairs as ``[{id, chaser, target}, ...]``."""
        with self._chase_lock:
            return [{'id': pair_id, **pair} for pair_id, pair in self._chase_pairs.items()]

    def _chase_loop(self) -> None:
        """Background loop for the chase feature.

        Every CHASE_PERIOD_SEC, send each active pair's chaser a move_to_pose
        toward its target's current pose. Runs for the lifetime of this
        watcher (daemon thread, stopped via `_chase_stop` in `close()`).
        """
        while not self._chase_stop.wait(CHASE_PERIOD_SEC):
            with self._chase_lock:
                pairs = list(self._chase_pairs.values())
            if not pairs:
                continue
            state = self.snapshot()
            for pair in pairs:
                target_robot = state.get(pair['target'])
                target_pose = target_robot.get('pose') if target_robot else None
                if not target_robot or not target_robot.get('online') or not target_pose:
                    continue
                chaser_robot = state.get(pair['chaser'])
                chaser_pose = chaser_robot.get('pose') if chaser_robot else None
                if chaser_pose:
                    yaw = math.atan2(target_pose['y'] - chaser_pose['y'], target_pose['x'] - chaser_pose['x'])
                else:
                    yaw = target_pose['yaw']
                try:
                    self.send_command(
                        pair['chaser'], 'move_to_pose', {
                            'x': target_pose['x'],
                            'y': target_pose['y'],
                            'yaw': yaw,
                            'map_name': target_robot.get('map_name') or '',
                        })
                except RuntimeError:
                    pass  # watcher not started -- shouldn't happen once _chase_loop is running
