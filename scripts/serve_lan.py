#!/usr/bin/env python3
"""Serve the built frontend and API on one authenticated private LAN address."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> int:
    settings = Settings()
    if not settings.pte_lan_mode:
        print("Set PTE_LAN_MODE=true in project .env first.", file=sys.stderr)
        return 2
    app = create_app(settings)
    print(f"LAN URL: http://{settings.pte_lan_bind_ip}:{settings.pte_lan_port}", flush=True)
    uvicorn.run(app, host=settings.pte_lan_bind_ip, port=settings.pte_lan_port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
