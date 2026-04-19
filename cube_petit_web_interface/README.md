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
│       │   ├── SystemPanel.tsx    # システムタブ（launch 制御・ノード監視）
│       │   ├── CustomTab.tsx      # カスタム会話タブ
│       │   ├── MapTab.tsx         # カスタムマップタブ（ポイント・部屋編集）
│       │   ├── MapView.tsx        # 2D マップ（Canvas）
│       │   ├── MapView3D.tsx      # 3D マップ（Three.js）
│       │   ├── Joystick.tsx       # 仮想ジョイスティック
│       │   ├── CameraView.tsx     # カメラ映像
│       │   └── QuickPhraseGrid.tsx
│       └── hooks/
│           ├── useRosConnection.ts
│           ├── useRosTopic.ts
│           ├── useRosTf.ts        # /tf 直接購読・チェーン合成
│           ├── useRosAction.ts
│           └── useRosService.ts
├── cube_petit_web_interface/
│   ├── api_server.py          # FastAPI バックエンド（launch 制御・マップ管理）
│   └── internal_state_relay.py
└── img/                       # ロボットアイコン画像
```

### 通信ポート

| 用途 | ポート | プロトコル |
|------|--------|-----------|
| フロントエンド | 5173 | HTTP |
| バックエンド API | 8000 | HTTP |
| rosbridge | 9090 | WebSocket |

---

## 起動手順（手動）

### 1. rosbridge の起動

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

### 2. バックエンド API サーバーの起動

```bash
cd ~/ros/src/cube_petit_scenario/cube_petit_web_interface
source /opt/ros/jazzy/setup.bash
source ~/ros/install/setup.bash
python3 -m uvicorn cube_petit_web_interface.api_server:app --host 0.0.0.0 --port 8000
```

### 3. フロントエンドの起動（手動時のみ）

PC 起動時の自動起動が設定済みの場合は不要。

```bash
source ~/.nvm/nvm.sh && nvm use 20
cd ~/ros/src/cube_petit_scenario/cube_petit_web_interface/frontend
npm run dev
```

### 4. ブラウザでアクセス

| 端末 | URL |
|------|-----|
| ロボット PC | `http://localhost:5173` |
| iPad / 他端末 | `http://<ロボットのIPアドレス>:5173` |

> iPad から `localhost` は使えない。同一 LAN に接続して IP アドレスでアクセスする。

---

## フロントエンド自動起動（systemd サービス）

PC 起動時にフロントエンドが自動で立ち上がるよう、systemd ユーザーサービスとして登録している。

### サービスファイル

`~/.config/systemd/user/cube-petit-frontend.service`

```ini
[Unit]
Description=Cube Petit Web Interface Frontend (Vite)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/cube-petit/ros/src/cube_petit_scenario/cube_petit_web_interface/frontend
ExecStart=/home/cube-petit/.nvm/versions/node/v20.20.2/bin/npm run dev -- --host
Restart=on-failure
RestartSec=5
Environment=PATH=/home/cube-petit/.nvm/versions/node/v20.20.2/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=default.target
```

### 導入手順

```bash
# 1. サービスファイルを配置
mkdir -p ~/.config/systemd/user/
# 上記の内容で ~/.config/systemd/user/cube-petit-frontend.service を作成

# 2. systemd に読み込ませる
systemctl --user daemon-reload

# 3. 自動起動を有効化してすぐ起動
systemctl --user enable --now cube-petit-frontend.service

# 4. ログイン不要で起動するよう linger を有効化
loginctl enable-linger cube-petit
```

### 管理コマンド

```bash
systemctl --user status  cube-petit-frontend   # 状態確認
systemctl --user start   cube-petit-frontend   # 起動
systemctl --user stop    cube-petit-frontend   # 停止
systemctl --user restart cube-petit-frontend   # 再起動
journalctl --user -u cube-petit-frontend -f    # ログ追跡
```

> `vite.config.ts` でポートを 5173 固定・`strictPort: true` に設定済み。
> ポートが競合している場合はサービス起動に失敗するので `lsof -ti :5173 | xargs kill -9` で解放する。

---

## ロボット側の起動

### 基本起動（bringup）

Web UI の「起動管理」から起動できる。手動の場合：

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch cube_petit_bringup cube_petit_bringup.launch.py
```

### ナビゲーション（自律走行）

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  ros2 launch cube_petit_navigation navigation.launch.py \
  map:=/path/to/map.yaml \
  keepout:=/path/to/map_keepout.yaml
```

Web UI の「システム」タブ → 起動管理 → navigation からも起動可能。マップ・keepout はドロップダウンで選択する（選択すると自動でフルパスに変換される）。

ナビゲーションが起動すると emcl2 が `map` TF を配信し、Web UI の map フレーム表示・ナビゲーションゴール送信が使えるようになる。

### マップの保存場所

| ディレクトリ | 用途 |
|------------|------|
| `~/ros/src/cube_petit_ros/cube_petit_navigation/map/` | 既定マップ |
| `~/map/` | Web UI から保存したマップ |

各マップフォルダの構成：

```
<マップ名>/
├── map.yaml / map.pgm          # 本体マップ
├── map_keepout.yaml / .pgm     # keepout マスク
├── places.yaml                 # ポイント一覧
└── rooms.yaml                  # 部屋範囲一覧
```

---

## 操作タブの使い方

### レイヤーボタン

画面上部のボタンで各レイヤーの表示を切り替える（オレンジ = ON）。

| ボタン | 表示内容 |
|--------|---------|
| LiDAR | LiDAR 点群（緑） |
| カメラ | カメラ映像（右カラム） |
| 音源 | DOA 方向矢印（黄色） |
| 人 | 検出した人のアイコン（赤） |
| マップ | 占有格子地図 |
| コスト | ローカルコストマップ（ピンク） |
| プラン | グローバルプラン（緑）・ローカルプラン（黄） |
| ポイント | places / rooms を地図上に重ね表示（紫 = ON）|

「ポイント」ボタンの右のドロップダウンで表示するマップを切り替えられる。navigation 起動時に使用したマップが自動で選択される。

### フレーム切り替え

| ボタン | 挙動 |
|--------|------|
| base | ロボットが常に中心。周囲が回転・移動する |
| odom | odom 原点が中心。ロボットが移動する |
| map | 地図が固定。ロボットが地図上を移動する（要ナビゲーション） |

フレームを切り替えると自動でロボットが画面中心にセンタリングされる。

### 操作モード

| ボタン | 操作 |
|--------|------|
| 🔄 操作 | ドラッグ: パン / ピンチ: ズーム / 2本指: 回転 |
| 📍 目標 | タップ: 目標位置を置く / そのままドラッグ: 向きを設定して送信 |
| 📌 初期 | タップ＆ドラッグで自己位置の初期値を設定して送信 |

> 目標・初期位置はタップを離したタイミングで ROS に送信される。

### 2D / 3D 切り替え

- **2D**: キャンバスベースの軽量マップ
- **3D**: Three.js による 3D 表示（目標・初期モード中は 2D に固定）

### ジョイスティック

画面右下に固定表示。ドラッグで並進・回転指令を送信する。

---

## システムタブの使い方

### 起動管理

各 launch をボタンで起動・停止できる。「ROS一括停止」ですべて終了。

| launch | 内容 |
|--------|------|
| bringup | ロボット基本起動 |
| anima | 感情・行動システム |
| demo | 音声会話デモ |
| create_map | SLAM マップ作成 |
| navigation | 自律走行（マップ・keepout 選択あり） |

### コマンドログ

起動・停止の操作履歴をタイムスタンプ付きで表示する。

### デバイス状態

CAN0・LiDAR・IMU・CANable・RealSense・OAK の接続状態を表示。

### ノード監視

主要ノードの稼働状態をリアルタイムで確認できる。

---

## カスタムマップタブの使い方

地図上にポイント（places）と部屋範囲（rooms）を登録・編集する。

### モード

| ボタン | 操作 |
|--------|------|
| 🖊 マップ編集 | keepout マスクを描画・消去 |
| 📍 ポイント追加 | クリックで地図上にポイントを配置（カテゴリ・名前を指定） |
| 🏠 部屋範囲 | 矩形または多角形で部屋の領域を指定 |
| ✏️ 名前変更 | ポイント・部屋の名前をインライン編集 |

### データの保存場所

各マップフォルダの `places.yaml` / `rooms.yaml` に保存される。

---

## 会話タブの使い方

- テキスト入力でロボットへの文脈追加・発話指示
- 会話内容がリアルタイムで表示される
- **クイックフレーズ**: 登録した定型文をボタン 1 タップで発話
  - 「＋」ボタンで新しいフレーズを追加

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

`localhost` は使えない。ロボットの IP アドレスでアクセスする（例: `http://192.168.1.16:5173`）。

### フロントエンドが起動していない

```bash
systemctl --user status cube-petit-frontend
journalctl --user -u cube-petit-frontend -n 30
```

ポート競合の場合:

```bash
lsof -ti :5173 | xargs kill -9
systemctl --user restart cube-petit-frontend
```

### map フレームで何も動かない

ナビゲーション（emcl2）が未起動の可能性がある。`/tf` に `map` フレームが流れているか確認：

```bash
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ros2 topic echo /tf --once 2>/dev/null | grep frame_id
```

`frame_id: map` が含まれていれば TF は正常。

> `amcl_pose` トピックは使用しない。ロボットの map 座標は TF から取得している。

### keepout がずれる・動く

`local_costmap` の `global_frame` が `odom` のため、keepout フィルターはグローバルコストマップのみに適用する設定にしている（`nav2_params_orange.yaml` の `local_costmap.filters` は空）。

### Node.js バージョンエラー

Vite 8 は Node.js 20 以上が必要：

```bash
source ~/.nvm/nvm.sh && nvm use 20
```
