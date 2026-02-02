# servo_autonomous

Autonomous servo behavior package for Cube petit.

This node controls a servo motor in a calm, lifelike manner based on
an internal **arousal level** that changes over time and external stimuli.

---

## Concept

The servo normally moves in a slow, wandering motion.
When stimuli are detected (sound direction, people nearby),
the arousal level increases and the motion becomes more active.

A special **emergency interrupt** allows the servo to immediately
react to a wake word.

---

## States

### NORMAL
- Servo moves autonomously
- Motion frequency depends on arousal level

### EMERGENCY
- Triggered by a keyword on `/detect_word`
- Servo immediately points to sound direction
- Automatically returns to NORMAL after a timeout

---

## Arousal Model

- Arousal value ranges from `0.0` to `1.0`
- Naturally decays over time
- Increases with:
  - DOA input
  - People detection
  - (Easy to extend with new topics)

---

## Topics

### Subscribed

| Topic | Type | Description |
|------|------|-------------|
| `/doa` | `geometry_msgs/PoseStamped` | Direction of arrival |
| `/object_detection/laser/pair_of_legs_position` | `people_msgs/PositionMeasurementArray` | People detection |
| `/detect_word` | `std_msgs/String` | Wake word trigger |

### Action

| Action | Type |
|------|------|
| `set_servo_angle` | `servo_action/SetServoAngle` |

---

## Parameters

All parameters are defined in:

`config/servo_autonomous.yaml`


The config file contains:
- Servo limits and speed
- Arousal decay and increments
- Motion intervals for each arousal level
- Emergency behavior settings
- Topic names

The YAML file itself serves as documentation.

---

## Usage

### Build

```bash
colcon build --packages-select servo_autonomous
source install/setup.bash
```

### Launch
```bash
ros2 launch servo_autonomous servo_autonomous.launch.py
```

### Design Philosophy

- Minimal state machine
- Parameter-driven behavior
- Easy to extend with new stimuli
- Designed for lifelike, non-deterministic motion

This package is intended to be a core behavioral layer
for Cube petit.
