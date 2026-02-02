
import math
import time
from enum import Enum
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from people_msgs.msg import PositionMeasurementArray

from servo_action.action import SetServoAngle
from std_msgs.msg import String


# ================= Utility =================

def quat_to_yaw(q) -> float:
    """Quaternion -> yaw [rad] (-pi, pi]"""
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def unwrap_yaw(prev: Optional[float], curr: float) -> float:
    """Keep yaw continuous across -pi <-> +pi"""
    if prev is None:
        return curr

    diff = curr - prev
    if diff > math.pi:
        curr -= 2.0 * math.pi
    elif diff < -math.pi:
        curr += 2.0 * math.pi
    return curr


# ================= State =================

class Mode(Enum):
    NORMAL = 0
    EMERGENCY = 1


# ================= Node =================

class ServoAutonomous(Node):

    def __init__(self) -> None:
        super().__init__('servo_autonomous')

        # ---------- Parameters ----------
        self.declare_parameter('servo_action_name', 'set_servo_angle')

        self.declare_parameter('emergency_timeout_sec', 5.0)

        self.declare_parameter('arousal_decay_per_sec', 0.01)
        self.declare_parameter('arousal_from_doa', 0.02)
        self.declare_parameter('arousal_from_people', 0.05)
        self.declare_parameter('arousal_emergency', 0.3)

        self.declare_parameter('offset_yaw', -math.pi)
        self.declare_parameter('scale_yaw', 1.0)

        self.declare_parameter('center_deg', 90.0)
        self.declare_parameter('min_deg', 0.0)
        self.declare_parameter('max_deg', 180.0)

        self.declare_parameter('deadband_rad', 0.01)
        self.declare_parameter('max_jump_deg', 90.0)

        self.declare_parameter('slow_time_sec', 3)

        self.declare_parameter('doa_topic', '/doa')
        self.declare_parameter(
            'people_topic',
            '/object_detection/laser/pair_of_legs_position'
        )
        self.declare_parameter('detect_word_topic', '/detect_word')

        self.declare_parameter('enable_sst', True)
        self.declare_parameter('sst_topic', '/julius_result_text')

        self.declare_parameter('enable_doa', True)
        self.declare_parameter('enable_people', True)
        self.declare_parameter('enable_hotword', True)

        self.enable_sst = self.get_parameter('enable_sst').value
        self.enable_doa = self.get_parameter('enable_doa').value
        self.enable_people = self.get_parameter('enable_people').value
        self.enable_hotword = self.get_parameter('enable_hotword').value
        # ---------- Cached params ----------
        self.offset_yaw = float(self.get_parameter('offset_yaw').value)
        self.scale_yaw = float(self.get_parameter('scale_yaw').value)
        self.center_deg = float(self.get_parameter('center_deg').value)
        self.min_deg = float(self.get_parameter('min_deg').value)
        self.max_deg = float(self.get_parameter('max_deg').value)
        self.deadband = float(self.get_parameter('deadband_rad').value)
        self.max_jump_deg = float(self.get_parameter('max_jump_deg').value)

        # ---------- State ----------
        self.mode = Mode.NORMAL
        self.arousal = 0.3

        self.last_emergency_time = 0.0
        self.last_motion_time = 0.0
        self.direction = 1

        self._prev_mode = self.mode

        # yaw / servo state
        self._last_raw_yaw: Optional[float] = None
        self._last_unwrapped_yaw: Optional[float] = None
        self._last_sent_angle: Optional[int] = None
        self._current_goal_handle = None
        self._goal_in_flight = False


        # ---------- Action client ----------
        self.client = ActionClient(
            self,
            SetServoAngle,
            self.get_parameter('servo_action_name').value
        )
        self.get_logger().info('Waiting for servo action server...')
        self.client.wait_for_server()
        self.get_logger().info('Servo action server ready')

        self.declare_parameter('autonomous_send_interval_sec', 1.0)
        self._last_autonomous_send_time = 0.0

        # ---------- Subscriptions ----------

        if self.enable_sst:
            self.create_subscription(
                String,
                self.get_parameter('sst_topic').value,
                self.cb_sst,
                10
            )

        if self.enable_hotword:
            self.create_subscription(
                String,
                self.get_parameter('detect_word_topic').value,
                self.cb_detect_word,
                10,
            )

        if self.enable_doa:
            self.create_subscription(
                PoseStamped,
                self.get_parameter('doa_topic').value,
                self.cb_doa,
                10,
            )

        if self.enable_people:
            self.create_subscription(
                PositionMeasurementArray,
                self.get_parameter('people_topic').value,
                self.cb_people,
                10,
            )

        self._sine_start_time = time.time()

        # ---------- Timer ----------
        self.timer = self.create_timer(0.1, self.on_timer)

    # ================= Callbacks =================

    def update_emergency(self, boost_arousal: bool = False, cancel_goal: bool = True) -> None:
        if cancel_goal and self._current_goal_handle is not None:
            self._current_goal_handle.cancel_goal_async()
            self._current_goal_handle = None

        self.mode = Mode.EMERGENCY
        self.last_emergency_time = time.time()

        if boost_arousal:
            self.arousal = min(
                1.0,
                self.arousal + self.get_parameter('arousal_emergency').value
            )            

    def cb_detect_word(self, msg: String) -> None:
        self.get_logger().info("cb_detect_word")
        if msg.data == 'Cube-petit':
            self.mode = Mode.EMERGENCY
            self.update_emergency(boost_arousal=True)
            if self.enable_doa:
                self.point_to_doa()

    def cb_doa(self, msg: PoseStamped) -> None:
        self.get_logger().info("cb_doa")
        # --- yaw calculation ---
        raw_yaw = quat_to_yaw(msg.pose.orientation)
        raw_yaw += self.offset_yaw

        yaw = unwrap_yaw(self._last_raw_yaw, raw_yaw)

        # deadband
        if self._last_unwrapped_yaw is not None:
            if abs(yaw - self._last_unwrapped_yaw) < self.deadband:
                return

        self._last_raw_yaw = raw_yaw
        self._last_unwrapped_yaw = yaw

        # arousal update
        self.arousal = min(
            1.0,
            self.arousal + self.get_parameter('arousal_from_doa').value
        )

        # if self.mode == Mode.EMERGENCY:
        #     self.update_emergency(boost_arousal=False, cancel_goal=False)

    def cb_people(self, msg: PositionMeasurementArray) -> None:
        if msg.people:
            self.arousal = min(
                1.0,
                self.arousal + self.get_parameter('arousal_from_people').value
            )

    # ================= Core Logic =================

    def on_timer(self) -> None:
        # decay arousal
        self.arousal = max(
            0.0,
            self.arousal
            - self.get_parameter('arousal_decay_per_sec').value * 0.1
        )

        now = time.time()

        # emergency timeout
        if self.mode == Mode.EMERGENCY:
            if now - self.last_emergency_time > self.get_parameter(
                'emergency_timeout_sec'
            ).value:
                self.mode = Mode.NORMAL
            else:
                self._prev_mode = self.mode
                return

        if self._prev_mode == Mode.EMERGENCY and self.mode == Mode.NORMAL:
            center = self.get_parameter('center_deg').value
            self.get_logger().info("send_servo_from on timer")
            self.send_servo(int(center), sec=2)
            self.last_motion_time = time.time()
            self._sine_start_time = time.time()
            

        self._prev_mode = self.mode


        self.autonomous_motion()

    def autonomous_motion(self) -> None:
        now = time.time()
        if now - self._last_autonomous_send_time < float(self.get_parameter('autonomous_send_interval_sec').value):
            return
                
        t = now - self._sine_start_time

        arousal = self.arousal

        amplitude = 30.0 + 60.0 * arousal        # [deg] 30〜90
        period = 60.0 - 50.0 * arousal           # [sec] 60〜10
        omega = 2.0 * math.pi / period
        s = math.sin(omega * t)
        s = math.copysign(abs(s) ** 0.7, s)
        angle = self.center_deg + amplitude * s

        angle = max(self.min_deg, min(self.max_deg, angle))
        angle_i = int(round(angle))

        if self._last_sent_angle is not None:
            if abs(angle_i - self._last_sent_angle) < 3:
                return

        if self._goal_in_flight:
            return

        self._last_sent_angle = angle_i
        self._last_autonomous_send_time = now

        self.send_servo(angle_i)


    # ================= Servo Control =================

    def point_to_doa(self) -> None:
        self.get_logger().info("point_to_doa")
        if self._last_unwrapped_yaw is None:
            return

        deg = math.degrees(self._last_unwrapped_yaw)

        # clamp by ±90°
        if deg <= -90.0:
            angle = self.min_deg
        elif deg >= 90.0:
            angle = self.max_deg
        else:
            angle = self.center_deg + deg * self.scale_yaw

        angle = int(round(angle))

        self.get_logger().info(f"angle: {angle}")
        # jump suppression
        sec = 0
        if self._last_sent_angle is not None:
            if abs(angle - self._last_sent_angle) >= self.max_jump_deg:
                sec = self.get_parameter('slow_time_sec').value

        self._last_sent_angle = angle

        if self._current_goal_handle is not None:
            self._current_goal_handle.cancel_goal_async()
            self._current_goal_handle = None

        self.get_logger().info(f"send_servo_point_to_dos: {angle}")
        self.send_servo(angle, sec=sec, force=True)

    def cb_sst(self, msg: String) -> None:
        if not self.get_parameter('enable_sst').value:
            return

        text = msg.data
        angle = self.direction_to_angle(text)

        if angle is None:
            return

        self.update_emergency(boost_arousal=True)

        if self._current_goal_handle is not None:
            self._current_goal_handle.cancel_goal_async()
            self._current_goal_handle = None

        self.get_logger().info("send_servo_from cb_sst")
        self.send_servo(angle, sec=0, force=True)


    def direction_to_angle(self, text: str) -> Optional[int]:
        center = self.get_parameter('center_deg').value
        min_deg = self.get_parameter('min_deg').value
        max_deg = self.get_parameter('max_deg').value

        if '右' in text:
            self.get_logger().info("migi")
            return min(max_deg, center + 90)
        if '左' in text:
            self.get_logger().info("hidari")
            return max(min_deg, center - 90)
        if '後ろ' in text:
            self.get_logger().info("ushiro")

            return center

        return None

    def send_servo(self, angle: int, sec: Optional[int] = None, force: Optional[bool] = False) -> None:
        if self._goal_in_flight and not force:
            self.get_logger().warn("self._goal_in_flight")
            return
        goal = SetServoAngle.Goal()
        goal.angle = int(angle)

        if sec is not None:
            goal.time_sec = int(sec)
        else:
            goal.time_sec = int(self.get_parameter('slow_time_sec').value)

        self._goal_in_flight = True
        future = self.client.send_goal_async(goal)
        future.add_done_callback(self._goal_response_cb)

    def _goal_response_cb(self, future) -> None:
        goal_handle = future.result()
        self._goal_in_flight = False
        if not goal_handle.accepted:
            self.get_logger().warn("Goal rejected")
            return

        self._current_goal_handle = goal_handle


def main() -> None:
    rclpy.init()
    node = ServoAutonomous()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
