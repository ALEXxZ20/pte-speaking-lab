#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec backend/.venv/bin/python scripts/serve_lan.py
