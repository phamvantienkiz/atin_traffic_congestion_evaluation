"""Per-camera Staging worker wrapping poc/backend/ai CameraProcessor and Detector."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import cv2
import numpy as np

from .config import settings
from .storage_client import upload_snapshot

from ai.config import AIConfig
from ai.core_pipeline.detector import Detector
from ai.engine.camera_processor import CameraProcessor

logger = logging.getLogger("worker")
VN_TZ = timezone(timedelta(hours=7))

_STATE_META = {
    "CLEAR": ("#22c55e", "THÔNG THOÁNG"),
    "CONGESTED": ("#f59e0b", "ÙN TẮC"),
    "GRIDLOCKED": ("#ef4444", "KẸT XE"),
    "UNKNOWN": ("#9ca3af", "MẤT TÍN HIỆU"),
}


def _fmt_sec(val: float | None) -> str:
    return "–" if val is None else f"{float(val):.1f}s"


class CongestionStagingWorker:
    """Runs poc/backend/ai CameraProcessor on RTSP and publishes BBox/HUD/Events to AIOC VMS."""

    def __init__(
        self,
        camera_id: str,
        camera_code: str,
        rtsp_url: str,
        mqtt_client: Any,
        detector: Detector,
        detector_lock: threading.Lock,
        ai_cfg: AIConfig,
        organization_id: int = 0,
        initial_zones: list[dict] | None = None,
    ) -> None:
        self.camera_id = camera_id
        self.camera_code = camera_code
        self.rtsp_url = rtsp_url
        self.mqtt_client = mqtt_client
        self.detector = detector
        self.detector_lock = detector_lock
        self.ai_cfg = ai_cfg
        self.organization_id = organization_id

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_zone_id: str | None = None
        self._active_zone_name: str = "ROI"

        points, zid, zname = self._select_zone_points(initial_zones or [])
        self._active_zone_id = zid
        self._active_zone_name = zname

        cam_meta = {
            "id": camera_code,
            "zone": points,
            "has_traffic_light": False,
        }
        self.processor = CameraProcessor(cam=cam_meta, cfg=ai_cfg, rtsp_url=rtsp_url)

        self.stats = {
            "frames_processed": 0,
            "bbox_published": 0,
            "events_logged": 0,
            "events_published": 0,
            "last_inference_ms": 0.0,
            "last_state": "UNKNOWN",
            "start_time": time.time(),
        }

    def _select_zone_points(self, zones: list[dict]) -> tuple[list[dict[str, float]], str | None, str]:
        """Select active ROI polygon matching target module, or local/fallback ROI."""
        if settings.FORCE_LOCAL_ROI and len(settings.FALLBACK_ROI_POINTS) >= 3:
            return list(settings.FALLBACK_ROI_POINTS), None, "Local_Override_ROI"

        allowed_mods = {settings.BBOX_AI_MODULE, settings.EVENT_PUBLISH_MODE, "ZONE", "ANOMALY"}
        for z in zones:
            if not z.get("is_active", True):
                continue
            z_mod = str(z.get("ai_modules") or settings.BBOX_AI_MODULE).upper()
            if z_mod not in allowed_mods:
                continue
            pts = z.get("points") or []
            if len(pts) >= 3:
                norm_pts = [{"x": float(p["x"]), "y": float(p["y"])} for p in pts]
                return norm_pts, z.get("id"), str(z.get("name") or "ROI")

        if settings.ALLOW_FALLBACK_ROI and len(settings.FALLBACK_ROI_POINTS) >= 3:
            return list(settings.FALLBACK_ROI_POINTS), None, "Fallback_ROI"
        return [], None, "Full_Frame"

    def update_zones(self, zones: list[dict]) -> None:
        """Hot-reload ROI polygon into CameraProcessor in RAM (C03)."""
        if settings.FORCE_LOCAL_ROI and len(settings.FALLBACK_ROI_POINTS) >= 3:
            logger.info("[%s] Giữ nguyên Local ROI (bỏ qua %d ai_zones từ MQTT vì FORCE_LOCAL_ROI=true).", self.camera_code, len(zones))
            return
        points, zid, zname = self._select_zone_points(zones)
        self._active_zone_id = zid
        self._active_zone_name = zname
        self.processor.set_zone(points)
        logger.info(
            "[%s] Hot-reload ROI '%s' (%d điểm) vào CameraProcessor (C03).",
            self.camera_code,
            zname,
            len(points),
        )

    def start(self) -> None:
        """Start StreamReader and inference/publish loop."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.processor.start()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"congestion_{self.camera_code}",
            daemon=True,
        )
        self._thread.start()
        logger.info("[%s] Worker started | RTSP=%s", self.camera_code, self.rtsp_url)

    def stop(self) -> None:
        """Stop worker and underlying RTSP StreamReader safely (C02)."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.processor.stop()
        logger.info("[%s] Worker stopped.", self.camera_code)

    def _publish_bbox(self, result: dict) -> None:
        """Publish realtime BBox + 5-line PoC HUD to smart_vms/ai/bbox/{camera_code} (C07)."""
        state = str(result.get("state", "UNKNOWN"))
        state_color, state_label = _STATE_META.get(state, _STATE_META["UNKNOWN"])
        if result.get("occlusion_hold"):
            state_label = f"{state_label} (che khuất)"

        metrics = result.get("metrics") or {}
        n_2w = int(metrics.get("n_2w", 0))
        n_4w = int(metrics.get("n_4w", 0))
        o_vis_pct = round(float(metrics.get("o_vis") or 0.0) * 100.0)
        v_flow = round(float(metrics.get("v_flow") or 0.0), 1)
        t50_4w = _fmt_sec(metrics.get("t50_4w"))
        t50_2w = _fmt_sec(metrics.get("t50_2w"))
        d85_4w = _fmt_sec(metrics.get("d85_4w"))
        d85_2w = _fmt_sec(metrics.get("d85_2w"))

        vms_dets = [
            {
                "id": f"veh_{d.get('tid', idx + 1)}",
                "class": d.get("cls", "vehicle"),
                "confidence": d.get("conf", 0.0),
                "bbox": d.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                "track_id": d.get("tid", idx + 1),
            }
            for idx, d in enumerate(result.get("detections") or [])
        ]

        topic = f"smart_vms/ai/bbox/{self.camera_code}"
        payload = {
            "camera_code": self.camera_code,
            "camera_id": self.camera_id,
            "organization_id": self.organization_id,
            "ai_modules": settings.BBOX_AI_MODULE,
            "timestamp": time.time(),
            "detections": vms_dets,
            "hud": {
                "lines": [
                    state_label,
                    f"Độ phủ: {o_vis_pct}% · Dòng xe: {v_flow} px/s",
                    f"Trong vùng: {n_2w} xe máy · {n_4w} ô tô",
                    f"Thoát vùng: Ô tô {t50_4w} · Xe máy {t50_2w}",
                    f"Dừng/chậm: Ô tô {d85_4w} · Xe máy {d85_2w}",
                ],
                "line_colors": [state_color, "#e2e8f0", "#e2e8f0", "#e2e8f0", "#e2e8f0"],
                "color": state_color,
                "display_ms": 1000,
            },
        }
        self.mqtt_client.publish(topic, json.dumps(payload), qos=0)
        self.stats["bbox_published"] += 1

    def _draw_evidence(self, frame_bgr: np.ndarray, partial: dict) -> np.ndarray:
        """Render ROI polygon, vehicle detections, and congestion banner onto snapshot."""
        vis = frame_bgr.copy()
        h, w = vis.shape[:2]

        if self.processor.zone_px is not None and len(self.processor.zone_px) >= 3:
            cv2.polylines(vis, [self.processor.zone_px], isClosed=True, color=(0, 255, 255), thickness=2)

        for d in partial.get("detections") or []:
            x1, y1, x2, y2 = d["bbox"]
            p1 = (int(x1 * w), int(y1 * h))
            p2 = (int(x2 * w), int(y2 * h))
            color = (0, 0, 255) if d.get("in_zone") else (0, 200, 0)
            cv2.rectangle(vis, p1, p2, color, 2)

        metrics = partial.get("metrics") or {}
        o_vis_pct = round(float(metrics.get("o_vis") or 0.0) * 100.0, 1)
        v_flow = round(float(metrics.get("v_flow") or 0.0), 1)
        n_veh = int(metrics.get("n_2w", 0)) + int(metrics.get("n_4w", 0))
        banner = f"{partial['state']} ({partial['event_stage']}) | {n_veh} xe | O_vis: {o_vis_pct}% | Flow: {v_flow} px/s"
        cv2.rectangle(vis, (10, 10), (min(w - 10, 860), 48), (15, 23, 42), -1)
        cv2.putText(vis, banner, (20, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return vis

    def _build_event_payload(self, mode: str, partial: dict, object_key: str | None) -> tuple[str, dict] | None:
        """Build AIOC MQTT topic and payload according to configured EVENT_PUBLISH_MODE."""
        state = partial["state"]
        metrics = partial.get("metrics") or {}
        n_veh = int(metrics.get("n_2w", 0)) + int(metrics.get("n_4w", 0))
        o_vis = round(float(metrics.get("o_vis") or 0.0), 4)
        v_flow = round(float(metrics.get("v_flow") or 0.0), 2)
        now_iso = datetime.now(VN_TZ).isoformat(timespec="seconds")
        entity_id = f"congestion_{self.camera_code}_{int(time.time())}"

        congestion_meta = {
            "state": state,
            "event_stage": partial["event_stage"],
            "duration_s": partial["duration_s"],
            "o_vis": o_vis,
            "flow_speed_px_s": v_flow,
            "vehicle_count": n_veh,
            "zone_name": self._active_zone_name,
        }

        if mode == "PLATE":
            return (
                "smart_vms/ai_events/PLATE",
                {
                    "ai_modules": "PLATE",
                    "camera_id": self.camera_id,
                    "camera_code": self.camera_code,
                    "event_time": now_iso,
                    "entity_type": "VEHICLE",
                    "entity_id": entity_id,
                    "payload": {
                        "direction": "IN",
                        "confidence": partial["confidence"],
                        "vehicle": {
                            "license_plate": {"text": state, "status": "DETECTED", "plate_color": "YELLOW"},
                            "vehicle_type": "CAR",
                        },
                        "congestion_meta": congestion_meta,
                    },
                    "snapshot_url": object_key,
                },
            )
        if mode == "ZONE":
            return (
                "smart_vms/ai_events/ZONE",
                {
                    "ai_modules": "ZONE",
                    "camera_id": self.camera_id,
                    "camera_code": self.camera_code,
                    "event_time": now_iso,
                    "entity_type": "VEHICLE",
                    "entity_id": entity_id,
                    "count": n_veh,
                    "payload": {
                        "zone_id": self._active_zone_id or f"congestion_{self.camera_code}",
                        "zone_name": self._active_zone_name,
                        "direction": "IN",
                        **congestion_meta,
                    },
                    "snapshot_url": object_key,
                },
            )
        if mode == "CROWD_DETECTION":
            return (
                "smart_vms/ai_events/CROWD_DETECTION",
                {
                    "ai_modules": "CROWD_DETECTION",
                    "submodule_code": "CROWD_DETECTION",
                    "camera_id": self.camera_id,
                    "camera_code": self.camera_code,
                    "event_time": now_iso,
                    "event_type": "CROWD_DETECTION",
                    "entity_type": "VEHICLE",
                    "confidence": partial["confidence"],
                    "severity": "HIGH" if state == "GRIDLOCKED" else "MEDIUM",
                    "payload": {
                        "type": "HIGH_DENSITY",
                        "person_count": n_veh,
                        "threshold": 10,
                        **congestion_meta,
                    },
                    "snapshot_url": object_key,
                },
            )
        if mode == "TRAFFIC_CONGESTION":
            return (
                "smart_vms/ai_events/TRAFFIC_CONGESTION",
                {
                    "ai_modules": "TRAFFIC_CONGESTION",
                    "camera_id": self.camera_id,
                    "camera_code": self.camera_code,
                    "event_time": now_iso,
                    "entity_type": "TRAFFIC_STATE",
                    "entity_id": entity_id,
                    "confidence": partial["confidence"],
                    "severity": "HIGH" if state == "GRIDLOCKED" else "MEDIUM",
                    "payload": congestion_meta,
                    "snapshot_url": object_key,
                },
            )
        return None

    def _handle_confirmed_event(self, partial: dict, frame_bgr: np.ndarray) -> None:
        """Log confirmed congestion event locally and optionally publish to AIOC VMS."""
        self.stats["events_logged"] += 1
        metrics = partial.get("metrics") or {}
        logger.info(
            "[CONFIRMED EVENT] cam=%s | state=%s (%s) | dur=%ss | o_vis=%.3f | flow=%.1f px/s | veh=%d",
            self.camera_code,
            partial["state"],
            partial["event_stage"],
            partial["duration_s"],
            float(metrics.get("o_vis") or 0.0),
            float(metrics.get("v_flow") or 0.0),
            int(metrics.get("n_2w", 0)) + int(metrics.get("n_4w", 0)),
        )

        mode = settings.EVENT_PUBLISH_MODE
        if mode in ("NONE", "LOG_ONLY", ""):
            return

        vis = self._draw_evidence(frame_bgr, partial)
        category_map = {"PLATE": "plate", "ZONE": "zone", "CROWD_DETECTION": "anomaly", "TRAFFIC_CONGESTION": "anomaly"}
        object_key = upload_snapshot(vis, self.camera_id, category=category_map.get(mode, settings.STORAGE_CATEGORY))

        built = self._build_event_payload(mode, partial, object_key)
        if built is None:
            logger.warning("EVENT_PUBLISH_MODE='%s' không hợp lệ, bỏ qua publish MQTT.", mode)
            return

        topic, payload = built
        info = self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
        self.stats["events_published"] += 1
        logger.info(
            "[EVENT PUBLISH] topic=%s | camera=%s (%s) | object_key=%s | rc=%s",
            topic,
            self.camera_code,
            self.camera_id,
            object_key,
            info.rc,
        )

    def _run_loop(self) -> None:
        """Main loop: infer new frames via poc/backend/ai and publish BBox/HUD every 0.2s."""
        last_bbox_ts = 0.0

        while not self._stop_event.is_set():
            prep = self.processor.prepare()
            now_mono = time.monotonic()

            if prep is not None:
                crop, offset = prep
                t0 = time.perf_counter()
                with self.detector_lock:
                    dets = self.detector.detect_batch([crop], [offset])
                result = self.processor.process(dets[0], now_mono)
                self.stats["last_inference_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
                self.stats["frames_processed"] += 1
                self.stats["last_state"] = result["state"]

                if self.processor.pending_event is not None:
                    partial, ev_frame = self.processor.pending_event
                    self.processor.pending_event = None
                    self._handle_confirmed_event(partial, ev_frame)
            else:
                result = self.processor.idle_result(now_mono)
                time.sleep(0.02)

            now_wall = time.time()
            if result.get("stream_ok") and (now_wall - last_bbox_ts) >= settings.BBOX_PUBLISH_INTERVAL:
                last_bbox_ts = now_wall
                self._publish_bbox(result)
