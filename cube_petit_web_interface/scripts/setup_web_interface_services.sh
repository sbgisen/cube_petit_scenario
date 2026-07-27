#!/usr/bin/env bash
# cube_petit_web_interface の永続サービス(systemd --user)をこのマシンにセットアップする。
# 新しい機体(pink/yellow/...)でも同じ手順で使えるようにするための共通スクリプト。
#
# やること:
#   1. Python venv(--system-site-packages)を作り、requirements.txt をuvで入れる
#   2. frontend/ の npm install (node/npmが無ければ apt で入れる)
#   3. ROS環境をsourceした状態のenvをsystemd用envファイルとして書き出す
#   4. cube-petit-api.service / cube-petit-frontend.service を生成してenable+start
#
# 前提: このリポジトリが ~/ros/src/cube_petit_scenario にcloneされていること。
set -euo pipefail

REPO_DIR="$HOME/ros/src/cube_petit_scenario"
WEBIF_DIR="$REPO_DIR/cube_petit_web_interface"
FRONTEND_DIR="$WEBIF_DIR/frontend"
VENV_DIR="$WEBIF_DIR/.venv"
SYSTEMD_DIR="$HOME/.config/systemd/user"
ENV_FILE="$SYSTEMD_DIR/cube-petit-api.env"

echo "== 1. Python venv + eclipse-zenoh (uv) =="
if ! command -v uv >/dev/null 2>&1; then
  echo "uv が無いので入れます"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv --system-site-packages "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" -r "$WEBIF_DIR/requirements.txt"
"$VENV_DIR/bin/python" -c "import zenoh, fastapi, uvicorn, rclpy; print('venv OK: zenoh/fastapi/uvicorn/rclpy import成功')"

echo "== 2. Node.js / npm install (frontend) =="
if ! command -v npm >/dev/null 2>&1; then
  echo "node/npm が無いので apt で入れます"
  sudo apt-get install -y nodejs npm
fi
NPM_BIN="$(command -v npm)"
echo "npm: $NPM_BIN ($(node --version))"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  (cd "$FRONTEND_DIR" && npm install)
fi

echo "== 3. systemd用envファイル生成 =="
mkdir -p "$SYSTEMD_DIR"
KNOWN_KEYS='^(AMENT_PREFIX_PATH|PATH|PYTHONPATH|RMW_IMPLEMENTATION|ROS_AUTOMATIC_DISCOVERY_RANGE|ROS_DOMAIN_ID|ROS_DISTRO|ROS_PYTHON_VERSION|ROS_VERSION|DISPLAY|LD_LIBRARY_PATH)='
# 既存envファイルに、上記以外の手動追加の変数(OPENAI_API_KEY等の秘密鍵)があれば
# 保持する。このスクリプトは秘密鍵を生成しないので、上書きで消さないようにするため。
EXTRA_LINES=""
if [ -f "$ENV_FILE" ]; then
  EXTRA_LINES="$(grep -vE "$KNOWN_KEYS" "$ENV_FILE" || true)"
fi

set +u  # ROSのsetup.bash群がunbound variableを参照するため、source中だけ緩める
source /opt/ros/jazzy/setup.bash
source "$HOME/ros/install/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-94}"
export DISPLAY="${DISPLAY:-:0}"
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

systemctl --user daemon-reload
systemctl --user enable --now cube-petit-api.service cube-petit-frontend.service
sleep 2
systemctl --user status cube-petit-api.service cube-petit-frontend.service --no-pager -l | grep -E 'Loaded|Active'
echo "== 完了 =="
