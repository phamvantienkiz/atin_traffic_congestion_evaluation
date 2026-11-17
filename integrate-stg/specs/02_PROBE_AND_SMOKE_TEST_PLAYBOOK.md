# HƯỚNG DẪN THỰC THI: PROBE, SMOKE TEST & TRIỂN KHAI STAGING (`camera_junction`)

> **Tài liệu này** cung cấp quy trình 4 bước thực hành từng bước để kiểm tra kết nối từ máy trạm / server AI tới **AIOC Staging (`https://aioc-stg.atin.vn/`)** cho camera **`Junction Camera` (`camera_junction`)**, xác nhận thông luồng BBox/HUD/Storage/Event trước khi chạy mô-đun đánh giá ùn tắc giao thông.

---

## Bước 1: Probe Thông Tin `camera_junction` Từ MQTT & Kiểm Tra RTSP (5 phút)

### Mục tiêu
Từ Web STG mới chỉ biết `camera_code = camera_junction`, module `PLATE`, và luồng gốc `rtsp://192.168.1.198:28537/tshtest`. Bước này giúp lấy đủ 4 thông tin bắt buộc còn thiếu:
1. **`camera_id` (UUID)** của `camera_junction`.
2. **`organization_id`** và **`zone_id`** chứa `camera_junction`.
3. **`rtsp_url` (MediaMTX `18554`)** do VMS cấp (nếu máy chạy AI không truy cập trực tiếp được `192.168.1.198:28537`).
4. Danh sách **`ai_zones`** hiện có trên `camera_junction` (nếu đã vẽ vùng trên Web VMS).

### Cách thực hiện
Tái sử dụng mẫu script `sidewalk_ai/scripts/step1_probe_mqtt_rtsp.py` với cấu hình `.env` trỏ vào `TARGET_CAMERA_CODE=camera_junction`:
- Subscribe wildcard:
  - `smart_vms/cameras/zone/+`
  - `smart_vms/cameras/company/+`
  - `smart_vms/cameras/camera_junction/ai_zones`
  - `smart_vms/cameras/camera_junction/ai_zones/#`
- Đọc toàn bộ bản tin retained trong 6 giây; lọc camera có `cam.get("code", "").lower() == "camera_junction"`.
- Kiểm tra đọc thử 1 frame từ `cam["rtsp_url"]` (nếu có), sau đó fallback sang `rtsp://192.168.1.198:28537/tshtest` bằng `cv2.VideoCapture(..., cv2.CAP_FFMPEG)` với `OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp|stimeout;5000000"`.

### Kết quả kỳ vọng
- In ra JSON của `camera_junction` gồm `id` (UUID), `zone_id`, `ai_modules` (xác nhận có `"PLATE"`), `rtsp_url`.
- Lưu được ảnh `probe_frame.jpg` từ luồng RTSP (nếu máy có VPN/LAN tới MediaMTX hoặc `192.168.1.198:28537`).

> [!NOTE]
> Nếu chạy trên máy cá nhân ngoài mạng công ty bị timeout `192.168.1.198:28537` hoặc `192.168.1.250:18554`, hãy kiểm tra kết nối VPN nội bộ ATIN hoặc triển khai chạy Worker trực tiếp trên Server AI nội bộ.

---

## Bước 2: Smoke Test Thông Luồng Web VMS Staging (5 phút)

Sau khi có `camera_id` (UUID) và `organization_id` từ Bước 1, tiến hành kiểm tra 3 kênh giao tiếp **trước khi ghép model `poc/backend/ai`**:

### 2.1. Test BBox & HUD Realtime trên Live View (`PLATE`)

- **Topic:** `smart_vms/ai/bbox/camera_junction` (`qos=0`, `retain=False`)
- **Tần suất:** gửi 50 gói, mỗi `0.2s` (10 giây).
- **Payload mẫu:**
  ```json
  {
    "camera_code": "camera_junction",
    "camera_id": "<UUID_TU_BUOC_1>",
    "organization_id": "<ORG_ID_TU_BUOC_1>",
    "ai_modules": "PLATE",
    "timestamp": 1763356800.0,
    "detections": [
      {
        "id": "veh_1",
        "class": "car",
        "confidence": 0.91,
        "bbox": [0.22, 0.40, 0.45, 0.72],
        "track_id": 101
      }
    ],
    "hud": {
      "text": "TEST: CONGESTED | 14 xe | O: 72% | Flow: 8.5 px/s",
      "display_ms": 1500,
      "color": "#f59e0b"
    }
  }
  ```
- **Kiểm tra trên Web `https://aioc-stg.atin.vn/monitoring`:**
  1. Mở ô camera **Junction Camera**.
  2. Bật nút **Phát hiện AI**.
  3. Tại dropdown **"AI: ..."** ở góc ô, chọn **Giám sát phương tiện** (`PLATE`).
  4. Xác nhận thấy khung chữ nhật `car 0.91` và dòng HUD màu vàng cam hiện đè lên video.

### 2.2. Test Upload Snapshot lên Storage API

- **Endpoint:** `POST https://aioc-stg.atin.vn/storage/upload/file`
- **Form-data:**
  - `file`: `probe_frame.jpg` (hoặc JPEG nén từ RAM)
  - `camera_id`: `<UUID_TU_BUOC_1>`
  - `category`: `plate` *(nếu test kênh PLATE)* hoặc `zone` / `anomaly` *(nếu bật thêm module tương ứng)*
- **Kiểm tra:**
  - Response `200` trả về `object_key`.
  - Mở trình duyệt `https://aioc-stg.atin.vn/api/v1/snapshot/image?object_key=<object_key>` thấy ảnh hiển thị bình thường.

### 2.3. Test Publish Event (Tùy theo Option A hoặc B ở Tài liệu `01`)

#### Trường hợp 1 — Option A (Khuyến nghị: Đã bật thêm `ZONE` hoặc `CROWD_DETECTION` trên `camera_junction` và chờ 60s)
- Nếu dùng **`ZONE`** (`category=zone`, topic `smart_vms/ai_events/ZONE`):
  ```json
  {
    "ai_modules": "ZONE",
    "camera_id": "<UUID_TU_BUOC_1>",
    "camera_code": "camera_junction",
    "event_time": "2026-11-17T12:30:00+07:00",
    "entity_type": "VEHICLE",
    "entity_id": "congestion_junction_01",
    "count": 18,
    "payload": {
      "zone_id": "<AI_ZONE_UUID_HOAC_CODE>",
      "zone_name": "Junction_ROI",
      "direction": "IN",
      "congestion_state": "CONGESTED",
      "o_vis": 0.74,
      "flow_speed_px_s": 8.4
    },
    "snapshot_url": "<object_key>"
  }
  ```
- Nếu dùng **`CROWD_DETECTION`** (`category=anomaly`, topic `smart_vms/ai_events/CROWD_DETECTION`):
  ```json
  {
    "ai_modules": "CROWD_DETECTION",
    "submodule_code": "CROWD_DETECTION",
    "camera_id": "<UUID_TU_BUOC_1>",
    "camera_code": "camera_junction",
    "event_time": "2026-11-17T12:30:00+07:00",
    "event_type": "CROWD_DETECTION",
    "entity_type": "VEHICLE",
    "confidence": 0.88,
    "severity": "HIGH",
    "payload": {
      "type": "HIGH_DENSITY",
      "person_count": 18,
      "threshold": 12,
      "zone_name": "Junction_ROI",
      "congestion_state": "CONGESTED",
      "o_vis": 0.74,
      "flow_speed_px_s": 8.4
    },
    "snapshot_url": "<object_key>"
  }
  ```

#### Trường hợp 2 — Option B (Chỉ giữ nguyên module `PLATE` trên `camera_junction`)
- Topic: `smart_vms/ai_events/PLATE` (`category=plate`), **bắt buộc** giữ đúng cấu trúc lồng `payload.vehicle.license_plate.text`:
  ```json
  {
    "ai_modules": "PLATE",
    "camera_id": "<UUID_TU_BUOC_1>",
    "camera_code": "camera_junction",
    "event_time": "2026-11-17T12:30:00+07:00",
    "entity_type": "VEHICLE",
    "entity_id": "congestion_junction_1763358600",
    "payload": {
      "direction": "IN",
      "confidence": 0.88,
      "vehicle": {
        "license_plate": { "text": "CONGESTED", "status": "DETECTED", "plate_color": "YELLOW" },
        "vehicle_type": "CAR"
      },
      "congestion_meta": {
        "state": "CONGESTED",
        "o_vis": 0.74,
        "flow_speed_px_s": 8.4,
        "vehicle_count": 18
      }
    },
    "snapshot_url": "<object_key>"
  }
  ```

---

## Bước 3: Cấu Hình Môi Trường & Đóng Gói Adapter Chạy Thật

### 3.1. File cấu hình `.env.staging.example`

```ini
# --- 1. MQTT Staging ---
MQTT_HOST=aioc-stg.atin.vn
MQTT_PORT=443
MQTT_WS_PATH=/mqtt
MQTT_USER=atin
MQTT_PASS=<NHAP_MAT_KHAU_STG>
MQTT_CLIENT_ID=ai_edge_congestion_junction_01
MQTT_KEEPALIVE=30

# --- 2. Phạm vi & Camera mục tiêu (Điền giá trị từ Bước 1 Probe) ---
ORGANIZATION_ID=<ORG_ID_TU_BUOC_1>
ZONE_ID=<ZONE_ID_TU_BUOC_1>
TARGET_CAMERA_CODE=camera_junction
TARGET_CAMERA_ID=<UUID_TU_BUOC_1>
FALLBACK_RTSP_URL=rtsp://192.168.1.198:28537/tshtest

# --- 3. Định tuyến Module AIOC ---
# BBox hiển thị trên ô Live View (khớp module đã bật trên Junction Camera)
BBOX_AI_MODULE=PLATE
# Kênh gửi sự kiện: ZONE | CROWD_DETECTION | PLATE | NONE (chỉ log local, không pub event)
EVENT_AI_MODULE=PLATE
STORAGE_UPLOAD_URL=https://aioc-stg.atin.vn/storage/upload/file
STORAGE_CATEGORY=plate

# --- 4. Tham số PoC Traffic Congestion V2 (đồng bộ poc/backend/ai/config.py) ---
MODEL_PATH=yolo26s.pt
DEVICE=cuda:0
MOG2_LR_NORMAL=0.002
O_CLEAR=0.40
O_CONGESTED=0.70
O_GRIDLOCK=0.85
BBOX_PUBLISH_INTERVAL=0.2
# Khi test nhanh trên staging có thể giảm tạm thời (chuẩn prod = 180)
EVENT_CONFIRM_S=180.0
# ROI fallback (normalized 0..1) nếu camera chưa được vẽ ai_zones trên Web VMS
FALLBACK_ROI_POINTS=[[0.15,0.25],[0.85,0.25],[0.95,0.95],[0.05,0.95]]
```

### 3.2. Nguyên tắc tích hợp code vào `poc/backend` (hoặc service riêng)

- Giữ nguyên lõi thuật toán trong `poc/backend/ai/` (`CameraProcessor`, `Detector`, `FlowOccupancy`, `OcclusionShield`, `StateMachine`, `geometry.py`) — **không nhân bản thuật toán**.
- Tạo lớp Adapter mỏng (tương tự `sidewalk_ai/src/main.py`, `worker.py`, `storage_client.py`) gọi trực tiếp `CameraProcessor.process_frame(frame)`:
  1. Đọc RTSP với `rtsp_transport;tcp`, `CAP_PROP_BUFFERSIZE=1`, resize về `1280x720` nếu cần (hoặc để `CameraProcessor` tự chuẩn hóa).
  2. Cập nhật `ai_zones` hot-reload vào `CameraProcessor` khi nhận polygon mới từ MQTT.
  3. Throttle gửi `smart_vms/ai/bbox/camera_junction` mỗi `0.2s`.
  4. Khi `FrameResult.event` khác `None`, upload ảnh qua `storage_client` và publish lên `smart_vms/ai_events/{EVENT_AI_MODULE}`.
- Tuân thủ `AGENTS.md`:
  - Chạy Python bằng `poc/backend/.venv` hoặc `uv run --project poc/backend`, **không** cài gói global.
  - Không lưu file `.env` có mật khẩu thật lên Git.

---

## Bước 4: Checklist Nghiệm Thu & Xử Lý Sự Cố Nhanh

### Checklist Nghiệm Thu Trên `https://aioc-stg.atin.vn/`
- [ ] **C01:** Log worker báo `MQTT CONNECTED (rc=0)` và không bị disconnect/reconnect lặp lại.
- [ ] **C02:** Worker tìm thấy `camera_junction`, lấy đúng `camera_id` UUID và đọc được luồng video `tshtest` (hoặc MediaMTX `18554`).
- [ ] **C03:** Khi vẽ/sửa polygon trên Web STG (nếu dùng `ZONE`/`ANOMALY`) $\rightarrow$ log báo `Hot-reload` cập nhật đúng số điểm mới mà không crash.
- [ ] **C04:** Luồng video ổn định, không trễ khung hình > 1s, tự phục hồi khi ngắt RTSP tạm thời.
- [ ] **C07:** Trên `/monitoring`, bật **Phát hiện AI** + chọn đúng module ở góc ô $\rightarrow$ thấy BBox xe + dòng chữ trạng thái `CLEAR / CONGESTED / GRIDLOCKED` + `O_vis` + `px/s` cập nhật mượt mỗi `0.2s`.
- [ ] **C05 & C06 & C08:** Khi có sự kiện xác nhận, ảnh snapshot mở được qua `/api/v1/snapshot/image?object_key=...` và sự kiện xuất hiện trong Lịch sử sự kiện trên Web VMS (nếu bật kênh event).

### Bảng Xử Lý Sự Cố Nhanh (Staging)

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không mở được `rtsp://192.168.1.198:28537/tshtest` | Máy chạy code không nằm trong LAN/VPN nội bộ hoặc port chỉ mở cho MediaMTX | Kiểm tra VPN; ưu tiên dùng `rtsp_url` (`192.168.1.250:18554/...`) trả về từ bản tin MQTT camera. |
| Đã gửi BBox `rc=0` nhưng Web `/monitoring` không hiện khung | 1) Chưa bật nút **Phát hiện AI**.<br>2) Dropdown góc ô đang chọn khác module `BBOX_AI_MODULE`.<br>3) Gửi chậm hơn `0.35s`. | Kiểm tra lại dropdown góc ô = `Giám sát phương tiện (PLATE)`, giữ interval `0.2s`. |
| Publish Event `rc=0` nhưng Web không lưu sự kiện | 1) Module event chưa được bật trên `camera_junction` (hoặc chưa qua 60s cache).<br>2) Gửi sai topic/schema (`TRAFFIC_CONGESTION` bị Backend drop). | Dùng đúng module đã bật trên `camera_junction` (Option A hoặc Option B). |
| Kết nối MQTT chập chờn `Connected` $\leftrightarrow$ `Disconnected` liên tục | Trùng `MQTT_CLIENT_ID` với tiến trình khác đang chạy | Đổi `MQTT_CLIENT_ID` thành chuỗi duy nhất mới. |
