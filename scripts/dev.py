#!/usr/bin/env python3
"""Run both local development servers and stop them together."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend/.venv/bin/python"


def main():
    if not PYTHON.is_file() or not shutil.which("npm"):
        print("请先按 README 安装 Python 虚拟环境及 Node.js 依赖。", file=sys.stderr)
        return 1
    if not (ROOT / "frontend/node_modules").is_dir():
        print("前端依赖缺失，请运行 npm ci --prefix frontend。", file=sys.stderr)
        return 1
    probe = subprocess.run([str(PYTHON), "-c", "import fastapi, uvicorn"], capture_output=True)
    if probe.returncode:
        print("后端依赖缺失，请安装 backend/requirements.lock。", file=sys.stderr)
        return 1
    for port in (8000, 5173):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                print(f"端口 {port} 已被占用，请先关闭对应服务。", file=sys.stderr)
                return 1
    frontend_env = {
        key: value for key, value in os.environ.items()
        if not any(part in key.upper() for part in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"))
        and not key.startswith("VITE_")
    }
    processes = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    try:
        processes.append(subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "backend"),
             "--host", "127.0.0.1", "--port", "8000", "--reload", "--reload-dir", str(ROOT / "backend")],
            cwd=ROOT, start_new_session=True,
        ))
        processes.append(subprocess.Popen(
            [shutil.which("npm"), "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
            cwd=ROOT / "frontend", env=frontend_env, start_new_session=True,
        ))
        print("\n网页：http://127.0.0.1:5173\nAPI：http://127.0.0.1:8000/api/v1/health\n按 Ctrl+C 同时停止两个服务。\n", flush=True)
        while not stopping and all(proc.poll() is None for proc in processes):
            time.sleep(0.25)
        if not stopping:
            print("一个服务已退出，正在停止其他服务。", file=sys.stderr)
            return 1
        return 0
    finally:
        for proc in processes:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()


if __name__ == "__main__":
    sys.exit(main())
