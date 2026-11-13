"""Unit tests for ai.decision.classifier."""

from __future__ import annotations

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
    assert classify(_metrics(w_total=3.0, n_4w=1, d85_4w=60.0, o_vis=0.10), CFG) == "CLEAR"


def test_dense_but_fast_moving_is_clear() -> None:
    m = _metrics(w_total=20.0, n_4w=4, n_2w=8, t50_4w=2.1, t50_2w=1.8, o_vis=0.50, v_flow=8.5)
    assert classify(m, CFG) == "CLEAR"


def test_cars_stalled_motorbikes_weaving_is_congested() -> None:
    m = _metrics(
        w_total=20.0,
        n_4w=4,
        n_2w=8,
        t50_4w=9.0,
        t50_2w=4.0,
        o_vis=0.55,
        v_flow=2.5,
    )
    assert classify(m, CFG) == "CONGESTED"


def test_congested_via_macro_flow_slow() -> None:
    m = _metrics(w_total=16.0, n_4w=3, o_vis=0.50, v_flow=3.0)
    assert classify(m, CFG) == "CONGESTED"


def test_gridlocked_mixed_traffic() -> None:
    m = _metrics(
        w_total=30.0,
        n_4w=5,
        n_2w=15,
        d85_4w=25.0,
        d85_2w=15.0,
        o_vis=0.80,
        v_flow=0.2,
    )
    assert classify(m, CFG) == "GRIDLOCKED"


def test_gridlocked_2w_only() -> None:
    m = _metrics(
        w_total=26.0,
        n_4w=0,
        n_2w=26,
        t50_2w=6.2,
        o_vis=0.68,
        v_flow=0.5,
    )
    assert classify(m, CFG) == "GRIDLOCKED"


def test_gridlocked_macro_rescue_when_t50_d85_none() -> None:
    m = _metrics(w_total=19.0, n_4w=3, o_vis=0.78, v_flow=0.4)
    assert classify(m, CFG) == "GRIDLOCKED"


def test_high_density_high_dwell_but_fast_flow_not_gridlocked() -> None:
    m = _metrics(
        w_total=28.0,
        n_4w=5,
        n_2w=10,
        d85_4w=12.0,
        d85_2w=9.0,
        o_vis=0.65,
        v_flow=4.0,
    )
    assert classify(m, CFG) == "CONGESTED"


def test_env_overrides_thresholds_and_weights(monkeypatch) -> None:
    monkeypatch.setenv("W_CLEAR", "10.0")
    monkeypatch.setenv("CONGESTED_T50_4W_S", "4.5")
    monkeypatch.setenv("WEIGHT_CAR", "2.5")
    monkeypatch.setenv("O_CLEAR", "   ")  # empty string falls back to default

    cfg = AIConfig()
    assert cfg.w_clear == 10.0
    assert cfg.congested_t50_4w_s == 4.5
    assert cfg.class_weights["car"] == 2.5
    assert cfg.o_clear == 0.35

    m = _metrics(w_total=16.0, n_4w=4, t50_4w=4.0, o_vis=0.40, v_flow=7.0)
    assert classify(m, cfg) == "CLEAR"
    m_slow = _metrics(w_total=16.0, n_4w=4, t50_4w=4.6, o_vis=0.40, v_flow=7.0)
    assert classify(m_slow, cfg) == "CONGESTED"


def test_env_invalid_number_raises_clear_error(monkeypatch) -> None:
    import pytest

    monkeypatch.setenv("W_CLEAR", "not_a_number")
    with pytest.raises(ValueError, match="W_CLEAR"):
        AIConfig()
