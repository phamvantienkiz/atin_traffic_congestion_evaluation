# 00 — TỔNG QUAN, QUYẾT ĐỊNH KỸ THUẬT ĐÃ CHỐT & LỘ TRÌNH TRIỂN KHAI (PoC PHASE 1)

> Tài liệu gốc: [deployment-and-demo-plan.md](./deployment-and-demo-plan.md) · Giải pháp thuật toán: [core-solution.md](../../docs/research/core-solution.md)
> Bộ tài liệu này **tự đủ**: dev chỉ cần đọc lần lượt các file `00 → 05` là có thể code mà không cần đọc tài liệu khác.

## 1. Danh sách file kế hoạch

| File | Nội dung | Người thực hiện |
| :-- | :-- | :-- |
| [00-overview-and-decisions.md](./00-overview-and-decisions.md) | Quyết định kỹ thuật, kiến trúc, hợp đồng dữ liệu chung, lộ trình | Tất cả |
| [01-environment-and-infra.md](./01-environment-and-infra.md) | Server GPU, `.venv`, MediaMTX, SSH tunnel, cấu trúc repo | DevOps / AI |
| [02-ai-pipeline.md](./02-ai-pipeline.md) | `poc/backend/ai/`: Reader, Detector, Batcher, ByteTrack, T50/D85, MOG2/Flow, State Machine | AI |
| [03-backend.md](./03-backend.md) | `poc/backend/`: FastAPI, API camera/zone, WebSocket, Snapshot (chứa luôn `ai/`) | Backend |
| [04-frontend.md](./04-frontend.md) | `poc/frontend/`: HTML/CSS/JS, WebRTC, Canvas overlay, vẽ Zone, Event feed | Frontend |
| [05-integration-test-and-demo.md](./05-integration-test-and-demo.md) | Kiểm thử, tinh chỉnh ngưỡng, kịch bản demo | Tất cả |

## 2. Quyết định kỹ thuật đã CHỐT (ưu tiên đơn giản — PoC Phase 1)

| # | Vấn đề | Quyết định | Lý do |
| :-: | :-- | :-- | :-- |
| D1 | Số tiến trình & Cấu trúc | **1 tiến trình Python duy nhất** trong `poc/backend/`: gộp `ai/` vào `poc/backend/ai/` và dùng chung 1 môi trường `poc/backend/.venv`. `main.py` import `ai` trực tiếp và chạy AI trong các thread nền. | Không cần serialize ảnh qua mạng, cô lập hoàn toàn trong `poc/backend/`, không cần `PYTHONPATH` phức tạp. |
| D2 | Gateway video | **MediaMTX** (binary Linux, không cần Docker). Mỗi camera là 1 path `cam1..cam8` với `source: rtsp://...` và `sourceOnDemand: no`. | 1 kết nối tới camera gốc, phát cả RTSP (cho AI) và WebRTC (cho web). |
| D3 | Luồng AI `720p @ 15 FPS` | AI đọc `rtsp://127.0.0.1:8554/camX` bằng OpenCV, **resize về 1280x720 và lấy mẫu 15 FPS trong code** (bỏ frame dựa trên timestamp). **Không transcode** bằng FFmpeg. | Không tốn CPU encode lại; đầu vào AI vẫn chuẩn `720p @ 15 FPS` như ATIN. |
| D4 | Hiển thị video trên web | `<iframe>` trang WebRTC có sẵn của MediaMTX `http://<host>:8889/camX/?controls=false&muted=true&autoplay=true` + `<canvas>` đè lên. Fallback: `<img>` MJPEG `/api/cameras/{id}/mjpeg` từ backend. | Không phải tự viết WHEP client. |
| D5 | Inference runtime | **Ultralytics + PyTorch `.pt`, `half=True`, `device=cuda:0`**. ONNX chỉ là tùy chọn (script export có sẵn). **Không dùng TensorRT** ở Phase 1. | 0% rủi ro môi trường, đủ nhanh cho ≤ 8–10 cam. |
| D6 | Batching | 1 thread `GpuBatcher` chạy nhịp **66.7 ms**, gom frame mới của mọi camera → `model.predict(list, ...)` 1 lần. | Không tranh chấp GPU. |
| D7 | ROI crop | Cắt hình chữ nhật bao Poly Zone + lề 10%. Chưa có zone → dùng nguyên khung. | Xe xa to hơn, ít nhiễu. |
| D8 | Tracker | **`supervision.ByteTrack`** — mỗi camera 1 instance (không dùng `model.track()` vì không hỗ trợ batch nhiều nguồn). | Dễ dùng, tách biệt từng camera. |
| D9 | Hậu xử lý | Chạy tuần tự trong thread `GpuBatcher` sau khi có kết quả (8 cam × ~2 ms = ~16 ms, vẫn < 66.7 ms). Chỉ dùng `ThreadPoolExecutor` nếu đo thấy vượt ngân sách. | Đơn giản, không race condition. |
| D10 | Đồng hồ | Mọi tính toán thời gian dùng `time.monotonic()`; payload gửi web dùng `time.time()`. | Không bị ảnh hưởng chỉnh giờ hệ thống. |
| D11 | Lưu cấu hình | File JSON `poc/backend/data/cameras.json` (URL RTSP + zone). Không DB. | PoC. |
| D12 | Đẩy kết quả | 1 WebSocket `/ws` broadcast mọi camera, **5 Hz** (mỗi 200 ms gửi trạng thái mới nhất). | Đủ mượt cho BBox, nhẹ mạng. |
| D13 | Sự kiện | Lưu trong RAM (deque 200) + ảnh JPEG trong `poc/backend/data/snapshots/`. | PoC. |
| D14 | Frontend | **HTML + CSS + Vanilla JS**, tái sử dụng style "Soft Clean Cards" từ `scripts/RTSP/styles.css`. Không build tool. | Nhanh. |
| D15 | Thời gian xác nhận sự kiện | Cấu hình được, mặc định `60s/120s`; có **"Demo mode" `15s/30s`** bật bằng biến môi trường `DEMO_MODE=1`. | Cấp trên không phải chờ lâu. |
| D16 | Bảo mật | Không auth (chỉ truy cập qua VPN/SSH tunnel). Bind `0.0.0.0` nhưng chỉ mở qua tunnel. | PoC nội bộ. |
| D17 | OS Server | Giả định **Ubuntu 20.04/22.04 + NVIDIA driver ≥ 525**. Python **3.10/3.11** qua `uv`. | Phổ biến. |
| D18 | Lớp model | Model [models/vehicle_n_best.pt](../../models/vehicle_n_best.pt) đã xác nhận có **4 lớp**: `{0: 'bus', 1: 'car', 2: 'motobike', 3: 'truck'}`. Map `motobike` (và `motorcycle`/`bicycle` nếu dùng model dự phòng `yolo26s.pt`) → nhóm `2W`; `car/bus/truck` → `4W`. | Đọc trực tiếp từ metadata checkpoint. |
| D19 | Codec & Phát video | Mặc định ưu tiên **MediaMTX WebRTC** (cần camera xuất H.264) + **Fallback MJPEG** (`/api/cameras/{id}/mjpeg`, giống cơ chế trong [scripts/RTSP/server.py](../../scripts/RTSP/server.py) giải mã bằng OpenCV ở server nên chạy được cả H.264 lẫn H.265). | Đảm bảo 100% lên hình với mọi loại camera. |

## 3. Kiến trúc chốt

```mermaid
flowchart LR
    CAM["Camera RTSP (4-8)"] --> MTX["MediaMTX\nRTSP :8554 / WebRTC :8889"]
    subgraph PY["1 tiến trình Python: poc/backend/main.py (:8080)"]
        RD["ai.ingestion.StreamReader x N\n(720p, 15 FPS, buffer=1)"]
        GB["ai.engine.GpuBatcher (66.7ms)\nROI crop -> YOLO batch FP16"]
        CP["ai.engine.CameraProcessor x N\nByteTrack + T50/D85 + MOG2/Flow\n+ Occlusion + StateMachine"]
        ST["ai.engine.ResultStore\n(kết quả mới nhất + events)"]
        API["FastAPI REST + WebSocket /ws (5Hz)\n+ static frontend"]
        RD --> GB --> CP --> ST --> API
    end
    MTX -- "rtsp://127.0.0.1:8554/camX" --> RD
    MTX -- "WebRTC iframe" --> WEB["Trình duyệt laptop\n(qua VPN / SSH tunnel)"]
    API -- "HTTP + WS JSON" --> WEB
```

## 4. Hợp đồng dữ liệu chung (MỌI phần phải tuân theo)

### 4.1. Cấu hình camera — `poc/backend/data/cameras.json`
```json
{
  "cameras": [
    {
      "id": "cam1",
      "name": "Nguyễn Văn Linh - Hướng Q7",
      "rtsp_url": "rtsp://user:pass@10.0.0.11:554/stream1",
      "enabled": true,
      "has_traffic_light": false,
      "zone": [{"x": 0.12, "y": 0.35}, {"x": 0.88, "y": 0.37}, {"x": 0.95, "y": 0.85}, {"x": 0.05, "y": 0.83}]
    }
  ]
}
```
- `id` ∈ `cam1..cam8` (cũng là tên path MediaMTX). `zone` có thể `[]` (chưa vẽ). Tọa độ chuẩn hóa `[0..1]`, gốc ở góc trên-trái.

### 4.2. Kết quả AI mỗi camera (`CameraResult`) — gửi qua WebSocket
```json
{
  "camera_id": "cam1",
  "ts": 1762918200.125,
  "stream_ok": true,
  "fps": 14.8,
  "detections": [
    {"tid": 102, "group": "4W", "cls": "car", "conf": 0.91, "bbox": [0.215, 0.410, 0.385, 0.680], "in_zone": true}
  ],
  "metrics": {
    "w_total": 30.0, "n_2w": 18, "n_4w": 4,
    "t50_2w": 4.1, "t50_4w": 8.4, "d85_2w": 5.0, "d85_4w": 14.2,
    "n_completed_2w": 9, "n_completed_4w": 2,
    "o_vis": 0.72, "v_flow": 0.3
  },
  "raw_state": "GRIDLOCKED",
  "state": "CONGESTED",
  "occlusion_hold": false,
  "confirmed_state": "CONGESTED"
}
```
- `bbox` = `[x1, y1, x2, y2]` chuẩn hóa. Giá trị `t50_*`/`d85_*` = `null` nếu không đủ mẫu.
- `state` ∈ `UNKNOWN | CLEAR | CONGESTED | GRIDLOCKED` (trạng thái hiển thị góc dưới phải, đã làm mượt).
- `confirmed_state` = trạng thái sự kiện đã xác nhận gần nhất (hoặc `CLEAR`).

### 4.3. Thông điệp WebSocket `/ws` (server → client)
```json
{"type": "results", "data": [<CameraResult>, ...]}
{"type": "event", "data": <Event>}
```

### 4.4. Sự kiện (`Event`)
```json
{"id": "evt_cam1_1762918200", "camera_id": "cam1", "camera_name": "...", "state": "GRIDLOCKED",
 "ts": 1762918200.1, "duration_s": 120, "snapshot_url": "/snapshots/evt_cam1_1762918200.jpg", "metrics": {...}}
```

## 5. Lộ trình (khoảng 3 tuần, 1–2 dev)

| Giai đoạn | Việc | Đầu ra / Tiêu chí xong | File |
| :-- | :-- | :-- | :-- |
| **G0** (0.5 ngày) | Dựng môi trường server, MediaMTX, tunnel | Xem được WebRTC `cam1` trên laptop qua `http://localhost:8889/cam1/` | 01 |
| **G1** (3 ngày) | AI offline trên file video: Detector + ByteTrack + T50/D85 + MOG2/Flow | Script `poc/backend/ai/tools/run_video.py` xuất video debug có BBox + chỉ số | 02 (B1–B6) |
| **G2** (2 ngày) | State machine + occlusion + GpuBatcher đa camera | 8 camera RTSP chạy ≥ 13 FPS/cam, log trạng thái | 02 (B7–B10) |
| **G3** (2 ngày) | Backend FastAPI + WebSocket + snapshot | `curl`/`wscat` nhận JSON đúng hợp đồng 4.2 | 03 |
| **G4** (3 ngày) | Frontend: lưới, iframe WebRTC, canvas overlay, vẽ zone, event feed | Demo đầy đủ trên laptop | 04 |
| **G5** (2–3 ngày) | Tinh chỉnh ngưỡng trên camera thật, kịch bản demo | Checklist nghiệm thu file 05 đạt | 05 |

> Quy tắc chung: Python luôn chạy qua `uv`/`.venv` của `poc/backend/` (xem file 01). Không cài global. Không commit `print()` debug; dùng `logging`.
