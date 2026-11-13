"""Event store and annotated JPEG snapshot writer."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from schemas import Camera

STATE_COLORS_BGR = {
    "CLEAR": (94, 197, 34),
    "CONGESTED": (11, 158, 245),
    "GRIDLOCKED": (68, 68, 239),
    "UNKNOWN": (175, 163, 156),
}


class EventStore:
    """Stores up to 200 recent confirmed events in memory and saves snapshots to disk."""

    def __init__(self, snap_dir: Path, maxlen: int = 200) -> None:
        self.snap_dir = snap_dir
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        self._items: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, partial: dict, frame: np.ndarray, cam: Camera | None) -> dict:
        cam_id = partial["camera_id"]
        state = partial["state"]
        ts = float(partial.get("ts") or time.time())
        evt_id = f"evt_{cam_id}_{int(ts)}"

        img = frame.copy()
        h, w = img.shape[:2]
        color = STATE_COLORS_BGR.get(state, (200, 200, 200))

        if cam is not None and len(cam.zone) >= 3:
            pts = np.array(
                [[round(p.x * w), round(p.y * h)] for p in cam.zone],
                dtype=np.int32,
            )
            cv2.polylines(img, [pts], True, color, 3)

        for det in partial.get("detections", []):
            bx1, by1, bx2, by2 = det["bbox"]
            x1, y1 = int(round(bx1 * w)), int(round(by1 * h))
            x2, y2 = int(round(bx2 * w)), int(round(by2 * h))
            b_color = (248, 189, 56) if det.get("group") == "2W" else (250, 139, 167)
            cv2.rectangle(img, (x1, y1), (x2, y2), b_color, 2)

        label = f"{cam.name if cam else cam_id} | {state} ({partial.get('duration_s', 0)}s)"
        cv2.rectangle(img, (12, 12), (min(w - 12, 24 + len(label) * 11), 48), (0, 0, 0), -1)
        cv2.putText(img, label, (20, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        snap_path = self.snap_dir / f"{evt_id}.jpg"
        cv2.imwrite(str(snap_path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])

        event = {
            "id": evt_id,
            "camera_id": cam_id,
            "camera_name": cam.name if cam else cam_id,
            "state": state,
            "ts": ts,
            "duration_s": partial.get("duration_s", 0),
            "snapshot_url": f"/snapshots/{evt_id}.jpg",
            "metrics": partial.get("metrics", {}),
        }
        with self._lock:
            self._items.appendleft(event)
        return event

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._items)
