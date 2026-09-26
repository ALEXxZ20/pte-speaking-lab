#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd -P)
PID_FILE="$ROOT/data/run/lan.pid"
LABEL='com.pte-speaking-lab.lan'
DOMAIN="gui/$(id -u)"
PORT=$(PYTHONPATH=backend backend/.venv/bin/python -c 'from app.config import Settings; print(Settings().pte_lan_port)')
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL"
  COUNT=0
  while launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 && [ "$COUNT" -lt 30 ]; do
    sleep 1
    COUNT=$((COUNT + 1))
  done
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo '内网服务未能从 launchd 退出，请检查后重试。' >&2
    exit 1
  fi
  rm -f "$PID_FILE"
  echo '内网服务已停止。'
  exit 0
fi
PID=''
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
fi
if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
  PID=$(lsof -nP -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)
fi
if [ -z "$PID" ]; then
  rm -f "$PID_FILE"
  echo '内网服务已经停止。'
  exit 0
fi
COMMAND=$(ps -p "$PID" -o command= 2>/dev/null || true)
CWD=$(lsof -a -p "$PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)
case "$COMMAND" in
  *scripts/serve_lan.py*) ;;
  *) echo "PID $PID 不是本项目内网服务，未停止。" >&2; exit 1 ;;
esac
if [ "$CWD" != "$ROOT" ]; then
  echo "PID $PID 的工作目录不属于本项目，未停止。" >&2
  exit 1
fi
kill "$PID"
COUNT=0
while kill -0 "$PID" 2>/dev/null && [ "$COUNT" -lt 15 ]; do
  sleep 1
  COUNT=$((COUNT + 1))
done
if kill -0 "$PID" 2>/dev/null; then
  echo "PID $PID 未在 15 秒内退出，请检查后手动处理。" >&2
  exit 1
fi
rm -f "$PID_FILE"
echo '内网服务已停止。'
