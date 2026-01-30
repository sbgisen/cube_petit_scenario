cmake_minimum_required(VERSION 3.8)
project(pose_to_servo)


find_package(ament_cmake REQUIRED)
find_package(rclpy REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(action_msgs REQUIRED)
find_package(servo_action REQUIRED)


install(
PROGRAMS
pose_to_servo/pose_to_servo_node.py
DESTINATION lib/${PROJECT_NAME}
)


ament_package()
