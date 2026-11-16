"""Run a standalone fake RTSP server from recorded MP4 files via MediaMTX + FFmpeg."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

POC_DIR = Path(__file__).resolve().parents[2]
TOOL_DIR = Path(__file__).resolve().parent
RECORD_DIR = Path(os.getenv("RECORD_DIR", str(POC_DIR / "records")))
MEDIAMTX_BIN = POC_DIR / "mediamtx" / ("mediamtx.exe" if os.name == "nt" else "mediamtx")
MEDIAMTX_CFG = TOOL_DIR / "mediamtx_fake.yml"
RTSP_PORT = os.getenv("FAKE_RTSP_PORT", "28555")

PDG_FILE = RECORD_DIR / "8phandinhgiot_clip.mp4"
HVT_FILE_1 = RECORD_DIR / "tram-xe-buyt-247-duong-hoang-van-thu_clip.mp4"
HVT_FILE_2 = RECORD_DIR / "tram-xe-buyt-247-duong-hoang-van-thu_clip_2.mp4"


def _stop_procs(procs: list[subprocess.Popen]) -> None:
    for p in reversed(procs):
        if p.poll() is None:
            p.terminate()
    deadline = time.monotonic() + 3.0
    for p in reversed(procs):
        if p.poll() is None:
            rem = max(0.1, deadline - time.monotonic())
            try:
                p.wait(timeout=rem)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=1.0)


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("[ERROR] ffmpeg chua duoc cai dat. Cai bang: sudo apt-get update && sudo apt-get install -y ffmpeg", file=sys.stderr)
        return 1

    if not MEDIAMTX_BIN.exists():
        print(f"[ERROR] Khong tim thay MediaMTX tai: {MEDIAMTX_BIN}", file=sys.stderr)
        return 1

    if not any(f.is_file() for f in (PDG_FILE, HVT_FILE_1, HVT_FILE_2)):
        print(f"[ERROR] Khong tim thay file MP4 nao trong: {RECORD_DIR}", file=sys.stderr)
        return 1

    procs: list[subprocess.Popen] = []
    concat_file: Path | None = None
    stopping = False

    def _handle_sig(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        print(f"[fake_rtsp] Starting MediaMTX on :{RTSP_PORT}...")
        mtx = subprocess.Popen([str(MEDIAMTX_BIN), str(MEDIAMTX_CFG)])
        procs.append(mtx)
        time.sleep(1.5)
        if mtx.poll() is not None:
            print("[ERROR] MediaMTX thoat som. Kiem tra port 28555 co dang bi chiem khong.", file=sys.stderr)
            return 1

        if PDG_FILE.is_file():
            url = f"rtsp://127.0.0.1:{RTSP_PORT}/pdg"
            print(f"[fake_rtsp] Publishing PDG -> {url}")
            procs.append(
                subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-loglevel", "warning",
                    "-re", "-stream_loop", "-1", "-i", str(PDG_FILE),
                    "-c:v", "copy", "-an", "-f", "rtsp", "-rtsp_transport", "tcp", url,
                ])
            )
        else:
            print(f"[WARN] Thieu {PDG_FILE.name}, bo qua /pdg")

        hvt_url = f"rtsp://127.0.0.1:{RTSP_PORT}/hvt"
        if HVT_FILE_1.is_file() and HVT_FILE_2.is_file():
            fd, tmp_path = tempfile.mkstemp(prefix="hvt_concat_", suffix=".txt")
            os.close(fd)
            concat_file = Path(tmp_path)
            concat_file.write_text(
                f"file '{HVT_FILE_1.as_posix()}'\nfile '{HVT_FILE_2.as_posix()}'\n",
                encoding="utf-8",
            )
            print(f"[fake_rtsp] Publishing HVT (clip 1 + clip 2) -> {hvt_url}")
            procs.append(
                subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-loglevel", "warning",
                    "-re", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-c:v", "copy", "-an", "-f", "rtsp", "-rtsp_transport", "tcp", hvt_url,
                ])
            )
        elif HVT_FILE_1.is_file() or HVT_FILE_2.is_file():
            src = HVT_FILE_1 if HVT_FILE_1.is_file() else HVT_FILE_2
            print(f"[fake_rtsp] Publishing HVT ({src.name}) -> {hvt_url}")
            procs.append(
                subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-loglevel", "warning",
                    "-re", "-stream_loop", "-1", "-i", str(src),
                    "-c:v", "copy", "-an", "-f", "rtsp", "-rtsp_transport", "tcp", hvt_url,
                ])
            )
        else:
            print("[WARN] Thieu video Hoang Van Thu, bo qua /hvt")

        print("[fake_rtsp] Streams are live. Press Ctrl+C to stop cleanly.")
        while not stopping:
            if mtx.poll() is not None:
                print("[ERROR] MediaMTX da dung dot ngot.", file=sys.stderr)
                return 1
            time.sleep(0.5)
    finally:
        print("\n[fake_rtsp] Stopping MediaMTX and FFmpeg...")
        _stop_procs(procs)
        if concat_file is not None and concat_file.exists():
            concat_file.unlink(missing_ok=True)
        print("[fake_rtsp] Stopped cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
