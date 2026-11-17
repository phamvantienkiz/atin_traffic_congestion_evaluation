"""Step 1: Probe camera_junction metadata, ai_zones, competing BBox streams, and RTSP."""

from __future__ import annotations

import json
import os
import ssl
import time
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

INTEGRATE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(INTEGRATE_ROOT / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "aioc-stg.atin.vn")
MQTT_PORT = int(os.getenv("MQTT_PORT", "443"))
MQTT_WS_PATH = os.getenv("MQTT_WS_PATH", "/mqtt")
MQTT_USER = os.getenv("MQTT_USER", "atin")
MQTT_PASS = os.getenv("MQTT_PASS", "")
TARGET_CAMERA = os.getenv("TARGET_CAMERA_CODE", "camera_junction")
FALLBACK_RTSP = os.getenv("FALLBACK_RTSP_URL", "rtsp://192.168.1.198:28537/tshtest")
ORG_ID = int(os.getenv("ORGANIZATION_ID", "0"))
ZONE_ID = int(os.getenv("ZONE_ID", "0"))

probe_result: dict = {
    "camera_info": None,
    "organization_id": None,
    "ai_zones": [],
    "existing_bbox_messages": [],
    "raw_topics_seen": [],
}


def on_connect(client, userdata, flags, rc, props=None) -> None:
    print(f"[MQTT] Connected (rc={rc}). Scanning camera, ai_zones, and live BBox traffic...")
    client.subscribe("smart_vms/cameras/zone/+", qos=1)
    client.subscribe("smart_vms/cameras/company/+", qos=1)
    client.subscribe(f"smart_vms/cameras/{TARGET_CAMERA}/ai_zones", qos=1)
    client.subscribe(f"smart_vms/cameras/{TARGET_CAMERA}/ai_zones/#", qos=1)
    # Kiểm tra xem có worker nào khác đang bắn BBox lên camera này không
    client.subscribe(f"smart_vms/ai/bbox/{TARGET_CAMERA}", qos=0)
    client.subscribe(f"smart_vms/bbox/{TARGET_CAMERA}", qos=0)

    if ORG_ID > 0:
        req = {"organization_id": ORG_ID}
        if ZONE_ID > 0:
            req["zone_id"] = ZONE_ID
        client.publish("smart_vms/cameras/getdevice", json.dumps(req), qos=1)


def on_message(client, userdata, msg) -> None:
    topic = msg.topic
    raw = msg.payload.decode("utf-8", errors="ignore").strip()
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    if topic not in probe_result["raw_topics_seen"]:
        probe_result["raw_topics_seen"].append(topic)

    if topic.startswith("smart_vms/cameras/zone/") or topic.startswith("smart_vms/cameras/company/"):
        org = data.get("organization_id") or data.get("company_id")
        for cam in data.get("cameras") or []:
            if str(cam.get("code", "")).lower() == TARGET_CAMERA.lower():
                probe_result["camera_info"] = cam
                if org and not probe_result["organization_id"]:
                    probe_result["organization_id"] = org
                print(f"\n[FOUND CAMERA] topic={topic} | org_id={org}:")
                print(json.dumps(cam, indent=2, ensure_ascii=False))

    elif "/ai_zones" in topic and "/lines" not in topic:
        zones = data.get("ai_zones") or []
        print(f"\n[FOUND ZONES] topic={topic} ({len(zones)} vùng):")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if zones:
            probe_result["ai_zones"] = zones

    elif "/bbox/" in topic:
        if len(probe_result["existing_bbox_messages"]) < 5:
            summary = {
                "topic": topic,
                "ai_modules": data.get("ai_modules"),
                "det_count": len(data.get("detections") or []),
                "hud": data.get("hud"),
            }
            probe_result["existing_bbox_messages"].append(summary)
            print(f"\n[WARNING - EXISTING BBOX TRAFFIC] Phát hiện worker khác đang bắn BBox: {summary}")


def test_rtsp(rtsp_url: str, zones: list[dict], out_path: Path) -> bool:
    print(f"\n[RTSP] Thử kết nối: {rtsp_url} ...")
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print(f"[RTSP ERROR] Không mở được: {rtsp_url}")
        return False

    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print(f"[RTSP ERROR] Mở được nhưng không đọc được frame: {rtsp_url}")
        return False

    h, w = frame.shape[:2]
    print(f"[RTSP OK] Đọc thành công 1 frame ({w}x{h}) từ {rtsp_url}")
    for z in zones:
        pts = z.get("points") or []
        if len(pts) >= 3:
            poly = np.array([[int(p["x"] * w), int(p["y"] * h)] for p in pts], np.int32)
            cv2.polylines(frame, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
    cv2.imwrite(str(out_path), frame)
    print(f"[SAVED] Ảnh chụp RTSP lưu tại: {out_path}")
    return True


def main() -> None:
    if not MQTT_PASS:
        print("[WARN] MQTT_PASS đang trống trong integrate-stg/.env! Hãy kiểm tra lại.")

    cid = f"{os.getenv('MQTT_CLIENT_ID', 'ai_edge_congestion')}_probe_{int(time.time()) % 10000}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, transport="websockets")
    client.ws_set_options(path=MQTT_WS_PATH)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[PROBE] Kết nối {MQTT_HOST}:{MQTT_PORT} (client_id={cid}) cho camera '{TARGET_CAMERA}'...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    time.sleep(8)
    client.loop_stop()
    client.disconnect()

    out_dir = Path(__file__).resolve().parent
    result_path = out_dir / "probe_result.json"
    result_path.write_text(json.dumps(probe_result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[SAVED] Kết quả Probe lưu tại: {result_path}")

    if not probe_result["existing_bbox_messages"]:
        print("[OK] Không có worker khác đang bắn BBox lên camera này trong 8s qua.")

    frame_path = out_dir / "probe_frame.jpg"
    mqtt_rtsp = (probe_result.get("camera_info") or {}).get("rtsp_url")
    ok = False
    if mqtt_rtsp:
        ok = test_rtsp(mqtt_rtsp, probe_result["ai_zones"], frame_path)
    if not ok and FALLBACK_RTSP and FALLBACK_RTSP != mqtt_rtsp:
        test_rtsp(FALLBACK_RTSP, probe_result["ai_zones"], frame_path)


if __name__ == "__main__":
    main()
