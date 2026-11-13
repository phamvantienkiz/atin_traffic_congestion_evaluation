"""Polygon zone geometry, ROI cropping, and coordinate helpers."""

from __future__ import annotations

import math

import cv2
import numpy as np


def zone_to_px(zone: list[dict[str, float]] | None, w: int, h: int) -> np.ndarray | None:
    """Convert normalized [{x, y}, ...] points into an (N, 2) int32 pixel array."""
    if not zone or len(zone) < 3:
        return None
    pts = np.array(
        [[round(float(p["x"]) * w), round(float(p["y"]) * h)] for p in zone],
        dtype=np.int32,
    )
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
    return pts


def roi_from_zone(
    zone_px: np.ndarray | None,
    w: int,
    h: int,
    pad: float = 0.10,
) -> tuple[int, int, int, int]:
    """Return padded (x0, y0, x1, y1) ROI bounds clamped to frame dimensions."""
    if zone_px is None or len(zone_px) < 3:
        return (0, 0, w, h)

    x_min = int(zone_px[:, 0].min())
    y_min = int(zone_px[:, 1].min())
    x_max = int(zone_px[:, 0].max())
    y_max = int(zone_px[:, 1].max())

    bw = max(1, x_max - x_min)
    bh = max(1, y_max - y_min)
    px = int(round(bw * pad))
    py = int(round(bh * pad))

    x0 = max(0, x_min - px)
    y0 = max(0, y_min - py)
    x1 = min(w, x_max + px)
    y1 = min(h, y_max + py)

    if x1 <= x0 or y1 <= y0:
        return (0, 0, w, h)
    return (x0, y0, x1, y1)


def zone_axis_length(zone_px: np.ndarray | None) -> float:
    """Compute longitudinal zone length (px) between top-edge and bottom-edge midpoints."""
    if zone_px is None or len(zone_px) < 3:
        return 0.0

    # Sort vertices by y ascending; take top 2 and bottom 2 vertices
    idx = np.argsort(zone_px[:, 1])
    top_pts = zone_px[idx[:2]]
    bot_pts = zone_px[idx[-2:]]

    top_mid = top_pts.mean(axis=0)
    bot_mid = bot_pts.mean(axis=0)
    return float(math.hypot(float(bot_mid[0] - top_mid[0]), float(bot_mid[1] - top_mid[1])))


def point_in_zone(zone_px: np.ndarray | None, pt: tuple[float, float]) -> bool:
    """Return True if pt is inside or on the boundary of zone_px (or True if no zone)."""
    if zone_px is None or len(zone_px) < 3:
        return True
    return cv2.pointPolygonTest(zone_px, (float(pt[0]), float(pt[1])), False) >= 0


def zone_mask(zone_px: np.ndarray | None, w: int, h: int) -> np.ndarray:
    """Return a uint8 0/255 mask for zone_px (all 255 if zone_px is None)."""
    if zone_px is None or len(zone_px) < 3:
        return np.full((h, w), 255, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [zone_px], 255)
    return mask
