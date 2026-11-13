"""Tests for CameraProcessor metadata and zone updates."""

from ai.config import CFG
from ai.engine.camera_processor import CameraProcessor


def test_update_meta_and_set_zone_do_not_deadlock() -> None:
    cam = {
        "id": "cam1",
        "name": "Cam 1",
        "rtsp_url": "rtsp://127.0.0.1:28554/cam1",
        "has_traffic_light": False,
        "enabled": True,
        "zone": [],
    }
    proc = CameraProcessor(cam=cam, cfg=CFG, rtsp_url=cam["rtsp_url"])
    proc.update_meta(
        {
            **cam,
            "has_traffic_light": True,
            "zone": [
                {"x": 0.1, "y": 0.2},
                {"x": 0.9, "y": 0.2},
                {"x": 0.9, "y": 0.8},
                {"x": 0.1, "y": 0.8},
            ],
        }
    )
    assert proc.sm.has_traffic_light is True
    assert proc.zone_px is not None
    assert proc.zone_px.shape == (4, 2)
