"""MediaMTX configuration generator and subprocess manager."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

import yaml

from schemas import Camera
from settings import (
    MEDIAMTX_API_PORT,
    MEDIAMTX_ICE_TCP_PORT,
    MEDIAMTX_RTSP_PORT,
    MEDIAMTX_WEBRTC_PORT,
)

logger = logging.getLogger("mediamtx")

BASE_CONFIG: dict = {
    "logLevel": "info",
    "api": True,
    "apiAddress": f"127.0.0.1:{MEDIAMTX_API_PORT}",
    "rtsp": True,
    "rtspAddress": f":{MEDIAMTX_RTSP_PORT}",
    "protocols": ["tcp"],
    "rtmp": False,
    "hls": False,
    "srt": False,
    "webrtc": True,
    "webrtcAddress": f":{MEDIAMTX_WEBRTC_PORT}",
    "webrtcLocalUDPAddress": "",
    "webrtcLocalTCPAddress": f":{MEDIAMTX_ICE_TCP_PORT}",
    "webrtcIPsFromInterfaces": False,
    "webrtcAdditionalHosts": ["127.0.0.1"],
    "webrtcAllowOrigin": "*",
}


class MediaMTX:
    """Manages mediamtx.yml generation and the MediaMTX child process."""

    def __init__(self, bin_path: Path, cfg_path: Path) -> None:
        self.bin_path = bin_path
        self.cfg_path = cfg_path
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def write_config(self, cameras: list[Camera]) -> None:
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        paths = {
            c.id: {
                "source": c.rtsp_url,
                "rtspTransport": "tcp",
                "sourceOnDemand": False,
            }
            for c in cameras
            if c.enabled
        }
        data = {**BASE_CONFIG, "paths": paths or {"all_others": None}}
        with self.cfg_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    def start(self) -> None:
        with self._lock:
            if not self.bin_path.exists():
                logger.warning(
                    "MediaMTX binary not found at %s; skipping subprocess start",
                    self.bin_path,
                )
                return
            if self.proc is not None and self.proc.poll() is None:
                return
            self.proc = subprocess.Popen(
                [str(self.bin_path), str(self.cfg_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            threading.Thread(
                target=self._pump_logs,
                args=(self.proc,),
                name="mediamtx-logs",
                daemon=True,
            ).start()
            logger.info("MediaMTX started (pid=%s)", self.proc.pid)

    def _pump_logs(self, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                logger.info("%s", line)

    def stop(self) -> None:
        with self._lock:
            if self.proc is None:
                return
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
            self.proc = None
            logger.info("MediaMTX stopped")

    def restart(self) -> None:
        self.stop()
        self.start()
