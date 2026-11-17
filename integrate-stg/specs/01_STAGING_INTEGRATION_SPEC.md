# ĐẶC TẢ TÍCH HỢP MÔ-ĐUN ĐÁNH GIÁ ÙN TẮC GIAO THÔNG LÊN MÔI TRƯỜNG STAGING (AIOC / SMART VMS)

> **Mục tiêu:** Đưa mô-đun AI đánh giá ùn tắc giao thông (`poc/backend/ai` — V2 Pipeline) tích hợp thử nghiệm lên hệ thống **AIOC Smart VMS Staging** (`https://aioc-stg.atin.vn/`) với camera mục tiêu **`Junction Camera` (`camera_junction`)**.
>
> **Tài liệu tham chiếu:** `docs/onboard/00..03`, `docs/onboard/AIOC-System-Design.md`, `sidewalk_ai/src/*`, `poc/backend/ai/*`.

---

## 1. Thông Số Môi Trường Staging & Camera Mục Tiêu

### 1.1. Hạ tầng AIOC Staging (`https://aioc-stg.atin.vn/`)

| Thành phần | Giá trị Staging | Ghi chú kỹ thuật |
|---|---|---|
| **Web VMS UI** | `https://aioc-stg.atin.vn/` | Giám sát trực tiếp: `/monitoring`, Quản lý camera, Lịch sử sự kiện |
| **MQTT Broker** | `wss://aioc-stg.atin.vn/mqtt` | MQTT 3.1.1 over WebSocket TLS, Port `443`, `keepalive = 30s` |
| **MQTT Credentials** | `atin` / `Atin@2026#` | Không commit `.env` chứa mật khẩu thật lên Git |
| **MQTT `client_id`** | `ai_edge_congestion_01` *(đề xuất)* | **CẤM** đặt bắt đầu bằng `vms_staging_backend` / `vms_prod_backend`; phải duy nhất cho mỗi process |
| **Storage API (Upload ảnh)** | `https://aioc-stg.atin.vn/storage/upload/file` | `POST multipart/form-data` (`file`, `camera_id`, `category`), tối đa `10 MB` |
| **Snapshot Verify URL** | `https://aioc-stg.atin.vn/api/v1/snapshot/image?object_key=<key>` | Luôn lấy `object_key` từ response Upload API, **tuyệt đối không dùng** `url` (`127.0.0.1:18646`) |

### 1.2. Thông Tin Camera Mục Tiêu (Từ Web Staging)

| Thuộc tính | Giá trị đã biết | Trạng thái / Cách lấy phần còn thiếu |
|---|---|---|
| **Tên camera** | `Junction Camera` | Đã có từ Web STG |
| **Mã camera (`camera_code`)** | `camera_junction` | Đã có từ Web STG |
| **Module AI đang bật** | `PLATE` (*Giám sát phương tiện - PLATE*) | Đã bật trên Web STG |
| **Luồng RTSP gốc** | `rtsp://192.168.1.198:28537/tshtest` | Có thể chỉ truy cập được qua LAN/VPN hoặc qua MediaMTX restream |
| **`camera_id` (UUID)** | *Chưa biết* | **Bắt buộc chạy Script Probe (Bước 1)** để lấy từ MQTT `smart_vms/cameras/...` |
| **`organization_id` / `zone_id`** | *Chưa biết* | **Bắt buộc chạy Script Probe (Bước 1)** (STG hiện có các org `103, 107, 109, 110, 112, 113, 115...`) |
| **MediaMTX `rtsp_url`** | *Chưa biết* (`rtsp://...@192.168.1.250:18554/...`) | Ưu tiên lấy động từ trường `rtsp_url` trong payload MQTT camera; fallback về `rtsp://192.168.1.198:28537/tshtest` |
| **Vùng vẽ (`ai_zones`)** | *Chưa biết* | Kiểm tra qua `smart_vms/cameras/camera_junction/ai_zones/#` hoặc vẽ mới trên Web VMS |

---

## 2. Phân Tích Hợp Đồng Giao Tiếp (Contract Gap) & Chiến Lược Tích Hợp

> [!WARNING]
> **PHÁT HIỆN QUAN TRỌNG TỪ `AI_MODULES_MQTT.md` (§1.2.1, §2.2, §5.1–§5.8):**
> 1. Backend AIOC VMS hiện **CHƯA có handler** cho module `TRAFFIC_CONGESTION`. Mọi bản tin gửi lên `smart_vms/ai_events/TRAFFIC_CONGESTION` sẽ rơi vào `handle_ai_event` — **chỉ ghi log, KHÔNG lưu Database và KHÔNG hiện thông báo**.
> 2. Backend kiểm tra phân quyền module trên từng camera (**Mục §1.2.1**): Sự kiện và BBox chỉ được chấp nhận khi `camera_junction` **đã bật đúng `ai_modules` đó trên Web VMS** (cache đồng bộ tối đa 60 giây).

Hiện tại trên Web STG, `camera_junction` chỉ đang bật module **`PLATE`** (*Giám sát phương tiện*). Do đó, cần tách bạch rõ **2 luồng dữ liệu** khi tích hợp lên Staging:

### 2.1. Luồng 1: BBox & HUD Realtime trên Live View (`/monitoring`) — Chạy ngay với `PLATE`

- **Topic:** `smart_vms/ai/bbox/camera_junction` (QoS `0`, `retain=False`).
- **Tần suất:** Bắt buộc gửi đều mỗi **`0.15s – 0.20s`** (5–6.6 FPS), vì Web VMS tự xóa khung BBox sau **`0.35s`** nếu không có gói tin mới (§5.8).
- **Khớp Module UI:** Đặt `"ai_modules": "PLATE"` trong payload BBox. Khi mở `Junction Camera` trên Web `/monitoring`:
  - Bật nút **Phát hiện AI**.
  - Chọn dropdown góc ô video là **`AI: Giám sát phương tiện`** (`PLATE`).
- **Dữ liệu hiển thị:**
  - `detections[]`: danh sách bounding box xe phát hiện bởi YOLO (`car`, `motorcycle`, `bus`, `truck`, `bicycle`), chuẩn hóa `[x1, y1, x2, y2]` trong `0..1`.
  - `hud`: hiển thị trạng thái ùn tắc tức thời + chỉ số cốt lõi ngay trên khung hình Web VMS:
    - `CLEAR` (`#22c55e`), `CONGESTED` (`#f59e0b`), `GRIDLOCKED` (`#ef4444`).
    - Ví dụ `hud.text`: `"CONGESTED | 18 xe | O_vis: 74% | Flow: 9.2 px/s"`.

### 2.2. Luồng 2: Sự Kiện Xác Nhận (`smart_vms/ai_events/...`) — 3 Phương Án Triển Khai

Vì `camera_junction` mới bật `PLATE` và Backend chưa có `TRAFFIC_CONGESTION`, nhóm cần chọn 1 trong 3 phương án sau (có thể kết hợp theo giai đoạn):

| Phương án | Cách thực hiện | Ưu điểm | Hạn chế / Lưu ý |
|---|---|---|---|
| **Option A (Khuyến nghị để test đủ luồng trên STG):** Bật thêm `ZONE` hoặc `CROWD_DETECTION` trên `camera_junction` | Vào Quản lý camera trên Web STG, bật thêm module `ZONE` (hoặc `CROWD_DETECTION`), chờ 60s. Dùng `PLATE` để vẽ BBox/HUD hoặc chọn đúng module đó trên ô video; bắn sự kiện xác nhận qua `smart_vms/ai_events/ZONE` (hoặc `CROWD_DETECTION`). | - Hỗ trợ **vẽ đa giác ROI (`ai_zones`)** chuẩn trên Web VMS.<br>- Sự kiện được Backend lưu PostgreSQL, hiện thông báo chuông & lịch sử thật.<br>- Không cần sửa code Backend VMS. | - `ANOMALY` (`CROWD_DETECTION`) sinh **2 notification/event** (§7 #2) và mặc định `severity=HIGH`.<br>- `ZONE` phát `NEW_ZONE_EVENT` 2 lần (§7 #2).<br>- Tên hiển thị trên Web là "Vùng cấm" / "Đám đông" thay vì "Ùn tắc". |
| **Option B (Giữ nguyên chỉ bật `PLATE`):** Chạy BBox/HUD qua `PLATE` + log event nội bộ (hoặc test gửi `PLATE` event tạm) | Chỉ dùng `smart_vms/ai/bbox/camera_junction` (`ai_modules: "PLATE"`) để trình diễn AI realtime trên Web VMS. Nếu bắt buộc test lưu DB qua `PLATE`, phải dùng schema `PLATE` (§5.3) với `payload.vehicle.license_plate.text`. | - Không cần xin quyền sửa cấu hình module trên `camera_junction`. | - `PLATE` thông thường **không bắn notification** (chỉ bắn khi biển nằm trong blacklist).<br>- Sai ngữ nghĩa nghiệp vụ (lưu vào bảng `plate_event`). |
| **Option C (Chuẩn Production dài hạn):** Đề xuất Backend mở module `TRAFFIC_CONGESTION` | Giữ nguyên Edge Adapter, đề xuất Backend bổ sung handler `handle_congestion_event` (xem file [`03_BACKEND_CONTRACT_PROPOSAL.md`](./03_BACKEND_CONTRACT_PROPOSAL.md)). | - Chuẩn hóa 100% schema (`state`, `o_vis`, `flow_speed`, `vehicle_count`, `duration_s`), UI riêng, SOP riêng. | - Cần thời gian team Backend AIOC triển khai & deploy. |

---

## 3. Kiến Trúc Kết Nối Edge Worker (`poc/backend/ai` $\leftrightarrow$ AIOC Staging)

```mermaid
flowchart LR
    subgraph VMS_STG ["AIOC Staging (aioc-stg.atin.vn)"]
        MTX["MediaMTX / RTSP\n192.168.1.198:28537/tshtest\nhoặc 192.168.1.250:18554/..."]
        MQ["Mosquitto MQTT\nwss://aioc-stg.atin.vn/mqtt :443"]
        MINIO["Storage API\nPOST /storage/upload/file"]
        WEB["Web VMS UI\n/monitoring & Lịch sử"]
    end

    subgraph EDGE ["Congestion AI Edge Worker (Adapter mới)"]
        ORCH["MQTT Orchestrator\n- Sub cameras/zone/+ & company/+\n- Pub getdevice\n- Hot-reload ai_zones (0..1)"]
        READER["RTSP Stream Reader\n- rtsp_transport;tcp\n- BUFFERSIZE=1 + Reconnect"]
        PROC["poc/backend/ai Core\n- Detector (YOLO 2W/4W)\n- FlowOccupancy (MOG2 + Perspective)\n- OcclusionShield + Classifier V2\n- StateMachine (5s/15s/3m/2m/15m)"]
        PUB["VMS Publisher\n- Throttle BBox+HUD mỗi 0.2s (QoS 0)\n- Upload JPEG RAM -> object_key\n- Pub Event xác nhận (QoS 1)"]

        ORCH --> READER --> PROC --> PUB
    end

    MTX ==>|"RTSP Video"| READER
    ORCH <==|"C01/C02/C03 Retained"| MQ
    PUB ==>|"smart_vms/ai/bbox/camera_junction"| MQ
    PUB ==>|"JPEG (cv2.imencode)"| MINIO
    MINIO -.->|"object_key"| PUB
    PUB ==>|"smart_vms/ai_events/{MODULE}"| MQ
    MQ --> WEB
```

---

## 4. Ánh Xạ Chi Tiết Từ `poc/backend/ai` Sang Hợp Đồng AIOC VMS

### 4.1. Ánh xạ đầu vào: `ai_zones` (VMS) $\rightarrow$ `zone` (`poc/backend/ai/geometry.py`)

- **Định dạng VMS gửi xuống** (`smart_vms/cameras/camera_junction/ai_zones[/{MODULE}]`):
  ```json
  {
    "camera_code": "camera_junction",
    "ai_zones": [
      {
        "id": "<uuid>",
        "name": "NgaTu_Chinh",
        "is_active": true,
        "ai_modules": "ZONE",
        "points": [{"x": 0.12, "y": 0.25}, {"x": 0.87, "y": 0.27}, ...]
      }
    ]
  }
  ```
- **Chuyển đổi sang `poc/backend/ai`:**
  - Lọc `z["is_active"] == True` và `z["ai_modules"]` khớp module cấu hình (hoặc `TARGET_ZONE_MODULES`).
  - Chuyển `[{"x": p["x"], "y": p["y"]}]` thành `[[p["x"], p["y"]], ...]` (đã chuẩn hóa `0..1`, tương thích trực tiếp với `zone_to_px()` trong `poc/backend/ai/geometry.py` và `extend_zone_longitudinal()` Rail-Aligned +20%).
  - **Cơ chế an toàn (C03):**
    - Nếu nhận payload rỗng `""` hoặc `{"ai_zones": []}`: không crash `json.loads`; xóa zone hoặc chuyển về vùng fallback cấu hình trong `.env` (nếu bật `ALLOW_FALLBACK_ROI=true` để test).
    - **Bỏ qua** `/lines` và các topic `ai_zones/<MODULE_KHÁC>` để tránh ghi đè mất ROI trong RAM (bài học từ `sidewalk_ai`).

### 4.2. Ánh xạ xử lý khung hình (`CameraProcessor.process_frame`)

- `poc/backend/ai` xử lý nội bộ trên độ phân giải chuẩn `1280x720` (`FRAME_W = 1280`, `FRAME_H = 720`).
- Các tham số V2 đã ổn định trên PoC giữ nguyên:
  - `MOG2_LR_NORMAL = 0.002`, `O_CLEAR = 0.40`, `O_CONGESTED = 0.70`, `O_GRIDLOCK = 0.85`.
  - `FlowOccupancy` với perspective row weighting (`2.2` tại `y_min` $\rightarrow$ `0.8` tại `y_max`) và `MORPH_CLOSE (5, 5)`.
  - `OcclusionShield` (`40s` max hold) và `StateMachine` (`5s` smooth, `10s` exit hysteresis, `3m` initial confirm, `+2m` escalate, `+15m` ongoing reminder).
- **Quy đổi BBox ra hệ tọa độ `0..1` cho Web VMS:**
  - `CameraProcessor` trả về `Det` trong tọa độ pixel `1280x720` (`xyxy`).
  - Khi đóng gói gửi MQTT `smart_vms/ai/bbox/camera_junction`, chia tọa độ cho `(1280.0, 720.0)` và clip về `[0.0, 1.0]`.
  - Nhịp gửi BBox: giữ throttle `BBOX_PUBLISH_INTERVAL = 0.2s` (tức 5 FPS), tách khỏi việc infer nhanh hơn nếu GPU chạy 15–25 FPS.

### 4.3. Ánh xạ HUD (`hud` object trong BBox payload)

Theo §5.8, Web VMS hỗ trợ `hud: {"text": ..., "display_ms": ..., "color": ...}`:

| Trạng thái `state` | Màu `hud.color` | Nội dung `hud.text` mẫu |
|---|---|---|
| `CLEAR` | `#22c55e` (Xanh lá) | `CLEAR \| 6 xe \| O: 18% \| Flow: 41.5 px/s` |
| `CONGESTED` | `#f59e0b` (Vàng cam) | `CONGESTED \| 21 xe \| O: 72% \| Flow: 8.4 px/s` |
| `GRIDLOCKED` | `#ef4444` (Đỏ) | `GRIDLOCKED \| 28 xe \| O: 88% \| Flow: 1.9 px/s` |

> **Lưu ý từ PoC UI:** Không hiển thị chỉ số "Tin cậy 95%" giả định trên HUD; giữ đơn vị dòng xe là `px/s` rõ ràng.

### 4.4. Ánh xạ Sự Kiện Xác Nhận (`StateMachine` $\rightarrow$ Storage + MQTT Event)

Trong `poc/backend/ai/decision/state_machine.py`, `StateMachine` chỉ phát ra `ConfirmedEvent` khi:
1. Vượt ngưỡng xác nhận ban đầu (`3 phút` với `CONGESTED` / `GRIDLOCKED`), hoặc
2. Leo thang (`CONGESTED` $\rightarrow$ `GRIDLOCKED`, `+2 phút`), hoặc
3. Nhắc lại khi ùn tắc kéo dài (`+15 phút`), hoặc
4. Phục hồi về `CLEAR` sau một sự kiện đã xác nhận.

**Quy trình khi có `ConfirmedEvent` (trừ trường hợp chỉ muốn báo động khi ùn tắc/leo thang):**
1. Vẽ overlay trực quan lên frame gốc (đa giác ROI + BBox các xe + banner trạng thái `state`, `O_vis`, `Flow`, `vehicle_count`) bằng OpenCV.
2. Nén JPEG trong RAM (`cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 85])`) và `POST` lên `https://aioc-stg.atin.vn/storage/upload/file` với `camera_id` (UUID) và `category` tương ứng (`zone` / `anomaly` / `plate`).
3. Lấy `object_key` gán vào `snapshot_url`.
4. Publish QoS 1 (không retain) lên `smart_vms/ai_events/{TARGET_EVENT_MODULE}` kèm `event_time` múi giờ `+07:00`.

---

## 5. Danh Sách 12 Lưu Ý Bắt Buộc Khi Đưa Lên Staging (`camera_junction`)

Áp dụng trực tiếp từ `docs/onboard/02_CAM_NANG_TICH_HOP_VA_LUU_Y_THUC_CHIEN.md` cho trường hợp `camera_junction`:

1. **`MQTT_CLIENT_ID` riêng biệt:** Đặt `ai_edge_congestion_junction_01` (không dùng prefix `vms_staging_backend`, không chạy 2 bản trùng ID).
2. **Không dùng `getdevice/zone/{id}`:** Luôn publish `{"organization_id": ...}` hoặc `{"zone_id": ..., "organization_id": ...}` lên topic gốc `smart_vms/cameras/getdevice`.
3. **Lọc Zone theo `ai_modules`:** Nếu `camera_junction` bật nhiều module (VD `PLATE` và `ZONE`), luôn lọc `z.get("ai_modules")` để không lấy nhầm vùng của module khác.
4. **Không subscribe `ai_zones/#` thiếu kiểm soát:** Chặn `/lines` và kiểm tra hậu tố module trước khi cập nhật `self._zones`.
5. **Chịu được payload retained rỗng `""` hoặc `ai_zones: []`:** Không để crash `JSONDecodeError`.
6. **Đúng mã module & `payload.type`:** Không tự chế tên topic `CONGESTION` khi Backend chưa hỗ trợ (sẽ bị silent drop).
7. **Độ trễ cache 60 giây:** Sau khi bật module mới cho `camera_junction` trên Web STG, chờ đủ 60s rồi mới test gửi event.
8. **Upload ảnh lấy `object_key`:** Tuyệt đối không gửi `snapshot_base64` hoặc `url` (`127.0.0.1`).
9. **Quy tắc `0.35s` BBox:** Gửi BBox mỗi `0.2s` với `ai_modules` khớp đúng lựa chọn `"AI: ..."` trên ô video của `/monitoring`.
10. **RTSP TCP & Bufferless:** Bắt buộc `OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp|stimeout;5000000"` và `cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)`. Ưu tiên `rtsp_url` từ MQTT (MediaMTX `18554`) nếu máy chạy Edge không thông trực tiếp tới `192.168.1.198:28537/tshtest`.
11. **Chống spam event:** `StateMachine` của PoC đã có sẵn `3m / +2m / +15m`, nhưng trong lúc **smoke test / demo nhanh**, có thể tạm hạ tham số `EVENT_CONFIRM_S` xuống (VD `10s–15s`) qua `.env` để dễ quan sát, sau đó trả lại chuẩn `180s`.
12. **Wildcard `+` cho `{camera_code}` khi subscribe:** Dùng `smart_vms/cameras/+/ai_zones/...` và đối chiếu `data["camera_code"] == "camera_junction"`.
