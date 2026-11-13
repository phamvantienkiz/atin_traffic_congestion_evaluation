"""Backend API & WebSocket unit tests using a mocked TrafficEngine."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from camera_store import CameraStore
from events import EventStore
from main import create_app
from mediamtx import MediaMTX


class MockEngine:
    def __init__(self) -> None:
        self.cameras: dict[str, dict] = {}
        self.started = False
        self._frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def upsert_camera(self, cam: dict) -> None:
        self.cameras[cam["id"]] = cam

    def remove_camera(self, cam_id: str) -> None:
        self.cameras.pop(cam_id, None)

    def latest_results(self) -> list[dict]:
        return [
            {
                "camera_id": cid,
                "ts": 1700000000.0,
                "stream_ok": True,
                "fps": 15.0,
                "detections": [],
                "metrics": {
                    "w_total": 0.0, "n_2w": 0, "n_4w": 0,
                    "t50_2w": None, "t50_4w": None,
                    "d85_2w": None, "d85_4w": None,
                    "n_completed_2w": 0, "n_completed_4w": 0,
                    "o_vis": 0.0, "v_flow": 0.0,
                },
                "raw_state": "CLEAR",
                "state": "CLEAR",
                "occlusion_hold": False,
                "confirmed_state": "CLEAR",
            }
            for cid in self.cameras
        ]

    def pop_events(self) -> list[tuple[dict, np.ndarray]]:
        return []

    def latest_frame(self, cam_id: str) -> np.ndarray | None:
        return self._frame if cam_id in self.cameras else None


def _build_client(tmp_path: Path) -> tuple[TestClient, MockEngine]:
    store = CameraStore(tmp_path / "cameras.json", max_cameras=8)
    mtx = MediaMTX(tmp_path / "missing_mediamtx", tmp_path / "mediamtx.yml")
    engine = MockEngine()
    events = EventStore(tmp_path / "snapshots")
    app = create_app(store=store, mtx=mtx, engine=engine, events=events, startup_delay_s=0.0)
    return TestClient(app), engine


def test_camera_crud_zone_snapshot_and_ws(tmp_path: Path) -> None:
    client, engine = _build_client(tmp_path)
    with client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Add camera
        r = client.post(
            "/api/cameras",
            json={"name": "Cam 1", "rtsp_url": "rtsp://127.0.0.1:554/stream1"},
        )
        assert r.status_code == 200
        cam = r.json()
        assert cam["id"] == "cam1"
        assert "cam1" in engine.cameras

        # Invalid zone (< 3 points) -> 422
        r = client.put(
            "/api/cameras/cam1/zone",
            json={"points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}]},
        )
        assert r.status_code == 422

        # Valid 4-point zone
        pts = [
            {"x": 0.1, "y": 0.35},
            {"x": 0.9, "y": 0.37},
            {"x": 0.95, "y": 0.85},
            {"x": 0.05, "y": 0.83},
        ]
        r = client.put("/api/cameras/cam1/zone", json={"points": pts})
        assert r.status_code == 200
        assert len(r.json()["zone"]) == 4

        # Snapshot JPEG
        r = client.get("/api/cameras/cam1/snapshot.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

        # WebSocket initial payload
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "results"
            assert msg["data"][0]["camera_id"] == "cam1"

        # Delete camera
        r = client.delete("/api/cameras/cam1")
        assert r.status_code == 200
        assert client.get("/api/cameras").json() == []


def test_frontend_static_files_served(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    with client:
        r = client.get("/")
        assert r.status_code == 200
        assert "ATIN Traffic Congestion" in r.text
        assert client.get("/styles.css").status_code == 200
        assert client.get("/js/main.js").status_code == 200

