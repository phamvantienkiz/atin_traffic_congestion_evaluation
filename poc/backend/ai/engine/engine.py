"""Public TrafficEngine API used by FastAPI backend."""

from __future__ import annotations

import logging
import threading

import numpy as np

from ai.config import AIConfig, CFG
from ai.core_pipeline.detector import Detector
from ai.engine.camera_processor import CameraProcessor
from ai.engine.gpu_batcher import GpuBatcher, ResultStore

logger = logging.getLogger(__name__)


class TrafficEngine:
    """Orchestrates Detector, GpuBatcher, and per-camera CameraProcessors."""

    def __init__(self, cfg: AIConfig = CFG) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._processors: dict[str, CameraProcessor] = {}
        self._urls: dict[str, str] = {}
        self._store = ResultStore()
        self._detector: Detector | None = None
        self._batcher: GpuBatcher | None = None

    def start(self) -> None:
        if self._batcher is not None and self._batcher.is_alive():
            return
        self._detector = Detector(self.cfg)
        self._batcher = GpuBatcher(
            cfg=self.cfg,
            detector=self._detector,
            store=self._store,
            get_processors=self._snapshot_processors,
        )
        self._batcher.start()
        logger.info("TrafficEngine started")

    def stop(self) -> None:
        if self._batcher is not None:
            self._batcher.stop_evt.set()
            self._batcher.join(timeout=5.0)
            self._batcher = None
        with self._lock:
            for proc in self._processors.values():
                proc.stop()
            self._processors.clear()
            self._urls.clear()
        logger.info("TrafficEngine stopped")

    def _snapshot_processors(self) -> list[CameraProcessor]:
        with self._lock:
            return list(self._processors.values())

    def upsert_camera(self, cam: dict) -> None:
        """Add or update a camera; reads rtsp://127.0.0.1:8554/{cam_id} via MediaMTX."""
        cam_id = cam["id"]
        rtsp_url = f"rtsp://127.0.0.1:8554/{cam_id}"
        if not cam.get("enabled", True):
            self.remove_camera(cam_id)
            return

        with self._lock:
            existing = self._processors.get(cam_id)
            if existing is not None and self._urls.get(cam_id) == rtsp_url:
                existing.update_meta(cam)
                return
            if existing is not None:
                existing.stop()

            proc = CameraProcessor(cam=cam, cfg=self.cfg, rtsp_url=rtsp_url)
            proc.start()
            self._processors[cam_id] = proc
            self._urls[cam_id] = rtsp_url
            logger.info("Camera upserted in engine: %s", cam_id)

    def remove_camera(self, cam_id: str) -> None:
        with self._lock:
            proc = self._processors.pop(cam_id, None)
            self._urls.pop(cam_id, None)
        if proc is not None:
            proc.stop()
        self._store.remove(cam_id)
        logger.info("Camera removed from engine: %s", cam_id)

    def latest_results(self) -> list[dict]:
        return self._store.latest_all()

    def pop_events(self) -> list[tuple[dict, np.ndarray]]:
        return self._store.pop_events()

    def latest_frame(self, cam_id: str) -> np.ndarray | None:
        with self._lock:
            proc = self._processors.get(cam_id)
        return proc.latest_frame() if proc is not None else None
