# Cube Petit State Machine (ROS 2 Jazzy)
This repository provides ROS 2 Jazzy state machine nodes for demonstrating the Cube petit robot. <br>
It includes conversation (Talk FSM) and motion (Action FSM) control, <br>
designed with a modular FSM architecture and parameter-driven configuration.

## Supported Environment
- OS: Ubuntu 24.04
- ROS 2: Jazzy Jalisco
- Python: 3.12
- Hardware:
    - Camera (USB / OAK-D)
    - Microphone & Speaker
    - (Optional) OAK AI Camera

## Package Overview

This package contains two FSM nodes:

| FSM	| Description |
| -- | -- |
Talk FSM|	Handles hotword detection, speech recognition, rule-based conversation, GPT conversation
Action FSM|	Handles robot motion such as spinning and gesture-based interaction


A Supervisor FSM coordinates Talk and Action FSMs and manages safety (e.g. emergency stop).

## Features
**Talk FSM**
- Hotword detection (キューブプチ)
- Julius-based speech recognition
- Rule-based conversation via YAML parameters
- GPT-based conversation (online)
- Vision-based interaction (“What can you see?”)

**Action FSM**
- Idle state
- Spin-in-place motion
- Gesture-based rock-paper-scissors

**Design Highlights**
- FSM implemented without SMACH (pure Python FSM)
- Topic / service names externalized via YAML
- Conversation contents defined via YAML parameters
- ROS 2 Jazzy–compatible parameter handling

**Installation**
```bash
cd ~/<COLCON_WORKSPACE>/src
git clone git@github.com:sbgisen/cube_petit_smach_ros.git
cd ~/<COLCON_WORKSPACE>
vcs import src < cube_petit_smach_ros/.rosinstall
rosdep install --from-paths src --ignore-src -r -y
colcon build
```

## Required ROS Packages

The following packages are required depending on enabled features:

- depthai_hand_tracker
    - Used for rock-paper-scissors and vision-based interaction

- cube_speech
    - Used for text-to-speech output

- cube_petit_speech_to_text
    - Used for hotword detection and speech recognition

## Configuration (YAML-based)

All topic names and conversation contents are defined externally.

Topic configuration
`config/topic_names.yaml`

Conversation configuration
`config/conversations.yaml`


Example:
```
/**:
  ros__parameters:
    conversations:
      introduce:
        julius:
          - 自己紹介して
        response:
          - 僕の名前はキューブプチです！

```
This allows changing robot behavior without rebuilding.

## Launch (Minimal Demo)
#### Terminal 1 – Hotword detection
`ros2 launch cube_petit_speech_to_text cube_petit_hotword.launch.py`

#### Terminal 2 – Text-to-speech
`ros2 launch cube_speech cube_speech.launch.py`

#### Terminal 3 – Hand tracker (optional)
`ros2 launch depthai_hand_tracker depthai_hand_tracker.launch.py`

#### Terminal 4 – Speech recognition
`ros2 launch cube_petit_speech_to_text cube_petit_speech_to_text.launch.py`

#### Terminal 5 – FSM demo
`ros2 launch cube_petit_smach_ros demo.launch.py`

### Gazebo Simulation
#### Terminal 1 – Gazebo
`ros2 launch cube_petit_gazebo cube_petit_gazebo.launch.py`

#### Terminal 2 – FSM
`ros2 launch cube_petit_smach_ros demo.launch.py`

## Default Voice Commands
### Basic Commands
Command |	Description
| -- | --| 
こんにちは	|Robot responds with a greeting
自己紹介して|	Robot introduces itself
くるくるして|	Robot spins in place

### Advanced Commands

Command| 	Description
| -- | --|
会話して|	Start GPT-based conversation (online)
何が見える	|Describe what the camera sees
ジャンケンして|	Play rock-paper-scissors

## GPT Conversation

Supported topics
- Introduction
- Robot functions
- Exhibition schedule

Say 「会話を終了して」 to exit GPT conversation mode.

## Rock-Paper-Scissors

- Uses AI camera hand gesture recognition
- Robot randomly selects a hand
- Game result is spoken aloud

## Architecture Summary
```
Supervisor FSM
 ├── Talk FSM
 │    ├── Hotword
 │    ├── Julius
 │    ├── Rule-based conversation
 │    └── GPT conversation
 └── Action FSM
      ├── Idle
      └── Motion / Gesture actions

```

## Notes
- This package is designed for ROS 2 Jazzy
- Rule-based conversations and topics are fully configurable via YAML
- FSM logic and conversation content are intentionally separated

## License
Apache License 2.0
© 2024–2025 SoftBank Corp.

