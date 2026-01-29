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

import threading
import time
from typing import Optional

import rclpy
from rclpy.action import ActionServer
from rclpy.action import CancelResponse
from rclpy.action import GoalResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.node import Node
import serial

from servo_action.action import SetServoAngle


class ServoActionServer(Node):

    def __init__(self) -> None:
        super().__init__('servo_action_server')
        self.declare_parameter('serial_port', '/dev/ttyUSB0')

        serial_port: str = (self.get_parameter('serial_port').get_parameter_value().string_value)

        self.get_logger().info(f'Using serial port: {serial_port}')

        self._action_server: ActionServer = ActionServer(
            self,
            SetServoAngle,
            'set_servo_angle',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )

        self.ser: serial.Serial = serial.Serial(serial_port, 115200, timeout=0.1)
        time.sleep(2)  # Arduino reset wait

        self._lock: threading.Lock = threading.Lock()
        self._latest_angle: Optional[int] = None

        self._reader_thread: threading.Thread = threading.Thread(target=self.serial_reader, daemon=True)
        self._reader_thread.start()

    # ---------- Serial reader ----------
    def serial_reader(self) -> None:
        while rclpy.ok():
            try:
                line: str = self.ser.readline().decode().strip()
            except UnicodeDecodeError:
                continue

            if line.startswith('ANGLE:'):
                try:
                    angle: int = int(line.split(':')[1])
                except ValueError:
                    continue

                with self._lock:
                    self._latest_angle = angle

    # ---------- Action callbacks ----------
    def goal_callback(
        self,
        goal_request: SetServoAngle.Goal,
    ) -> GoalResponse:
        self.get_logger().info(f'Goal received: angle={goal_request.angle}, time={goal_request.time_sec}')
        return GoalResponse.ACCEPT

    def cancel_callback(
        self,
        goal_handle: ServerGoalHandle,
    ) -> CancelResponse:
        self.get_logger().info('Cancel requested')
        self.ser.write(b'CANCEL\n')
        return CancelResponse.ACCEPT

    async def execute_callback(
        self,
        goal_handle: ServerGoalHandle,
    ) -> SetServoAngle.Result:

        angle: int = goal_handle.request.angle
        time_sec: int = goal_handle.request.time_sec

        cmd: str = f'SET {angle} {time_sec}\n'
        self.ser.write(cmd.encode())

        result: SetServoAngle.Result = SetServoAngle.Result()

        while rclpy.ok():
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                return result

            with self._lock:
                if self._latest_angle == angle:
                    result.success = True
                    result.final_angle = angle
                    goal_handle.succeed()
                    return result

            time.sleep(0.05)

        result.success = False
        return result

    def destroy(self) -> None:
        self._action_server.destroy()
        self.ser.close()


def main() -> None:
    rclpy.init()
    node: ServoActionServer = ServoActionServer()
    rclpy.spin(node)
    node.destroy()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
