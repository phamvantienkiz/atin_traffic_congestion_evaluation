"""Configuration loader for AIOC Staging integration, reusing poc/backend/ai."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ép FFmpeg đọc RTSP không đệm để giảm độ trễ BBox so với luồng WebRTC trên Web VMS
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|probesize;32768|analyzeduration;0|stimeout;5000000",
)

INTEGRATE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = INTEGRATE_ROOT.parent
POC_BACKEND_DIR = REPO_ROOT / "poc" / "backend"

if str(POC_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(POC_BACKEND_DIR))

load_dotenv(INTEGRATE_ROOT / ".env")

from ai.config import AIConfig  # noqa: E402


def _resolve_model_path(raw_path: str) -> str:
    """Resolve model path across repo root, poc/backend, or absolute paths."""
    candidate = Path(raw_path)
    if candidate.is_absolute() or candidate.exists():
        return str(candidate)
    for base in (REPO_ROOT, POC_BACKEND_DIR, INTEGRATE_ROOT):
        resolved = (base / raw_path).resolve()
        if resolved.exists():
            return str(resolved)
    return raw_path


def _parse_roi_points(raw: str) -> list[dict[str, float]]:
    """Parse normalized fallback ROI polygon points from JSON env string."""
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [{"x": float(p["x"]), "y": float(p["y"])} for p in data if "x" in p and "y" in p]
    except Exception:
        pass
    return []


class StagingSettings:
    """Environment-backed settings for AIOC Staging MQTT, Storage, and RTSP."""

    MQTT_HOST: str = os.getenv("MQTT_HOST", "aioc-stg.atin.vn")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "443"))
    MQTT_WS_PATH: str = os.getenv("MQTT_WS_PATH", "/mqtt")
    MQTT_USER: str = os.getenv("MQTT_USER", "atin")
    MQTT_PASS: str = os.getenv("MQTT_PASS", "")
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "ai_edge_congestion_junction_01")
    MQTT_KEEPALIVE: int = int(os.getenv("MQTT_KEEPALIVE", "30"))
    MQTT_TLS_INSECURE: bool = os.getenv("MQTT_TLS_INSECURE", "false").strip().lower() in ("1", "true", "yes")
    STAGING_HOST_HEADER: str = os.getenv("STAGING_HOST_HEADER", "").strip()

    ORGANIZATION_ID: int = int(os.getenv("ORGANIZATION_ID", "0"))
    ZONE_ID: int = int(os.getenv("ZONE_ID", "0"))
    TARGET_CAMERA_CODE: str = os.getenv("TARGET_CAMERA_CODE", "camera_junction")
    TARGET_CAMERA_ID: str = os.getenv("TARGET_CAMERA_ID", "")
    FALLBACK_RTSP_URL: str = os.getenv("FALLBACK_RTSP_URL", "rtsp://192.168.1.198:28537/tshtest")
    RTSP_URL_OVERRIDE: str = os.getenv("RTSP_URL_OVERRIDE", "").strip()

    BBOX_AI_MODULE: str = os.getenv("BBOX_AI_MODULE", "PLATE").strip().upper()
    EVENT_PUBLISH_MODE: str = os.getenv("EVENT_PUBLISH_MODE", "NONE").strip().upper()
    STORAGE_UPLOAD_URL: str = os.getenv("STORAGE_UPLOAD_URL", "https://aioc-stg.atin.vn/storage/upload/file")
    STORAGE_CATEGORY: str = os.getenv("STORAGE_CATEGORY", "plate").strip().lower()

    AI_TARGET_FPS: float = float(os.getenv("AI_TARGET_FPS", "25.0"))
    BBOX_PUBLISH_INTERVAL: float = float(os.getenv("BBOX_PUBLISH_INTERVAL", "0.1"))
    FORCE_LOCAL_ROI: bool = os.getenv("FORCE_LOCAL_ROI", "false").strip().lower() in ("1", "true", "yes")
    ALLOW_FALLBACK_ROI: bool = os.getenv("ALLOW_FALLBACK_ROI", "true").strip().lower() in ("1", "true", "yes")
    FALLBACK_ROI_POINTS: list[dict[str, float]] = _parse_roi_points(
        os.getenv(
            "FALLBACK_ROI_POINTS",
            '[{"x":0.0247,"y":0.5172},{"x":0.4374,"y":0.3009},{"x":0.8836,"y":0.3574},{"x":0.9065,"y":0.884}]',
        )
    )


def build_ai_config() -> AIConfig:
    """Build poc/backend/ai AIConfig from environment variables."""
    from dataclasses import replace

    cfg = AIConfig()
    resolved_model = _resolve_model_path(cfg.model_path)
    updates: dict = {"target_fps": settings.AI_TARGET_FPS}
    if resolved_model != cfg.model_path:
        updates["model_path"] = resolved_model
    return replace(cfg, **updates)


settings = StagingSettings()
