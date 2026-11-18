"""In-memory JPEG snapshot uploader for AIOC Storage API (C05)."""

from __future__ import annotations

import logging

import cv2
import numpy as np
import requests

from .config import settings

logger = logging.getLogger("storage_client")


def upload_snapshot(frame_bgr: np.ndarray, camera_id: str, category: str | None = None) -> str | None:
    """Encode a BGR frame to JPEG in RAM and upload to Storage API, returning object_key."""
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        logger.error("Không thể nén ảnh snapshot sang JPEG.")
        return None

    files = {"file": ("snapshot.jpg", buf.tobytes(), "image/jpeg")}
    data = {
        "camera_id": camera_id,
        "category": category or settings.STORAGE_CATEGORY,
    }

    headers = {"Host": settings.STAGING_HOST_HEADER} if settings.STAGING_HOST_HEADER else None
    verify_tls = not settings.MQTT_TLS_INSECURE

    for attempt in range(1, 3):
        try:
            resp = requests.post(
                settings.STORAGE_UPLOAD_URL,
                files=files,
                data=data,
                headers=headers,
                verify=verify_tls,
                timeout=12,
            )
            resp.raise_for_status()
            body = resp.json()
            object_key = body.get("object_key")
            if object_key:
                logger.info("[STORAGE] Upload OK | camera_id=%s | object_key=%s", camera_id, object_key)
                return object_key
            logger.error("[STORAGE] Response thiếu object_key: %s", body)
        except Exception as exc:
            logger.warning("[STORAGE] Lỗi upload ảnh (lần %d/2): %s", attempt, exc)
    return None
