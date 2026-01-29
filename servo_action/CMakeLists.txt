cmake_minimum_required(VERSION 3.8)
project(servo_action)

find_package(ament_cmake REQUIRED)
find_package(rclpy REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME} "action/SetServoAngle.action")

install(
  PROGRAMS servo_action/servo_action_server.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
