# ĐẶC TẢ & HƯỚNG DẪN TRIỂN KHAI TỐI ƯU ĐỘ TRỄ BBOX REALTIME TRÊN STAGING (`05_LOW_LATENCY_BBOX_OPTIMIZATION_SPEC.md`)

> **Mục tiêu:** Triệt tiêu hoàn toàn độ trễ của khung BBox so với luồng video WebRTC trên trang Giám sát trực tiếp (`https://aioc-stg.atin.vn/monitoring`) cho camera **`camera_junction`** (`2560x1440` qua MediaMTX), giữ nguyên model `.pt` (`models/vehicle_n_best.pt`) và tuân thủ tuyệt đối quy tắc cô lập môi trường `.venv` trong `AGENTS.md`.
>
> **Người thực thi:** Hydrogen (triển khai code & chạy kiểm thử trên server `aiot`).

---

## 1. Phân Tích Kỹ Thuật: `python3-opencv` (apt + GStreamer) vs. `FFmpeg CUDA/NVDEC` (`h264_cuvid` / `hevc_cuvid`)

### 1.1. Tại sao KHÔNG nên cài `python3-opencv` qua `apt` để lấy GStreamer?
Mặc dù trên Ubuntu 22.04 có thể cài `sudo apt install python3-opencv gstreamer1.0-*`, phương án này có **4 rủi ro lớn về quản lý môi trường và hiệu năng**:

1. **Xung đột trực tiếp với môi trường cô lập `poc/backend/.venv` (Vi phạm `AGENTS.md` Mục 3):**
   - `python3-opencv` của `apt` cài vào `/usr/lib/python3/dist-packages` (Python hệ thống).
   - Môi trường `poc/backend/.venv` đang chạy với cờ cô lập mặc định (`include-system-site-packages = false`). Nếu bật `--system-site-packages`, hàng loạt gói cũ của Ubuntu 22.04 (`numpy 1.21`, `PIL`, `scipy`, `urllib3`...) sẽ tràn vào `.venv` và xung đột ABI với `torch` / `ultralytics` / `supervision` đang cài qua `uv`.
2. **Xung đột `cv2` của `ultralytics` và `supervision`:**
   - Cả `ultralytics` và `supervision` đều khai báo phụ thuộc `opencv-python` / `opencv-python-headless` trên PyPI. Khi `pip` / `uv` có mặt gói `opencv-python-headless` trong `.venv`, Python sẽ luôn ưu tiên nạp bản trong `.venv` (vốn `GStreamer: NO`) và đè lên bản `apt`.
3. **Không có plugin giải mã phần cứng NVIDIA (`nvv4l2decoder` / `nvdec`) sẵn trong `apt`:**
   - Gói GStreamer mặc định của Ubuntu (`gstreamer1.0-plugins-bad/ugly`) chỉ có decoder CPU (`avdec_h264`). Muốn GStreamer giải mã bằng GPU RTX A400 phải cài bộ **NVIDIA DeepStream SDK** hoặc tự biên dịch `gst-plugins-bad` với CUDA toolkit.
4. **Cần quyền `sudo` và làm bẩn môi trường host:**
   - Vi phạm nguyên tắc *"No Global Scope Spillage"* trong `AGENTS.md`.

---

### 1.2. Tại sao `FFmpeg CUDA / CUVID` (`h264_cuvid` / `hevc_cuvid`) có sẵn trên server `aiot` là "Mỏ Vàng"?

Kết quả kiểm tra thực tế trên server `aiot` cho thấy binary `/usr/bin/ffmpeg` của máy đã được biên dịch đầy đủ hỗ trợ phần cứng NVIDIA:
```text
Hardware acceleration methods: vdpau, cuda, vaapi, qsv, drm, opencl
Decoders:
 V..... h264_cuvid           Nvidia CUVID H264 decoder (codec h264)
 V..... hevc_cuvid           Nvidia CUVID HEVC decoder (codec hevc)
```

Khi sử dụng `ffmpeg` subprocess với `cuda` / `cuvid` thay cho `cv2.VideoCapture` trong `StreamReader`:
1. **Giải mã 2K (`2560x1440`) trên chip NVDEC chuyên dụng (0% tải CUDA Core của YOLO):**
   - GPU NVIDIA RTX A400 có khối phần cứng **NVDEC** tách biệt hoàn toàn với nhân CUDA/Tensor chạy YOLO `.pt`. Giải mã `h264_cuvid` / `hevc_cuvid` không làm chậm tốc độ suy luận của YOLO.
2. **Scale `2560x1440` $\rightarrow$ `1280x720` ngay trong bộ giải mã (`-resize 1280x720` của `cuvid`):**
   - Bộ giải mã `h264_cuvid` / `hevc_cuvid` hỗ trợ tham số phần cứng `-resize 1280x720` ngay trên chip NVDEC trước khi đẩy frame ra RAM!
   - Nhờ đó:
     - **Băng thông PCIe (GPU $\rightarrow$ CPU RAM) giảm 4 lần** (chỉ truyền frame `1280x720x3 = 2.76 MB` thay vì `2560x1440x3 = 11.05 MB`).
     - **Loại bỏ hoàn toàn hàm `cv2.resize` trên CPU** (tiết kiệm ngay `8 – 12 ms/frame`).
3. **Kiểm soát 100% cờ chống trễ của FFmpeg CLI:**
   - Truyền trực tiếp `-fflags nobuffer -flags low_delay -probesize 32768 -analyzeduration 0 -rtsp_transport tcp` vào `ffmpeg` CLI, không bị giới hạn bởi lớp wrapper hạn chế của `cv2.VideoCapture`.
4. **Cô lập môi trường 100%:**
   - Chỉ gọi `/usr/bin/ffmpeg` thông qua `subprocess.Popen` chuẩn của Python bên trong `poc/backend/.venv`, **không cần cài bất kỳ gói `apt` hay `pip` nào thêm**, giữ nguyên `cv2` fallback an toàn nếu chạy trên máy không có `ffmpeg`.

---

## 2. Chẩn Đoán Toàn Bộ Các Điểm Nghẽn Khiến BBox Bị Chậm So Với Video

| STT | Điểm nghẽn trong code hiện tại | Vị trí file & dòng code | Độ trễ gây ra | Cách khắc phục triệt để |
| :-: | :--- | :--- | :---: | :--- |
| **1** | **Decode 2K (`2560x1440`) bằng CPU + `cv2.resize(..., INTER_AREA)`** | [`poc/backend/ai/ingestion/stream_reader.py:100-126`](../../poc/backend/ai/ingestion/stream_reader.py#L100-L126) | `15 – 35 ms/frame` + tích tụ TCP buffer `300 – 800 ms` | Dùng **`FFmpeg CUVID Pipe` (`-c:v h264_cuvid -resize 1280x720`)** đọc liên tục xả cạn pipe, tự động fallback về `cv2.VideoCapture` + `INTER_LINEAR` nếu stream là H.265 hoặc không có NVDEC. |
| **2** | **Luồng tuần tự bắt BBox phải chờ `FlowOccupancy` (MOG2 + Farneback Optical Flow) chạy xong mới được publish** | [`integrate-stg/src/worker.py:375-389`](../src/worker.py#L375-L389) & [`camera_processor.py:108-191`](../../poc/backend/ai/engine/camera_processor.py#L108-L191) | `15 – 25 ms/frame` (giảm FPS từ 25 xuống ~14 FPS) | **Tách 2 nhánh sau Tracking:**<br>- **Nhánh 1 (Fast Path):** `YOLO (.pt) -> ByteTrack -> Publish BBox + HUD (cached) NGAY LẬP TỨC`.<br>- **Nhánh 2 (Macro Worker Thread):** Đẩy `(frame, det, tracks, now)` vào `Latest-Frame Slot` để tính `ZoneTime + MOG2 + Farneback + StateMachine` ở thread nền song song. |
| **3** | **BBox vẽ bằng tọa độ dự đoán của Kalman Filter (`tracked.xyxy`) làm khung bị tụt lại sau đuôi xe** | [`poc/backend/ai/core_pipeline/tracker.py:62-68`](../../poc/backend/ai/core_pipeline/tracker.py#L62-L68) | Trễ pha `1 – 2 frame` (`60 – 120 ms`) khi xe chạy nhanh | Sau khi `sv.ByteTrack` gán `tracker_id`, **khớp IoU ngược lại với `det.xyxy` của YOLO** để lấy **tọa độ BBox thật 100% trên frame hiện tại** (đúng chuẩn **C09**). |
| **4** | **Ngưỡng kích hoạt Track quá cao (`TRACK_ACTIVATION_CONF = 0.45`) làm xe mới vào vùng bị trễ 2–3 frame mới hiện BBox** | [`poc/backend/ai/config.py:79`](../../poc/backend/ai/config.py#L79) | `100 – 150 ms` lúc xe mới xuất hiện | Hạ `TRACK_ACTIVATION_CONF` trong `integrate-stg/.env` xuống **`0.25`** (hoặc `0.22`) để xe vừa lọt vào ống kính là hiện BBox ngay ở frame đầu tiên. |

---

## 3. Kiến Trúc Luồng Xử Lý Mới Sau Khi Tối Ưu (End-to-End Pipeline)

```mermaid
flowchart LR
    subgraph INGEST ["1. RTSP Ingestion (StreamReader)"]
        FF["FFmpeg NVDEC Subprocess\n-rtsp_transport tcp\n-fflags nobuffer -flags low_delay\n-c:v h264_cuvid -resize 1280x720\n(Tự động dò h264/hevc_cuvid -> fallback CPU)"]
        LATEST_FRM[("Latest Frame\n1280x720 BGR\n(Drop old frames)")]
        FF ==>|"Raw BGR Pipe\n(Xả liên tục 25-30 FPS)"| LATEST_FRM
    end

    subgraph FAST ["2. Nhánh 1: Fast BBox Thread (Độ trễ ~16-20ms)"]
        PREP["prepare()\nCắt ROI từ Frame mới nhất"]
        YOLO["Detector (.pt FP16)\ndetect_batch()"]
        TRK["CameraTracker.update()\nByteTrack + Snap về det.xyxy gốc"]
        PUB_BBOX["Publish MQTT QoS 0 NGAY\nsmart_vms/ai/bbox/camera_junction\n(BBox tức thời + HUD từ Cache)"]

        LATEST_FRM --> PREP --> YOLO --> TRK ==>|"0 ms chờ CPU Aux"| PUB_BBOX
    end

    subgraph SLOW ["3. Nhánh 2: Async Macro Thread (Chạy song song trên CPU)"]
        SLOT[("Latest Macro Slot\n(Ghi đè, không xếp hàng)")]
        MACRO["process_macro()\n1. ZoneTime (W, T50, D85)\n2. FlowOccupancy (MOG2 + Farneback)\n3. OcclusionShield + Classifier V2\n4. StateMachine"]
        HUD_CACHE[("HUD & Metrics Cache\n(state, o_vis, v_flow, t50, d85)")]
        EVT["Nếu có ConfirmedEvent:\nUpload Snapshot -> Publish Event"]

        TRK -.->|"Đẩy không chặn\n(non-blocking)"| SLOT
        SLOT --> MACRO --> HUD_CACHE
        MACRO --> EVT
        HUD_CACHE -.->|"Đọc tức thì"| PUB_BBOX
    end
```

---

## 4. Hướng Dẫn Chi Tiết Từng Bước Sửa Code (Dành Cho Hydrogen)

### Bước 1: Nâng cấp `poc/backend/ai/ingestion/stream_reader.py` (Hỗ trợ `FFmpeg NVDEC / CUVID` + Low-Latency)

**Mục tiêu:**
- Tự động ưu tiên đọc luồng RTSP qua `ffmpeg` subprocess với phần cứng NVIDIA (`h264_cuvid` + `-resize 1280x720` ngay trên NVDEC), giảm tải CPU về gần `0%` và loại bỏ `cv2.resize`.
- Nếu camera phát `hevc` hoặc môi trường không có GPU/ffmpeg, tự động chuyển sang `hevc_cuvid` hoặc fallback mượt về `cv2.VideoCapture` với `cv2.INTER_LINEAR`.
- Luôn đọc kiệt (drain) pipe ở tốc độ thực của camera để **không bao giờ tồn đọng frame cũ trong buffer**.

**Thiết kế chi tiết cần cập nhật trong [`poc/backend/ai/ingestion/stream_reader.py`](../../poc/backend/ai/ingestion/stream_reader.py):**

1. Cập nhật biến môi trường mặc định đầu file:
   ```python
   os.environ.setdefault(
       "OPENCV_FFMPEG_CAPTURE_OPTIONS",
       "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|probesize;32768|analyzeduration;0|stimeout;5000000",
   )
   ```
2. Thêm cơ chế chọn backend đọc RTSP qua biến môi trường `RTSP_BACKEND`:
   - `RTSP_BACKEND=auto` *(mặc định)*: Thử `ffmpeg_cuda` (`h264_cuvid` $\rightarrow$ `hevc_cuvid` $\rightarrow$ `ffmpeg_cpu`) trước; nếu không có binary `ffmpeg` hoặc là file video `.mp4` local thì dùng `opencv`.
   - `RTSP_BACKEND=opencv`: Dùng `cv2.VideoCapture` truyền thống (đổi `cv2.INTER_AREA` thành `cv2.INTER_LINEAR`).
3. Cấu trúc lệnh `ffmpeg` subprocess chuẩn cho `h264_cuvid` (và tương tự cho `hevc_cuvid`):
   ```python
   cmd = [
       "ffmpeg",
       "-hide_banner",
       "-loglevel", "error",
       "-rtsp_transport", "tcp",
       "-fflags", "nobuffer",
       "-flags", "low_delay",
       "-strict", "experimental",
       "-probesize", "32768",
       "-analyzeduration", "0",
       "-hwaccel", "cuda",
       "-c:v", codec_cuvid,          # "h264_cuvid" hoặc "hevc_cuvid"
       "-resize", f"{self.w}x{self.h}",
       "-i", self.url,
       "-an", "-sn",
       "-f", "rawvideo",
       "-pix_fmt", "bgr24",
       "pipe:1",
   ]
   ```
4. Trong vòng lặp đọc `pipe:1`:
   - Mỗi frame có kích thước cố định `frame_bytes = self.w * self.h * 3` (`1280 * 720 * 3 = 2,764,800 bytes`).
   - Dùng `proc.stdout.read(frame_bytes)` đọc liên tục **không `sleep`**, để mọi frame vừa ra khỏi NVDEC đều được lấy ngay lập tức (xả sạch OS pipe buffer).
   - Dùng `np.frombuffer(raw, dtype=np.uint8).reshape((self.h, self.w, 3)).copy()` và chỉ cập nhật `self._latest` khi `now - last_emit >= interval - 0.003`.
   - Khi `stop()` hoặc mất luồng (`len(raw) != frame_bytes`), gọi `proc.kill()` + `proc.wait(timeout=2.0)` sạch sẽ trước khi reconnect.
5. Trong nhánh fallback `_run_opencv()`:
   - Đổi `cv2.INTER_AREA` ở dòng 126 thành **`cv2.INTER_LINEAR`** (tăng tốc gấp 3–4 lần khi hạ từ `2560x1440` xuống `1280x720`).

---

### Bước 2: Khử Độ Trễ Pha Kalman Filter Trong `poc/backend/ai/core_pipeline/tracker.py` (Chuẩn C09)

**Vấn đề hiện tại:**
Ở [`poc/backend/ai/core_pipeline/tracker.py:62-68`](../../poc/backend/ai/core_pipeline/tracker.py#L62-L68):
```python
tracked = self.bt.update_with_detections(sv_dets)
...
xyxy = tracked.xyxy[i].astype(np.float32)
```
`tracked.xyxy` là tọa độ ước lượng từ bộ lọc Kalman của ByteTrack, luôn bị trễ pha so với `det.xyxy` thật vừa suy luận từ YOLO trên frame hiện tại.

**Cách sửa trong [`poc/backend/ai/core_pipeline/tracker.py`](../../poc/backend/ai/core_pipeline/tracker.py):**
- Viết thêm 1 hàm nhỏ `_snap_to_raw_detections(tracked_xyxy: np.ndarray, raw_xyxy: np.ndarray, iou_thresh: float = 0.5) -> np.ndarray`:
  - Tính ma trận IoU giữa `tracked_xyxy` (`M x 4`) và `raw_xyxy` (`N x 4`) của YOLO trên frame hiện tại.
  - Với mỗi track `i`, nếu có detection gốc `j` đạt `IoU >= 0.5` lớn nhất, **thay thế `xyxy` của track bằng chính `raw_xyxy[j]`** (tọa độ YOLO thật 100% ở frame hiện tại!).
  - Nhờ đó: vẫn giữ được `tid` ổn định và `voted_cls` của ByteTrack để tính `T50/D85`, nhưng hình chữ nhật BBox gửi lên Web VMS bám khít 100% vào vị trí xe thực tế trên video ở từng mili-giây.

**Đoạn code mẫu cho `_snap_to_raw_detections`:**
```python
def _snap_box_to_raw(track_box: np.ndarray, raw_boxes: np.ndarray, min_iou: float = 0.45) -> np.ndarray:
    """Replace Kalman-smoothed box with exact current-frame YOLO box if IoU >= min_iou (C09)."""
    if len(raw_boxes) == 0:
        return track_box
    x1 = np.maximum(track_box[0], raw_boxes[:, 0])
    y1 = np.maximum(track_box[1], raw_boxes[:, 1])
    x2 = np.minimum(track_box[2], raw_boxes[:, 2])
    y2 = np.minimum(track_box[3], raw_boxes[:, 3])

    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_t = max(1e-6, float((track_box[2] - track_box[0]) * (track_box[3] - track_box[1])))
    area_r = np.maximum(1e-6, (raw_boxes[:, 2] - raw_boxes[:, 0]) * (raw_boxes[:, 3] - raw_boxes[:, 1]))
    ious = inter / (area_t + area_r - inter)

    best_idx = int(np.argmax(ious))
    if float(ious[best_idx]) >= min_iou:
        return raw_boxes[best_idx].astype(np.float32)
    return track_box
```
Và trong vòng `for i in range(len(tracked)):` của `CameraTracker.update()`:
```python
xyxy = _snap_box_to_raw(tracked.xyxy[i].astype(np.float32), det.xyxy)
```

---

### Bước 3: Tách `CameraProcessor` Thành 2 Bước: `process_fast()` (Nhánh 1) & `process_macro()` (Nhánh 2)

**Mục tiêu:** Giữ nguyên hàm `process(det, now)` cũ để **100% tương thích ngược** với PoC (`GpuBatcher` và toàn bộ 27 unit tests hiện có), đồng thời cung cấp 2 phương thức tách nhánh cho Staging Worker:

Trong [`poc/backend/ai/engine/camera_processor.py`](../../poc/backend/ai/engine/camera_processor.py):

1. **Phương thức 1 — `process_fast(self, det: Det, now: float) -> tuple[dict, tuple[np.ndarray, Det, list[Track], float]]`:**
   - Chỉ chạy `tracks = self.tracker.update(det, now)` và quy đổi `detections` sang tọa độ chuẩn hóa `0..1` (`~1–2 ms`).
   - Kết hợp `detections` mới nhất vừa tìm được với các chỉ số vĩ mô (`metrics`, `state`, `state_conf`, `occlusion_hold`, `confirmed_state`) từ `self._last_result` (hoặc giá trị khởi tạo mặc định nếu là frame đầu tiên).
   - Trả về ngay `(fast_result, macro_task)` với `macro_task = (frame, det, tracks, now)`.

2. **Phương thức 2 — `process_macro(self, frame: np.ndarray, det: Det, tracks: list[Track], now: float) -> dict`:**
   - Chạy phần nặng trên CPU:
     - `zm = self.zone_time.update(tracks, now)`
     - `o_vis, v_flow = self.flow_occ.update(frame, det.xyxy, dt=dt, stalled_hint=stalled_hint)`
     - `occ = self.occlusion.update(tracks, o_vis, now)`
     - `raw_state, state_conf = classify(metrics, self.cfg)`
     - `display_state, ev_trigger = self.sm.update(...)`
   - Cập nhật `self._last_result` và `self.pending_event` (nếu có `ev_trigger`).

3. **Giữ nguyên hàm `process(self, det: Det, now: float) -> dict`:**
   - Gọi `_, macro_task = self.process_fast(det, now)` rồi `return self.process_macro(*macro_task)` — đảm bảo PoC và toàn bộ test cũ chạy y hệt như trước!

---

### Bước 4: Cập Nhật `integrate-stg/src/worker.py` Chạy Song Song 2 Nhánh (Zero-Wait BBox Publish)

Trong [`integrate-stg/src/worker.py`](../src/worker.py):

1. **Thêm bộ đệm 1-phần-tử (`Latest-Macro-Slot`) và Thread phụ `_macro_loop`:**
   - Trong `__init__`:
     ```python
     self._macro_lock = threading.Lock()
     self._macro_evt = threading.Event()
     self._latest_macro_task: tuple[np.ndarray, Any, list, float] | None = None
     self._macro_thread: threading.Thread | None = None
     ```
   - Trong `start()`: khởi chạy cả 2 thread:
     - `self._thread` (`_run_loop` — **Nhánh 1: Fast Detection + Tracking + Publish BBox Ngay**).
     - `self._macro_thread` (`_macro_loop` — **Nhánh 2: Xử lý tiếp Frame tính `ZoneTime + FlowOccupancy + StateMachine` + Publish Event**).

2. **Luồng của Nhánh 1 (`_run_loop`):**
   ```python
   prep = self.processor.prepare()
   now_mono = time.monotonic()

   if prep is not None:
       crop, offset = prep
       t0 = time.perf_counter()
       with self.detector_lock:
           dets = self.detector.detect_batch([crop], [offset])

       # 1. NHÁNH 1: Chạy ByteTrack & lấy BBox tức thời (~1ms)
       fast_result, macro_task = self.processor.process_fast(dets[0], now_mono)
       self.stats["last_inference_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
       self.stats["frames_processed"] += 1

       # Bắn BBox lên MQTT NGAY LẬP TỨC (Không chờ MOG2 / Optical Flow!)
       last_bbox_ts = time.time()
       self._publish_bbox(fast_result)

       # 2. NHÁNH 2: Đẩy sang Macro Worker không chặn (chỉ giữ frame mới nhất)
       with self._macro_lock:
           self._latest_macro_task = macro_task
       self._macro_evt.set()
   ```

3. **Luồng của Nhánh 2 (`_macro_loop`):**
   ```python
   while not self._stop_event.is_set():
       if not self._macro_evt.wait(timeout=0.1):
           continue
       self._macro_evt.clear()

       with self._macro_lock:
           task = self._latest_macro_task
           self._latest_macro_task = None

       if task is None:
           continue

       frame, det, tracks, now_mono = task
       macro_res = self.processor.process_macro(frame, det, tracks, now_mono)
       self.stats["last_state"] = macro_res["state"]

       if self.processor.pending_event is not None:
           partial, ev_frame = self.processor.pending_event
           self.processor.pending_event = None
           self._handle_confirmed_event(partial, ev_frame)
   ```

> **Lợi ích kép của thiết kế này:**
> - **BBox bắn tức thì:** Ngay khi GPU vừa trả kết quả YOLO xong, chỉ mất `~1ms` ghép ID từ ByteTrack là gói tin BBox bay thẳng lên Mosquitto.
> - **GPU và CPU chạy song song (Pipelined):** Trong lúc CPU đang tính `MOG2 + Farneback` cho Frame $N$ ở `_macro_loop`, thì `_run_loop` đã lấy Frame $N+1$ đưa vào GPU RTX A400 để suy luận YOLO! Tốc độ BBox tăng vọt lên đúng tốc độ phần cứng của GPU (`20 – 25 FPS`), không bao giờ bị nghẽn bởi CPU.

---

### Bước 5: Cập Nhật Cấu Hình Trong `integrate-stg/.env.example` & `integrate-stg/.env`

Thêm 2 biến cấu hình tối ưu độ trễ vào [`integrate-stg/.env.example`](../.env.example) và file `.env` trên server `aiot`:

```ini
# Backend giải mã RTSP: auto (ưu tiên FFmpeg CUDA h264_cuvid/hevc_cuvid + scale phần cứng) | opencv
RTSP_BACKEND=auto

# Hạ ngưỡng kích hoạt ByteTrack từ 0.45 xuống 0.25 để xe vừa vào vùng là hiện BBox ngay frame đầu tiên
TRACK_ACTIVATION_CONF=0.25
```

---

## 5. Quy Trình Kiểm Thử & Nghiệm Thu Trên Server `aiot` (Dành Cho Hydrogen)

Sau khi cập nhật các file trên, chạy lần lượt các lệnh sau để xác minh:

### 5.1. Chạy Unit Tests đảm bảo không phá vỡ logic V2 hiện có
```bash
cd ~/projects/tien/atin_traffic_congestion_evaluation/poc/backend
uv run pytest ai/tests tests -v
```
*(Kỳ vọng: Pass 100% toàn bộ các bài test).*

### 5.2. Kiểm tra nhanh `FFmpeg CUVID` với luồng RTSP Staging trên server `aiot`
```bash
ffmpeg -hide_banner -loglevel info -rtsp_transport tcp -fflags nobuffer -flags low_delay \
  -hwaccel cuda -c:v h264_cuvid -resize 1280x720 \
  -i "rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect" \
  -frames:v 5 -f null -
```
- Nếu trả về 5 frame thành công không báo lỗi $\rightarrow$ Luồng là H.264 và `h264_cuvid` + `-resize 1280x720` hoạt động hoàn hảo trên NVDEC.
- Nếu luồng gốc là H.265 (HEVC), `StreamReader` sẽ tự động chuyển sang `hevc_cuvid`.

### 5.3. Khởi động lại Worker trong `tmux` và quan sát Log `[STATS]`
```bash
tmux attach -t stg
# Bấm Ctrl+C để dừng bản cũ, sau đó chạy lại:
uv run --project poc/backend --no-sync python integrate-stg/run_staging.py
```

**Chỉ số kỳ vọng trên Log và Web `https://aioc-stg.atin.vn/monitoring`:**
1. Log khởi tạo báo: `[camera_junction] Connected via FFmpeg CUDA (h264_cuvid 1280x720)`.
2. Log `[STATS cam=camera_junction]` báo:
   - `Infer`: giảm từ `~35–45ms` (gộp cả MOG2/Farneback) xuống chỉ còn **`~14–20ms`** (chỉ tốn thời gian YOLO + ByteTrack).
   - `FPS`: đạt **`20.0 – 25.0 FPS`** (thay vì bị kẹt ở `12–15 FPS`).
3. Trên giao diện Web `/monitoring` của `Junction Camera`:
   - Khung BBox xuất hiện ngay khi xe vừa đi vào vùng và bám sát thân xe theo thời gian thực, không còn hiện tượng khung chữ nhật chạy đuổi theo sau đuôi xe.
   - Bảng HUD 5 dòng ở góc trên vẫn cập nhật mượt mà đầy đủ `Độ phủ`, `Dòng xe`, `Thoát vùng`, `Dừng/chậm`.
