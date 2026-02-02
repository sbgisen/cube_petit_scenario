# Cube_Petit_Smach_ROS
This is ROS2 package for Cube petit Demonstration State Machine

## Install

```
cd ~/<COLCON_WORKSPACE>/src
git clone git@github.com:sbgisen/cube_petit_smach_ros.git
cd ~/<COLCON_WORKSPACE>/
vcs import src < cube_petit_smach_ros/.rosinstall
rosdep install --from-paths src --ignore-src -r -y
colcon build
```

## Need Ros Package

- `depthai_hand_tracker`: To use Rock-Paper-Scissors and What robot can see.
- `cube_speech`: To use Talking API

## Hardware & Software

- Ubuntu22.04
- ROS humble
- camera
- microphone & speaker
- (optional) OAK AI Camera

## Minimam Launch

Terminal1
```
ros2 launch cube_petit_speech_to_text cube_petit_hotword.launch.py
```
Terminal2
```
ros2 launch cube_speech cube_speech.launch.py
```
Terminal3
```
ros2 launch depthai_hand_tracker depthai_hand_tracker.launch.py
```
Terminal4
```
ros2 launch cube_petit_speech_to_text cube_petit_speech_to_text.launch.py
```
Terminal5
```
ros2 launch cube_petit_smach_ros demo.launch.py
```

## Launch Gazebo
Terminal1
```
ros2 launch cube_petit_gazebo cube_petit_gazebo.launch.py
```
Terminal2
```
ros2 launch cube_petit_smach_ros demo.launch.py
```

## Summary of State Machine
There are 2 State Machines: 
- Talk demo is about conversation function
- Action demo is about robot's movement function.

### State Machine
最初にホットワードを受け付けます。キューブプチと認識したら命令を受け付けます。
デフォルトで以下の命令があります。
The system first listens for a hotword. Once it recognizes "Cube Petit," it will accept commands. The default commands are:

- `こんにちは(Hello)`: ロボットがこんにちはと返します (The robot will respond with "Hello")
- `自己紹介して(Introduce yourself)`: ロボットが自己紹介します (The robot will introduce itself)
- `くるくるして(Spin around)`: ロボットがその場旋回します (The robot will spin in place)

追加で以下の命令があります。
Additionally, the following commands are available:
- (オンライン:Online)`会話して(Have a conversation)`: ChatGPTを使った会話ができます。終了したいときは会話を終了してといいます。You can converse using ChatGPT. Say "End conversation" to stop.
- (オンライン:Online)`何が見える(What can you see)`: AIカメラを使って何が見えるか答えます。前面カメラに顔を近づけてください。The AI camera will describe what it sees. Please bring your face close to the front camera.
- `ジャンケンして(Rock-paper-scissors)`: AIカメラを使ったジャンケンができます。前面カメラと平行になるように手を出してください。You can play rock-paper-scissors with the AI camera. Place your hand parallel to the front camera.

**GPT会話(GPT Conversation)**

話せること：自己紹介、機能、展示の予定<br>
Topics: Introduction, functions, exhibition schedule

**ジャンケン(Rock-paper-scissors)**

じゃんけんができます。ランダムで手を出します。<br>
You can play rock-paper-scissors. The robot will randomly choose a hand.
