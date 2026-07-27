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
"""Pure (zenoh-free) helpers for the Tier 2 fleet-wide multi-robot picker.

Kept free of the `zenoh` import so it can be unit tested with plain pytest
without the `eclipse-zenoh` pip package installed, mirroring
cube_petit_fleet_bridge/cube_petit_fleet_bridge/fleet_bridge_logic.py and
cube_petit_shared_controller/cube_petit_shared_controller/shared_controller_logic.py:
fleet_zenoh.py owns the zenoh session/subscriber glue, this module owns key
parsing, JSON decoding, and snapshot building.

Zenoh key convention this module reads (fixed by cube_petit_fleet_bridge, do
not change -- see its fleet_bridge_logic.py docstring for the full picture):

    robots/<robot_name>/pose         (pub)  {"x","y","yaw"}
    robots/<robot_name>/battery      (pub)  float in [0, 1]
    robots/<robot_name>/map_name     (pub)  JSON string
"""

from __future__ import annotations

import json
import typing

#: The three read-only state fields the Tier 2 picker subscribes to
#: (deliberately excludes `command` / `command_is_completed`: sending commands
#: to other robots is out of scope for this read-only fleet visibility feature).
FIELDS: typing.Tuple[str, ...] = ('pose', 'battery', 'map_name')

#: A robot is considered offline once its last state publish is older than
#: this many seconds. fleet_bridge's own `state_publish_period_sec` default is
#: 1.0s, so 5x that tolerates a few dropped/late publishes before flipping.
STALE_AFTER_SEC = 5.0


def parse_robot_name(key_expr: str, field: str) -> typing.Optional[str]:
    """Extract ``<robot_name>`` from a ``robots/<robot_name>/<field>`` key.

    Args:
        key_expr: The full zenoh key expression of an incoming sample.
        field: The expected trailing segment (one of `FIELDS`).

    Returns:
        The robot name, or ``None`` if `key_expr` doesn't match the expected
        ``robots/<name>/<field>`` shape (defensive: a malformed/foreign
        publisher on the same zenoh network should never crash the watcher).
    """
    parts = key_expr.split('/')
    if len(parts) == 3 and parts[0] == 'robots' and parts[2] == field and parts[1]:
        return parts[1]
    return None


def decode_field(payload: typing.Union[bytes, bytearray, str]) -> typing.Union[dict, float, str]:
    """Decode a ``pose`` / ``battery`` / ``map_name`` zenoh payload (all JSON).

    Args:
        payload: Raw zenoh payload, as ``bytes``/``bytearray`` or ``str``.

    Returns:
        The decoded JSON value (dict for pose, float for battery, str for map_name).

    Raises:
        ValueError: If the payload is not valid JSON.
    """
    text = payload.decode('utf-8') if isinstance(payload, (bytes, bytearray)) else payload
    return json.loads(text)


def build_snapshot(state: typing.Dict[str, dict],
                   now: float,
                   stale_after: float = STALE_AFTER_SEC) -> typing.Dict[str, dict]:
    """Build the JSON-serializable ``/fleet/robots`` payload from raw per-robot state.

    Args:
        state: ``{robot_name: {"pose": ..., "battery": ..., "map_name": ..., "last_seen": monotonic_time}}``,
            as accumulated by FleetZenohWatcher._on_sample. Missing fields are
            simply absent from a robot's dict (e.g. before its first publish).
        now: Current `time.monotonic()` reading (passed in for testability).
        stale_after: Seconds since `last_seen` after which a robot is `online: False`.

    Returns:
        ``{robot_name: {pose, battery, map_name, online, last_seen_sec_ago}}``.
    """
    result = {}
    for name, robot in state.items():
        last_seen = robot.get('last_seen', 0.0)
        age = now - last_seen
        result[name] = {
            'pose': robot.get('pose'),
            'battery': robot.get('battery'),
            'map_name': robot.get('map_name'),
            'online': age < stale_after,
            'last_seen_sec_ago': round(age, 1),
        }
    return result
