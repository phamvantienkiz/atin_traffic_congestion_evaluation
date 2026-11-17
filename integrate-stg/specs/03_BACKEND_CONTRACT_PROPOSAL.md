# ĐỀ XUẤT HỢP ĐỒNG MQTT CHÍNH THỨC CHO MODULE ĐÁNH GIÁ ÙN TẮC GIAO THÔNG (`TRAFFIC_CONGESTION`)

> **Mục đích:** Trong giai đoạn PoC/Staging, hệ thống tạm thời sử dụng kênh `PLATE` (hoặc `ZONE` / `CROWD_DETECTION`) để kiểm thử trên `aioc-stg.atin.vn` vì Backend VMS hiện chưa định tuyến module ùn tắc giao thông. Tài liệu này đề xuất đặc tả chuẩn để team Backend AIOC mở rộng hỗ trợ chính thức ở giai đoạn tiếp theo.

---

## 1. Định Danh Module & Topic

| Thành phần | Giá trị đề xuất | Ghi chú |
|---|---|---|
| **Module Code (`ai_modules`)** | `TRAFFIC_CONGESTION` *(hoặc sub-module dưới `ANOMALY`: `TRAFFIC_CONGESTION`)* | Thêm vào bảng module camera & `on_message` routing của `aioc-backend` |
| **Topic Event** | `smart_vms/ai_events/TRAFFIC_CONGESTION` | QoS `1`, `retain=False` |
| **Topic BBox & HUD** | `smart_vms/ai/bbox/{camera_code}` | QoS `0`, `retain=False`, `ai_modules: "TRAFFIC_CONGESTION"` |
| **Topic Zone ROI** | `smart_vms/cameras/{camera_code}/ai_zones/TRAFFIC_CONGESTION` | QoS `1`, `retain=True` (Vùng đa giác mặt đường giám sát ùn tắc) |
| **Storage `category`** | `anomaly` *(hoặc `traffic`)* | `POST /storage/upload/file` lấy `object_key` |

---

## 2. Schema Payload Sự Kiện Đề Xuất (`smart_vms/ai_events/TRAFFIC_CONGESTION`)

```json
{
  "ai_modules": "TRAFFIC_CONGESTION",
  "camera_id": "2e994218-ebc9-4e7a-9396-4c3054b0d5ac",
  "camera_code": "camera_junction",
  "event_time": "2026-11-17T12:30:00+07:00",
  "entity_type": "TRAFFIC_STATE",
  "entity_id": "congestion_camera_junction_1763357400",
  "confidence": 0.90,
  "severity": "HIGH",
  "payload": {
    "state": "CONGESTED",
    "prev_state": "CLEAR",
    "event_kind": "CONFIRMED",
    "zone_id": "<ai_zone uuid>",
    "zone_name": "NgaTu_Chinh",
    "o_vis": 0.742,
    "flow_speed_px_s": 8.4,
    "vehicle_count": 18,
    "duration_s": 182.5,
    "occlusion_active": false
  },
  "snapshot_url": "anomaly/2026-11-17/camera_2e994218.../xxx.jpg"
}
```

### Quy ước giá trị trường `payload`:
- `state` / `prev_state`: `CLEAR` | `CONGESTED` | `GRIDLOCKED`
- `event_kind`:
  - `CONFIRMED`: vừa xác nhận ùn tắc sau `3 phút` (`severity = MEDIUM` cho `CONGESTED`, `HIGH` cho `GRIDLOCKED`).
  - `ESCALATED`: leo thang từ `CONGESTED` lên `GRIDLOCKED` sau `+2 phút` (`severity = HIGH`).
  - `REMINDER`: ùn tắc kéo dài mỗi `+15 phút` (`severity = HIGH`).
  - `RECOVERED`: phục hồi về `CLEAR` (`severity = LOW`).
- `o_vis`: tỉ lệ chiếm dụng mặt đường có trọng số phối cảnh (`0.0 .. 1.0`).
- `flow_speed_px_s`: vận tốc dòng xe (`px/s`).

---

## 3. Yêu Cầu Phía Backend & Web VMS (Khi Triển Khai Chính Thức)

1. **Routing:** Thêm `TRAFFIC_CONGESTION` vào `on_message` (`handle_congestion_event` hoặc `handle_anomaly_event` với `payload.type` tương ứng) để không bị rơi vào `handle_ai_event` (silent drop).
2. **Notification & SOP:**
   - Chỉ sinh **1 notification** mỗi event (tránh lỗi double notification như `ANOMALY` hiện tại).
   - Không bật chuông cảnh báo khi `event_kind == "RECOVERED"` (chỉ đóng trạng thái / ghi lịch sử).
3. **Web UI `/monitoring`:**
   - Thêm tùy chọn `TRAFFIC_CONGESTION` vào danh sách **AI Module** của camera để người dùng vẽ ROI mặt đường (`ai_zones`) và chọn hiển thị HUD/BBox trực tiếp trên ô Live View.
