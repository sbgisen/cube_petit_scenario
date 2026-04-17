# cube_petit_web_interface

オレンジプチ（ROS2 Jazzy）用のWebインターフェース。
iPadからロボットの状態確認・操作・会話ができる。

---

## 構成

```
cube_petit_web_interface/
├── frontend/                  # React + TypeScript + Vite (UIアプリ)
│   └── src/
│       ├── App.tsx            # ルートコンポーネント、ロボット選択・タブ切替
│       ├── components/
│       │   ├── MainTab.tsx        # メインタブ（マップ＋ジョイスティック＋会話）
│       │   ├── MapView.tsx        # 2Dマップ（LiDAR・人・DOA・ロボット）
│       │   ├── MapView3D.tsx      # 3Dマップ（Three.js）
│       │   ├── Joystick.tsx       # 仮想ジョイスティック
│       │   ├── ConversationPanel.tsx  # 会話パネル
│       │   └── SystemPanel.tsx    # ノード死活・launch制御
│       ├── hooks/
│       │   ├── useRosConnection.ts  # rosbridge WebSocket接続管理
│       │   ├── useRosTopic.ts       # トピック購読
│       │   └── useRosService.ts     # サービス呼び出し
│       └── types/ros.ts            # 型定義
├── cube_petit_web_interface/
│   └── api_server.py          # FastAPI バックエンド（launch制御）
└── img/                       # ロボットアイコン画像
```

---

## 起動方法

### 前提
- rosbridge が起動していること（port 9090）
- Node.js 20以上（nvmでインストール済み）

```bash
# Node 20を有効化（新しいターミナルを開くたびに必要）
source ~/.nvm/nvm.sh && nvm use 20
```

### 開発サーバー（ファイル変更が即反映）

```bash
cd ~/ros/src/cube_petit_scenario/cube_petit_web_interface/frontend

# ローカルのみ
npm run dev

# iPad・他端末からもアクセスする場合
npm run dev -- --host
```

アクセス先：
- PC: `http://localhost:5173`
- iPad: `http://192.168.8.107:5173`（ロボットPCと同じWi-Fiに接続する）

### 本番ビルド

```bash
npm run build   # dist/ フォルダに出力
npm run preview # ビルド結果の動作確認
```

### APIサーバー（launch制御用）

```bash
cd ~/ros/src/cube_petit_scenario/cube_petit_web_interface
python3 cube_petit_web_interface/api_server.py
# → http://localhost:8000 で起動
```

---

## 機能

### メインタブ

| 機能 | 説明 |
|------|------|
| 2D/3D マップ | LiDAR点群・人検出・DOA方向・ロボット位置を表示。ピンチ/ホイールでズーム、ドラッグでパン、2本指で回転 |
| レイヤー切替 | LiDAR・人・DOA・カメラをボタンでON/OFF |
| 2D/3D切替 | ボタンで2Dキャンバス表示と3D（Three.js）表示を切替 |
| ジョイスティック | 画面上の仮想スティックでロボット移動操作。`cmd_vel`（TwistStamped）をパブリッシュ |
| 会話 | テキスト入力でロボットに文脈追加。会話内容をリアルタイム表示 |

### システムタブ

| 機能 | 説明 |
|------|------|
| ノード監視 | 主要ノードの生死を3秒ごとに確認して表示 |
| Bringup起動/停止 | `cube_petit_bringup` の起動・停止 |
| Demo起動/停止 | `cube_petit_talk_demo` の起動・停止 |

---

## ROSトピック・サービス

| 種別 | 名前 | 型 |
|------|------|----|
| Subscribe | `/{namespace}/scan` | `sensor_msgs/LaserScan` |
| Subscribe | `/object_detection/laser/marker` | `visualization_msgs/MarkerArray` |
| Subscribe | `/{namespace}/doa` | `geometry_msgs/PoseStamped` |
| Subscribe | `/{namespace}/realtime_conversation_content` | - |
| Publish | `/{namespace}/diff_drive_controller/cmd_vel` | `geometry_msgs/TwistStamped` |
| Service | `/{namespace}/enable_realtime_conversation` | `std_srvs/SetBool` |
| Service | `/{namespace}/add_realtime_context` | - |

デフォルトのnamespace: `cube_petit_orange`

---

## 接続先の変更

`frontend/src/App.tsx` の `ROBOTS` 配列を編集する：

```ts
const ROBOTS: RobotConfig[] = [
  {
    name: 'オレンジプチ',
    namespace: 'cube_petit_orange',
    rosbridgeUrl: 'ws://192.168.8.107:9090', // iPadから直接接続する場合
  },
];
```

---

## 依存パッケージ

| パッケージ | 用途 |
|-----------|------|
| React 19 + TypeScript | UIフレームワーク |
| Vite 8 | ビルドツール・開発サーバー |
| roslib 2 | rosbridge WebSocket通信 |
| Three.js 0.184 | 3Dマップ描画 |
| MUI (Material-UI) | UIコンポーネント・アイコン |
| FastAPI | launch制御APIサーバー |
