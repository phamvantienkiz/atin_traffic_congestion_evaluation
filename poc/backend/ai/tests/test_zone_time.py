"""Unit tests for ai.core_pipeline.zone_time."""

from __future__ import annotations

import numpy as np

from ai.config import AIConfig
from ai.core_pipeline.tracker import Track
from ai.core_pipeline.zone_time import ZoneTimeAnalyzer


def _make_track(tid: int, group: str, foot: tuple[float, float]) -> Track:
    cls_name = "motobike" if group == "2W" else "car"
    x, y = foot
    return Track(
        tid=tid,
        xyxy=np.array([x - 10, y - 20, x + 10, y], dtype=np.float32),
        conf=0.9,
        cls_name=cls_name,
        group=group,
        foot=foot,
    )


def test_completed_median_travel_time() -> None:
    cfg = AIConfig(min_completed_samples=3, min_active_samples=2)
    analyzer = ZoneTimeAnalyzer(cfg)
    zone = np.array([[100, 100], [300, 100], [300, 300], [100, 300]], dtype=np.int32)
    analyzer.set_zone(zone)

    # 5 cars cross the 200px zone from y=110 to y=290 in 4.0s each
    for i in range(5):
        tid = i + 1
        t_enter = float(i)
        analyzer.update([_make_track(tid, "4W", (200.0, 110.0))], now=t_enter)
        analyzer.update([_make_track(tid, "4W", (200.0, 290.0))], now=t_enter + 4.0)
        # Track moves outside zone
        res = analyzer.update([_make_track(tid, "4W", (200.0, 320.0))], now=t_enter + 4.2)

    assert res["n_completed_4w"] == 5
    assert res["t50_4w"] is not None
    assert abs(res["t50_4w"] - 4.0) < 0.05


def test_stalled_active_dwell_d85() -> None:
    cfg = AIConfig(min_completed_samples=3, min_active_samples=2, min_dwell_s=1.5)
    analyzer = ZoneTimeAnalyzer(cfg)
    zone = np.array([[100, 100], [300, 100], [300, 300], [100, 300]], dtype=np.int32)
    analyzer.set_zone(zone)

    # 6 cars enter at t=0 and stay stationary inside zone for 20s
    tracks = [_make_track(i + 1, "4W", (150.0 + i * 20, 200.0)) for i in range(6)]
    analyzer.update(tracks, now=0.0)
    res = analyzer.update(tracks, now=20.0)

    assert res["t50_4w"] is None
    assert res["d85_4w"] is not None
    assert abs(res["d85_4w"] - 20.0) < 0.05
    assert res["n_4w"] == 6
    assert res["w_total"] > 0.0


def test_short_fragment_filtered_out() -> None:
    cfg = AIConfig(min_completed_samples=1, min_travel_ratio=0.45)
    analyzer = ZoneTimeAnalyzer(cfg)
    zone = np.array([[100, 100], [300, 100], [300, 300], [100, 300]], dtype=np.int32)
    analyzer.set_zone(zone)

    # Track moves only 20px (< 45% of 200px) then exits -> filtered out
    analyzer.update([_make_track(1, "2W", (200.0, 150.0))], now=0.0)
    analyzer.update([_make_track(1, "2W", (200.0, 170.0))], now=1.0)
    res = analyzer.update([_make_track(1, "2W", (200.0, 350.0))], now=1.2)

    assert res["n_completed_2w"] == 0
    assert res["t50_2w"] is None
