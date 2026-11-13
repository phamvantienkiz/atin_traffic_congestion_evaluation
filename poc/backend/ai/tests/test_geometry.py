"""Unit tests for ai.geometry."""

from __future__ import annotations

import numpy as np

from ai.geometry import point_in_zone, roi_from_zone, zone_axis_length, zone_mask, zone_to_px


def test_zone_to_px_and_none() -> None:
    assert zone_to_px(None, 1280, 720) is None
    assert zone_to_px([{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}], 1280, 720) is None

    pts = zone_to_px(
        [
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 1.0, "y": 1.0},
            {"x": 0.0, "y": 1.0},
        ],
        1280,
        720,
    )
    assert pts is not None
    assert pts.shape == (4, 2)
    assert pts.dtype == np.int32
    assert tuple(pts[2]) == (1279, 719)


def test_roi_from_zone_clamped() -> None:
    # Full frame fallback when zone is None
    assert roi_from_zone(None, 1280, 720, pad=0.1) == (0, 0, 1280, 720)

    # Box near top-left edge should clamp to 0
    zone = np.array([[10, 10], [110, 10], [110, 210], [10, 210]], dtype=np.int32)
    x0, y0, x1, y1 = roi_from_zone(zone, 1280, 720, pad=0.2)
    assert x0 == 0
    assert y0 == 0
    assert x1 == 130
    assert y1 == 250


def test_zone_axis_length_rectangle() -> None:
    rect = np.array([[100, 50], [200, 50], [200, 250], [100, 250]], dtype=np.int32)
    assert zone_axis_length(rect) == 200.0
    assert zone_axis_length(None) == 0.0


def test_point_in_zone_and_mask() -> None:
    rect = np.array([[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.int32)
    assert point_in_zone(rect, (150, 150)) is True
    assert point_in_zone(rect, (100, 100)) is True
    assert point_in_zone(rect, (50, 50)) is False
    assert point_in_zone(None, (50, 50)) is True

    mask = zone_mask(rect, 300, 300)
    assert mask.shape == (300, 300)
    assert mask[150, 150] == 255
    assert mask[10, 10] == 0
