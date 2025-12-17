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

import sqlite3
import time
from typing import Optional

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from std_msgs.msg import Float32MultiArray
from std_msgs.msg import String


class SpeakerMemoryNode(Node):
    """Speaker identification + persistence node."""

    def __init__(self) -> None:
        super().__init__('speaker_memory_node')

        self.sub = self.create_subscription(
            Float32MultiArray,
            'voice_embedding',
            self.on_embedding,
            10,
        )

        self.pub_identity = self.create_publisher(String, 'speaker_identity', 10)
        self.pub_confidence = self.create_publisher(Float32, 'speaker_confidence', 10)

        self.same_threshold: float = 0.75

        self.db = sqlite3.connect(
            '/home/gisen/ros/speaker_memory.db',
            check_same_thread=False,
        )
        self._init_db()

        self.get_logger().info('SpeakerMemoryNode with persistence started')

    # ---------------- DB ----------------

    def _init_db(self) -> None:
        cur = self.db.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS speakers (
                speaker_id INTEGER PRIMARY KEY,
                user_id TEXT,
                embedding BLOB
            )
        """)
        self.db.commit()

    def _load_speakers(self) -> list[tuple[int, str, np.ndarray]]:
        cur = self.db.cursor()
        cur.execute('SELECT speaker_id, user_id, embedding FROM speakers')
        rows = cur.fetchall()

        speakers = []
        for sid, uid, blob in rows:
            emb = np.frombuffer(blob, dtype=np.float32)
            speakers.append((sid, uid, emb))
        return speakers

    def _save_speaker(self, speaker_id: int, user_id: str, emb: np.ndarray) -> None:
        cur = self.db.cursor()
        cur.execute(
            'INSERT OR REPLACE INTO speakers VALUES (?, ?, ?)',
            (speaker_id, user_id, emb.astype(np.float32).tobytes()),
        )
        self.db.commit()

    # ---------------- Logic ----------------

    def on_embedding(self, msg: Float32MultiArray) -> None:
        emb = np.array(msg.data, dtype=np.float32)
        emb /= np.linalg.norm(emb)

        # best_id: Optional[int] = None
        best_uid: Optional[str] = None
        best_sim: float = -1.0

        for sid, uid, ref in self._load_speakers():
            sim = float(np.dot(emb, ref))
            if sim > best_sim:
                best_sim = sim
                # best_id = sid
                best_uid = uid

        if best_sim >= self.same_threshold and best_uid is not None:
            confidence = self.similarity_to_confidence(best_sim)
            self.pub_identity.publish(String(data=best_uid))
            self.pub_confidence.publish(Float32(data=confidence))
            self.get_logger().info(f'Matched user={best_uid}, sim={best_sim:.3f}')
        else:
            self.pub_identity.publish(String(data='new'))
            self.pub_confidence.publish(Float32(data=0.0))
            new_user_id = f'anon_{time.time()}'
            self.register_user(new_user_id, emb)
            self.get_logger().info('New speaker detected')

    @staticmethod
    def similarity_to_confidence(sim: float) -> float:
        if sim <= 0.4:
            return 0.0
        if sim >= 0.85:
            return 1.0
        return (sim - 0.4) / (0.85 - 0.4)

    # -------- called from MemoryTalkDemoNode --------

    def register_user(self, user_id: str, emb: np.ndarray) -> None:
        speaker_id = self._next_speaker_id()
        self._save_speaker(speaker_id, user_id, emb)
        self.get_logger().info(f'Registered user {user_id} as speaker {speaker_id}')

    def _next_speaker_id(self) -> int:
        cur = self.db.cursor()
        cur.execute('SELECT MAX(speaker_id) FROM speakers')
        row = cur.fetchone()
        return 0 if row[0] is None else row[0] + 1


def main() -> None:
    rclpy.init()
    node = SpeakerMemoryNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
