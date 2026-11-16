"""Centralized configuration for the Traffic Congestion Evaluation AI pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TypeVar

from dotenv import load_dotenv

_POC_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_POC_DIR / ".env")

_DEFAULT_MODEL = str(_POC_DIR.parent / "models" / "vehicle_n_best.pt")
DEMO_MODE: bool = os.getenv("DEMO_MODE", "0") == "1"

_T = TypeVar("_T", int, float, str)


def _env(key: str, default: _T, cast: Callable[[str], _T]) -> _T:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid env value for {key}={raw!r}") from exc


def _env_field(key: str, default: _T, cast: Callable[[str], _T]):  # type: ignore[no-untyped-def]
    return field(default_factory=lambda: _env(key, default, cast))


def _default_weights() -> dict[str, float]:
    w2 = _env("WEIGHT_2W", 1.0, float)
    w_car = _env("WEIGHT_CAR", 3.0, float)
    w_heavy = _env("WEIGHT_HEAVY", 6.0, float)
    return {
        "motobike": w2,
        "motorcycle": w2,
        "motorbike": w2,
        "bicycle": w2,
        "car": w_car,
        "bus": w_heavy,
        "truck": w_heavy,
    }


@dataclass(frozen=True)
class AIConfig:
    """Immutable configuration parameters for AI inference, tracking, and decision."""

    model_path: str = _env_field("MODEL_PATH", _DEFAULT_MODEL, str)
    device: str = _env_field("DEVICE", "cuda:0", str)
    imgsz: int = _env_field("YOLO_IMGSZ", 640, int)
    conf: float = _env_field("YOLO_CONF", 0.15, float)
    iou: float = _env_field("YOLO_IOU", 0.5, float)
    frame_w: int = 1280
    frame_h: int = 720
    target_fps: float = 15.0
    roi_padding: float = _env_field("ROI_PADDING", 0.10, float)

    # Confirmed from models/vehicle_n_best.pt: {0: 'bus', 1: 'car', 2: 'motobike', 3: 'truck'}
    class_groups: dict[str, str] = field(default_factory=lambda: {
        "motobike": "2W",
        "motorcycle": "2W",
        "motorbike": "2W",
        "bicycle": "2W",
        "car": "4W",
        "bus": "4W",
        "truck": "4W",
    })
    class_weights: dict[str, float] = field(default_factory=_default_weights)
    heavy_classes: tuple[str, ...] = ("bus", "truck")

    # ByteTrack
    track_buffer_s: float = _env_field("TRACK_BUFFER_S", 2.5, float)
    track_activation_conf: float = _env_field("TRACK_ACTIVATION_CONF", 0.45, float)
    match_thresh: float = _env_field("TRACK_MATCH_THRESH", 0.8, float)

    # Zone time (T50 & D85 for Poly Zone 18-22m)
    window_s: float = _env_field("ZONE_WINDOW_S", 30.0, float)
    min_dwell_s: float = _env_field("ZONE_MIN_DWELL_S", 2.0, float)
    min_travel_ratio: float = _env_field("ZONE_MIN_TRAVEL_RATIO", 0.45, float)
    min_completed_samples: int = _env_field("ZONE_MIN_COMPLETED_SAMPLES", 2, int)
    min_active_samples: int = _env_field("ZONE_MIN_ACTIVE_SAMPLES", 2, int)
    lost_timeout_s: float = _env_field("ZONE_LOST_TIMEOUT_S", 1.0, float)

    # Auxiliary pipeline (MOG2 + Farneback on 320x180, flow_zone_px +20% each end)
    aux_w: int = 320
    aux_h: int = 180
    flow_zone_extend_ratio: float = _env_field("FLOW_ZONE_EXTEND_RATIO", 0.20, float)
    mog2_lr_normal: float = _env_field("MOG2_LR_NORMAL", 0.005, float)
    flow_noise_px: float = _env_field("FLOW_NOISE_PX", 0.8, float)
    v_stall: float = _env_field("V_STALL", 6.0, float)
    v_gridlock_max: float = _env_field("V_GRIDLOCK_MAX", 15.0, float)
    v_congested_macro: float = _env_field("V_CONGESTED_MACRO", 18.0, float)
    v_congested_max: float = _env_field("V_CONGESTED_MAX", 25.0, float)
    v_clear_min: float = _env_field("V_CLEAR_MIN", 10.0, float)

    # Classifier V2: O_vis + Flow + T50/D85 (W used as sanity gate & confidence bonus)
    w_sanity_min: float = _env_field("W_SANITY_MIN", 3.0, float)
    o_clear: float = _env_field("O_CLEAR", 0.40, float)
    o_congested: float = _env_field("O_CONGESTED", 0.70, float)
    o_gridlock: float = _env_field("O_GRIDLOCK", 0.85, float)

    # Classifier time thresholds (T50 & D85 in seconds)
    congested_t50_4w_s: float = _env_field("CONGESTED_T50_4W_S", 5.5, float)
    congested_d85_4w_s: float = _env_field("CONGESTED_D85_4W_S", 6.5, float)
    congested_t50_2w_s: float = _env_field("CONGESTED_T50_2W_S", 4.5, float)
    congested_d85_2w_s: float = _env_field("CONGESTED_D85_2W_S", 5.0, float)
    gridlock_t50_4w_s: float = _env_field("GRIDLOCK_T50_4W_S", 16.0, float)
    gridlock_d85_4w_s: float = _env_field("GRIDLOCK_D85_4W_S", 20.0, float)
    gridlock_t50_2w_s: float = _env_field("GRIDLOCK_T50_2W_S", 13.5, float)
    gridlock_d85_2w_s: float = _env_field("GRIDLOCK_D85_2W_S", 17.0, float)

    # Occlusion shield
    heavy_area_ratio: float = _env_field("HEAVY_AREA_RATIO", 0.45, float)
    bbox_drop_ratio: float = _env_field("BBOX_DROP_RATIO", 0.65, float)
    occ_o_vis: float = _env_field("OCC_O_VIS", 0.72, float)
    occ_hold_max_s: float = _env_field("OCC_HOLD_MAX_S", 40.0, float)

    # State machine (3m confirm -> +2m followup -> +15m periodic & immediate transition)
    smooth_window_s: float = _env_field("SMOOTH_WINDOW_S", 5.0, float)
    stream_timeout_s: float = _env_field("STREAM_TIMEOUT_S", 5.0, float)
    red_light_hold_s: float = _env_field("RED_LIGHT_HOLD_S", 15.0 if DEMO_MODE else 90.0, float)
    confirm_state_s: float = _env_field("CONFIRM_STATE_S", 30.0 if DEMO_MODE else 180.0, float)
    followup_after_confirm_s: float = _env_field(
        "FOLLOWUP_AFTER_CONFIRM_S", 20.0 if DEMO_MODE else 120.0, float
    )
    periodic_reminder_s: float = _env_field(
        "PERIODIC_REMINDER_S", 90.0 if DEMO_MODE else 900.0, float
    )
    persistence_tolerance_s: float = _env_field("PERSISTENCE_TOLERANCE_S", 5.0, float)
    exit_clear_s: float = _env_field("EXIT_CLEAR_S", 15.0, float)


CFG = AIConfig()
