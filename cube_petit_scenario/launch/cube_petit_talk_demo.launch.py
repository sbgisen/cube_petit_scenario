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

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.actions import GroupAction
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
from launch_ros.substitutions import FindPackageShare  # realtime_chat/leg_detector用


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument('robot', default_value='cube_petit_orange', description='Robot namespace.'),
        DeclareLaunchArgument('address', default_value='192.168.8.107', description='Display server address.'),
        DeclareLaunchArgument('certfile', default_value='/home/cube-petit/mycert.pem', description='SSL cert file.'),
        DeclareLaunchArgument('keyfile', default_value='/home/cube-petit/mykey.pem', description='SSL key file.'),
        DeclareLaunchArgument('display_src_dir',
                              default_value='/home/cube-petit/ros/src/cube_petit_demonstration_2025/display_petit_panel',
                              description='Path to display_petit_panel source directory.'),
    ]

    robot = LaunchConfiguration('robot')
    address = LaunchConfiguration('address')
    certfile = LaunchConfiguration('certfile')
    keyfile = LaunchConfiguration('keyfile')
    display_src_dir = LaunchConfiguration('display_src_dir')

    realtime_chat = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare('cube_petit_chat'), '/launch/cube_petit_realtime_chat.launch.py']),
        launch_arguments={'robot': robot}.items(),
    )

    leg_detector = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare('cube_petit_perception'), '/launch/leg_detector.launch.py']),
        launch_arguments={'robot': robot}.items(),
    )

    respeaker = GroupAction(actions=[
        PushRosNamespace(robot),
        Node(
            package='respeaker_ros',
            executable='respeaker_node',
            name='respeaker_node',
            output='screen',
        ),
    ])

    display = ExecuteProcess(
        cmd=[
            PathJoinSubstitution([display_src_dir, '.venv', 'bin', 'panel']),
            'serve', 'display_petit_panel_local.py',
            '--address', address, '--port', '5006',
            '--ssl-certfile', certfile,
            '--ssl-keyfile', keyfile,
            '--allow-websocket-origin', [address, ':5006'],
            '--autoreload', '--args',
            '--robot_namespaces', robot,
        ],
        cwd=display_src_dir,
        output='screen',
    )

    display_movies = ExecuteProcess(
        cmd=[
            PathJoinSubstitution([display_src_dir, '.venv', 'bin', 'panel']),
            'serve', PathJoinSubstitution([display_src_dir, 'movie_show.py']),
            '--address', address, '--port', '5007',
            '--ssl-certfile', certfile,
            '--ssl-keyfile', keyfile,
            '--allow-websocket-origin', [address, ':5007'],
            '--autoreload', '--args',
            '--title', 'Movie Show',
            '--video1_url', 'https://youtu.be/pZz0myy-HF0', '--video1_title', 'デモの説明はこちら(約2分30秒)',
            '--video2_url', 'https://youtu.be/pwvUUi0kq_0', '--video2_title', 'キーホルダープレゼントについて(50秒)',
            '--video3_url', 'https://youtu.be/Xm9ldk8qxBM', '--video3_title', 'チェキ風シールグッズプレゼントについて(1分30秒)',
        ],
        cwd=display_src_dir,
        output='screen',
    )

    return LaunchDescription(args + [realtime_chat, leg_detector, respeaker, display, display_movies])
