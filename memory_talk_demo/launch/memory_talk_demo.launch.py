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
import tempfile

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.actions import IncludeLaunchDescription
from launch.actions import OpaqueFunction
from launch.launch_context import LaunchContext
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
from launch_ros.substitutions import FindPackageShare
import yaml


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


def generate_realtime_setting(context: LaunchContext, color: str) -> str:
    pkg_share_path = FindPackageShare('memory_talk_demo').perform(context)

    template_dir = os.path.join(pkg_share_path, 'config')
    base_setting = os.path.join(template_dir, 'realtime_chat_setting.txt')
    petit_template = os.path.join(template_dir, 'petit_setting_template.txt')
    color_yaml = os.path.join(template_dir, f'color_settings/{color}_setting.yaml')

    with open(base_setting, 'r', encoding='utf-8') as f:
        base_text = f.read()
    with open(petit_template, 'r', encoding='utf-8') as f:
        petit_template_text = f.read()
    with open(color_yaml, 'r', encoding='utf-8') as f:
        color_dict = yaml.safe_load(f)

    petit_filled = petit_template_text.format(**color_dict)
    full_text = base_text.replace('{petit_setting}', petit_filled)

    tmp_file = tempfile.NamedTemporaryFile(mode='w',
                                           delete=False,
                                           encoding='utf-8',
                                           prefix=f'realtime_chat_setting_{color}_',
                                           suffix='.txt')
    tmp_file.write(full_text)
    tmp_file.close()

    print(f'[INFO] Generated realtime_chat_setting for {color}: {tmp_file.name}')
    return tmp_file.name


def launch_setup(context: LaunchContext) -> None:

    color = LaunchConfiguration('color').perform(context)
    print(color)
    setting_file_path = generate_realtime_setting(context, color)
    print(setting_file_path)

    bringup = GroupAction([
        PushRosNamespace(LaunchConfiguration('cube_petit_host_name')),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(FindPackageShare('sbgisen_speech').find('sbgisen_speech'), 'sbgisen_speech.launch.py')),),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(
                FindPackageShare('cube_petit_facial_animation').find('cube_petit_facial_animation'), 'launch',
                'cube_petit_facial_animation.launch.py')),
                                 launch_arguments={'color': LaunchConfiguration('color')}.items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    FindPackageShare('cube_petit_bringup').find('cube_petit_bringup'), 'launch',
                    'teleop.launch.py')),),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    FindPackageShare('cube_petit_chat').find('cube_petit_chat'), 'launch',
                    'cube_petit_realtime_chat.launch.py')),
            launch_arguments={
                'setting_file': setting_file_path,
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
        Node(package='memory_talk_demo', executable='user_store_node', name='user_store_node', output='screen'),
        Node(package='memory_talk_demo', executable='memory_speaker_node', name='memory_speaker_node',
             output='screen'),
        Node(package='memory_talk_demo', executable='voice_embed', name='voice_embed', output='screen'),
        Node(package='memory_talk_demo', executable='memory_talk_demo', name='memory_talk_demo', output='screen'),
    ])

    return [bringup]


def generate_launch_description() -> LaunchDescription:
    hostname = socket.gethostname()
    namespace = hostname.replace('-', '_')
    # For debug
    namespace = 'cube_petit_pink'

    interface = get_active_interface()
    wifi_ip = get_ip_address(interface)
    color_name = namespace.split('_')[-1]
    args = []
    args.append(DeclareLaunchArgument('cube_petit_host_name', default_value=namespace))
    args.append(DeclareLaunchArgument('cube_petit_ip', default_value=wifi_ip))
    args.append(DeclareLaunchArgument('color', default_value=color_name))

    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
