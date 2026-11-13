"""Centralized 66.7ms GPU micro-batcher for all active cameras."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from ai.config import AIConfig
from ai.core_pipeline.detector import Detector

if TYPE_CHECKING:
    from ai.engine.camera_processor import CameraProcessor

logger = logging.getLogger(__name__)


class ResultStore:
    """Thread-safe store for latest per-camera results and pending events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: dict[str, dict] = {}
        self._events: deque[tuple[dict, np.ndarray]] = deque(maxlen=100)

    def set(self, cam_id: str, result: dict) -> None:
        with self._lock:
            self._results[cam_id] = result

    def remove(self, cam_id: str) -> None:
        with self._lock:
            self._results.pop(cam_id, None)

    def latest_all(self) -> list[dict]:
        with self._lock:
            return list(self._results.values())

    def push_event(self, partial: dict, frame: np.ndarray) -> None:
        with self._lock:
            self._events.append((partial, frame))

    def pop_events(self) -> list[tuple[dict, np.ndarray]]:
        with self._lock:
            items = list(self._events)
            self._events.clear()
            return items


class GpuBatcher(threading.Thread):
    """Single GPU inference loop running at target_fps (~66.7ms tick)."""

    def __init__(
        self,
        cfg: AIConfig,
        detector: Detector,
        store: ResultStore,
        get_processors: callable,
    ) -> None:
        super().__init__(name="gpu-batcher", daemon=True)
        self.cfg = cfg
        self.detector = detector
        self.store = store
        self.get_processors = get_processors
        self.stop_evt = threading.Event()

    def run(self) -> None:
        period = 1.0 / self.cfg.target_fps if self.cfg.target_fps > 0 else 0.0667
        batch_times: deque[float] = deque(maxlen=150)
        last_log = time.monotonic()

        while not self.stop_evt.is_set():
            t0 = time.monotonic()
            try:
                procs: list[CameraProcessor] = self.get_processors()
                items = [(p, p.prepare()) for p in procs]
                ready = [(p, x) for p, x in items if x is not None]

                if ready:
                    crops = [x[0] for _, x in ready]
                    offsets = [x[1] for _, x in ready]
                    dets = self.detector.detect_batch(crops, offsets)
                    for (p, _), det in zip(ready, dets):
                        res = p.process(det, time.monotonic())
                        self.store.set(p.cam_id, res)
                        if p.pending_event is not None:
                            partial, frame = p.pending_event
                            p.pending_event = None
                            self.store.push_event(partial, frame)

                for p, x in items:
                    if x is None:
                        self.store.set(p.cam_id, p.idle_result(time.monotonic()))

                elapsed = time.monotonic() - t0
                batch_times.append(elapsed)

                if t0 - last_log >= 10.0 and batch_times:
                    avg_ms = (sum(batch_times) / len(batch_times)) * 1000.0
                    logger.info(
                        "GpuBatcher: active_cams=%d avg_cycle=%.1fms",
                        len(procs),
                        avg_ms,
                    )
                    last_log = t0
            except Exception:
                logger.exception("Error in GpuBatcher loop")

            sleep_s = max(0.0, period - (time.monotonic() - t0))
            if sleep_s > 0:
                self.stop_evt.wait(sleep_s)
