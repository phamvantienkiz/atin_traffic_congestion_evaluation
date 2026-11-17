"""Unit tests for ai.aux_pipeline.flow_occupancy."""

from __future__ import annotations

import numpy as np

from ai.aux_pipeline.flow_occupancy import FlowOccupancy
from ai.config import AIConfig


def test_perspective_row_weights_range_and_direction() -> None:
    fo = FlowOccupancy(AIConfig())
    zone = np.array([[200, 200], [1000, 200], [1100, 600], [100, 600]], dtype=np.int32)
    fo.set_zone(zone)

    ys = np.where(fo.zone_mask_small > 0)[0]
    y_min, y_max = int(ys.min()), int(ys.max())
    assert abs(float(fo.row_weights[y_min, 0]) - 2.2) < 1e-4
    assert abs(float(fo.row_weights[y_max, 0]) - 0.8) < 1e-4
    assert fo.row_weights[y_min, 0] > fo.row_weights[y_max, 0]


def test_perspective_weights_boost_far_vehicles_over_near() -> None:
    cfg = AIConfig()
    zone = np.array([[200, 180], [1000, 180], [1000, 540], [200, 540]], dtype=np.int32)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    fo_far = FlowOccupancy(cfg)
    fo_far.set_zone(zone)
    fo_far.update(frame, np.zeros((0, 4), dtype=np.float32), dt=0.1, stalled_hint=False)
    # Same-size box placed in the far (top) half of the zone
    o_far, _ = fo_far.update(
        frame, np.array([[400, 200, 600, 300]], dtype=np.float32), dt=0.1, stalled_hint=False
    )

    fo_near = FlowOccupancy(cfg)
    fo_near.set_zone(zone)
    fo_near.update(frame, np.zeros((0, 4), dtype=np.float32), dt=0.1, stalled_hint=False)
    # Same-size box placed in the near (bottom) half of the zone
    o_near, _ = fo_near.update(
        frame, np.array([[400, 420, 600, 520]], dtype=np.float32), dt=0.1, stalled_hint=False
    )

    assert o_far > o_near


def test_morph_close_bridges_small_motorbike_gaps() -> None:
    cfg = AIConfig()
    zone = np.array([[100, 100], [500, 100], [500, 500], [100, 500]], dtype=np.int32)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Two boxes separated by a 16px horizontal gap (4px in 320x180, < 9px close kernel)
    boxes = np.array(
        [[200, 200, 280, 320], [296, 200, 376, 320]],
        dtype=np.float32,
    )
    fo = FlowOccupancy(cfg)
    fo.set_zone(zone)
    o_vis, _ = fo.update(frame, boxes, dt=0.1, stalled_hint=False)

    # Raw box area ratio without MORPH_CLOSE would be (2 * 80 * 120) / (400 * 400) = 0.12
    assert o_vis > 0.12
