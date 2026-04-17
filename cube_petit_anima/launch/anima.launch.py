#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
# 
# <<licensetext>>
#!/usr/bin/env python

from launch import LaunchDescription
from launch_ros.actions import Node, PushRosNamespace
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():

    package_name = 'cube_petit_anima'

    config_file = os.path.join(
        get_package_share_directory(package_name),
        'config',
        'anima_params.yaml'
    )
    config_se_path = PathJoinSubstitution([
        FindPackageShare("cube_petit_anima"),
        "config",
        "se.yaml"
    ])

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock'
    )

    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([

        use_sim_time_arg,

        PushRosNamespace('cube_petit_orange'),

        Node(
            package=package_name,
            executable='internal_state_node',
            name='internal_state_node',
            parameters=[config_file, {'use_sim_time': use_sim_time}],
            output='screen'
        ),

        Node(
            package=package_name,
            executable='sensor_influence_node',
            name='sensor_influence_node',
            parameters=[config_file, {'use_sim_time': use_sim_time}],
            output='screen'
        ),


        Node(
            package=package_name,
            executable='behavior_node',
            name='behavior_node',
            parameters=[config_file, {'use_sim_time': use_sim_time, 'config_se_path': config_se_path}],
            output='screen'
        ),
    ])
