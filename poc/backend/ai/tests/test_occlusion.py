"""Unit tests for ai.decision.occlusion."""

from __future__ import annotations

import numpy as np

from ai.config import AIConfig
from ai.core_pipeline.tracker import Track
from ai.decision.occlusion import OcclusionShield


def _track(tid: int, cls_name: str, xyxy: list[float]) -> Track:
    x1, y1, x2, y2 = xyxy
    return Track(
        tid=tid,
        xyxy=np.array(xyxy, dtype=np.float32),
        conf=0.9,
        cls_name=cls_name,
        group="4W" if cls_name in ("car", "bus", "truck") else "2W",
        foot=((x1 + x2) * 0.5, y2),
    )


def test_heavy_vehicle_area_triggers_hold_then_unknown() -> None:
    cfg = AIConfig(heavy_area_ratio=0.35, occ_hold_max_s=10.0)
    shield = OcclusionShield(cfg)
    zone = np.array([[200, 200], [600, 200], [600, 500], [200, 500]], dtype=np.int32)
    shield.set_zone(zone)

    # Bus covers most of the zone
    bus = _track(1, "bus", [210, 210, 590, 490])
    assert shield.update([bus], o_vis=0.8, now=0.0) == "HOLD"
    assert shield.update([bus], o_vis=0.8, now=11.0) == "UNKNOWN_HOLD"


def test_sudden_bbox_drop_with_high_ovis_triggers_hold() -> None:
    cfg = AIConfig(bbox_drop_ratio=0.60, occ_o_vis=0.70)
    shield = OcclusionShield(cfg)
    zone = np.array([[200, 200], [600, 200], [600, 500], [200, 500]], dtype=np.int32)
    shield.set_zone(zone)

    cars = [_track(i + 1, "car", [220 + i * 50, 250, 260 + i * 50, 350]) for i in range(5)]
    assert shield.update(cars, o_vis=0.6, now=0.0) == "NONE"

    # Sudden drop from 5 cars to 1 car while o_vis is 0.85
    assert shield.update([cars[0]], o_vis=0.85, now=1.0) == "HOLD"
