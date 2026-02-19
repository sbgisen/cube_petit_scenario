#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
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

from dataclasses import dataclass
import sqlite3
import time
from typing import Optional


@dataclass
class User:
    user_id: str
    interaction_count: int
    confidence: float
    display_name: Optional[str]


class UserStore:

    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        cur = self.db.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            interaction_count INTEGER,
            confidence REAL,
            display_name TEXT
        )
        """)
        self.db.commit()

    # -------------------------------------------------
    # CRUD
    # -------------------------------------------------
    def create_user_with_id(self, user_id: str) -> None:
        """
        SpeakerMemoryNode 等で生成された user_id.

        UserStore 側に正式登録する
        """
        if self.get_user(user_id) is not None:
            return self.get_user(user_id)

        cur = self.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, interaction_count, confidence, display_name)
            VALUES (?, 0, 0.0, NULL)
            """,
            (user_id,),
        )
        self.db.commit()

        return self.get_user(user_id)

    def create_new_user(self) -> User:
        user_id = f'user_{int(time.time() * 1000)}'
        cur = self.db.cursor()
        cur.execute(
            'INSERT INTO users VALUES (?, ?, ?, ?)',
            (user_id, 0, 0.0, None),
        )
        self.db.commit()
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> Optional[User]:
        cur = self.db.cursor()
        cur.execute(
            'SELECT user_id, interaction_count, confidence, display_name '
            'FROM users WHERE user_id = ?',
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return User(*row)

    def update_interaction(self, user_id: str) -> None:
        cur = self.db.cursor()
        cur.execute(
            """
            UPDATE users
            SET interaction_count = interaction_count + 1,
                confidence = MIN(confidence + 0.1, 1.0)
            WHERE user_id = ?
            """,
            (user_id,),
        )
        self.db.commit()

    # -------------------------------------------------
    # Display name
    # -------------------------------------------------

    def set_display_name_candidate(self, user_id: str, name: str) -> None:
        # 今回は candidate と confirmed を分けず、即保存でOK
        self.confirm_display_name(user_id, name)

    def confirm_display_name(self, user_id: str, name: str) -> None:
        cur = self.db.cursor()
        cur.execute(
            'UPDATE users SET display_name = ? WHERE user_id = ?',
            (name, user_id),
        )
        self.db.commit()

    # -------------------------------------------------

    def close(self) -> None:
        self.db.close()
