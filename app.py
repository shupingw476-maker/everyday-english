#!/usr/bin/env python3
"""Start the 进步 Progress website (frontend + API)."""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

if __name__ == "__main__":
    host = os.environ.get("JINBU_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("JINBU_PORT", "8765"))
    print(f"进步 Progress 学习站：http://127.0.0.1:{port}/")
    uvicorn.run("server.main:app", host=host, port=port, reload=False)
