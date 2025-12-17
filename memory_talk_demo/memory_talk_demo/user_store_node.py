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

from cube_petit_interaction_msgs.srv import CreateUser
from cube_petit_interaction_msgs.srv import GetUserSummary
from cube_petit_interaction_msgs.srv import SetDisplayName
from cube_petit_interaction_msgs.srv import UpdateInteraction
import rclpy
from rclpy.node import Node

from memory_talk_demo.user_store import UserStore


class UserStoreNode(Node):
    """
    ROS 2 node responsible for user memory persistence.

    Responsibilities:
    - Create anonymous users
    - Update interaction count & confidence
    - Provide user summary for conversation / LLM
    """

    def __init__(self) -> None:
        super().__init__('user_store_node')

        # ---------------- Parameters ----------------
        self.declare_parameter('db_path', 'users.db')
        db_path: str = self.get_parameter('db_path').value

        # ---------------- Store ----------------
        self.store = UserStore(db_path)

        # ---------------- Services ----------------
        self.create_service(
            CreateUser,
            'create_user',
            self.handle_create_user,
        )

        self.create_service(
            UpdateInteraction,
            'update_interaction',
            self.handle_update_interaction,
        )

        self.create_service(
            GetUserSummary,
            'get_user_summary',
            self.handle_get_user_summary,
        )

        self.create_service(
            SetDisplayName,
            'set_display_name',
            self.handle_set_display_name,
        )

        self.get_logger().info('UserStoreNode started')

    # ==========================================================
    # Service handlers
    # ==========================================================
    def handle_set_display_name(
        self,
        request: SetDisplayName.Request,
        response: SetDisplayName.Response,
    ) -> SetDisplayName.Response:
        user = self.store.get_user(request.user_id)
        if user is None:
            self.store.create_user_with_id(request.user_id)

        if request.confirmed:
            self.store.confirm_display_name(
                request.user_id,
                request.display_name,
            )
            self.get_logger().info(f'Confirmed display name for {request.user_id}: {request.display_name}')
        else:
            self.store.set_display_name_candidate(
                request.user_id,
                request.display_name,
            )
            self.get_logger().info(f'Set display name candidate for {request.user_id}: {request.display_name}')

        response.success = True
        return response

    def handle_create_user(
        self,
        request: CreateUser.Request,
        response: CreateUser.Response,
    ) -> CreateUser.Response:
        """
        Create a new anonymous user.

        Used when speaker is detected as 'new'.
        """
        user = self.store.create_new_user()

        response.user_id = user.user_id
        response.confidence = float(user.confidence)
        response.interaction_count = int(user.interaction_count)

        self.get_logger().info(f'Created new user: {user.user_id}')
        return response

    def handle_update_interaction(
        self,
        request: UpdateInteraction.Request,
        response: UpdateInteraction.Response,
    ) -> UpdateInteraction.Response:
        """Update interaction count and confidence for an existing user."""
        user = self.store.get_user(request.user_id)
        if user is None:
            self.get_logger().warn(f'Unknown user_id: {request.user_id}')
            return response

        self.store.update_interaction(request.user_id)
        user = self.store.get_user(request.user_id)

        response.interaction_count = user.interaction_count
        response.confidence = float(user.confidence)

        self.get_logger().info('realizing the previous context, '
                               f'Updated user {user.user_id}: '
                               f'count={user.interaction_count}, conf={user.confidence:.2f}')
        return response

    def handle_get_user_summary(
        self,
        request: GetUserSummary.Request,
        response: GetUserSummary.Response,
    ) -> GetUserSummary.Response:
        """Return summarized user information for dialogue / LLM."""
        user = self.store.get_user(request.user_id)
        if user is None:
            self.get_logger().warn(f'User not found: {request.user_id}')
            return response

        response.interaction_count = user.interaction_count
        response.confidence = float(user.confidence)
        response.has_name = user.display_name is not None
        response.display_name = user.display_name or ''

        return response

    # ==========================================================
    # Lifecycle
    # ==========================================================

    def destroy_node(self) -> None:
        self.store.close()
        super().destroy_node()


def main() -> None:
    rclpy.init()
    node = UserStoreNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
