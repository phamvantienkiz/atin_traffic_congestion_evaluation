"""Unit tests for ai.core_pipeline.tracker (verifies supervision.ByteTrack integration)."""

from __future__ import annotations

import numpy as np

from ai.config import AIConfig
from ai.core_pipeline.detector import Det
from ai.core_pipeline.tracker import CameraTracker, _snap_box_to_raw


def test_camera_tracker_and_majority_voting() -> None:
    cfg = AIConfig()
    tracker = CameraTracker(cfg, fps=15.0)

    # Empty detections should not crash
    assert tracker.update(Det.empty(), now=0.0) == []

    # Consistent car detections over several frames
    det_car = Det(
        xyxy=np.array([[100.0, 100.0, 200.0, 200.0]], dtype=np.float32),
        conf=np.array([0.9], dtype=np.float32),
        cls_name=["car"],
    )
    tracks = []
    for i in range(5):
        tracks = tracker.update(det_car, now=0.1 * (i + 1))

    assert len(tracks) == 1
    assert tracks[0].cls_name == "car"
    assert tracks[0].group == "4W"
    assert tracks[0].foot == (150.0, 200.0)


def test_snap_box_to_raw_eliminates_kalman_lag() -> None:
    # Kalman box slightly lagging behind current YOLO box (IoU ~ 0.68 >= 0.45)
    kalman_box = np.array([100.0, 100.0, 200.0, 200.0], dtype=np.float32)
    raw_boxes = np.array([[120.0, 100.0, 220.0, 200.0]], dtype=np.float32)
    snapped = _snap_box_to_raw(kalman_box, raw_boxes)
    np.testing.assert_allclose(snapped, raw_boxes[0])

    # Unmatched far box should retain Kalman box
    far_boxes = np.array([[500.0, 500.0, 600.0, 600.0]], dtype=np.float32)
    kept = _snap_box_to_raw(kalman_box, far_boxes)
    np.testing.assert_allclose(kept, kalman_box)
