# cube_petit_anima

Existential and motivational core layer for CubePetit.

CubePetit の「存在（anima）」を司るパッケージです。  
センサ値や外界の影響を統合し、内的状態を生成・維持します。

This package does not control hardware directly.  
It maintains an internal motivational state and publishes it as `InternalState`.

---

## 🌱 Concept

CubePetit is not designed as a reactive assistant.

It is designed as:

- A small presence
- A drifting intelligence
- A being with continuity

The anima layer is responsible for:

- Curiosity
- Boredom
- Energy
- Silence tendency
- Sleep cycle
- Presence detection

Sensors influence the anima,  
but anima remains the final authority.

---

## 🧠 Architecture

[sensors]
↓
sensor_influence_node
↓
/internal_state_delta
↓
cube_petit_anima (internal_state_node)
↓
/internal_state
↓
behavior_node
↓
motion / speech

yaml
コードをコピーする

---

## 📦 Nodes

### internal_state_node

- Maintains InternalState
- Applies drift and delta aggregation
- Handles sleep hysteresis
- Saves state locally
- Restores state on startup

Publishes:

/internal_state (cube_petit_scenario_msgs/msg/InternalState)

makefile
コードをコピーする

Subscribes:

/internal_state_delta (cube_petit_scenario_msgs/msg/InternalStateDelta)

yaml
コードをコピーする

---

### behavior_node

- Reads InternalState
- Decides motion
- Triggers speech
- Does not modify state

Publishes:

/diff_drive_controller/cmd_vel
/speech_action_server (action)

yaml
コードをコピーする

---

## 💾 State Persistence

State is stored locally at:

~/.cube_petit/<hostname>/anima_state.json

csharp
コードをコピーする

Hostname is converted:

cube-petit-pink → cube_petit_pink

yaml
コードをコピーする

State survives reboot.

---

## 💤 Sleep Logic

Sleep hysteresis:

- Enter sleep: energy ≤ 20
- Wake up: energy ≥ 60

Sleep mode:

- Energy regenerates
- Boredom decreases

---

## 🎛 InternalState Fields

- curiosity
- boredom
- energy
- silence_bias
- body_generation
- human_detected
- petit_detected
- sleep_mode

Values range from 0.0 to 100.0 unless otherwise specified.

---

## 🔌 Sensor Integration

Sensors should not modify state directly.

Instead, publish `InternalStateDelta`:

Example:

```python
delta.d_curiosity = 5.0
delta.weight = 0.8
delta.source = "mic"
Anima aggregates all deltas once per second.

🚀 Launch
bash

ros2 launch cube_petit_anima anima.launch.py
🎯 Design Philosophy
State has continuity.

Sensors influence, but do not control.

Sleep is gradual.

Motion and speech emerge from internal condition.

The robot does not react instantly to everything.

CubePetit is not optimized for utility.

It is optimized for presence.

📖 Future Extensions
Long-term memory fragments

Personality drift over body generations

Peer interaction (petit_detected)

Cloud backup encryption

Emotion-coupled motion

License
Copyright (c) 2026 SoftBank Corp.
