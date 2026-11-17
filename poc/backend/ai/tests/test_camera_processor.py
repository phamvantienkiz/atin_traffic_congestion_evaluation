"""Tests for CameraProcessor metadata, zone updates, and split fast/macro pipeline."""

import numpy as np

from ai.config import CFG
from ai.core_pipeline.detector import Det
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

    idle = proc.idle_result(0.0)
    assert idle["state_conf"] == 0.0
    assert idle["metrics"]["state_conf"] == 0.0


def test_process_fast_and_process_macro_split() -> None:
    cam = {
        "id": "cam_split",
        "name": "Cam Split",
        "rtsp_url": "rtsp://127.0.0.1:28554/cam_split",
        "has_traffic_light": False,
        "enabled": True,
        "zone": [
            {"x": 0.1, "y": 0.2},
            {"x": 0.9, "y": 0.2},
            {"x": 0.9, "y": 0.8},
            {"x": 0.1, "y": 0.8},
        ],
    }
    proc = CameraProcessor(cam=cam, cfg=CFG, rtsp_url=cam["rtsp_url"])
    proc._last_frame = np.zeros((CFG.frame_h, CFG.frame_w, 3), dtype=np.uint8)
    det = Det(
        xyxy=np.array([[300.0, 300.0, 420.0, 420.0]], dtype=np.float32),
        conf=np.array([0.9], dtype=np.float32),
        cls_name=["car"],
    )

    fast_res, macro_task = proc.process_fast(det, now=1.0)
    assert len(fast_res["detections"]) == 1
    assert fast_res["state"] in ("CLEAR", "UNKNOWN")
    assert proc._last_result is None  # macro has not run yet

    macro_res = proc.process_macro(*macro_task)
    assert macro_res["camera_id"] == "cam_split"
    assert proc._last_result is not None
