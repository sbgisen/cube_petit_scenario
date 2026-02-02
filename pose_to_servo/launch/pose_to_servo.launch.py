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
#

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([

        # Servo Action Server
        Node(
            package='servo_action',
            executable='servo_action_server.py',
            name='servo_action_server',
            output='screen',
            parameters=[{
                'serial_port': '/dev/ttyUSB0',
            }],
        ),

        # Pose → Servo bridge
        Node(
            package='pose_to_servo',
            executable='pose_to_servo_node.py',
            name='pose_to_servo',
            output='screen',
            parameters=[{
                'topic_name': '/pose',
                'offset_yaw': 0.0,
                'scale_yaw': 1.0,
                'center_deg': 90.0,
                'min_deg': 0.0,
                'max_deg': 180.0,
                'time_sec': 1,
                'deadband_rad': 0.01,
            }],
        ),
    ])
