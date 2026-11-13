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
            varThreshold=25,
            detectShadows=True,
        )
        self._kernel = np.ones((3, 3), dtype=np.uint8)
        self.prev_gray: np.ndarray | None = None
        self.zone_mask_small = np.full((cfg.aux_h, cfg.aux_w), 255, dtype=np.uint8)
        self.zone_area_small = int(cfg.aux_h * cfg.aux_w)
        self.frozen = False
        self._o_ema: float | None = None
        self._v_ema: float | None = None

    def set_zone(self, zone_px_1280: np.ndarray | None) -> None:
        """Update 320x180 zone mask and reset temporal state."""
        if zone_px_1280 is None or len(zone_px_1280) < 3:
            self.zone_mask_small = np.full(
                (self.cfg.aux_h, self.cfg.aux_w), 255, dtype=np.uint8
            )
        else:
            sx = self.cfg.aux_w / float(self.cfg.frame_w)
            sy = self.cfg.aux_h / float(self.cfg.frame_h)
            scaled = np.round(zone_px_1280.astype(np.float32) * np.array([sx, sy])).astype(np.int32)
            self.zone_mask_small = zone_mask(scaled, self.cfg.aux_w, self.cfg.aux_h)

        self.zone_area_small = max(1, int(cv2.countNonZero(self.zone_mask_small)))
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
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, self._kernel)

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

        occupied = cv2.bitwise_and(cv2.bitwise_or(fg, mask_yolo), self.zone_mask_small)
        o_vis_raw = float(cv2.countNonZero(occupied)) / float(self.zone_area_small)

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
