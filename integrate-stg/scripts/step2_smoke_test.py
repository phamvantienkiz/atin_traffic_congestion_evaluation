"""Step 2: Smoke test BBox+HUD (PLATE), Storage API upload, and optional Event publish."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv

INTEGRATE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(INTEGRATE_ROOT / ".env")

VN_TZ = timezone(timedelta(hours=7))


def upload_image(image_path: Path, camera_id: str, upload_url: str, category: str) -> str | None:
    with image_path.open("rb") as f:
        files = {"file": ("snapshot.jpg", f, "image/jpeg")}
        data = {"camera_id": camera_id, "category": category}
        resp = requests.post(upload_url, files=files, data=data, timeout=15)
    resp.raise_for_status()
    object_key = resp.json().get("object_key")
    print(f"[STORAGE OK] object_key = {object_key}")
    print(f"[VERIFY URL] https://aioc-stg.atin.vn/api/v1/snapshot/image?object_key={object_key}")
    return object_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Staging BBox/HUD + Storage + Event")
    parser.add_argument("--publish-event", action="store_true", help="Gửi kèm 1 event test theo EVENT_PUBLISH_MODE")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    probe_file = script_dir / "probe_result.json"

    camera_code = os.getenv("TARGET_CAMERA_CODE", "camera_junction")
    camera_id = os.getenv("TARGET_CAMERA_ID", "")
    org_id = int(os.getenv("ORGANIZATION_ID", "0"))
    bbox_module = os.getenv("BBOX_AI_MODULE", "PLATE").upper()
    event_mode = os.getenv("EVENT_PUBLISH_MODE", "NONE").upper()

    if probe_file.exists():
        probe = json.loads(probe_file.read_text(encoding="utf-8"))
        cam = probe.get("camera_info") or {}
        camera_id = cam.get("id") or camera_id
        camera_code = cam.get("code") or camera_code
        org_id = int(probe.get("organization_id") or org_id)

    if not camera_id:
        raise SystemExit("Thiếu TARGET_CAMERA_ID! Hãy chạy step1_probe_camera.py hoặc điền vào .env trước.")

    print(f"[SMOKE] camera_code={camera_code} | camera_id={camera_id} | org_id={org_id} | module={bbox_module}")

    cid = f"{os.getenv('MQTT_CLIENT_ID', 'ai_edge_congestion')}_smoke_{int(time.time()) % 10000}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, transport="websockets")
    client.ws_set_options(path=os.getenv("MQTT_WS_PATH", "/mqtt"))
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.username_pw_set(os.getenv("MQTT_USER", "atin"), os.getenv("MQTT_PASS", ""))
    client.connect(os.getenv("MQTT_HOST", "aioc-stg.atin.vn"), int(os.getenv("MQTT_PORT", "443")), keepalive=30)
    client.loop_start()

    bbox_topic = f"smart_vms/ai/bbox/{camera_code}"
    print(f"[BBOX TEST] Gửi 50 gói (10s @ 5 FPS) lên {bbox_topic} ...")
    for _ in range(50):
        payload = {
            "camera_code": camera_code,
            "camera_id": camera_id,
            "organization_id": org_id,
            "ai_modules": bbox_module,
            "timestamp": time.time(),
            "detections": [
                {"id": "veh_1", "class": "car", "confidence": 0.92, "bbox": [0.22, 0.40, 0.45, 0.72], "track_id": 1}
            ],
            "hud": {
                "text": "SMOKE TEST: CONGESTED | 14 xe | O_vis: 72% | Flow: 8.5 px/s",
                "display_ms": 1500,
                "color": "#f59e0b",
            },
        }
        client.publish(bbox_topic, json.dumps(payload), qos=0)
        time.sleep(0.2)

    img_path = script_dir / "probe_frame.jpg"
    if not img_path.exists():
        blank = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(blank, "AIOC CONGESTION SMOKE TEST", (60, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.imwrite(str(img_path), blank)

    category = "plate" if event_mode in ("NONE", "PLATE") else ("zone" if event_mode == "ZONE" else "anomaly")
    object_key = upload_image(
        img_path,
        camera_id=camera_id,
        upload_url=os.getenv("STORAGE_UPLOAD_URL", "https://aioc-stg.atin.vn/storage/upload/file"),
        category=category,
    )

    if args.publish_event and event_mode != "NONE":
        now_iso = datetime.now(VN_TZ).isoformat(timespec="seconds")
        topic = f"smart_vms/ai_events/{event_mode}"
        if event_mode == "PLATE":
            ev = {
                "ai_modules": "PLATE",
                "camera_id": camera_id,
                "camera_code": camera_code,
                "event_time": now_iso,
                "entity_type": "VEHICLE",
                "entity_id": f"smoke_{int(time.time())}",
                "payload": {
                    "direction": "IN",
                    "confidence": 0.9,
                    "vehicle": {"license_plate": {"text": "CONGESTED", "status": "DETECTED"}, "vehicle_type": "CAR"},
                },
                "snapshot_url": object_key,
            }
        else:
            ev = {
                "ai_modules": event_mode,
                "camera_id": camera_id,
                "camera_code": camera_code,
                "event_time": now_iso,
                "entity_type": "VEHICLE",
                "payload": {"zone_id": f"congestion_{camera_code}", "direction": "IN", "type": "HIGH_DENSITY"},
                "snapshot_url": object_key,
            }
        info = client.publish(topic, json.dumps(ev), qos=1)
        info.wait_for_publish(timeout=5)
        print(f"[EVENT PUBLISHED] topic={topic} | rc={info.rc}")

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
