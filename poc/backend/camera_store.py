"""Thread-safe JSON persistence for camera configurations."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from schemas import Camera


class CameraStore:
    """Reads and writes cameras.json atomically under a threading.Lock."""

    def __init__(self, path: Path, max_cameras: int = 8) -> None:
        self.path = path
        self.max_cameras = max_cameras
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_raw({"cameras": []})

    def _read_raw(self) -> dict:
        if not self.path.exists():
            return {"cameras": []}
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_raw(self, payload: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def load(self) -> list[Camera]:
        with self._lock:
            data = self._read_raw()
            return [Camera(**c) for c in data.get("cameras", [])]

    def save(self, cameras: list[Camera]) -> None:
        with self._lock:
            self._write_raw({"cameras": [c.model_dump() for c in cameras]})

    def get(self, cam_id: str) -> Camera | None:
        for c in self.load():
            if c.id == cam_id:
                return c
        return None

    def next_id(self, cameras: list[Camera]) -> str:
        used = {c.id for c in cameras}
        for i in range(1, self.max_cameras + 1):
            cid = f"cam{i}"
            if cid not in used:
                return cid
        raise ValueError(f"Đã đạt giới hạn tối đa {self.max_cameras} camera")
