"""MOG2 Visual Occupancy (O_vis) and Farneback Optical Flow (V_flow) on 320x180 ROI."""

from __future__ import annotations

import cv2
import numpy as np

from ai.config import AIConfig
from ai.geometry import zone_mask


class FlowOccupancy:
    """Computes macro visual occupancy ratio O_vis [0..1] and flow speed V_flow (px/s)."""

    def __init__(self, cfg: AIConfig) -> None:
        self.cfg = cfg
        self.mog2 = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=16,
            detectShadows=True,
        )
        self.close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 7))
        self.prev_gray: np.ndarray | None = None
        self.zone_mask_small = np.full((cfg.aux_h, cfg.aux_w), 255, dtype=np.uint8)
        self.row_weights = self._build_row_weights(0, cfg.aux_h - 1)
        self.zone_weight_sum = float(self.row_weights.sum()) * float(cfg.aux_w)
        self.frozen = False
        self._o_ema: float | None = None
        self._v_ema: float | None = None

    def _build_row_weights(self, y_min: int, y_max: int) -> np.ndarray:
        """Build linear perspective row weights from 2.2 (far/top) to 0.8 (near/bottom)."""
        y_coords = np.arange(self.cfg.aux_h, dtype=np.float32)[:, None]
        denom = float(max(1, y_max - y_min))
        weights = 2.2 - 1.4 * ((y_coords - float(y_min)) / denom)
        return np.clip(weights, 0.8, 2.2).astype(np.float32)

    def set_zone(self, zone_px_1280: np.ndarray | None) -> None:
        """Update 320x180 zone mask, perspective row weights, and reset temporal state."""
        if zone_px_1280 is None or len(zone_px_1280) < 3:
            self.zone_mask_small = np.full(
                (self.cfg.aux_h, self.cfg.aux_w), 255, dtype=np.uint8
            )
        else:
            sx = self.cfg.aux_w / float(self.cfg.frame_w)
            sy = self.cfg.aux_h / float(self.cfg.frame_h)
            scaled = np.round(zone_px_1280.astype(np.float32) * np.array([sx, sy])).astype(np.int32)
            self.zone_mask_small = zone_mask(scaled, self.cfg.aux_w, self.cfg.aux_h)

        ys = np.where(self.zone_mask_small > 0)[0]
        if len(ys) > 0:
            y_min, y_max = int(ys.min()), int(ys.max())
        else:
            y_min, y_max = 0, self.cfg.aux_h - 1

        self.row_weights = self._build_row_weights(y_min, y_max)
        zone_bool = (self.zone_mask_small > 0).astype(np.float32)
        self.zone_weight_sum = max(1e-6, float((zone_bool * self.row_weights).sum()))
        self.prev_gray = None
        self.frozen = False
        self._o_ema = None
        self._v_ema = None

    def update(
        self,
        frame_1280: np.ndarray,
        bboxes_1280: np.ndarray,
        dt: float,
        stalled_hint: bool,
    ) -> tuple[float, float]:
        """Process one 1280x720 frame and return smoothed (o_vis, v_flow)."""
        small = cv2.resize(
            frame_1280,
            (self.cfg.aux_w, self.cfg.aux_h),
            interpolation=cv2.INTER_AREA,
        )
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        lr = 0.0 if self.frozen else self.cfg.mog2_lr_normal
        fg = self.mog2.apply(small, learningRate=lr)
        # Keep only strong foreground (255), discard shadows (127)
        fg = np.where(fg == 255, 255, 0).astype(np.uint8)

        mask_yolo = np.zeros((self.cfg.aux_h, self.cfg.aux_w), dtype=np.uint8)
        if len(bboxes_1280) > 0:
            sx = self.cfg.aux_w / float(self.cfg.frame_w)
            sy = self.cfg.aux_h / float(self.cfg.frame_h)
            for box in bboxes_1280:
                x1 = max(0, min(self.cfg.aux_w - 1, int(round(box[0] * sx))))
                y1 = max(0, min(self.cfg.aux_h - 1, int(round(box[1] * sy))))
                x2 = max(0, min(self.cfg.aux_w - 1, int(round(box[2] * sx))))
                y2 = max(0, min(self.cfg.aux_h - 1, int(round(box[3] * sy))))
                if x2 > x1 and y2 > y1:
                    cv2.rectangle(mask_yolo, (x1, y1), (x2, y2), 255, thickness=-1)

        raw_union = cv2.bitwise_or(fg, mask_yolo)
        closed = cv2.morphologyEx(raw_union, cv2.MORPH_CLOSE, self.close_kernel)
        occupied = cv2.bitwise_and(closed, self.zone_mask_small)
        occ_bool = (occupied > 0).astype(np.float32)
        o_vis_raw = float((occ_bool * self.row_weights).sum()) / self.zone_weight_sum

        v_flow_raw = 0.0
        if self.prev_gray is not None and dt > 0.0:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray,
                gray,
                None,
                0.5,
                3,
                15,
                3,
                5,
                1.2,
                0,
            )
            mag = np.linalg.norm(flow, axis=2)
            mag[mag < self.cfg.flow_noise_px] = 0.0
            sel = occupied > 0
            if sel.any():
                v_flow_raw = float(mag[sel].mean() / dt)

        self.prev_gray = gray

        alpha = 0.3
        self._o_ema = o_vis_raw if self._o_ema is None else alpha * o_vis_raw + (1.0 - alpha) * self._o_ema
        self._v_ema = v_flow_raw if self._v_ema is None else alpha * v_flow_raw + (1.0 - alpha) * self._v_ema

        self.frozen = (self._v_ema < self.cfg.v_stall) and stalled_hint
        return round(self._o_ema, 4), round(self._v_ema, 2)
