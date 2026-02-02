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

from enum import Enum, auto

import rclpy
from rclpy.node import Node

from cube_petit_state_machine.nodes.supervisor_fsm import SupervisorFSM
from rcl_interfaces.msg import ParameterDescriptor

from cube_petit_state_machine.scripts.talk_demo.states import (
    WaitForHotword,
    HotwordDetected,
    JuliusSearch,
    CreateResponse,
    # HowOldYouAre,
    # RockPaperScissors,
    # GPTConversation,
)


class TalkState(Enum):
    WAIT_FOR_HOTWORD = auto()
    HOTWORD_DETECTED = auto()
    JULIUS_SEARCH = auto()
    CREATE_RESPONSE = auto()
    HOW_OLD_YOU_ARE = auto()
    ROCK_PAPER_SCISSORS = auto()
    GPT_CONVERSATION = auto()


class TalkFSM:
    def __init__(self, node: Node, supervisor: SupervisorFSM):
        self.node = node
        self.supervisor = supervisor
        self.state = TalkState.WAIT_FOR_HOTWORD

        self.wait_for_hotword = WaitForHotword(node)
        self.hotword_detected = HotwordDetected(node)
        self.julius_search = JuliusSearch(node)
        self.create_response = CreateResponse(node)
        # self.how_old = HowOldYouAre(node)
        # self.rps = RockPaperScissors(node)
        # self.gpt = GPTConversation(node)


        self.node.get_logger().info("TalkFSM initialized")

    def step(self) -> None:
        # ----- permission check -----
        if not self.supervisor.is_talk_allowed():
            self.supervisor.set_talk_active(False)
            return

        self.supervisor.set_talk_active(True)

        # ----- FSM body -----
        if self.state == TalkState.WAIT_FOR_HOTWORD:
            result = self.wait_for_hotword.execute()
            if result == 'hotword_detected':
                self._transition(TalkState.HOTWORD_DETECTED)

        elif self.state == TalkState.HOTWORD_DETECTED:
            self.hotword_detected.execute()
            self._transition(TalkState.JULIUS_SEARCH)

        elif self.state == TalkState.JULIUS_SEARCH:
            result = self.julius_search.execute()
            if result is None:
                return

            outcome, cmd = result
            self.node.get_logger().info(f"{outcome}, {cmd}")

            if cmd == 'come_to_me':
                self.node.get_logger().info("TalkFSM: request ActionFSM (come_to_me)")
                self.supervisor.set_action_active(True)
                self._transition(TalkState.WAIT_FOR_HOTWORD)
                return
            if cmd == 'facing_me':
                self.supervisor.set_action_active(True)
                self._transition(TalkState.WAIT_FOR_HOTWORD)
                return
                
            if cmd:
                self.create_response.set_input_cmd(cmd)
            #     self.gpt.set_input_cmd(cmd)
            
            if outcome == 'response':
                self._transition(TalkState.CREATE_RESPONSE)
            elif outcome == 'how_old_you_are':
                self._transition(TalkState.HOW_OLD_YOU_ARE)
            elif outcome == 'rock_paper_scissors':
                self._transition(TalkState.ROCK_PAPER_SCISSORS)
            elif outcome == 'gpt_conversation':
                self._transition(TalkState.GPT_CONVERSATION)
                
            else:
                self._transition(TalkState.WAIT_FOR_HOTWORD)

        elif self.state == TalkState.CREATE_RESPONSE:
            self.create_response.execute()
            self._transition(TalkState.WAIT_FOR_HOTWORD)

        # elif self.state == TalkState.HOW_OLD_YOU_ARE:
        #     if self.how_old.execute() == 'success':
        #         self._transition(TalkState.WAIT_FOR_HOTWORD)

        # elif self.state == TalkState.ROCK_PAPER_SCISSORS:
        #     if self.rps.execute() == 'success':
        #         self._transition(TalkState.WAIT_FOR_HOTWORD)

        # elif self.state == TalkState.GPT_CONVERSATION:
        #     outcome = self.gpt.execute()
        #     if outcome == 'how_old_you_are':
        #         self._transition(TalkState.HOW_OLD_YOU_ARE)
        #     elif outcome == 'rock_paper_scissors':
        #         self._transition(TalkState.ROCK_PAPER_SCISSORS)
        #     else:
        #         self._transition(TalkState.WAIT_FOR_HOTWORD)

        # idle → talk inactive
        if self.state == TalkState.WAIT_FOR_HOTWORD:
            self.supervisor.set_talk_active(False)

    def _transition(self, next_state: TalkState) -> None:
        if self.state != next_state:
            self.node.get_logger().info(
                f"[TalkFSM] {self.state.name} -> {next_state.name}"
            )
        self.state = next_state


class TalkFSMNode(Node):
    def __init__(self):
        super().__init__(
            'talk_fsm_node',
            automatically_declare_parameters_from_overrides=True
        )
        self.get_logger().info("Talk FSM Node started")

        self.supervisor = SupervisorFSM(self)
        self.talk_fsm = TalkFSM(self, self.supervisor)

        self.timer = self.create_timer(0.1, self._step)

    def _step(self):
        self.supervisor.step()
        self.talk_fsm.step()


def main(args=None):
    rclpy.init(args=args)
    node = TalkFSMNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
