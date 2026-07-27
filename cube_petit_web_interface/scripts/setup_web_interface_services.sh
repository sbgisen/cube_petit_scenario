#!/usr/bin/env bash
# cube_petit_web_interface の永続サービス(systemd --user)をこのマシンにセットアップする。
# 新しい機体(pink/yellow/...)でも同じ手順で使えるようにするための共通スクリプト。
#
# やること:
#   1. Python venv(--system-site-packages)を作り、requirements.txt をuvで入れる
#   2. frontend/ の npm install (node/npmが無ければ apt で入れる)
#   3. ROS環境をsourceした状態のenvをsystemd用envファイルとして書き出す
#   4. cube-petit-api.service / cube-petit-frontend.service / cube-petit-zenoh-connector.service
#      (+ hubトポロジ時はcube-petit-zenohd.serviceもorangeでのみ)を生成してenable+start
#
# zenohトポロジは環境変数で切替可能:
#   ZENOH_TOPOLOGY=hub (デフォルト): orangeが `rmw_zenohd` (ROS標準同梱のzenoh router)を
#     動かし、全機体がclientモードでそこへ接続する。スター型なので会場Wi-Fi等
#     マルチキャストが通らない環境でも繋がりやすい。
#   ZENOH_TOPOLOGY=peer: routerを使わず全機体peerモード(マルチキャスト到達性が
#     良い環境向けのフォールバック。routerが死んでいる/到達不可のときの緊急退避用)。
#   RUN_ZENOH_ROUTER=1/0: このマシンでrouter自体を動かすか。省略時はhubトポロジかつ
#     hostnameがcube-petit-orangeの場合のみ自動で1になる。
#
# 前提: このリポジトリが ~/ros/src/cube_petit_scenario に、cube_petit_ros(fleet_bridge)が
# ~/ros/src/cube_petit_ros にcloneされていること。
set -euo pipefail

REPO_DIR="$HOME/ros/src/cube_petit_scenario"
WEBIF_DIR="$REPO_DIR/cube_petit_web_interface"
FRONTEND_DIR="$WEBIF_DIR/frontend"
VENV_DIR="$WEBIF_DIR/.venv"
SYSTEMD_DIR="$HOME/.config/systemd/user"
ENV_FILE="$SYSTEMD_DIR/cube-petit-api.env"
FLEET_BRIDGE_BUILD_DIR="$HOME/ros/build/cube_petit_fleet_bridge/cube_petit_fleet_bridge"
ZENOHD_BIN="/opt/ros/jazzy/lib/rmw_zenoh_cpp/rmw_zenohd"

# ROS環境を先にsourceしておく(PYTHONPATHにrclpy等が乗る)。以降のvenv importチェックや
# 4章のenvファイル生成でも使う。一部のROS setup.bash群がunbound variableを参照するため
# source中だけ set -u を緩める
set +u
source /opt/ros/jazzy/setup.bash
source "$HOME/ros/install/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-94}"
export DISPLAY="${DISPLAY:-:0}"

ROBOT_NAMESPACE="$(hostname | tr '-' '_')"
HUB_ENDPOINT="tcp/cube-petit-orange.local:7447"
ZENOH_TOPOLOGY="${ZENOH_TOPOLOGY:-hub}"   # hub | peer
if [ "$ZENOH_TOPOLOGY" = "hub" ]; then
  export ZENOH_MODE=client
  export ZENOH_ROUTER_ENDPOINT="$HUB_ENDPOINT"
  DEFAULT_RUN_ROUTER=0
  [ "$ROBOT_NAMESPACE" = "cube_petit_orange" ] && DEFAULT_RUN_ROUTER=1
else
  export ZENOH_MODE=peer
  export ZENOH_ROUTER_ENDPOINT="$HUB_ENDPOINT"
  DEFAULT_RUN_ROUTER=0
fi
RUN_ZENOH_ROUTER="${RUN_ZENOH_ROUTER:-$DEFAULT_RUN_ROUTER}"
echo "zenohトポロジ: $ZENOH_TOPOLOGY (このマシンのmode=$ZENOH_MODE, router起動=$RUN_ZENOH_ROUTER, namespace=$ROBOT_NAMESPACE)"

echo "== 1. Python venv + eclipse-zenoh (uv) =="
if ! command -v uv >/dev/null 2>&1; then
  echo "uv が無いので入れます"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv --system-site-packages --clear "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" -r "$WEBIF_DIR/requirements.txt"
# requirements.txt は Tier 2(zenoh)専用で、fastapi/uvicorn/pyyaml 等の基本依存は
# 「rosdep/apt で入ってる前提」だったが、機体によっては入っていないため明示的に入れる
# (--system-site-packages なので、既に入ってる機体では何もしない)
uv pip install --python "$VENV_DIR/bin/python" fastapi "uvicorn[standard]" pyyaml pydantic
"$VENV_DIR/bin/python" -c "import zenoh, fastapi, uvicorn, rclpy; print('venv OK: zenoh/fastapi/uvicorn/rclpy import成功')"

echo "== 2. Node.js / npm install (frontend) =="
# vite 8系はNode.js >=20.19 (or >=22.12) が必須。機体によってapt由来の古いnode(18系等)が
# 入っていたり(yellowで発覚: node 18.19.1でCustomEvent is not definedというエラーで
# vite自体が起動できずcube-petit-frontend.serviceがクラッシュループしていた)、そもそも
# 入っていなかったりする。sudoが使えない機体もあるため、apt更新はせずnodejs.orgの
# 公式tarballを $HOME/.local 配下にsudoなしで展開して使う(uvと同じ思想)。
NODE_MIN_MAJOR=20
NODE_DIST_VERSION=22.14.0
LOCAL_NODE_DIR="$HOME/.local/nodejs-v${NODE_DIST_VERSION}"

node_major() { "$1" -e 'console.log(process.versions.node.split(".")[0])' 2>/dev/null || echo 0; }

if command -v node >/dev/null 2>&1 && [ "$(node_major node)" -ge "$NODE_MIN_MAJOR" ]; then
  NODE_BIN_DIR="$(dirname "$(command -v node)")"
else
  echo "システムのNode.jsが無い/古い(要 >=${NODE_MIN_MAJOR})ので $LOCAL_NODE_DIR にNode.js v${NODE_DIST_VERSION}を入れます"
  if [ ! -x "$LOCAL_NODE_DIR/bin/node" ]; then
    case "$(uname -m)" in
      x86_64) NODE_ARCH=x64 ;;
      aarch64) NODE_ARCH=arm64 ;;
      *) echo "未対応のarch: $(uname -m)"; exit 1 ;;
    esac
    TARBALL="node-v${NODE_DIST_VERSION}-linux-${NODE_ARCH}.tar.xz"
    curl -LsSf "https://nodejs.org/dist/v${NODE_DIST_VERSION}/${TARBALL}" -o "/tmp/${TARBALL}"
    mkdir -p "$LOCAL_NODE_DIR"
    tar -xf "/tmp/${TARBALL}" -C "$LOCAL_NODE_DIR" --strip-components=1
    rm -f "/tmp/${TARBALL}"
  fi
  NODE_BIN_DIR="$LOCAL_NODE_DIR/bin"
  export PATH="$NODE_BIN_DIR:$PATH"
fi
NPM_BIN="$NODE_BIN_DIR/npm"
echo "npm: $NPM_BIN ($("$NODE_BIN_DIR/node" --version))"
# node_modules は使用したnodeのメジャーバージョンをマーカーファイルに記録しておき、
# 前回と違うnodeで再実行された場合(yellowでnode18→22に切り替えた際に発覚: 古いnpmが
# 作ったnode_modulesのままだとrolldownのネイティブbindingが欠落しvite起動時に
# MODULE_NOT_FOUNDでクラッシュした)は入れ直す
NODE_MARKER="$FRONTEND_DIR/node_modules/.node_major_used"
CURRENT_NODE_MAJOR="$("$NODE_BIN_DIR/node" -e 'console.log(process.versions.node.split(".")[0])')"
if [ -d "$FRONTEND_DIR/node_modules" ] && [ "$(cat "$NODE_MARKER" 2>/dev/null || echo '')" != "$CURRENT_NODE_MAJOR" ]; then
  echo "node_modules が別のNode.jsメジャーバージョンで作られているため入れ直します"
  rm -rf "$FRONTEND_DIR/node_modules"
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  (cd "$FRONTEND_DIR" && "$NPM_BIN" install)
  echo "$CURRENT_NODE_MAJOR" > "$NODE_MARKER"
fi

echo "== 3. systemd用envファイル生成 =="
mkdir -p "$SYSTEMD_DIR"
KNOWN_KEYS='^(AMENT_PREFIX_PATH|PATH|PYTHONPATH|RMW_IMPLEMENTATION|ROS_AUTOMATIC_DISCOVERY_RANGE|ROS_DOMAIN_ID|ROS_DISTRO|ROS_PYTHON_VERSION|ROS_VERSION|DISPLAY|LD_LIBRARY_PATH|ZENOH_ROUTER_ENDPOINT|ZENOH_MODE)='
# 既存envファイルに、上記以外の手動追加の変数(OPENAI_API_KEY等の秘密鍵)があれば
# 保持する。このスクリプトは秘密鍵を生成しないので、上書きで消さないようにするため。
EXTRA_LINES=""
if [ -f "$ENV_FILE" ]; then
  EXTRA_LINES="$(grep -vE "$KNOWN_KEYS" "$ENV_FILE" || true)"
fi

env | grep -E "$KNOWN_KEYS" > "$ENV_FILE"
if [ -n "$EXTRA_LINES" ]; then
  echo "$EXTRA_LINES" >> "$ENV_FILE"
  echo "→ 既存の追加変数($(echo "$EXTRA_LINES" | cut -d= -f1 | tr '\n' ' ')) を保持しました"
fi
echo "→ $ENV_FILE を生成しました($(wc -l < "$ENV_FILE")行)"
echo "  ※ OPENAI_API_KEY 等の秘密鍵がまだ無ければ手動で追記してください(このスクリプトは生成しません)"

echo "== 4. systemdユニット生成 =="
cat > "$SYSTEMD_DIR/cube-petit-api.service" <<EOF
[Unit]
Description=Cube Petit Web Interface API Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$WEBIF_DIR
ExecStart=$VENV_DIR/bin/python -m uvicorn cube_petit_web_interface.api_server:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=default.target
EOF

cat > "$SYSTEMD_DIR/cube-petit-frontend.service" <<EOF
[Unit]
Description=Cube Petit Web Interface Frontend (Vite)
After=network.target

[Service]
Type=simple
WorkingDirectory=$FRONTEND_DIR
ExecStart=$NPM_BIN run dev -- --host
Restart=on-failure
RestartSec=5
Environment=PATH=$(dirname "$NPM_BIN"):/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=default.target
EOF

cat > "$SYSTEMD_DIR/cube-petit-zenoh-connector.service" <<EOF
[Unit]
Description=Cube Petit Fleet Bridge zenoh connector ($ROBOT_NAMESPACE)
After=network.target

[Service]
Type=simple
WorkingDirectory=$FLEET_BRIDGE_BUILD_DIR
ExecStart=$VENV_DIR/bin/python $FLEET_BRIDGE_BUILD_DIR/zenoh_connector.py --ros-args -r __node:=zenoh_connector -r __ns:=/$ROBOT_NAMESPACE -p zenoh_router_endpoint:=$ZENOH_ROUTER_ENDPOINT -p zenoh_mode:=$ZENOH_MODE
Restart=on-failure
RestartSec=5
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=default.target
EOF

SERVICES_TO_START="cube-petit-api.service cube-petit-frontend.service cube-petit-zenoh-connector.service"

if [ "$RUN_ZENOH_ROUTER" = "1" ]; then
  cat > "$SYSTEMD_DIR/cube-petit-zenohd.service" <<EOF
[Unit]
Description=Cube Petit zenoh router (rmw_zenohd, hubトポロジ用)
After=network.target

[Service]
Type=simple
ExecStart=$ZENOHD_BIN
Restart=on-failure
RestartSec=5
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=default.target
EOF
  SERVICES_TO_START="cube-petit-zenohd.service $SERVICES_TO_START"
else
  # peerモードに切り替えた場合や、hubだが役割から外れた場合に古いrouterサービスが
  # 残らないようにする(既に無ければ何もしない)
  systemctl --user disable --now cube-petit-zenohd.service 2>/dev/null || true
fi

systemctl --user daemon-reload
systemctl --user enable --now $SERVICES_TO_START
sleep 2
systemctl --user status $SERVICES_TO_START --no-pager -l | grep -E 'Loaded|Active|●'
echo "== 完了 =="
