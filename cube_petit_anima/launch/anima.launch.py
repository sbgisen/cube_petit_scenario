#!/usr/bin/env python
# -*- coding:utf-8 -*-

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
"""anima ノード群 (internal_state / sensor_influence / behavior) の launch."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    """Launch anima nodes."""
    package_name = 'cube_petit_anima'

    config_file = os.path.join(get_package_share_directory(package_name), 'config', 'anima_params.yaml')
    config_se_path = PathJoinSubstitution([FindPackageShare('cube_petit_anima'), 'config', 'se.yaml'])

    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='false', description='Use simulation clock')

    robot_arg = DeclareLaunchArgument('robot', default_value='cube_petit_orange', description='Robot namespace.')

    swing_arg = DeclareLaunchArgument('swing',
                                      default_value='false',
                                      description='Enable swing motion of behavior_node.')

    # Default matches behavior_logic.SWING_AMPLITUDE. Kept adjustable here so the value
    # can be raised for real-robot tuning without touching code (2026-07-10 feedback:
    # 1.5 was too weak to overcome static friction).
    swing_amplitude_arg = DeclareLaunchArgument('swing_amplitude',
                                                default_value='4.0',
                                                description='Amplitude [rad/s] of the swing angular.z command.')

    use_sim_time = LaunchConfiguration('use_sim_time')
    swing_enabled = LaunchConfiguration('swing')
    swing_amplitude = LaunchConfiguration('swing_amplitude')

    return LaunchDescription([
        use_sim_time_arg,
        robot_arg,
        swing_arg,
        swing_amplitude_arg,
        PushRosNamespace(LaunchConfiguration('robot')),
        Node(package=package_name,
             executable='internal_state_node',
             name='internal_state_node',
             parameters=[config_file, {
                 'use_sim_time': use_sim_time
             }],
             output='screen'),
        Node(package=package_name,
             executable='sensor_influence_node',
             name='sensor_influence_node',
             parameters=[config_file, {
                 'use_sim_time': use_sim_time
             }],
             output='screen'),
        Node(package=package_name,
             executable='behavior_node',
             name='behavior_node',
             parameters=[
                 config_file, {
                     'use_sim_time': use_sim_time,
                     'config_se_path': config_se_path,
                     'swing_enabled': swing_enabled,
                     'swing_amplitude': swing_amplitude
                 }
             ],
             output='screen'),
    ])
