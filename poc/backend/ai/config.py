"""Centralized configuration for the Traffic Congestion Evaluation AI pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_MODEL = str(Path(__file__).resolve().parents[3] / "models" / "vehicle_n_best.pt")
DEMO_MODE: bool = os.getenv("DEMO_MODE", "0") == "1"


@dataclass(frozen=True)
class AIConfig:
    """Immutable configuration parameters for AI inference, tracking, and decision."""

    model_path: str = os.getenv("MODEL_PATH", _DEFAULT_MODEL)
    device: str = os.getenv("DEVICE", "cuda:0")
    imgsz: int = 640
    conf: float = 0.15
    iou: float = 0.5
    frame_w: int = 1280
    frame_h: int = 720
    target_fps: float = 15.0
    roi_padding: float = 0.10

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
    class_weights: dict[str, float] = field(default_factory=lambda: {
        "motobike": 1.0,
        "motorcycle": 1.0,
        "motorbike": 1.0,
        "bicycle": 1.0,
        "car": 3.0,
        "bus": 6.0,
        "truck": 6.0,
    })
    heavy_classes: tuple[str, ...] = ("bus", "truck")

    # ByteTrack
    track_buffer_s: float = 2.5
    track_activation_conf: float = 0.45
    match_thresh: float = 0.8

    # Zone time (T50 & D85)
    window_s: float = 15.0
    min_dwell_s: float = 1.5
    min_travel_ratio: float = 0.45
    min_completed_samples: int = 3
    min_active_samples: int = 2
    lost_timeout_s: float = 1.0

    # Auxiliary pipeline (MOG2 + Farneback on 320x180)
    aux_w: int = 320
    aux_h: int = 180
    mog2_lr_normal: float = 0.005
    flow_noise_px: float = 0.8
    v_stall: float = 1.0
    v_clear: float = 6.0

    # Classifier thresholds
    w_clear: float = 12.0
    w_congested: float = 15.0
    w_gridlock: float = 24.0
    w_rescue: float = 18.0
    o_clear: float = 0.35
    o_congested: float = 0.45
    o_gridlock: float = 0.65
    o_rescue: float = 0.75

    # Occlusion shield
    heavy_area_ratio: float = 0.35
    bbox_drop_ratio: float = 0.60
    occ_o_vis: float = 0.70
    occ_hold_max_s: float = 30.0

    # State machine
    smooth_window_s: float = 5.0
    stream_timeout_s: float = 5.0
    confirm_congested_s: float = 15.0 if DEMO_MODE else 60.0
    confirm_congested_light_s: float = 20.0 if DEMO_MODE else 90.0
    confirm_gridlock_s: float = 30.0 if DEMO_MODE else 120.0
    persistence_tolerance_s: float = 5.0
    exit_clear_s: float = 15.0
    cooldown_s: float = 60.0


CFG = AIConfig()
