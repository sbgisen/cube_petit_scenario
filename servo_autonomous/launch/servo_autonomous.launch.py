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
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    """Generate launch descriptions.

    Returns:
        Launch descriptions
    """
    # ---------- Launch arguments ----------
    serial_port = LaunchConfiguration('serial_port')

    declare_serial_port = DeclareLaunchArgument(
        'serial_port',
        default_value='/dev/ttyUSB2',
        description='Serial port for Arduino servo controller'
    )

    # ---------- Paths ----------
    servo_autonomous_pkg = get_package_share_directory('servo_autonomous')
    servo_action_pkg = get_package_share_directory('servo_action')
    speech_pkg = get_package_share_directory('cube_petit_speech_to_text')
    perception_pkg = get_package_share_directory('cube_petit_perception')

    servo_autonomous_config = os.path.join(
        servo_autonomous_pkg, 'config', 'servo_autonomous.yaml'
    )

    hotword_launch = os.path.join(
        speech_pkg, 'launch', 'cube_petit_hotword_detector.launch.py'
    )

    leg_detector_launch = os.path.join(
        perception_pkg, 'launch', 'leg_detector.launch.py'
        
    )
    julius_launch = os.path.join(
        speech_pkg,  'launch', 'cube_petit_speech_to_text.launch.py'
    )
    # ---------- Nodes ----------
    servo_action_server = Node(
        package='servo_action',
        executable='servo_action_server.py',
        name='servo_action_server',
        output='screen',
        # parameters=[{
        #     'serial_port': serial_port
        # }]
    )

    respeaker_node = Node(
        package='respeaker_ros',
        executable='respeaker_node',
        name='respeaker',
        output='screen'
    )

    servo_autonomous_node = Node(
        package='servo_autonomous',
        executable='servo_autonomous_node',
        name='servo_autonomous',
        output='screen',
        parameters=[servo_autonomous_config]
    )

    # ---------- Include other launches ----------
    hotword_detector = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(hotword_launch)
    )

    leg_detector = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(leg_detector_launch)
    )
    julius = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(julius_launch)
    )

    # ---------- LaunchDescription ----------
    return LaunchDescription([
        declare_serial_port,

        servo_action_server,
        respeaker_node,

        hotword_detector,
        leg_detector,
        julius,

        servo_autonomous_node,
    ])
