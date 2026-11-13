"""Zone presence lifecycle: W_total, Median Travel Time (T50), and Active Dwell (D85)."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from ai.config import AIConfig
from ai.core_pipeline.tracker import Track
from ai.geometry import point_in_zone, zone_axis_length


@dataclass
class ZoneVisit:
    """Lifecycle of a tracked vehicle while inside the Poly Zone."""

    tid: int
    group: str
    t_first: float
    t_last: float
    p_first: tuple[float, float]
    p_last: tuple[float, float]


class ZoneTimeAnalyzer:
    """Computes W_total, T50 (2W/4W), and D85 (2W/4W) inside a Poly Zone."""

    def __init__(self, cfg: AIConfig) -> None:
        self.cfg = cfg
        self.zone_px: np.ndarray | None = None
        self.axis_len: float = 0.0
        self.active: dict[int, ZoneVisit] = {}
        self.completed: deque[tuple[float, str, float]] = deque()
        self._w_ema: float = 0.0
        self._last_t: float | None = None

    def set_zone(self, zone_px: np.ndarray | None) -> None:
        """Update polygon zone and reset active/completed state."""
        self.zone_px = zone_px
        self.axis_len = zone_axis_length(zone_px)
        self.active.clear()
        self.completed.clear()
        self._w_ema = 0.0
        self._last_t = None

    def update(self, tracks: list[Track], now: float) -> dict[str, float | int | None]:
        """Update zone visits with current tracks and return Option 1 metrics."""
        if self.zone_px is None or len(self.zone_px) < 3:
            self._last_t = now
            return {
                "w_total": 0.0,
                "n_2w": 0,
                "n_4w": 0,
                "t50_2w": None,
                "t50_4w": None,
                "d85_2w": None,
                "d85_4w": None,
                "n_completed_2w": 0,
                "n_completed_4w": 0,
            }

        in_zone_tracks: list[Track] = []
        in_zone_ids: set[int] = set()

        for tr in tracks:
            if point_in_zone(self.zone_px, tr.foot):
                in_zone_tracks.append(tr)
                in_zone_ids.add(tr.tid)
                visit = self.active.get(tr.tid)
                if visit is None:
                    self.active[tr.tid] = ZoneVisit(
                        tid=tr.tid,
                        group=tr.group,
                        t_first=now,
                        t_last=now,
                        p_first=tr.foot,
                        p_last=tr.foot,
                    )
                else:
                    visit.group = tr.group
                    visit.t_last = now
                    visit.p_last = tr.foot

        # Finalize tracks that exited the zone or timed out
        to_remove: list[int] = []
        min_travel = self.cfg.min_travel_ratio * self.axis_len
        for tid, visit in self.active.items():
            if tid not in in_zone_ids and (
                tid not in {t.tid for t in tracks} or (now - visit.t_last) >= self.cfg.lost_timeout_s
            ):
                # Exited zone or lost for >= lost_timeout_s
                to_remove.append(tid)
            elif tid not in in_zone_ids and any(t.tid == tid for t in tracks):
                # Track is still alive outside the zone -> exited immediately
                to_remove.append(tid)

        for tid in to_remove:
            visit = self.active.pop(tid)
            travel = math.hypot(
                visit.p_last[0] - visit.p_first[0],
                visit.p_last[1] - visit.p_first[1],
            )
            dur = visit.t_last - visit.t_first
            if travel >= min_travel and dur > 0.0:
                self.completed.append((now, visit.group, dur))

        # Evict completed records outside sliding window
        cutoff = now - self.cfg.window_s
        while self.completed and self.completed[0][0] < cutoff:
            self.completed.popleft()

        # Instantaneous weighted density & counts
        w_inst = sum(self.cfg.class_weights.get(t.cls_name, 3.0) for t in in_zone_tracks)
        if self._last_t is None:
            self._w_ema = w_inst
        else:
            dt = max(0.0, now - self._last_t)
            alpha = 1.0 - math.exp(-dt / 3.0) if dt > 0 else 1.0
            self._w_ema = alpha * w_inst + (1.0 - alpha) * self._w_ema
        self._last_t = now

        n_2w = sum(1 for t in in_zone_tracks if t.group == "2W")
        n_4w = sum(1 for t in in_zone_tracks if t.group == "4W")

        comp_2w = [dur for _, grp, dur in self.completed if grp == "2W"]
        comp_4w = [dur for _, grp, dur in self.completed if grp == "4W"]

        t50_2w = (
            float(np.median(comp_2w))
            if len(comp_2w) >= self.cfg.min_completed_samples
            else None
        )
        t50_4w = (
            float(np.median(comp_4w))
            if len(comp_4w) >= self.cfg.min_completed_samples
            else None
        )

        dwell_2w = [
            now - v.t_first
            for v in self.active.values()
            if v.group == "2W" and (now - v.t_first) >= self.cfg.min_dwell_s
        ]
        dwell_4w = [
            now - v.t_first
            for v in self.active.values()
            if v.group == "4W" and (now - v.t_first) >= self.cfg.min_dwell_s
        ]

        d85_2w = (
            float(np.percentile(dwell_2w, 85))
            if len(dwell_2w) >= self.cfg.min_active_samples
            else None
        )
        d85_4w = (
            float(np.percentile(dwell_4w, 85))
            if len(dwell_4w) >= self.cfg.min_active_samples
            else None
        )

        return {
            "w_total": round(self._w_ema, 2),
            "n_2w": n_2w,
            "n_4w": n_4w,
            "t50_2w": round(t50_2w, 2) if t50_2w is not None else None,
            "t50_4w": round(t50_4w, 2) if t50_4w is not None else None,
            "d85_2w": round(d85_2w, 2) if d85_2w is not None else None,
            "d85_4w": round(d85_4w, 2) if d85_4w is not None else None,
            "n_completed_2w": len(comp_2w),
            "n_completed_4w": len(comp_4w),
        }
