# servo_action

Arduino（サーボ）を **ROS 2 Action** として制御するためのパッケージです。

- Arduino とは **シリアル通信**
- ROS 2 側では **Action (Goal / Result / Cancel)** を使用
- 角度指定（0–180°）、移動時間（秒指定）、キャンセルに対応

---

## できること

- サーボを **指定角度** に動かす
- **n 秒かけて**ゆっくり移動させる
- 実行中に **Cancel（即停止）**
- ゴール到達時に Result を返す

---

## 構成

```
[ ROS 2 Action Client ]
          |
          |  Action (SetServoAngle)
          v
[ servo_action_server ]
          |
          |  Serial (SET / CANCEL)
          v
[ Arduino + Servo ]
```

---

## Action 定義

`servo_action/action/SetServoAngle.action`

```text
# Goal
int32 angle        # 0–180
int32 time_sec     # 0 = immediate, 1 = 1秒, 2 = 2秒 ...

---
# Result
bool success
int32 final_angle

---
# Feedback
int32 current_angle
```

---

## Arduino 側のプロトコル（前提）

Arduino は以下のテキストプロトコルを実装している前提です。

### 受信

```
SET <angle> <time_sec>
CANCEL
```

例：
```
SET 90 0   # 即時 90°
SET 0 2    # 2秒で 0°
CANCEL     # 即停止
```

### 送信

```
ANGLE:<angle>   # ゴール到達時
CANCELED        # キャンセル時
```

---

## ビルド

```bash
cd ~/ros2_ws
colcon build
source install/setup.bash
```

---

## 起動

```bash
ros2 run servo_action servo_action_server.py --ros-args -p serial_port:=/dev/ttyUSB0
```

起動すると Arduino と接続し、Action Server として待機します。

---

## 使い方（コマンドライン）

### Action 一覧

```bash
ros2 action list
```

```
/set_servo_angle
```

---

### 即時で 90°

```bash
ros2 action send_goal \
  /set_servo_angle \
  servo_action/action/SetServoAngle \
  "{angle: 90, time_sec: 0}"
```

---

### 1秒で 0°

```bash
ros2 action send_goal \
  /set_servo_angle \
  servo_action/action/SetServoAngle \
  "{angle: 0, time_sec: 1}"
```

---

### 2秒で 180°

```bash
ros2 action send_goal \
  /set_servo_angle \
  servo_action/action/SetServoAngle \
  "{angle: 180, time_sec: 2}"
```

---

### 実行中にキャンセル

```bash
ros2 action cancel /set_servo_angle
```

- サーボはその場で停止
- Action は `CANCELED`

---

## よくある使い方

### 0–180° を繰り返す（テスト用）

```bash
while true; do
  ros2 action send_goal /set_servo_angle servo_action/action/SetServoAngle "{angle: 0, time_sec: 2}"
  ros2 action send_goal /set_servo_angle servo_action/action/SetServoAngle "{angle: 180, time_sec: 2}"
done
```

※ 実運用では **Action Client ノード**として実装するのがおすすめです。

---

## 注意事項

- 本サーボ（MG90D 等）は **実角度を取得できません**
  - `ANGLE:` は制御上の到達角度
- 正確な実角度が必要な場合は
  - AS5600 等の **絶対角度エンコーダ**を追加してください

---

## 拡張アイデア

- Feedback に現在角度を publish
- シリアルポートを ROS parameter 化
- 複数サーボ対応（ID付き Action）
- `FollowJointTrajectory` 互換 Action への拡張

---

## 対応環境

- ROS 2 Jazzy
- Python 3.12
- Arduino Nano + Servo

---

## ライセンス

Apache License 2.0

---

## メモ

このパッケージは
**「Arduino 実機制御を ROS 2 Action として安全に扱う」**
ための最小・実用構成です。

展示・実験・デモ用途を想定しています。
