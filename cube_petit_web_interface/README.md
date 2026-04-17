# cube_petit_web_interface

CubePetit ロボット（ROS2 Jazzy）操作・監視用 Web インターフェース。
iPad / PC のブラウザからリアルタイム操作・地図確認・音声会話が行える。

---

## 構成

```
cube_petit_web_interface/
├── frontend/                  # React + TypeScript + Vite (UIアプリ)
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── OperationTab.tsx   # 操作タブ（マップ・ジョイスティック・カメラ）
│       │   ├── TalkTab.tsx        # 会話タブ
│       │   ├── MapView.tsx        # 2D マップ
│       │   ├── MapView3D.tsx      # 3D マップ（Three.js）
│       │   ├── Joystick.tsx       # 仮想ジョイスティック
│       │   ├── CameraView.tsx     # カメラ映像
│       │   ├── QuickPhraseGrid.tsx
│       │   └── SystemPanel.tsx    # ノード死活・launch 制御
│       └── hooks/
│           ├── useRosConnection.ts
│           ├── useRosTopic.ts
│           ├── useRosTf.ts        # /tf 直接購読・チェーン合成
│           ├── useRosAction.ts
│           └── useRosService.ts
├── cube_petit_web_interface/
│   ├── api_server.py          # FastAPI バックエンド（launch 制御）
│   └── internal_state_relay.py
└── img/                       # ロボットアイコン画像
```

### 通信ポート

| 用途 | ポート | プロトコル |
|------|--------|-----------|
| フロントエンド (dev) | 5173 | HTTP |
| バックエンド API | 8000 | HTTP |
| rosbridge | 9090 | WebSocket |

---

## 起動手順

### 1. rosbridge の起動

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

### 2. バックエンド API サーバーの起動

```bash
cd ~/ros/src/cube_petit_scenario/cube_petit_web_interface
python3 cube_petit_web_interface/api_server.py
```

### 3. フロントエンド開発サーバーの起動

Node.js 20 以上が必要。nvm を使う場合：

```bash
source ~/.nvm/nvm.sh && nvm use 20
cd ~/ros/src/cube_petit_scenario/cube_petit_web_interface/frontend
npm run dev -- --host
```

### 4. ブラウザでアクセス

| 端末 | URL |
|------|-----|
| ロボット PC | `http://localhost:5173` |
| iPad / 他端末 | `http://<ロボットのIPアドレス>:5173` |

> iPad から `localhost` は使えない。同一 LAN に接続してIPアドレスでアクセスする。

---

## ロボット側の起動

### 基本起動（bringup）

Web UI の「起動」ボタンから起動できる。手動の場合：

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch cube_petit_bringup cube_petit_bringup.launch.py
```

### ナビゲーション（map フレーム・自律走行）

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch cube_petit_navigation navigation_orange.launch.py \
  map:=/path/to/map.yaml \
  keepout:=/path/to/keepout.yaml
```

ナビゲーションが起動すると emcl2 が `map` TF を配信し、Web UI の map フレーム表示・ナビゲーションゴール送信が使えるようになる。

### デモ（音声会話）

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch cube_petit_scenario cube_petit_talk_demo.launch.py
```

---

## 操作タブの使い方

### レイヤーボタン

画面上部のボタンで各レイヤーの表示を切り替える（オレンジ = ON）。

| ボタン | 表示内容 |
|--------|---------|
| LiDAR | LiDAR 点群（緑） |
| カメラ | カメラ映像（右カラム） |
| 音源方向 | DOA 方向矢印（黄色） |
| 人 | 検出した人のアイコン（赤） |
| マップ | 占有格子地図 |
| コスト | ローカルコストマップ（ピンク） |
| プラン | グローバルプラン（緑）・ローカルプラン（黄） |

### フレーム切り替え

| ボタン | 挙動 |
|--------|------|
| base_link | ロボットが常に中心。周囲が回転・移動する |
| odom | odom 原点が中心。ロボットが移動する |
| map | 地図が固定。ロボットが地図上を移動する（要ナビゲーション） |

フレームを切り替えると自動でロボットが画面中心にセンタリングされる。

### 操作モード

| ボタン | 操作 |
|--------|------|
| 🔄 操作 | ドラッグ: パン / ピンチ: ズーム / 2本指: 回転 |
| 📍 目標 | タップ: 目標位置を置く / そのままドラッグ: 向きを設定して送信 |
| 📌 初期位置 | タップ＆ドラッグで自己位置の初期値を設定して送信 |

> 目標・初期位置はタップを離したタイミングで ROS に送信される。

### 2D / 3D 切り替え

- **2D**: キャンバスベースの軽量マップ
- **3D**: Three.js による 3D 表示（目標・初期位置モード中は 2D に固定）

### ジョイスティック

画面右下に固定表示。ドラッグで並進・回転指令を送信する。

---

## 会話タブの使い方

- テキスト入力でロボットへの文脈追加・発話指示
- 会話内容がリアルタイムで表示される
- **クイックフレーズ**: 登録した定型文をボタン 1 タップで発話
  - 「＋」ボタンで新しいフレーズを追加

---

## システムパネル

右上のメニューアイコンから開く。

- **ノード監視**: 主要ノードの稼働状態を確認
- **起動 / 停止**: bringup・demo の起動・停止

---

## ROSトピック・サービス一覧

| 種別 | 名前 | 型 |
|------|------|----|
| Sub | `/{ns}/scan` | `sensor_msgs/LaserScan` |
| Sub | `/object_detection/laser/marker` | `visualization_msgs/MarkerArray` |
| Sub | `/{ns}/doa` | `geometry_msgs/PoseStamped` |
| Sub | `/{ns}/odom` | `nav_msgs/Odometry` |
| Sub | `/{ns}/navigation/map` | `nav_msgs/OccupancyGrid` |
| Sub | `/{ns}/navigation/local_costmap/costmap` | `nav_msgs/OccupancyGrid` |
| Sub | `/{ns}/navigation/plan` | `nav_msgs/Path` |
| Sub | `/{ns}/navigation/local_plan` | `nav_msgs/Path` |
| Sub | `/tf`, `/tf_static` | `tf2_msgs/TFMessage` |
| Pub | `/{ns}/diff_drive_controller/cmd_vel` | `geometry_msgs/TwistStamped` |
| Pub | `/{ns}/navigation/goal_pose` | `geometry_msgs/PoseStamped` |
| Pub | `/{ns}/navigation/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` |
| Action | `/{ns}/speech_action_server` | `cube_petit_speech_msgs/action/Speech` |

`{ns}` のデフォルト: `cube_petit_orange`

---

## トラブルシューティング

### iPad から接続できない

`localhost` は使えない。`--host` オプションつきで dev サーバーを起動し、ロボットの IP アドレスでアクセスする。

### 接続が点滅する

切断表示には 2 秒の遅延がある。短時間の再接続なら UI には表示されない。

### map フレームで何も動かない

ナビゲーション（emcl2）が未起動の可能性がある。`/tf` に `map` フレームが流れているか確認：

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ros2 topic echo /tf --once 2>/dev/null | grep frame_id
```

`frame_id: map` が含まれていれば TF は正常。

> `amcl_pose` トピックは使用しない。ロボットの map 座標は TF から取得している。

### Node.js バージョンエラー

Vite 8 は Node.js 20 以上が必要：

```bash
source ~/.nvm/nvm.sh && nvm use 20
```

---

## 設定変更

### ロボットの追加・変更

`frontend/src/App.tsx` の `ROBOTS` 配列を編集：

```typescript
const ROBOTS = [
  {
    name: 'オレンジプチ',
    namespace: 'cube_petit_orange',
    rosbridgeUrl: `ws://${HOST}:9090`,
  },
];
```

### rosbridge ポートの変更

`App.tsx` の `rosbridgeUrl` と rosbridge の起動引数を合わせて変更する。
