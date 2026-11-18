"""MQTT Orchestrator for AIOC Staging Traffic Congestion Integration (C01, C02, C03)."""

from __future__ import annotations

import json
import logging
import signal
import ssl
import threading
import time

import paho.mqtt.client as mqtt

from .config import build_ai_config, settings
from ai.core_pipeline.detector import Detector

from .worker import CongestionStagingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


class CongestionEdgeOrchestrator:
    """Manages MQTT lifecycle, camera worker spawn/stop, and hot-reload ai_zones."""

    def __init__(self) -> None:
        self.ai_cfg = build_ai_config()
        self.detector = Detector(self.ai_cfg)
        self.detector_lock = threading.Lock()

        self.workers: dict[str, CongestionStagingWorker] = {}
        self.zone_cache: dict[str, list[dict]] = {}
        self._stop_event = threading.Event()

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.MQTT_CLIENT_ID,
            transport="websockets",
        )
        ws_headers = {"Host": settings.STAGING_HOST_HEADER} if settings.STAGING_HOST_HEADER else None
        self.client.ws_set_options(path=settings.MQTT_WS_PATH, headers=ws_headers)
        if settings.MQTT_TLS_INSECURE:
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
        else:
            self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self.client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASS)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc, props=None) -> None:
        logger.info("[MQTT CONNECTED] rc=%s -> Subscribing camera & zone topics (C01)...", rc)

        if settings.ZONE_ID > 0:
            client.subscribe(f"smart_vms/cameras/zone/{settings.ZONE_ID}", qos=1)
        else:
            client.subscribe("smart_vms/cameras/zone/+", qos=1)

        if settings.ORGANIZATION_ID > 0:
            client.subscribe(f"smart_vms/cameras/company/{settings.ORGANIZATION_ID}", qos=1)
            req: dict[str, int] = {"organization_id": settings.ORGANIZATION_ID}
            if settings.ZONE_ID > 0:
                req["zone_id"] = settings.ZONE_ID
            client.publish("smart_vms/cameras/getdevice", json.dumps(req), qos=1)
        else:
            client.subscribe("smart_vms/cameras/company/+", qos=1)

        # C03: Subscribe camera ai_zones (tránh wildcard # bừa bãi để không bị ghi đè bởi /lines hoặc module khác)
        cam_code = settings.TARGET_CAMERA_CODE
        client.subscribe(f"smart_vms/cameras/{cam_code}/ai_zones", qos=1)
        client.subscribe(f"smart_vms/cameras/+/{'ai_zones'}/{settings.BBOX_AI_MODULE}", qos=1)
        if settings.EVENT_PUBLISH_MODE in ("ZONE", "CROWD_DETECTION", "TRAFFIC_CONGESTION"):
            client.subscribe(f"smart_vms/cameras/+/{'ai_zones'}/{settings.EVENT_PUBLISH_MODE}", qos=1)

    def on_disconnect(self, client, userdata, flags, rc, props=None) -> None:
        logger.warning("[MQTT DISCONNECT] rc=%s. Đang tự động kết nối lại (C01)...", rc)

    def on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        raw = msg.payload.decode("utf-8", errors="ignore").strip()

        if not raw:
            if "/ai_zones" in topic and "/lines" not in topic:
                parts = topic.split("/")
                cam_code = parts[2] if len(parts) >= 3 else settings.TARGET_CAMERA_CODE
                if cam_code.lower() == settings.TARGET_CAMERA_CODE.lower() and cam_code in self.workers:
                    self.workers[cam_code].update_zones([])
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[MQTT] Bỏ qua payload không phải JSON: %s", topic)
            return

        if topic.startswith("smart_vms/cameras/zone/") or topic.startswith("smart_vms/cameras/company/"):
            org_id = int(data.get("organization_id") or data.get("company_id") or settings.ORGANIZATION_ID or 0)
            self._handle_camera_list(data.get("cameras") or [], org_id)
        elif "/ai_zones" in topic:
            self._handle_zones_update(topic, data)

    def _handle_camera_list(self, cameras: list[dict], org_id: int) -> None:
        for cam in cameras:
            code = str(cam.get("code") or "")
            if code.lower() != settings.TARGET_CAMERA_CODE.lower():
                continue

            cam_id = str(cam.get("id") or settings.TARGET_CAMERA_ID)
            modules = {str(m).upper() for m in (cam.get("ai_modules") or [])}
            required_mod = settings.BBOX_AI_MODULE
            is_enabled = (required_mod in modules) or ("ANOMALY" in modules and required_mod == "CROWD_DETECTION")

            if is_enabled:
                rtsp_url = settings.RTSP_URL_OVERRIDE or str(cam.get("rtsp_url") or settings.FALLBACK_RTSP_URL)
                effective_org = org_id or settings.ORGANIZATION_ID
                if code not in self.workers:
                    logger.info(
                        "[C02] Camera '%s' (id=%s, org=%s) đã bật %s -> Khởi tạo Worker...",
                        code,
                        cam_id,
                        effective_org,
                        required_mod,
                    )
                    worker = CongestionStagingWorker(
                        camera_id=cam_id,
                        camera_code=code,
                        rtsp_url=rtsp_url,
                        mqtt_client=self.client,
                        detector=self.detector,
                        detector_lock=self.detector_lock,
                        ai_cfg=self.ai_cfg,
                        organization_id=effective_org,
                        initial_zones=self.zone_cache.get(code),
                    )
                    self.workers[code] = worker
                    worker.start()
            else:
                if code in self.workers:
                    logger.info("[C02] Module %s đã tắt trên '%s' -> Dừng Worker.", required_mod, code)
                    self.workers[code].stop()
                    del self.workers[code]

    def _handle_zones_update(self, topic: str, data: dict) -> None:
        if "/lines" in topic:
            return

        parts = topic.split("/")
        allowed_mods = {settings.BBOX_AI_MODULE, settings.EVENT_PUBLISH_MODE, "ZONE", "ANOMALY"}
        if len(parts) >= 5 and parts[3] == "ai_zones":
            if parts[4].upper() not in allowed_mods:
                return

        cam_code = str(data.get("camera_code") or (parts[2] if len(parts) >= 3 else settings.TARGET_CAMERA_CODE))
        if cam_code.lower() != settings.TARGET_CAMERA_CODE.lower():
            return

        zones = data.get("ai_zones") or []
        filtered = [
            z for z in zones if str(z.get("ai_modules") or settings.BBOX_AI_MODULE).upper() in allowed_mods
        ]

        if filtered or topic.endswith(f"/{settings.BBOX_AI_MODULE}") or topic.endswith("/ai_zones"):
            self.zone_cache[cam_code] = filtered
            if cam_code in self.workers:
                self.workers[cam_code].update_zones(filtered)

    def run(self) -> None:
        def sig_handler(signum, frame) -> None:
            logger.info("Nhận tín hiệu dừng (%s), đang thoát ngay...", signum)
            self._stop_event.set()
            # Cho phép bấm Ctrl+C lần 2 để thoát cưỡng bức nếu RTSP/MQTT đang kẹt
            signal.signal(signal.SIGINT, signal.SIG_DFL)

        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, sig_handler)
            signal.signal(signal.SIGTERM, sig_handler)

        logger.info("[ORCHESTRATOR] Kết nối MQTT %s:%s ...", settings.MQTT_HOST, settings.MQTT_PORT)
        self.client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=settings.MQTT_KEEPALIVE)
        self.client.loop_start()

        try:
            while not self._stop_event.wait(timeout=10.0):
                for code, worker in list(self.workers.items()):
                    elapsed = max(1.0, time.time() - worker.stats["start_time"])
                    fps = round(worker.stats["frames_processed"] / elapsed, 1)
                    logger.info(
                        "[STATS cam=%s] state=%s | FPS=%.1f | Infer=%.1fms | BBoxSent=%d | EvLogged=%d | EvPub=%d",
                        code,
                        worker.stats["last_state"],
                        fps,
                        worker.stats["last_inference_ms"],
                        worker.stats["bbox_published"],
                        worker.stats["events_logged"],
                        worker.stats["events_published"],
                    )
        finally:
            logger.info("Đang dừng Worker và ngắt kết nối MQTT...")
            for w in list(self.workers.values()):
                w.stop()
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Đã dừng hoàn tất.")


def main() -> None:
    CongestionEdgeOrchestrator().run()


if __name__ == "__main__":
    main()
