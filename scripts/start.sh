#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd -P)
RUN_DIR="$ROOT/data/run"
PID_FILE="$RUN_DIR/lan.pid"
LOG_FILE="$ROOT/data/logs/lan.log"
PLIST_FILE="$RUN_DIR/com.pte-speaking-lab.lan.plist"
LABEL='com.pte-speaking-lab.lan'
DOMAIN="gui/$(id -u)"
mkdir -p "$RUN_DIR" "$ROOT/data/logs"

CONFIG=$(PYTHONPATH=backend backend/.venv/bin/python -c 'from app.config import Settings; s=Settings(); print(f"{s.pte_lan_mode} {s.pte_lan_bind_ip} {s.pte_lan_port}")')
set -- $CONFIG
MODE=$1
BIND_IP=$2
PORT=$3
if [ "$MODE" != "True" ]; then
  echo '请先在项目 .env 设置 PTE_LAN_MODE=true。' >&2
  exit 2
fi
if [ ! -f frontend/dist/index.html ]; then
  echo '前端尚未构建，请先运行 npm run build --prefix frontend。' >&2
  exit 2
fi

LISTENER=$(lsof -nP -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)
if [ -n "$LISTENER" ]; then
  COMMAND=$(ps -p "$LISTENER" -o command= 2>/dev/null || true)
  CWD=$(lsof -a -p "$LISTENER" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)
  case "$COMMAND" in
    *scripts/serve_lan.py*)
      if [ "$CWD" = "$ROOT" ]; then
        printf '%s\n' "$LISTENER" > "$PID_FILE"
        echo "内网服务已在运行：http://$BIND_IP:$PORT/"
        exit 0
      fi ;;
  esac
  echo "端口 $PORT 已被其他程序占用（PID $LISTENER）。" >&2
  exit 1
fi
rm -f "$PID_FILE"
PYTHONPATH=backend backend/.venv/bin/python - "$PLIST_FILE" "$ROOT" "$LOG_FILE" <<'PY'
import plistlib
import os
import shutil
import sys
from pathlib import Path
from app.config import Settings

path, root, log = sys.argv[1:]
search_paths = ["/opt/homebrew/bin", "/usr/local/bin", *os.environ.get("PATH", "").split(os.pathsep),
                "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
effective_path = os.pathsep.join(dict.fromkeys(item for item in search_paths if item))
settings = Settings()
for label, binary in (("FFMPEG_BIN", settings.ffmpeg_bin), ("FFPROBE_BIN", settings.ffprobe_bin)):
    if shutil.which(binary, path=effective_path) is None:
        raise SystemExit(f"找不到 {label}={binary}；请先用 Homebrew 安装 ffmpeg，或在 .env 配置绝对路径。")
payload = {
    "Label": "com.pte-speaking-lab.lan",
    "ProgramArguments": [str(Path(root, "backend/.venv/bin/python")), str(Path(root, "scripts/serve_lan.py"))],
    "WorkingDirectory": root,
    "RunAtLoad": True,
    "KeepAlive": False,
    "EnvironmentVariables": {"PATH": effective_path},
    "StandardOutPath": log,
    "StandardErrorPath": log,
}
Path(path).write_bytes(plistlib.dumps(payload))
PY
if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootstrap "$DOMAIN" "$PLIST_FILE"
fi
COUNT=0
while [ "$COUNT" -lt 30 ]; do
  STATUS=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --connect-timeout 1 "http://$BIND_IP:$PORT/" || true)
  if [ "$STATUS" = 401 ]; then
    lsof -nP -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 > "$PID_FILE" || true
    echo "内网服务已启动：http://$BIND_IP:$PORT/ （需要账号密码）"
    exit 0
  fi
  if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    tail -n 20 "$LOG_FILE" >&2
    exit 1
  fi
  COUNT=$((COUNT + 1))
  sleep 1
done
echo "启动超时；请查看 $LOG_FILE" >&2
exit 1
