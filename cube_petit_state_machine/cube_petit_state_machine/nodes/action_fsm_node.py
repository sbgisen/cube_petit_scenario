#!/usr/bin/env python3
# -*- coding:utf-8 -*-

# Copyright (c) 2024 SoftBank Corp.
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
#
"""
Action FSM for Cube petit (SMACH-less version)
"""


from enum import Enum, auto

import rclpy
from rclpy.node import Node

from cube_petit_state_machine.nodes.supervisor_fsm import SupervisorFSM

from cube_petit_state_machine.scripts.action_demo.states import (
    Idolng,
    RoundAndRound,
    FacingMe,
)

# ===============================
# FSM State 定義
# ===============================

class ActionState(Enum):
    IDLING = auto()
    ROUND_AND_ROUND = auto()
    COME_TO_ME = auto()
    FACING_ME = auto()


# ===============================
# Action FSM 本体
# ===============================

class ActionFSM:
    def __init__(self, node: Node, supervisor: SupervisorFSM):
        self.node = node
        self.supervisor = supervisor
        self.state = ActionState.IDLING

        self.idling = Idolng(node)
        self.round_and_round = RoundAndRound(node)
        self.facing_me = FacingMe(node)

        self.node.get_logger().info("ActionFSM initialized")

    # ---------
    # FSM 1step
    # ---------
    def step(self) -> None:
        # ----- permission check -----
        if not self.supervisor.is_action_allowed():
            self.supervisor.set_action_active(False)
            return

        self.supervisor.set_action_active(True)

        # ----- FSM body -----
        if self.state == ActionState.IDLING:
            result = self.idling.execute()

            if result == 'round_and_round':
                self.supervisor.set_action_active(True)
                self._transition(ActionState.ROUND_AND_ROUND)
            elif result == 'come_to_me':
                self.supervisor.set_action_active(True)
                self._transition(ActionState.COME_TO_ME)
            elif result == 'facing_me':
                self.supervisor.set_action_active(True)
                self._transition(ActionState.FACING_ME)

            # None の場合は IDLING 継続
        elif self.state == ActionState.COME_TO_ME:
            result = self.come_to_me.execute()
            if result == 'success':
                self.supervisor.set_action_active(False)
                self._transition(ActionState.IDLING)

        elif self.state == ActionState.FACING_ME:
            result = self.facing_me.execute()
            if result == 'success':
                self.supervisor.set_action_active(False)
                self._transition(ActionState.IDLING)
                
        elif self.state == ActionState.ROUND_AND_ROUND:
            result = self.round_and_round.execute()

            if result == 'success':
                self.supervisor.set_action_active(False)
                self._transition(ActionState.IDLING)

        # IDLE に戻ったら Action inactive
        if self.state == ActionState.IDLING:
            self.supervisor.set_action_active(False)

    def _transition(self, next_state: ActionState) -> None:
        if self.state != next_state:
            self.node.get_logger().info(
                f"[ActionFSM] {self.state.name} -> {next_state.name}"
            )
        self.state = next_state


# ===============================
# ROS 2 Node
# ===============================

class ActionFSMNode(Node):
    def __init__(self):
        super().__init__(
            'action_fsm_node',
            automatically_declare_parameters_from_overrides=True
        )
        self.get_logger().info("Action FSM Node started")

        self.supervisor = SupervisorFSM(self)
        self.action_fsm = ActionFSM(self, self.supervisor)

        self.timer = self.create_timer(0.1, self._step)

    def _step(self):
        self.supervisor.step()
        self.action_fsm.step()


# ===============================
# main
# ===============================

def main(args=None):
    rclpy.init(args=args)
    node = ActionFSMNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()