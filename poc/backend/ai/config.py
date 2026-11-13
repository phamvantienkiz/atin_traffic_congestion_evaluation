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

    # Zone time (T50 & D85)
    window_s: float = _env_field("ZONE_WINDOW_S", 15.0, float)
    min_dwell_s: float = _env_field("ZONE_MIN_DWELL_S", 1.5, float)
    min_travel_ratio: float = _env_field("ZONE_MIN_TRAVEL_RATIO", 0.45, float)
    min_completed_samples: int = _env_field("ZONE_MIN_COMPLETED_SAMPLES", 3, int)
    min_active_samples: int = _env_field("ZONE_MIN_ACTIVE_SAMPLES", 2, int)
    lost_timeout_s: float = _env_field("ZONE_LOST_TIMEOUT_S", 1.0, float)

    # Auxiliary pipeline (MOG2 + Farneback on 320x180)
    aux_w: int = 320
    aux_h: int = 180
    mog2_lr_normal: float = _env_field("MOG2_LR_NORMAL", 0.005, float)
    flow_noise_px: float = _env_field("FLOW_NOISE_PX", 0.8, float)
    v_stall: float = _env_field("V_STALL", 1.0, float)
    v_clear: float = _env_field("V_CLEAR", 6.0, float)

    # Classifier density & occupancy thresholds
    w_clear: float = _env_field("W_CLEAR", 12.0, float)
    w_congested: float = _env_field("W_CONGESTED", 15.0, float)
    w_gridlock: float = _env_field("W_GRIDLOCK", 24.0, float)
    w_rescue: float = _env_field("W_RESCUE", 18.0, float)
    o_clear: float = _env_field("O_CLEAR", 0.35, float)
    o_congested: float = _env_field("O_CONGESTED", 0.45, float)
    o_gridlock: float = _env_field("O_GRIDLOCK", 0.65, float)
    o_macro_stall: float = _env_field("O_MACRO_STALL", 0.70, float)
    o_rescue: float = _env_field("O_RESCUE", 0.75, float)

    # Classifier time thresholds (T50 & D85 in seconds)
    congested_t50_4w_s: float = _env_field("CONGESTED_T50_4W_S", 3.0, float)
    congested_d85_4w_s: float = _env_field("CONGESTED_D85_4W_S", 5.0, float)
    congested_t50_2w_s: float = _env_field("CONGESTED_T50_2W_S", 3.0, float)
    congested_d85_2w_s: float = _env_field("CONGESTED_D85_2W_S", 4.5, float)
    gridlock_t50_4w_s: float = _env_field("GRIDLOCK_T50_4W_S", 7.0, float)
    gridlock_d85_4w_s: float = _env_field("GRIDLOCK_D85_4W_S", 10.0, float)
    gridlock_t50_2w_s: float = _env_field("GRIDLOCK_T50_2W_S", 5.0, float)
    gridlock_d85_2w_s: float = _env_field("GRIDLOCK_D85_2W_S", 8.0, float)
    gridlock_t50_2w_only_s: float = _env_field("GRIDLOCK_T50_2W_ONLY_S", 5.5, float)
    gridlock_d85_2w_only_s: float = _env_field("GRIDLOCK_D85_2W_ONLY_S", 8.5, float)

    # Occlusion shield
    heavy_area_ratio: float = _env_field("HEAVY_AREA_RATIO", 0.35, float)
    bbox_drop_ratio: float = _env_field("BBOX_DROP_RATIO", 0.60, float)
    occ_o_vis: float = _env_field("OCC_O_VIS", 0.70, float)
    occ_hold_max_s: float = _env_field("OCC_HOLD_MAX_S", 30.0, float)

    # State machine
    smooth_window_s: float = _env_field("SMOOTH_WINDOW_S", 5.0, float)
    stream_timeout_s: float = _env_field("STREAM_TIMEOUT_S", 5.0, float)
    confirm_congested_s: float = _env_field("CONFIRM_CONGESTED_S", 15.0 if DEMO_MODE else 60.0, float)
    confirm_congested_light_s: float = _env_field("CONFIRM_CONGESTED_LIGHT_S", 20.0 if DEMO_MODE else 90.0, float)
    confirm_gridlock_s: float = _env_field("CONFIRM_GRIDLOCK_S", 30.0 if DEMO_MODE else 120.0, float)
    persistence_tolerance_s: float = _env_field("PERSISTENCE_TOLERANCE_S", 5.0, float)
    exit_clear_s: float = _env_field("EXIT_CLEAR_S", 15.0, float)
    cooldown_s: float = _env_field("COOLDOWN_S", 60.0, float)


CFG = AIConfig()
