"""
RTSP Multi-Stream Server
High-performance, bufferless RTSP stream receiver and MJPEG broadcaster.
Complies with ATIN Traffic Congestion Evaluation specifications.
"""

import os
import sys
import time
import math
import logging
import threading
from typing import Dict, Optional, Generator
from pathlib import Path

# Configure OpenCV FFmpeg options for low latency
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|buffer_size;102400|max_delay;500000"

import cv2
import numpy as np
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RTSP-Server")

# Static directory path
CURRENT_DIR = Path(__file__).resolve().parent

app = FastAPI(title="RTSP Multi-Camera Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StreamConfig(BaseModel):
    url: str


class StreamWorker:
    """Manages an isolated thread for an RTSP capture slot."""

    def __init__(self, slot_id: int):
        self.slot_id = slot_id
        self.url: Optional[str] = None
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        # State variables
        self.last_frame: Optional[bytes] = None
        self.last_timestamp: float = 0.0
        self.fps: float = 0.0
        self.width: int = 0
        self.height: int = 0
        self.status: str = "idle"  # idle, connecting, live, error
        self.error_msg: str = ""
        self.frame_count: int = 0
        self.clients_count: int = 0

    def start(self, url: str):
        with self.lock:
            if self.is_running and self.url == url:
                return  # already running this URL
            self.stop_internal()
            self.url = url.strip()
            self.is_running = True
            self.status = "connecting"
            self.error_msg = ""
            self.thread = threading.Thread(target=self._run_loop, daemon=True, name=f"RTSP-Slot-{self.slot_id}")
            self.thread.start()
            logger.info(f"Slot {self.slot_id}: Started capture for '{self.url}'")

    def stop(self):
        with self.lock:
            self.stop_internal()
            self.status = "idle"
            self.url = None
            logger.info(f"Slot {self.slot_id}: Stopped.")

    def stop_internal(self):
        self.is_running = False
        if self.thread and self.thread.is_alive():
            # Wait briefly for thread to terminate
            self.thread.join(timeout=1.0)
        self.thread = None
        self.last_frame = None

    def _generate_synthetic_frame(self, t: float) -> np.ndarray:
        """Generates a professional synthetic test pattern for demo or camera testing."""
        w, h = 640, 360
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (18, 18, 24)  # Soft dark background

        # Grid lines
        for x in range(0, w, 40):
            cv2.line(frame, (x, 0), (x, h), (28, 28, 36), 1)
        for y in range(0, h, 40):
            cv2.line(frame, (0, y), (w, y), (28, 28, 36), 1)

        # Pulsing radar sweep
        cx, cy = w // 2, h // 2
        radius = 100
        cv2.circle(frame, (cx, cy), radius, (45, 45, 60), 1)
        cv2.circle(frame, (cx, cy), radius // 2, (45, 45, 60), 1)
        angle = (t * 2.5) % (2 * math.pi)
        px = int(cx + radius * math.cos(angle))
        py = int(cy + radius * math.sin(angle))
        cv2.line(frame, (cx, cy), (px, py), (31, 95, 255), 2)  # data-1 blue accent

        # Top banner with Camera ID
        cv2.rectangle(frame, (0, 0), (w, 36), (28, 28, 38), -1)
        cv2.putText(frame, f"CAM {self.slot_id:02d} - SYNTHETIC TEST PATTERN", (16, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        # Realtime timestamp
        now_str = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int((t % 1) * 1000):03d}"
        cv2.putText(frame, now_str, (w - 220, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 180), 1, cv2.LINE_AA)

        # Dynamic sine wave on bottom
        pts = []
        for x in range(20, w - 20, 4):
            val = math.sin((x * 0.05) + (t * 5.0)) * 25
            pts.append([x, int(h - 50 + val)])
        if len(pts) > 1:
            cv2.polylines(frame, [np.array(pts, dtype=np.int32)], False, (31, 166, 58), 2, cv2.LINE_AA)

        # Status text
        cv2.putText(frame, f"STATUS: LIVE SIMULATION | TARGET FPS: 25.0", (20, h - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (31, 166, 58), 1, cv2.LINE_AA)

        return frame

    def _run_loop(self):
        url = self.url
        is_demo = (url.lower() == "demo" or url.lower().startswith("demo:"))

        if is_demo:
            self._run_demo_loop()
        else:
            self._run_rtsp_loop(url)

    def _run_demo_loop(self):
        self.status = "live"
        self.width = 640
        self.height = 360
        last_calc = time.time()
        fps_counter = 0

        while self.is_running:
            t0 = time.time()
            frame = self._generate_synthetic_frame(t0)
            
            # Encode frame to JPEG
            ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with self.lock:
                    self.last_frame = buf.tobytes()
                    self.last_timestamp = t0
                    self.frame_count += 1

            fps_counter += 1
            if t0 - last_calc >= 1.0:
                self.fps = round(fps_counter / (t0 - last_calc), 1)
                fps_counter = 0
                last_calc = t0

            # Sleep to achieve ~25 FPS
            elapsed = time.time() - t0
            sleep_time = max(0.005, 0.04 - elapsed)
            time.sleep(sleep_time)

    def _run_rtsp_loop(self, url: str):
        reconnect_delay = 2.0
        while self.is_running:
            logger.info(f"Slot {self.slot_id}: Connecting to RTSP {url}...")
            self.status = "connecting"
            cap = None
            try:
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    raise RuntimeError("Failed to open RTSP stream source.")

                self.status = "live"
                self.error_msg = ""
                self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
                self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
                logger.info(f"Slot {self.slot_id}: Connected successfully ({self.width}x{self.height}).")

                last_calc = time.time()
                fps_counter = 0

                while self.is_running:
                    t0 = time.time()
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        logger.warning(f"Slot {self.slot_id}: Frame read returned empty or disconnected.")
                        break

                    # Encode to JPEG in memory
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 78]
                    ret_enc, buf = cv2.imencode(".jpg", frame, encode_params)
                    if ret_enc:
                        with self.lock:
                            self.last_frame = buf.tobytes()
                            self.last_timestamp = t0
                            self.frame_count += 1

                    fps_counter += 1
                    if t0 - last_calc >= 1.0:
                        self.fps = round(fps_counter / (t0 - last_calc), 1)
                        fps_counter = 0
                        last_calc = t0

                    # Cap capture loop yield
                    time.sleep(0.01)

            except Exception as e:
                self.status = "error"
                self.error_msg = str(e)
                logger.error(f"Slot {self.slot_id} error: {e}")
            finally:
                if cap is not None:
                    cap.release()

            if self.is_running:
                logger.info(f"Slot {self.slot_id}: Retrying in {reconnect_delay}s...")
                time.sleep(reconnect_delay)

    def get_info(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "url": self.url or "",
            "status": self.status,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "frame_count": self.frame_count,
            "error": self.error_msg,
            "clients": self.clients_count,
            "last_seen_sec": round(time.time() - self.last_timestamp, 2) if self.last_timestamp else None
        }


# Global store for 8 slots
SLOTS: Dict[int, StreamWorker] = {i: StreamWorker(i) for i in range(1, 9)}


@app.get("/api/status")
def get_status():
    """Returns the live status of all 8 slots."""
    return {"slots": [worker.get_info() for worker in SLOTS.values()]}


@app.post("/api/stream/{slot_id}/start")
def start_stream(slot_id: int, config: StreamConfig):
    """Starts or switches the RTSP stream for a specific slot."""
    if slot_id not in SLOTS:
        raise HTTPException(status_code=404, detail="Invalid slot ID (must be 1-8)")
    if not config.url.strip():
        raise HTTPException(status_code=400, detail="RTSP URL cannot be empty")

    worker = SLOTS[slot_id]
    worker.start(config.url)
    return {"message": f"Stream slot {slot_id} starting", "info": worker.get_info()}


@app.post("/api/stream/{slot_id}/stop")
def stop_stream(slot_id: int):
    """Stops the RTSP stream for a specific slot."""
    if slot_id not in SLOTS:
        raise HTTPException(status_code=404, detail="Invalid slot ID (must be 1-8)")

    worker = SLOTS[slot_id]
    worker.stop()
    return {"message": f"Stream slot {slot_id} stopped", "info": worker.get_info()}


def mjpeg_frame_generator(slot_id: int, url: Optional[str] = None) -> Generator[bytes, None, None]:
    """Generates an HTTP multipart MJPEG stream from the slot worker."""
    worker = SLOTS.get(slot_id)
    if not worker:
        return

    # If URL provided in query and worker not started, start it
    if url and (not worker.is_running or worker.url != url):
        worker.start(url)

    worker.clients_count += 1
    last_sent_ts = 0.0

    try:
        while True:
            # Check if new frame is available
            frame_data = None
            with worker.lock:
                if worker.last_frame is not None and worker.last_timestamp > last_sent_ts:
                    frame_data = worker.last_frame
                    last_sent_ts = worker.last_timestamp

            if frame_data is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame_data)).encode() + b"\r\n\r\n"
                    + frame_data
                    + b"\r\n"
                )
            
            # Rate limit client yielding to ~30 FPS
            time.sleep(0.03)

    except GeneratorExit:
        logger.info(f"Slot {slot_id}: Client disconnected from stream.")
    finally:
        worker.clients_count = max(0, worker.clients_count - 1)


@app.get("/api/stream/{slot_id}")
def stream_video(slot_id: int, url: Optional[str] = Query(None)):
    """
    Streams MJPEG live video directly to <img> or <canvas> tags in any browser.
    Accepts optional ?url=rtsp://... to trigger automatic start.
    """
    if slot_id not in SLOTS:
        raise HTTPException(status_code=404, detail="Invalid slot ID (must be 1-8)")

    return StreamingResponse(
        mjpeg_frame_generator(slot_id, url),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# Serve Static Assets explicitly so they are 100% accessible at root
@app.get("/")
def serve_index():
    index_file = CURRENT_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    return {"message": "RTSP Multi-Stream Server running. Please create index.html"}

@app.get("/styles.css")
def serve_css():
    css_file = CURRENT_DIR / "styles.css"
    if css_file.exists():
        return FileResponse(css_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="styles.css not found")

@app.get("/app.js")
def serve_js():
    js_file = CURRENT_DIR / "app.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="app.js not found")

# Also mount static directory at /static and fallback at root
app.mount("/static", StaticFiles(directory=str(CURRENT_DIR)), name="static")

def find_available_port(preferred_port: int = 8080) -> int:
    import socket
    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return preferred_port

if __name__ == "__main__":
    import uvicorn
    preferred = int(os.environ.get("PORT", 8080))
    port = find_available_port(preferred)
    print(f"============================================================")
    print(f"  RTSP Multi-Camera Gateway Server")
    print(f"  Listening on: http://localhost:{port}")
    print(f"  Open this URL in your browser to view the video cards")
    print(f"============================================================")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
