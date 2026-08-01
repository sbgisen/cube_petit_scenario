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
"""Plain pytest tests for fleet_zenoh_logic (no rclpy / no zenoh required).

Mirrors cube_petit_fleet_bridge/test/test_fleet_bridge_logic.py's style: this
module has no zenoh import, so these tests run in the plain-Python CI job
without the `eclipse-zenoh` pip package installed.
"""

import json

import pytest

from cube_petit_web_interface import fleet_zenoh_logic as logic


class TestParseRobotName:

    def test_matches_expected_shape(self) -> None:
        assert logic.parse_robot_name('robots/cube_petit_orange/pose', 'pose') == 'cube_petit_orange'
        assert logic.parse_robot_name('robots/cube_petit_pink/battery', 'battery') == 'cube_petit_pink'

    def test_rejects_wrong_field(self) -> None:
        # A subscriber declared for `pose` must not accept a `battery` sample
        # (each field has its own declare_subscriber() call in fleet_zenoh.py).
        assert logic.parse_robot_name('robots/cube_petit_orange/battery', 'pose') is None

    def test_rejects_wrong_prefix(self) -> None:
        assert logic.parse_robot_name('controller/selected_robot', 'pose') is None

    def test_rejects_missing_robot_name(self) -> None:
        assert logic.parse_robot_name('robots//pose', 'pose') is None

    def test_rejects_too_many_segments(self) -> None:
        assert logic.parse_robot_name('robots/cube_petit_orange/command/extra', 'command') is None


class TestDecodeField:

    def test_decodes_pose_object(self) -> None:
        payload = json.dumps({'x': 1.0, 'y': 2.0, 'yaw': 0.5})
        assert logic.decode_field(payload) == {'x': 1.0, 'y': 2.0, 'yaw': 0.5}
        assert logic.decode_field(payload.encode('utf-8')) == {'x': 1.0, 'y': 2.0, 'yaw': 0.5}

    def test_decodes_battery_float(self) -> None:
        assert logic.decode_field(json.dumps(0.87)) == pytest.approx(0.87)

    def test_decodes_map_name_string(self) -> None:
        assert logic.decode_field(json.dumps('orange_room')) == 'orange_room'

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ValueError):
            logic.decode_field('not json')


class TestParseCompletionPayload:

    def test_decodes_valid_payload(self) -> None:
        payload = json.dumps({'id': 'abc123', 'is_completed': True, 'success': True})
        assert logic.parse_completion_payload(payload) == ('abc123', True)

    def test_decodes_bytes(self) -> None:
        payload = json.dumps({'id': 'abc123', 'is_completed': True, 'success': False}).encode('utf-8')
        assert logic.parse_completion_payload(payload) == ('abc123', False)

    def test_missing_id_returns_none_command_id(self) -> None:
        payload = json.dumps({'is_completed': True, 'success': True})
        command_id, _ = logic.parse_completion_payload(payload)
        assert command_id is None

    def test_invalid_json_returns_none_command_id(self) -> None:
        command_id, success = logic.parse_completion_payload('not json')
        assert command_id is None
        assert success is False

    def test_non_object_returns_none_command_id(self) -> None:
        command_id, _ = logic.parse_completion_payload(json.dumps([1, 2, 3]))
        assert command_id is None

    def test_missing_success_defaults_to_false(self) -> None:
        payload = json.dumps({'id': 'xyz', 'is_completed': True})
        assert logic.parse_completion_payload(payload) == ('xyz', False)


class TestBuildSnapshot:

    def test_reports_online_within_stale_window(self) -> None:
        state = {'cube_petit_orange': {'pose': {'x': 1.0, 'y': 2.0, 'yaw': 0.0}, 'battery': 0.9, 'last_seen': 100.0}}
        snapshot = logic.build_snapshot(state, now=101.0, stale_after=5.0)
        assert snapshot['cube_petit_orange']['online'] is True
        assert snapshot['cube_petit_orange']['pose'] == {'x': 1.0, 'y': 2.0, 'yaw': 0.0}
        assert snapshot['cube_petit_orange']['battery'] == 0.9
        assert snapshot['cube_petit_orange']['map_name'] is None
        assert snapshot['cube_petit_orange']['last_seen_sec_ago'] == 1.0

    def test_reports_offline_past_stale_window(self) -> None:
        state = {'cube_petit_pink': {'pose': None, 'last_seen': 0.0}}
        snapshot = logic.build_snapshot(state, now=10.0, stale_after=5.0)
        assert snapshot['cube_petit_pink']['online'] is False

    def test_handles_robot_with_no_publishes_yet(self) -> None:
        # A robot key can exist with no `last_seen` only in pathological cases;
        # missing fields must not raise.
        snapshot = logic.build_snapshot({'cube_petit_yellow': {}}, now=5.0, stale_after=5.0)
        assert snapshot['cube_petit_yellow']['online'] is False
        assert snapshot['cube_petit_yellow']['pose'] is None

    def test_empty_state_returns_empty_snapshot(self) -> None:
        assert logic.build_snapshot({}, now=1.0) == {}
