"""RTSP stream reader normalized to 1280x720 @ 15 FPS with latest-frame buffer=1."""

from __future__ import annotations

import logging
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|probesize;32768|analyzeduration;0|stimeout;5000000",
)

logger = logging.getLogger(__name__)


def _resolve_ffmpeg_bin() -> str | None:
    """Prefer ffmpeg inside the active virtualenv bin/Scripts dir before system PATH."""
    venv_bin = Path(sys.executable).parent
    return shutil.which("ffmpeg", path=str(venv_bin)) or shutil.which("ffmpeg")


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
        self._proc: subprocess.Popen[bytes] | None = None
        self._latest: FramePacket | None = None
        self._seq = 0
        self._emit_times: deque[float] = deque(maxlen=60)
        self.backend = os.getenv("RTSP_BACKEND", "auto").strip().lower() or "auto"

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
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
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

    def _is_rtsp_url(self) -> bool:
        low = self.url.lower()
        return low.startswith("rtsp://") or low.startswith("rtsps://")

    def _build_ffmpeg_cmd(self, mode: str, ffmpeg_bin: str = "ffmpeg") -> list[str]:
        probe = "1000000" if mode == "cuda_hwaccel" else "500000"
        base = [
            ffmpeg_bin,
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-strict", "experimental",
            "-probesize", probe,
            "-analyzeduration", probe,
        ]
        if mode in ("h264_cuvid", "hevc_cuvid"):
            return base + [
                "-hwaccel", "cuda",
                "-c:v", mode,
                "-resize", f"{self.w}x{self.h}",
                "-i", self.url,
                "-an", "-sn",
                "-f", "rawvideo",
                "-pix_fmt", "bgr24",
                "pipe:1",
            ]
        hw_args = ["-hwaccel", "cuda"] if mode == "cuda_hwaccel" else []
        return base + hw_args + [
            "-i", self.url,
            "-an", "-sn",
            "-vf", f"scale={self.w}:{self.h}:flags=fast_bilinear",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "pipe:1",
        ]

    def _emit_frame(self, frame: np.ndarray, now: float) -> None:
        with self._lock:
            self._seq += 1
            self._latest = FramePacket(frame=frame, seq=self._seq, t_mono=now)
            self._emit_times.append(now)

    def _run(self) -> None:
        ffmpeg_bin = _resolve_ffmpeg_bin()
        use_ffmpeg = (
            self.backend in ("auto", "ffmpeg", "ffmpeg_cuda")
            and self._is_rtsp_url()
            and ffmpeg_bin is not None
        )
        if use_ffmpeg and ffmpeg_bin is not None:
            self._run_ffmpeg(ffmpeg_bin)
            return
        self._run_opencv()

    def _read_frame_bytes(self, pipe, frame_bytes: int) -> bytes | None:
        """Read exactly frame_bytes from pipe, returning None on EOF or timeout."""
        if os.name == "nt":
            raw = pipe.read(frame_bytes)
            return raw if len(raw) == frame_bytes else None

        fd = pipe.fileno()
        buf = bytearray()
        deadline = time.monotonic() + self.timeout_s
        while len(buf) < frame_bytes and not self._stop_evt.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if not ready:
                continue
            chunk = os.read(fd, frame_bytes - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf) if len(buf) == frame_bytes else None

    def _run_ffmpeg(self, ffmpeg_bin: str = "ffmpeg") -> None:
        interval = 1.0 / self.fps if self.fps > 0 else 0.0
        frame_bytes = self.w * self.h * 3
        modes = ["h264_cuvid", "cuda_hwaccel", "hevc_cuvid", "ffmpeg_cpu"]
        mode_idx = 0
        last_emit = 0.0

        while not self._stop_evt.is_set():
            mode = modes[mode_idx]
            cmd = self._build_ffmpeg_cmd(mode, ffmpeg_bin)
            logger.info("[%s] Opening RTSP via FFmpeg (%s)...", self.camera_id, mode)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            self._proc = proc
            got_frame = False

            try:
                assert proc.stdout is not None
                while not self._stop_evt.is_set():
                    raw = self._read_frame_bytes(proc.stdout, frame_bytes)
                    if raw is None:
                        break
                    if not got_frame:
                        got_frame = True
                        label = "CUDA" if (mode.endswith("_cuvid") or mode == "cuda_hwaccel") else "CPU"
                        logger.info(
                            "[%s] Connected via FFmpeg %s (%s %dx%d)",
                            self.camera_id,
                            label,
                            mode,
                            self.w,
                            self.h,
                        )
                    now = time.monotonic()
                    if now - last_emit < interval - 0.003:
                        continue
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.h, self.w, 3)).copy()
                    last_emit = now
                    self._emit_frame(frame, now)
            finally:
                if proc.poll() is None:
                    proc.kill()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
                self._proc = None

            if self._stop_evt.is_set():
                break

            if not got_frame:
                err_msg = ""
                if proc.stderr is not None:
                    try:
                        err_msg = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                    except Exception:
                        pass
                if mode_idx + 1 < len(modes):
                    logger.warning(
                        "[%s] FFmpeg %s failed (%s), falling back to %s",
                        self.camera_id,
                        mode,
                        err_msg or "no frames",
                        modes[mode_idx + 1],
                    )
                    mode_idx += 1
                    continue
                if self.backend == "auto":
                    logger.warning(
                        "[%s] All FFmpeg modes failed (%s), falling back to OpenCV",
                        self.camera_id,
                        err_msg or "no frames",
                    )
                    self._run_opencv()
                    return
                mode_idx = 0

            logger.warning("[%s] FFmpeg stream ended, reconnecting in 2s", self.camera_id)
            self._stop_evt.wait(2.0)

    def _run_opencv(self) -> None:
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
                logger.info("[%s] Connected to stream %s (OpenCV)", self.camera_id, self.url)

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
                frame = cv2.resize(frame, (self.w, self.h), interpolation=cv2.INTER_LINEAR)

            last_emit = now
            self._emit_frame(frame, now)

        if cap is not None:
            cap.release()
