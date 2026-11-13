"""RTSP stream reader normalized to 1280x720 @ 15 FPS with latest-frame buffer=1."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")

logger = logging.getLogger(__name__)


@dataclass
class FramePacket:
    """Single decoded frame normalized to target resolution."""

    frame: np.ndarray
    seq: int
    t_mono: float


class StreamReader:
    """Background RTSP reader that keeps only the latest sampled frame."""

    def __init__(
        self,
        camera_id: str,
        url: str,
        w: int = 1280,
        h: int = 720,
        fps: float = 15.0,
        timeout_s: float = 5.0,
    ) -> None:
        self.camera_id = camera_id
        self.url = url
        self.w = w
        self.h = h
        self.fps = fps
        self.timeout_s = timeout_s

        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: FramePacket | None = None
        self._seq = 0
        self._emit_times: deque[float] = deque(maxlen=60)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"rtsp-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def latest(self) -> FramePacket | None:
        with self._lock:
            return self._latest

    @property
    def healthy(self) -> bool:
        with self._lock:
            if self._latest is None:
                return False
            return (time.monotonic() - self._latest.t_mono) <= self.timeout_s

    @property
    def measured_fps(self) -> float:
        with self._lock:
            if len(self._emit_times) < 2:
                return 0.0
            span = self._emit_times[-1] - self._emit_times[0]
            if span <= 0:
                return 0.0
            return (len(self._emit_times) - 1) / span

    def _run(self) -> None:
        interval = 1.0 / self.fps if self.fps > 0 else 0.0
        last_emit = 0.0
        cap: cv2.VideoCapture | None = None

        while not self._stop_evt.is_set():
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    logger.warning("[%s] Failed to open RTSP stream, retrying in 2s", self.camera_id)
                    cap.release()
                    cap = None
                    self._stop_evt.wait(2.0)
                    continue
                logger.info("[%s] Connected to stream %s", self.camera_id, self.url)

            if not cap.grab():
                logger.warning("[%s] Stream grab failed, reconnecting in 2s", self.camera_id)
                cap.release()
                cap = None
                self._stop_evt.wait(2.0)
                continue

            now = time.monotonic()
            if now - last_emit < interval - 0.005:
                continue

            ok, frame = cap.retrieve()
            if not ok or frame is None:
                continue

            if frame.shape[1] != self.w or frame.shape[0] != self.h:
                frame = cv2.resize(frame, (self.w, self.h), interpolation=cv2.INTER_AREA)

            last_emit = now
            with self._lock:
                self._seq += 1
                self._latest = FramePacket(frame=frame, seq=self._seq, t_mono=now)
                self._emit_times.append(now)

        if cap is not None:
            cap.release()
