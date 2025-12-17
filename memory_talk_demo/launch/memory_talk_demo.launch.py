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
import os
import socket

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import PushRosNamespace
from launch_ros.substitutions import FindPackageShare


def get_active_interface() -> str:
    try:
        import netifaces
        candidates = []
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET not in addrs:
                continue
            ip_info = addrs[netifaces.AF_INET][0]
            ip = ip_info.get('addr', '')
            if ip.startswith('127.') or ip.startswith('169.') or ip == '':
                continue
            if 'docker' in iface or 'veth' in iface:
                continue
            candidates.append((iface, ip))
        if not candidates:
            raise RuntimeError('No active network interface found')
        # 最初の候補を返す
        iface, ip = candidates[0]
        print(f"[INFO] Using interface '{iface}' ({ip})")
        return iface
    except Exception as e:
        raise RuntimeError(f'[ERROR] Failed to find active network interface: {e}')


def get_ip_address(interface: str) -> str:
    try:
        import netifaces
        addresses = netifaces.ifaddresses(interface)
        ip = addresses[netifaces.AF_INET][0]['addr']
        # IP が 192.168.8.X でなければエラー
        # if not ip.startswith('192.168.8.'):
        #     raise RuntimeError(f"[ERROR] Unexpected IP address: {ip}. Expected it to start with '192.168.8.'")
        return ip
    except Exception as e:
        raise RuntimeError(f'[ERROR] Failed to get valid IP from {interface}: {e}')


def generate_launch_description() -> LaunchDescription:
    """Generate launch descriptions.

    Returns:
        Launch descriptions
    """
    args = []
    hostname = socket.gethostname()
    namespace = hostname.replace('-', '_')
    # for debug
    namespace = 'cube_petit_pink'
    interface = get_active_interface()
    wifi_ip = get_ip_address(interface)
    color_name = namespace.split('_')[-1]

    args.append(DeclareLaunchArgument('cube_petit_host_name', default_value=namespace))
    args.append(DeclareLaunchArgument('cube_petit_ip', default_value=wifi_ip))
    args.append(DeclareLaunchArgument('color', default_value=color_name))
    pkg_path = FindPackageShare('memory_talk_demo')
    args.append(
        DeclareLaunchArgument('setting_file',
                              default_value=[pkg_path, '/config/realtime_chat_setting.txt'],
                              description='Setting file.'))

    bringup = GroupAction([
        PushRosNamespace(LaunchConfiguration('cube_petit_host_name')),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(FindPackageShare('sbgisen_speech').find('sbgisen_speech'), 'sbgisen_speech.launch.py')),),
        # IncludeLaunchDescription(PythonLaunchDescriptionSource(
        #     os.path.join(
        #         FindPackageShare('cube_petit_facial_animation').find('cube_petit_facial_animation'), 'launch',
        #         'cube_petit_facial_animation.launch.py')),
        #                          launch_arguments={'color': LaunchConfiguration('color')}.items()),
        # IncludeLaunchDescription(
        #     PythonLaunchDescriptionSource(
        #         os.path.join(
        #             FindPackageShare('cube_petit_bringup').find('cube_petit_bringup'), 'launch',
        #             'teleop.launch.py')),),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    FindPackageShare('cube_petit_chat').find('cube_petit_chat'), 'launch',
                    'cube_petit_realtime_chat.launch.py')),
            launch_arguments={
                'setting_file': LaunchConfiguration('setting_file'),
                'use_speech_action': 'true',
            }.items(),
        ),
        # IncludeLaunchDescription(
        #     PythonLaunchDescriptionSource(
        #         os.path.join(
        #             FindPackageShare('realsense2_camera').find('realsense2_camera'), 'launch', 'rs_launch.py')),
        #     launch_arguments={
        #         'enable_depth': 'false',
        #         'enable_infra1': 'false',
        #         'enable_infra2': 'false',
        #         'enable_color': 'true',
        #         'color_width': '640',
        #         'color_height': '480',
        #         'color_fps': '10',
        #     }.items(),
        # ),
    ])

    return LaunchDescription(args + [bringup])
