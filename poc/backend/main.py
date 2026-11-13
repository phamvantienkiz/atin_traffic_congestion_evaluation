"""FastAPI backend entrypoint for Traffic Congestion Evaluation PoC."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import torch
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from ai.engine.engine import TrafficEngine
from camera_store import CameraStore
from events import EventStore
from mediamtx import MediaMTX
from schemas import Camera, CameraIn, ZoneIn
from settings import (
    CAMERAS_FILE,
    DEMO_MODE,
    FRONTEND_DIR,
    MAX_CAMERAS,
    MEDIAMTX_BIN,
    MEDIAMTX_CONFIG,
    MEDIAMTX_WEBRTC_PORT,
    SNAP_DIR,
    WS_PUSH_HZ,
)
from ws_hub import WsHub, push_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _gpu_name() -> str:
    if torch.cuda.is_available():
        return torch.cuda.get_device_name(0)
    return "cpu"


def create_app(
    store: CameraStore | None = None,
    mtx: MediaMTX | None = None,
    engine: TrafficEngine | None = None,
    events: EventStore | None = None,
    startup_delay_s: float = 2.0,
) -> FastAPI:
    store = store or CameraStore(CAMERAS_FILE, max_cameras=MAX_CAMERAS)
    mtx = mtx or MediaMTX(MEDIAMTX_BIN, MEDIAMTX_CONFIG)
    engine = engine or TrafficEngine()
    events = events or EventStore(SNAP_DIR)
    hub = WsHub()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        cams = store.load()
        mtx.write_config(cams)
        mtx.start()
        if startup_delay_s > 0:
            await asyncio.sleep(startup_delay_s)
        engine.start()
        for c in cams:
            if c.enabled:
                engine.upsert_camera(c.model_dump())
        task = asyncio.create_task(push_loop(engine, hub, events, store, hz=WS_PUSH_HZ))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            engine.stop()
            mtx.stop()

    app = FastAPI(title="ATIN Traffic Congestion PoC", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "gpu": _gpu_name(), "cameras": len(store.load())}

    @app.get("/api/config")
    def get_config() -> dict:
        return {"webrtc_port": MEDIAMTX_WEBRTC_PORT, "demo_mode": DEMO_MODE}

    @app.get("/api/cameras", response_model=list[Camera])
    def list_cameras() -> list[Camera]:
        return store.load()

    @app.post("/api/cameras", response_model=Camera)
    async def add_camera(body: CameraIn) -> Camera:
        cams = store.load()
        try:
            cam_id = store.next_id(cams)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        cam = Camera(id=cam_id, **body.model_dump(), zone=[])
        cams.append(cam)

        def _apply() -> None:
            store.save(cams)
            mtx.write_config(cams)
            mtx.restart()
            engine.upsert_camera(cam.model_dump())

        await asyncio.to_thread(_apply)
        return cam

    @app.put("/api/cameras/{cam_id}", response_model=Camera)
    async def update_camera(cam_id: str, body: CameraIn) -> Camera:
        cams = store.load()
        idx = next((i for i, c in enumerate(cams) if c.id == cam_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")

        old = cams[idx]
        updated = Camera(id=cam_id, **body.model_dump(), zone=old.zone)
        cams[idx] = updated
        need_mtx_restart = (old.rtsp_url != updated.rtsp_url) or (old.enabled != updated.enabled)

        def _apply() -> None:
            store.save(cams)
            if need_mtx_restart:
                mtx.write_config(cams)
                mtx.restart()
            engine.upsert_camera(updated.model_dump())

        await asyncio.to_thread(_apply)
        return updated

    @app.delete("/api/cameras/{cam_id}")
    async def delete_camera(cam_id: str) -> dict:
        cams = store.load()
        new_cams = [c for c in cams if c.id != cam_id]
        if len(new_cams) == len(cams):
            raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")

        def _apply() -> None:
            engine.remove_camera(cam_id)
            store.save(new_cams)
            mtx.write_config(new_cams)
            mtx.restart()

        await asyncio.to_thread(_apply)
        return {"ok": True}

    @app.put("/api/cameras/{cam_id}/zone", response_model=Camera)
    async def update_zone(cam_id: str, body: ZoneIn) -> Camera:
        cams = store.load()
        idx = next((i for i, c in enumerate(cams) if c.id == cam_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")

        updated = cams[idx].model_copy(update={"zone": body.points})
        cams[idx] = updated

        def _apply() -> None:
            store.save(cams)
            engine.upsert_camera(updated.model_dump())

        await asyncio.to_thread(_apply)
        return updated

    @app.get("/api/cameras/{cam_id}/snapshot.jpg")
    def camera_snapshot(cam_id: str) -> Response:
        if store.get(cam_id) is None:
            raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")
        frame = engine.latest_frame(cam_id)
        if frame is None:
            raise HTTPException(status_code=404, detail="Chưa có khung hình từ camera")
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise HTTPException(status_code=500, detail="Không thể mã hóa ảnh JPEG")
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    def _encode_mjpeg_preview(frame) -> bytes | None:
        h, w = frame.shape[:2]
        if w > 640:
            preview = cv2.resize(frame, (640, int(round(h * (640.0 / w)))), interpolation=cv2.INTER_AREA)
        else:
            preview = frame
        ok, buf = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 55])
        return buf.tobytes() if ok else None

    @app.get("/api/cameras/{cam_id}/mjpeg")
    async def camera_mjpeg(cam_id: str, request: Request) -> StreamingResponse:
        if store.get(cam_id) is None:
            raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' không tồn tại")

        async def _gen():
            while not await request.is_disconnected():
                frame = engine.latest_frame(cam_id)
                if frame is not None:
                    data = await asyncio.to_thread(_encode_mjpeg_preview, frame)
                    if data is not None:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(data)}\r\n\r\n".encode()
                            + data
                            + b"\r\n"
                        )
                await asyncio.sleep(0.125)

        return StreamingResponse(
            _gen(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/events")
    def list_events() -> list[dict]:
        return events.list()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await hub.connect(ws)
        try:
            await ws.send_json({"type": "results", "data": engine.latest_results()})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(ws)
        except Exception:
            hub.disconnect(ws)

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory=str(SNAP_DIR)), name="snapshots")

    if Path(FRONTEND_DIR).exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()
