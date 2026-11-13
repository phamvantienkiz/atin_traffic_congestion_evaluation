"""Per-camera stateful AI processor combining Option 1, Option 2, and StateMachine."""

from __future__ import annotations

import threading
import time
from dataclasses import replace

import numpy as np

from ai.aux_pipeline.flow_occupancy import FlowOccupancy
from ai.config import AIConfig
from ai.core_pipeline.detector import Det
from ai.core_pipeline.tracker import CameraTracker
from ai.core_pipeline.zone_time import ZoneTimeAnalyzer
from ai.decision.classifier import classify
from ai.decision.occlusion import OcclusionShield
from ai.decision.state_machine import StateMachine
from ai.geometry import point_in_zone, roi_from_zone, zone_to_px
from ai.ingestion.stream_reader import StreamReader


class CameraProcessor:
    """Holds all per-camera state and runs Option 1 + Option 2 + StateMachine."""

    def __init__(self, cam: dict, cfg: AIConfig, rtsp_url: str) -> None:
        self.cam_id: str = cam["id"]
        overrides = cam.get("overrides") or {}
        self.cfg = replace(cfg, **overrides) if overrides else cfg

        self._lock = threading.RLock()
        self.reader = StreamReader(
            camera_id=self.cam_id,
            url=rtsp_url,
            w=self.cfg.frame_w,
            h=self.cfg.frame_h,
            fps=self.cfg.target_fps,
            timeout_s=self.cfg.stream_timeout_s,
        )
        self.tracker = CameraTracker(self.cfg, fps=self.cfg.target_fps)
        self.zone_time = ZoneTimeAnalyzer(self.cfg)
        self.flow_occ = FlowOccupancy(self.cfg)
        self.occlusion = OcclusionShield(self.cfg)
        self.sm = StateMachine(self.cfg, has_traffic_light=bool(cam.get("has_traffic_light", False)))

        self.zone_px: np.ndarray | None = None
        self.roi: tuple[int, int, int, int] = (0, 0, self.cfg.frame_w, self.cfg.frame_h)
        self._last_seq: int = -1
        self._last_frame: np.ndarray | None = None
        self._last_process_t: float | None = None
        self._last_result: dict | None = None
        self.pending_event: tuple[dict, np.ndarray] | None = None

        self.set_zone(cam.get("zone") or [])

    def start(self) -> None:
        self.reader.start()

    def stop(self) -> None:
        self.reader.stop()

    def update_meta(self, cam: dict) -> None:
        with self._lock:
            self.sm.has_traffic_light = bool(cam.get("has_traffic_light", False))
            self._set_zone_unlocked(cam.get("zone") or [])

    def set_zone(self, zone: list[dict]) -> None:
        with self._lock:
            self._set_zone_unlocked(zone)

    def _set_zone_unlocked(self, zone: list[dict]) -> None:
        self.zone_px = zone_to_px(zone, self.cfg.frame_w, self.cfg.frame_h)
        self.roi = roi_from_zone(
            self.zone_px,
            self.cfg.frame_w,
            self.cfg.frame_h,
            self.cfg.roi_padding,
        )
        self.zone_time.set_zone(self.zone_px)
        self.flow_occ.set_zone(self.zone_px)
        self.occlusion.set_zone(self.zone_px)

    def latest_frame(self) -> np.ndarray | None:
        pkt = self.reader.latest()
        if pkt is not None:
            return pkt.frame
        with self._lock:
            return self._last_frame

    def prepare(self) -> tuple[np.ndarray, tuple[int, int]] | None:
        pkt = self.reader.latest()
        if pkt is None or pkt.seq == self._last_seq:
            return None
        with self._lock:
            self._last_seq = pkt.seq
            self._last_frame = pkt.frame
            x0, y0, x1, y1 = self.roi
            crop = pkt.frame[y0:y1, x0:x1]
            return crop, (x0, y0)

    def process(self, det: Det, now: float) -> dict:
        with self._lock:
            frame = self._last_frame
            assert frame is not None

            dt = (now - self._last_process_t) if self._last_process_t is not None else (1.0 / self.cfg.target_fps)
            self._last_process_t = now

            tracks = self.tracker.update(det, now)
            zm = self.zone_time.update(tracks, now)

            in_zone_boxes = [
                t.xyxy for t in tracks if point_in_zone(self.zone_px, t.foot)
            ]
            bboxes_arr = (
                np.stack(in_zone_boxes, axis=0)
                if in_zone_boxes
                else np.zeros((0, 4), dtype=np.float32)
            )
            d85_max = max(
                float(zm["d85_2w"] or 0.0),
                float(zm["d85_4w"] or 0.0),
            )
            o_vis, v_flow = self.flow_occ.update(
                frame,
                bboxes_arr,
                dt=dt,
                stalled_hint=(d85_max > 5.0),
            )

            occ = self.occlusion.update(tracks, o_vis, now)
            metrics = {**zm, "o_vis": o_vis, "v_flow": v_flow}
            raw_state = classify(metrics, self.cfg)
            display_state, new_ev = self.sm.update(
                raw_state,
                now,
                stream_ok=self.reader.healthy,
                occ=occ,
            )

            w_inv = 1.0 / float(self.cfg.frame_w)
            h_inv = 1.0 / float(self.cfg.frame_h)
            detections = [
                {
                    "tid": t.tid,
                    "group": t.group,
                    "cls": t.cls_name,
                    "conf": round(t.conf, 2),
                    "bbox": [
                        round(float(t.xyxy[0]) * w_inv, 4),
                        round(float(t.xyxy[1]) * h_inv, 4),
                        round(float(t.xyxy[2]) * w_inv, 4),
                        round(float(t.xyxy[3]) * h_inv, 4),
                    ],
                    "in_zone": point_in_zone(self.zone_px, t.foot),
                }
                for t in tracks
            ]

            ts_wall = time.time()
            result = {
                "camera_id": self.cam_id,
                "ts": round(ts_wall, 3),
                "stream_ok": self.reader.healthy,
                "fps": round(self.reader.measured_fps, 1),
                "detections": detections,
                "metrics": metrics,
                "raw_state": raw_state,
                "state": display_state,
                "occlusion_hold": occ == "HOLD",
                "confirmed_state": self.sm.confirmed_state,
            }
            self._last_result = result

            if new_ev is not None:
                dur_s = (
                    self.cfg.confirm_gridlock_s
                    if new_ev == "GRIDLOCKED"
                    else (
                        self.cfg.confirm_congested_light_s
                        if self.sm.has_traffic_light
                        else self.cfg.confirm_congested_s
                    )
                )
                partial = {
                    "camera_id": self.cam_id,
                    "state": new_ev,
                    "ts": round(ts_wall, 3),
                    "duration_s": round(dur_s),
                    "metrics": metrics,
                    "detections": detections,
                }
                self.pending_event = (partial, frame.copy())

            return result

    def idle_result(self, now: float) -> dict:
        with self._lock:
            healthy = self.reader.healthy
            if self._last_result is not None:
                res = dict(self._last_result)
                res["stream_ok"] = healthy
                res["fps"] = round(self.reader.measured_fps, 1)
                if not healthy:
                    res["state"] = "UNKNOWN"
                return res

            return {
                "camera_id": self.cam_id,
                "ts": round(time.time(), 3),
                "stream_ok": healthy,
                "fps": 0.0,
                "detections": [],
                "metrics": {
                    "w_total": 0.0,
                    "n_2w": 0,
                    "n_4w": 0,
                    "t50_2w": None,
                    "t50_4w": None,
                    "d85_2w": None,
                    "d85_4w": None,
                    "n_completed_2w": 0,
                    "n_completed_4w": 0,
                    "o_vis": 0.0,
                    "v_flow": 0.0,
                },
                "raw_state": "CLEAR",
                "state": "UNKNOWN" if not healthy else "CLEAR",
                "occlusion_hold": False,
                "confirmed_state": "CLEAR",
            }
