"""Backend settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
POC_DIR = BACKEND_DIR.parent

load_dotenv(POC_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
CAMERAS_FILE = DATA_DIR / "cameras.json"
SNAP_DIR = DATA_DIR / "snapshots"
FRONTEND_DIR = POC_DIR / "frontend"

MEDIAMTX_BIN = POC_DIR / os.getenv("MEDIAMTX_BIN", "mediamtx/mediamtx")
MEDIAMTX_CONFIG = POC_DIR / os.getenv("MEDIAMTX_CONFIG", "mediamtx/mediamtx.yml")
MEDIAMTX_RTSP_PORT = int(os.getenv("MEDIAMTX_RTSP_PORT", "28554"))
MEDIAMTX_WEBRTC_PORT = int(os.getenv("MEDIAMTX_WEBRTC_PORT", "28889"))
MEDIAMTX_ICE_TCP_PORT = int(os.getenv("MEDIAMTX_ICE_TCP_PORT", "28189"))
MEDIAMTX_API_PORT = int(os.getenv("MEDIAMTX_API_PORT", "29997"))
WS_PUSH_HZ = float(os.getenv("WS_PUSH_HZ", "5"))
MAX_CAMERAS = int(os.getenv("MAX_CAMERAS", "8"))
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
