"""Bus occlusion shield: prevents false CLEAR when heavy vehicles block the camera."""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from ai.config import AIConfig
from ai.core_pipeline.tracker import Track
from ai.geometry import point_in_zone, zone_mask


class OcclusionShield:
    """Detects heavy-vehicle occlusion via area ratio or sudden BBox drop + high O_vis."""

    def __init__(self, cfg: AIConfig) -> None:
        self.cfg = cfg
        self._zone_px: np.ndarray | None = None
        self._zone_mask_small: np.ndarray | None = None
        self._zone_area_small: int = 1
        self._history: deque[tuple[float, int]] = deque()
        self._hold_since: float | None = None

    def set_zone(self, zone_px: np.ndarray | None) -> None:
        self._zone_px = zone_px
        self._history.clear()
        self._hold_since = None
        if zone_px is None or len(zone_px) < 3:
            self._zone_mask_small = None
            self._zone_area_small = 1
            return

        sx = self.cfg.aux_w / float(self.cfg.frame_w)
        sy = self.cfg.aux_h / float(self.cfg.frame_h)
        scaled = np.round(zone_px.astype(np.float32) * np.array([sx, sy])).astype(np.int32)
        self._zone_mask_small = zone_mask(scaled, self.cfg.aux_w, self.cfg.aux_h)
        self._zone_area_small = max(1, int(cv2.countNonZero(self._zone_mask_small)))

    def update(self, tracks: list[Track], o_vis: float, now: float) -> str:
        """Return 'NONE', 'HOLD', or 'UNKNOWN_HOLD'."""
        if self._zone_px is None or self._zone_mask_small is None:
            self._hold_since = None
            return "NONE"

        in_zone = [t for t in tracks if point_in_zone(self._zone_px, t.foot)]
        n_now = len(in_zone)

        # Scenario A: heavy vehicles (bus/truck) cover > heavy_area_ratio of zone
        heavy_tracks = [t for t in tracks if t.cls_name in self.cfg.heavy_classes]
        heavy_occluded = False
        if heavy_tracks:
            sx = self.cfg.aux_w / float(self.cfg.frame_w)
            sy = self.cfg.aux_h / float(self.cfg.frame_h)
            heavy_mask = np.zeros((self.cfg.aux_h, self.cfg.aux_w), dtype=np.uint8)
            for t in heavy_tracks:
                x1 = max(0, min(self.cfg.aux_w - 1, int(round(t.xyxy[0] * sx))))
                y1 = max(0, min(self.cfg.aux_h - 1, int(round(t.xyxy[1] * sy))))
                x2 = max(0, min(self.cfg.aux_w - 1, int(round(t.xyxy[2] * sx))))
                y2 = max(0, min(self.cfg.aux_h - 1, int(round(t.xyxy[3] * sy))))
                if x2 > x1 and y2 > y1:
                    cv2.rectangle(heavy_mask, (x1, y1), (x2, y2), 255, thickness=-1)
            inter = cv2.bitwise_and(heavy_mask, self._zone_mask_small)
            ratio = float(cv2.countNonZero(inter)) / float(self._zone_area_small)
            heavy_occluded = ratio > self.cfg.heavy_area_ratio

        # Scenario B: sudden BBox drop (> 60%) while visual occupancy remains > 70%
        cutoff = now - 2.0
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        n_ref = max((cnt for _, cnt in self._history), default=0)
        drop_occluded = (
            n_ref >= 3
            and n_now <= (1.0 - self.cfg.bbox_drop_ratio) * n_ref
            and o_vis > self.cfg.occ_o_vis
        )

        # Only record non-occluded counts as reference baseline
        if not (heavy_occluded or drop_occluded):
            self._history.append((now, n_now))
            self._hold_since = None
            return "NONE"

        if self._hold_since is None:
            self._hold_since = now

        if (now - self._hold_since) > self.cfg.occ_hold_max_s:
            return "UNKNOWN_HOLD"
        return "HOLD"
