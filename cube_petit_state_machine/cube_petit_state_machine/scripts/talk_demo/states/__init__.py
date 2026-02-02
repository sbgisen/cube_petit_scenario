#!/usr/bin/env python
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
"""Specify importable states."""

from cube_petit_state_machine.scripts.talk_demo.states.create_response import CreateResponse
# from cube_petit_state_machine.scripts.talk_demo.states.gpt_conversation import GPTConversation
from cube_petit_state_machine.scripts.talk_demo.states.hotword_detected import HotwordDetected
# from cube_petit_state_machine.scripts.talk_demo.states.how_old_you_are import HowOldYouAre
from cube_petit_state_machine.scripts.talk_demo.states.julius_search import JuliusSearch
# from cube_petit_state_machine.scripts.talk_demo.states.rock_paper_scissors import RockPaperScissors
from cube_petit_state_machine.scripts.talk_demo.states.wait_for_hotword import WaitForHotword

__all__ = [
    'WaitForHotword',
    'HotwordDetected',
    'JuliusSearch',
    'CreateResponse',
    # 'RockPaperScissors',
    # 'HowOldYouAre',
    # 'GPTConversation'
]
