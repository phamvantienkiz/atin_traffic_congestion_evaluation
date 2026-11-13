# 06 — BÁO CÁO CHI TIẾT TRIỂN KHAI THỰC TẾ, THUẬT TOÁN & XỬ LÝ SỰ CỐ (PoC PHASE 1)

> Tài liệu này tổng hợp trung thực trạng thái triển khai thực tế của hệ thống PoC Đánh giá ùn tắc giao thông (`poc/backend/`, `poc/frontend/`), đối chiếu trực tiếp với bộ kế hoạch `00 → 05`, liệt kê đầy đủ các thuật toán đã cài đặt ở Phương án 1, Phương án 2, Tầng Quyết định, cùng toàn bộ các lỗi đã phát sinh trong quá trình chạy thử trên server GPU và hướng xử lý đã áp dụng.

---

## 1. Tổng quan mức độ hoàn thành so với kế hoạch

| Giai đoạn | Hạng mục theo kế hoạch | Trạng thái thực tế | Ghi chú / Sai khác có chủ đích |
| :-: | :-- | :-- | :-- |
| **G1** | Bộ máy AI (`poc/backend/ai/`) | **Đã hoàn thành & chạy thực tế** | Đã gộp `ai/` vào `poc/backend/ai/`, dùng `uv` + `.venv` cô lập (Python 3.12). |
| **G2** | Backend FastAPI + MediaMTX (`poc/backend/`) | **Đã hoàn thành & chạy thực tế** | Đổi dải port mặc định sang `28xxx` (`28080/28554/28889/28189/29997`) để tránh trùng trên server dùng chung. |
| **G3** | Frontend Dashboard (`poc/frontend/`) | **Đã hoàn thành & chạy thực tế** | Chuyển mặc định hiển thị từ WebRTC sang **MJPEG** do camera thực tế xuất codec H.265. |
| **G4** | Kiểm thử đơn vị (Unit + API tests) | **Đã chạy & đạt 25/25** | `uv run pytest ai/tests tests -v` trong `poc/backend` đạt **25 passed** (sau commit `1ed27c9`). |
| **G4** | Nghiệm thu E2E trên video/camera thực tế dài hạn | **Đang kiểm chứng thực địa** | Đã mở RTSP thật (H.265), lên BBox & MJPEG; vừa xử lý xong deadlock khi Lưu Setting / Poly Zone. |

### Cấu trúc code thực tế đã triển khai
- `poc/backend/ai/`: `config.py`, `geometry.py`, `ingestion/stream_reader.py`, `core_pipeline/{detector.py, tracker.py, zone_time.py}`, `aux_pipeline/flow_occupancy.py`, `decision/{occlusion.py, classifier.py, state_machine.py}`, `engine/{camera_processor.py, gpu_batcher.py, engine.py}`, `tools/{run_video.py, export_onnx.py}`, `tests/` (8 file test).
- `poc/backend/`: `main.py`, `mediamtx.py`, `camera_store.py`, `events.py`, `ws_hub.py`, `schemas.py`, `settings.py`, `pyproject.toml`, `tests/test_api.py`.
- `poc/frontend/`: `index.html`, `styles.css`, `js/{api.js, main.js, camera-card.js, overlay.js, zone-editor.js, events-panel.js}`.
- `poc/run.sh` và hướng dẫn triển khai `docs/poc/server-deployment-guide.md`.

---

## 2. Đối chiếu chi tiết Phương án 1, Phương án 2 & Tầng Quyết định

Cả **Phương án 1** và **Phương án 2** đều đã được triển khai **đầy đủ theo đúng thiết kế** trong [02-ai-pipeline.md](./02-ai-pipeline.md), cấu hình tập trung tại [config.py](../backend/ai/config.py) và chạy đồng thời trên mỗi khung hình trong [camera_processor.py](../backend/ai/engine/camera_processor.py).

### 2.1. Tiền xử lý & Nạp luồng (`ingestion` + `geometry`)
- **`StreamReader`** ([stream_reader.py](../backend/ai/ingestion/stream_reader.py)):
  - Mở RTSP bằng OpenCV FFmpeg qua TCP (`rtsp_transport;tcp|stimeout;5000000`), tự động thử kết nối lại mỗi `2s` nếu mất tín hiệu.
  - Chuẩn hóa kích thước khung hình về `1280x720` (`frame_w=1280, frame_h=720`), lấy mẫu theo thời gian thực ở mức `15.0 FPS` (`target_fps`), chỉ giữ khung hình mới nhất (`buffer=1`, ghi đè biến `_latest`).
  - Theo dõi `healthy` theo `stream_timeout_s = 5.0s` và `measured_fps` trên cửa sổ 60 khung hình.
- **`geometry.py`** ([geometry.py](../backend/ai/geometry.py)):
  - Chuyển đổi Poly Zone từ tọa độ chuẩn hóa `[0..1]` sang pixel `1280x720` (`zone_to_px`), cắt vùng ROI bao quanh Poly Zone cộng lề `roi_padding = 10%` (`roi_from_zone`), tính độ dài trục chính của zone (`zone_axis_length`) phục vụ lọc nhiễu track ngắn.

### 2.2. Phương án 1 (`core_pipeline`) — Phát hiện, Theo dõi & Thời gian trong Zone
1. **Batch Detector (`Detector`)** ([detector.py](../backend/ai/core_pipeline/detector.py)):
   - Dùng Ultralytics YOLO (`models/vehicle_n_best.pt`) với `imgsz=640`, `conf=0.15` (giữ detection yếu cho ByteTrack), `iou=0.5`, bật `half=True` (FP16) khi chạy `.pt` trên `cuda:0`.
   - Nhận danh sách ROI crop của tất cả camera từ `GpuBatcher`, chạy **1 lần `model.predict(crops, ...)` theo batch** mỗi `66.7ms`, rồi cộng offset `(ox, oy)` để đưa tọa độ BBox về `1280x720`.
   - Ánh xạ nhãn model `{0: 'bus', 1: 'car', 2: 'motobike', 3: 'truck'}` (cùng các tên dự phòng `motorcycle`, `motorbike`, `bicycle`) về 2 nhóm `2W` và `4W`.
2. **Tracker & Bầu chọn lớp (`CameraTracker`)** ([tracker.py](../backend/ai/core_pipeline/tracker.py)):
   - Mỗi camera có 1 instance `supervision.ByteTrack` riêng (`supervision==0.26.1`), tham số `track_activation_threshold=0.45`, `lost_track_buffer=2.5s * fps`, `minimum_matching_threshold=0.8`.
   - **Majority Class Voting**: cộng dồn trọng số theo `conf` cho từng `tracker_id` suốt vòng đời track để tránh nhảy nhãn giữa `car`/`bus`/`truck` hoặc `motobike`.
   - Điểm chân phương tiện dùng để xét trong/ngoài Poly Zone: `foot = ((x1 + x2) / 2, y2)`.
3. **Phân tích mật độ & thời gian trong Zone (`ZoneTimeAnalyzer`)** ([zone_time.py](../backend/ai/core_pipeline/zone_time.py)):
   - **`W_total`**: tổng trọng số quy đổi các xe có `foot` nằm trong Poly Zone (`motobike=1.0`, `car=3.0`, `bus=6.0`, `truck=6.0`), làm mượt bằng EMA.
   - **`T50_2W` / `T50_4W` (Median Travel Time)**: đo thời gian xe đi từ lúc vào đến lúc rời zone (hoặc mất dấu `>= 1.0s`). Chỉ tính mẫu hợp lệ nếu quãng đường dịch chuyển `travel >= 0.45 * axis_len`; lấy trung vị trên cửa sổ trượt `15.0s` khi có tối thiểu `3` mẫu hoàn thành.
   - **`D85_2W` / `D85_4W` (Active Dwell)**: tính bách phân vị thứ 85 thời gian đã nằm trong zone của các xe đang hiện diện (`dur >= 1.5s`), yêu cầu tối thiểu `2` mẫu đang hoạt động — giúp phát hiện xe kẹt cứng tại chỗ dù chưa thoát khỏi zone.

### 2.3. Phương án 2 (`aux_pipeline`) — Độ phủ thị giác & Dòng chảy quang học vĩ mô
- **`FlowOccupancy`** ([flow_occupancy.py](../backend/ai/aux_pipeline/flow_occupancy.py)):
  - Thu nhỏ khung hình về `320x180` (`aux_w=320, aux_h=180`) để giảm tải CPU.
  - **`O_vis` (Visual Occupancy `[0..1]`)**:
    - Chạy trừ nền `cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)`, chỉ giữ foreground mạnh (`== 255`), loại bỏ bóng đổ (`127`), khử nhiễu bằng `MORPH_OPEN` kernel `3x3`.
    - Hợp nhất (`bitwise_or`) mặt nạ MOG2 với mặt nạ hình chữ nhật của các BBox YOLO trong zone, cắt theo `zone_mask_small` để tính tỷ lệ pixel bị chiếm dụng.
    - **MOG2 Learning Freeze**: tự động đặt `learningRate = 0.0` khi `V_flow < 1.0 px/s` và có dấu hiệu xe dừng lâu (`d85_max > 5.0s`), ngăn xe kẹt cứng bị MOG2 học thành nền.
  - **`V_flow` (Optical Flow Speed `px/s`)**:
    - Tính Dense Optical Flow **Farneback** (`cv2.calcOpticalFlowFarneback`) trên ảnh xám `320x180`, triệt tiêu nhiễu nền nhỏ hơn `flow_noise_px = 0.8 px`, lấy trung bình vận tốc trên vùng `occupied`.
    - Làm mượt cả `O_vis` và `V_flow` bằng EMA (`alpha = 0.3`).

### 2.4. Tầng Hợp nhất & Quyết định (`decision` + `engine`)
1. **Lá chắn che khuất (`OcclusionShield`)** ([occlusion.py](../backend/ai/decision/occlusion.py)):
   - Chống tụt giả về `CLEAR` khi xe buýt/xe tải lớn che khuất camera theo 2 điều kiện:
     - **Kịch bản A**: tổng diện tích BBox nhóm `heavy_classes` (`bus`, `truck`) phủ `> 35%` diện tích Poly Zone.
     - **Kịch bản B**: số lượng BBox trong zone giảm đột ngột `> 60%` so với mức đỉnh `2s` gần nhất (với `n_ref >= 3`) trong khi `O_vis > 70%`.
   - Khi kích hoạt, trả về `HOLD` (giữ nguyên trạng thái hiển thị hiện tại) tối đa `30.0s`; quá `30.0s` chuyển sang `UNKNOWN_HOLD`.
2. **Bộ phân loại 3 trạng thái (`classify`)** ([classifier.py](../backend/ai/decision/classifier.py)):
   - Kết hợp chỉ số Phương án 1 (`W_total`, `T50`, `D85`, `n_2w`, `n_4w`) và Phương án 2 (`O_vis`, `V_flow`):
     - **`CLEAR`**: `W_total < 12` và `O_vis < 0.35`, hoặc không đạt điều kiện tắc/kẹt.
     - **`GRIDLOCKED`**: (`W_total >= 24` hoặc `O_vis >= 0.65`) kết hợp xe dừng lâu (`T50_4W > 7s` / `D85_4W > 10s`, `T50_2W > 5s` / `D85_2W > 8s`) và vĩ mô đứng dòng (`V_flow <= 1.0` hoặc `O_vis >= 0.70`); kèm nhánh **Macro Rescue** (`O_vis >= 0.75`, `V_flow <= 1.0`, `W_total >= 18`) khi che khuất nặng làm gãy ID ByteTrack.
     - **`CONGESTED`**: (`W_total >= 15` hoặc `O_vis >= 0.45`) kết hợp di chuyển chậm (`T50 > 3s`, `D85_4W > 5s`, `D85_2W > 4.5s`, hoặc `1.0 < V_flow < 6.0` khi `O_vis >= 0.45`).
3. **Máy trạng thái 2 tầng (`StateMachine`)** ([state_machine.py](../backend/ai/decision/state_machine.py)):
   - **Provisional (hiển thị live)**: làm mượt đa số trên cửa sổ `5.0s` (ưu tiên mức nặng hơn khi hòa), kết hợp **Exit Hysteresis** (`15.0s` liên tục `CLEAR` mới hạ từ `CONGESTED`/`GRIDLOCKED` về `CLEAR`).
   - **Confirmed (bắn sự kiện & lưu snapshot)**: yêu cầu duy trì đủ `60s` (`CONGESTED`), `90s` (`CONGESTED` khi `has_traffic_light=True`), `120s` (`GRIDLOCKED`) — hoặc `15s/20s/30s` khi bật `DEMO_MODE=1`; dung sai dao động ngắn `5.0s`, `cooldown_s = 60.0s`, cho phép nâng cấp thẳng `CONGESTED -> GRIDLOCKED` bỏ qua cooldown.
4. **Điều phối GPU (`GpuBatcher` + `TrafficEngine`)** ([gpu_batcher.py](../backend/ai/engine/gpu_batcher.py), [engine.py](../backend/ai/engine/engine.py)):
   - 1 thread `GpuBatcher` chạy chu kỳ `66.7ms`, gom frame mới từ tất cả `CameraProcessor`, suy luận batch GPU 1 lần rồi cập nhật tuần tự kết quả vào `ResultStore` để FastAPI đẩy qua WebSocket `/ws` ở tần số `5 Hz`.

---

## 3. Toàn bộ các lỗi đã gặp phải & Phương án đã áp dụng

| # | Lỗi / Hiện tượng gặp phải | Nguyên nhân gốc rễ | Phương án đã xử lý (Commit) |
| :-: | :-- | :-- | :-- |
| **1** | Trùng port khi chạy trên server GPU dùng chung (`aiot`) | Các port mặc định `8080`, `8554`, `8889`, `8189`, `9997` dễ đụng tiến trình khác trên server nhiều người dùng. | Chuyển toàn bộ dải port mặc định sang `28xxx` (`28080`, `28554`, `28889`, `28189`, `29997`) trong `settings.py`, `mediamtx.py`, `engine.py`, `run.sh` (`46d37d2`). |
| **2** | Lỗi `AttributeError` thiếu `sv.ByteTrack` sau `uv sync` | `supervision==0.31.7` thay đổi cấu trúc export `ByteTrack`. | Ghim `supervision>=0.25.0,<0.27.0` (chốt `0.26.1`) trong `pyproject.toml` (`7c4616d`). |
| **3** | Đổi cấu hình/reload camera bị đen hình hoặc nghẽn kết nối MJPEG | `camera_mjpeg` không kiểm tra `request.is_disconnected()`, thiếu `Content-Length`/`Cache-Control: no-store`; `CameraCard` cũ không hủy `src` của `iframe`/`img` khi tạo lại DOM. | Bổ sung `await request.is_disconnected()`, header `Content-Length` + `Cache-Control: no-store` trong `main.py`; thêm `CameraCard.destroy()` trong `camera-card.js` và gọi khi `reloadCameras()` (`0d1a6c0`). |
| **4** | Camera thật màn hình đen, báo `the stream doesn't contain any supported codec` | Camera thực tế xuất **H.265**, trong khi MediaMTX WebRTC + Chrome chỉ hỗ trợ AV1/VP9/VP8/H.264. | Đổi chế độ video mặc định từ `webrtc` sang `mjpeg` (backend OpenCV giải mã được cả H.264/H.265); kích hoạt đổi chế độ ngay khi đổi dropdown (`fec920a`). |
| **5** | Sau khi kéo code mới, Setting vẫn hiện WebRTC; bấm `Lưu` không rõ trạng thái | `localStorage` trình duyệt vẫn lưu `video_mode_cam1 = "webrtc"` từ lần chạy cũ nên ghi đè mặc định mới; nút `Lưu` không báo trạng thái đang xử lý. | Đổi key lưu sang `video_mode_v2_${cam.id}`, cập nhật nhãn option trong `index.html`, thêm trạng thái disable + text `Đang lưu...` khi submit form (`cd03fad`). |
| **6** | Bấm `Ctrl + C` không dừng được server | `uvicorn` mặc định đợi vô thời hạn các HTTP streaming response (`camera_mjpeg`) và WebSocket đóng trước khi shutdown; `uv run` trong shell làm wrapper. | Thêm `--timeout-graceful-shutdown 3` (`1d97936`) và dùng `exec uv run uvicorn ...` trong `poc/run.sh` (`1ed27c9`), đồng thời hướng dẫn chạy trực tiếp `uv run uvicorn ...`. |
| **7** | **Treo đơ toàn bộ UI-UX, backend, `F5` và `Ctrl + C` mỗi khi bấm `Lưu` Setting hoặc `Lưu` Poly Zone** | **Self-deadlock trong `CameraProcessor`**: `self._lock` dùng `threading.Lock()` (non-reentrant). Khi gọi `PUT /api/cameras/{id}` hoặc `PUT /api/cameras/{id}/zone`, `TrafficEngine.upsert_camera` (đang giữ `engine._lock`) gọi `CameraProcessor.update_meta()` (giữ `self._lock`) rồi gọi tiếp `self.set_zone()` (lại xin `self._lock` lần nữa) → khóa chết vĩnh viễn cả `GpuBatcher`, MJPEG, API và shutdown. | Đổi `CameraProcessor._lock` sang `threading.RLock()` và tách `_set_zone_unlocked()` trong `camera_processor.py`; thêm unit test hồi quy `test_camera_processor.py` (`1ed27c9`). |

---

## 4. Hướng dẫn kiểm chứng nhanh sau bản vá `1ed27c9`

1. Chạy trực tiếp backend từ `poc/backend` (không cần qua `.sh`):
   ```bash
   cd ~/projects/tien/atin_traffic_congestion_evaluation/poc/backend
   uv run uvicorn main:app --host 0.0.0.0 --port 28080 --timeout-graceful-shutdown 3
   ```
2. Mở trình duyệt tại `http://127.0.0.1:28080`, nhấn **`Ctrl + F5`**.
3. Kiểm tra lần lượt:
   - Video MJPEG lên hình kèm BBox (không còn lỗi codec H.265).
   - Mở Setting camera → bấm **Lưu** (modal đóng mượt, server không đứng).
   - Bấm vẽ Poly Zone → chọn điểm → bấm **Lưu** (lưu thành công, zone hiển thị ngay, `GpuBatcher` tiếp tục chạy bình thường).
   - Bấm `Ctrl + C` ở terminal server → thoát sạch trong tối đa 3 giây.
