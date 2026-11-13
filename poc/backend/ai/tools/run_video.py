"""Offline video runner for debugging and threshold tuning (G1 / G5)."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import cv2

from ai.aux_pipeline.flow_occupancy import FlowOccupancy
from ai.config import CFG
from ai.core_pipeline.detector import Detector
from ai.core_pipeline.tracker import CameraTracker
from ai.core_pipeline.zone_time import ZoneTimeAnalyzer
from ai.decision.classifier import classify
from ai.decision.occlusion import OcclusionShield
from ai.decision.state_machine import StateMachine
from ai.geometry import point_in_zone, roi_from_zone, zone_to_px

STATE_COLORS = {
    "CLEAR": (94, 197, 34),       # #22c55e (BGR)
    "CONGESTED": (11, 158, 245),  # #f59e0b
    "GRIDLOCKED": (68, 68, 239),  # #ef4444
    "UNKNOWN": (175, 163, 156),   # #9ca3af
}


def parse_zone(zone_str: str) -> list[dict[str, float]]:
    if not zone_str.strip():
        return []
    pts = []
    for pair in zone_str.split(";"):
        x_s, y_s = pair.strip().split(",")
        pts.append({"x": float(x_s), "y": float(y_s)})
    return pts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Run traffic congestion AI on an offline video.")
    ap.add_argument("--video", required=True, help="Input video file")
    ap.add_argument("--zone", default="", help="Normalized zone 'x1,y1;x2,y2;...'")
    ap.add_argument("--out", required=True, help="Output debug MP4 path")
    ap.add_argument("--light", action="store_true", help="Camera has traffic light")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.video}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = out_path.with_name(f"{out_path.stem}_metrics.csv")

    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        CFG.target_fps,
        (CFG.frame_w, CFG.frame_h),
    )

    detector = Detector(CFG)
    tracker = CameraTracker(CFG, fps=CFG.target_fps)
    zone_time = ZoneTimeAnalyzer(CFG)
    flow_occ = FlowOccupancy(CFG)
    occlusion = OcclusionShield(CFG)
    sm = StateMachine(CFG, has_traffic_light=args.light)

    zone_px = zone_to_px(parse_zone(args.zone), CFG.frame_w, CFG.frame_h)
    roi = roi_from_zone(zone_px, CFG.frame_w, CFG.frame_h, CFG.roi_padding)
    zone_time.set_zone(zone_px)
    flow_occ.set_zone(zone_px)
    occlusion.set_zone(zone_px)

    interval_ms = 1000.0 / CFG.target_fps
    next_ms = 0.0
    dt = 1.0 / CFG.target_fps

    with csv_path.open("w", newline="", encoding="utf-8") as f_csv:
        cw = csv.writer(f_csv)
        cw.writerow([
            "ts", "w_total", "n_2w", "n_4w", "t50_2w", "t50_4w",
            "d85_2w", "d85_4w", "o_vis", "v_flow", "raw_state", "state", "occ",
        ])

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if pos_ms < next_ms:
                continue
            next_ms = pos_ms + interval_ms
            now = pos_ms / 1000.0

            if frame.shape[1] != CFG.frame_w or frame.shape[0] != CFG.frame_h:
                frame = cv2.resize(frame, (CFG.frame_w, CFG.frame_h), interpolation=cv2.INTER_AREA)

            x0, y0, x1, y1 = roi
            det = detector.detect_batch([frame[y0:y1, x0:x1]], [(x0, y0)])[0]
            tracks = tracker.update(det, now)
            zm = zone_time.update(tracks, now)

            in_boxes = [t.xyxy for t in tracks if point_in_zone(zone_px, t.foot)]
            import numpy as np
            arr = np.stack(in_boxes, axis=0) if in_boxes else np.zeros((0, 4), dtype=np.float32)
            d85_max = max(float(zm["d85_2w"] or 0.0), float(zm["d85_4w"] or 0.0))
            o_vis, v_flow = flow_occ.update(frame, arr, dt=dt, stalled_hint=(d85_max > 5.0))
            occ = occlusion.update(tracks, o_vis, now)

            metrics = {**zm, "o_vis": o_vis, "v_flow": v_flow}
            raw_state = classify(metrics, CFG)
            state, _ = sm.update(raw_state, now, stream_ok=True, occ=occ)

            cw.writerow([
                round(now, 2), zm["w_total"], zm["n_2w"], zm["n_4w"],
                zm["t50_2w"], zm["t50_4w"], zm["d85_2w"], zm["d85_4w"],
                o_vis, v_flow, raw_state, state, occ,
            ])

            color = STATE_COLORS.get(state, (200, 200, 200))
            if zone_px is not None:
                cv2.polylines(frame, [zone_px], True, color, 3)

            for t in tracks:
                b_color = (248, 189, 56) if t.group == "2W" else (250, 139, 167)
                bx1, by1, bx2, by2 = [int(round(v)) for v in t.xyxy]
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), b_color, 2)
                cv2.putText(frame, f"{t.tid} {t.group}", (bx1, max(16, by1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, b_color, 2)
                cv2.circle(frame, (int(t.foot[0]), int(t.foot[1])), 3, b_color, -1)

            hud = (
                f"W:{zm['w_total']} 2B:{zm['n_2w']} 4B:{zm['n_4w']} | "
                f"T50(4B:{zm['t50_4w']} 2B:{zm['t50_2w']}) | "
                f"D85(4B:{zm['d85_4w']} 2B:{zm['d85_2w']}) | "
                f"O:{o_vis*100:.0f}% V:{v_flow:.1f}"
            )
            cv2.rectangle(frame, (10, 10), (920, 42), (0, 0, 0), -1)
            cv2.putText(frame, hud, (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.rectangle(frame, (CFG.frame_w - 230, CFG.frame_h - 55), (CFG.frame_w - 15, CFG.frame_h - 15), color, -1)
            cv2.putText(frame, state, (CFG.frame_w - 215, CFG.frame_h - 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            writer.write(frame)

    cap.release()
    writer.release()
    logging.info("Saved debug video to %s and metrics to %s", out_path, csv_path)


if __name__ == "__main__":
    main()
