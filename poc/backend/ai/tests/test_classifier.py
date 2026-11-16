"""Unit tests for ai.decision.classifier (V2)."""

from __future__ import annotations

import pytest

from ai.config import AIConfig
from ai.decision.classifier import classify

CFG = AIConfig()


def _metrics(**overrides: float | int | None) -> dict[str, float | int | None]:
    base: dict[str, float | int | None] = {
        "w_total": 0.0,
        "n_2w": 0,
        "n_4w": 0,
        "t50_2w": None,
        "t50_4w": None,
        "d85_2w": None,
        "d85_4w": None,
        "o_vis": 0.0,
        "v_flow": 0.0,
    }
    base.update(overrides)
    return base


def test_empty_or_parked_car_at_night_is_clear() -> None:
    st, conf = classify(_metrics(w_total=3.0, n_4w=1, d85_4w=60.0, o_vis=0.10, v_flow=18.0), CFG)
    assert st == "CLEAR"
    assert conf >= 0.85


def test_night_rain_glare_without_vehicles_blocked_by_sanity_gate() -> None:
    st, conf = classify(_metrics(w_total=0.0, o_vis=0.80, v_flow=2.0), CFG)
    assert st == "CLEAR"
    assert conf >= 0.85


def test_dense_but_fast_moving_is_clear() -> None:
    m = _metrics(w_total=20.0, n_4w=4, n_2w=8, t50_4w=4.8, t50_2w=3.8, o_vis=0.55, v_flow=18.0)
    st, conf = classify(m, CFG)
    assert st == "CLEAR"
    assert conf >= 0.85


def test_congested_with_time_metrics() -> None:
    m = _metrics(w_total=20.0, n_4w=4, n_2w=8, t50_4w=10.5, o_vis=0.78, v_flow=14.0)
    st, conf = classify(m, CFG)
    assert st == "CONGESTED"
    assert conf >= 0.85


def test_congested_macro_only_when_no_time_metrics() -> None:
    m = _metrics(w_total=9.0, n_4w=3, o_vis=0.75, v_flow=12.0)
    st, conf = classify(m, CFG)
    assert st == "CONGESTED"
    assert 0.70 <= conf <= 0.85


def test_gridlocked_with_time_metrics() -> None:
    m = _metrics(w_total=30.0, n_4w=5, n_2w=15, d85_4w=24.0, o_vis=0.88, v_flow=4.5)
    st, conf = classify(m, CFG)
    assert st == "GRIDLOCKED"
    assert conf >= 0.90


def test_gridlocked_macro_only_when_no_time_metrics() -> None:
    m = _metrics(w_total=6.0, n_4w=2, o_vis=0.88, v_flow=4.0)
    st, conf = classify(m, CFG)
    assert st == "GRIDLOCKED"
    assert 0.70 <= conf <= 0.85


def test_flow_overlap_resolved_by_t50() -> None:
    # Flow=12.0 sits in overlap between CLEAR (10..35), CONGESTED (6..25), GRIDLOCKED (0..15)
    st_clear, _ = classify(_metrics(w_total=15.0, o_vis=0.55, v_flow=12.0, t50_4w=4.5), CFG)
    st_cong, _ = classify(_metrics(w_total=20.0, o_vis=0.75, v_flow=12.0, t50_4w=10.0), CFG)
    st_grid, _ = classify(_metrics(w_total=25.0, o_vis=0.88, v_flow=12.0, t50_4w=17.0), CFG)
    assert st_clear == "CLEAR"
    assert st_cong == "CONGESTED"
    assert st_grid == "GRIDLOCKED"


def test_medium_occupancy_with_stalled_time_is_congested() -> None:
    m = _metrics(w_total=12.0, n_4w=4, o_vis=0.55, v_flow=8.0, d85_4w=22.0)
    st, conf = classify(m, CFG)
    assert st == "CONGESTED"
    assert conf == 0.82


def test_env_overrides_thresholds_and_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("W_SANITY_MIN", "2.0")
    monkeypatch.setenv("CONGESTED_T50_4W_S", "4.5")
    monkeypatch.setenv("WEIGHT_CAR", "2.5")
    monkeypatch.setenv("O_CLEAR", "   ")  # empty string falls back to default

    cfg = AIConfig()
    assert cfg.w_sanity_min == 2.0
    assert cfg.congested_t50_4w_s == 4.5
    assert cfg.class_weights["car"] == 2.5
    assert cfg.o_clear == 0.40

    st_ok, _ = classify(_metrics(w_total=12.0, t50_4w=4.0, o_vis=0.72, v_flow=15.0), cfg)
    st_slow, _ = classify(_metrics(w_total=12.0, t50_4w=4.6, o_vis=0.72, v_flow=15.0), cfg)
    assert st_ok == "CLEAR"
    assert st_slow == "CONGESTED"


def test_env_invalid_number_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("O_CLEAR", "not_a_number")
    with pytest.raises(ValueError, match="O_CLEAR"):
        AIConfig()
