# BÁO CÁO SỰ CỐ: KHÔNG ÁP DỤNG ĐƯỢC `FFMPEG + H264_CUVID / HEVC_CUVID` TRÊN LUỒNG `go2rtc/1.9.15` (`06_FFMPEG_CUVID_GO2RTC_ISSUE.md`)

> **Ngày ghi nhận:** 2026-11-17  
> **Môi trường:** Server `aiot` (Ubuntu 22.04.5 LTS, NVIDIA RTX A400 4GB, `poc/backend/.venv`)  
> **Luồng mục tiêu:** `rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect` (`camera_junction`, `2560x1440`, qua `go2rtc/1.9.15`)  
> **Liên quan:** [`05_LOW_LATENCY_BBOX_OPTIMIZATION_SPEC.md`](./05_LOW_LATENCY_BBOX_OPTIMIZATION_SPEC.md), [`poc/backend/ai/ingestion/stream_reader.py`](../../poc/backend/ai/ingestion/stream_reader.py)

---

## 1. Tóm Tắt Vấn Đề

Khi triển khai giải pháp đọc RTSP bằng **`FFmpeg CUDA/NVDEC` (`h264_cuvid` / `hevc_cuvid`)** trên server `aiot` để giải mã 2K bằng phần cứng và `-resize 1280x720`, luồng RTSP của `camera_junction` (đi qua **`go2rtc/1.9.15`**) **không thể giải mã được bằng binary `/usr/bin/ffmpeg` của hệ thống**.

Kết quả thực tế khi chạy `integrate-stg/run_staging.py` với `RTSP_BACKEND=auto`:
- Worker khởi tạo thành công, MQTT kết nối OK, hot-reload ROI `POLY_325208` OK.
- Tuy nhiên `StreamReader` đứng im hoàn toàn, không phát sinh bất kỳ frame nào trong >100 giây:
  ```text
  [INFO] main: [STATS cam=camera_junction] state=UNKNOWN | FPS=0.0 | Infer=0.0ms | BBoxSent=0 | EvLogged=0 | EvPub=0
  ```

---

## 2. Chi Tiết Các Lỗi Gặp Phải

### Lỗi 1: `StreamReader` bị treo im lặng (`blocking read` vô thời hạn) trong lần thử đầu (`d03a2ea`)
1. `proc.stdout.read(frame_bytes)` đọc blocking trên pipe `stdout` của `ffmpeg` nhưng **không có cơ chế timeout (`select.select`)** ở phía Python.
2. Lệnh `ffmpeg` ban đầu truyền `-probesize 32768 -analyzeduration 0` (quá nhỏ đối với keyframe 2K `2560x1440` vốn >100 KB) và thiếu `-nostdin` / `stdin=subprocess.DEVNULL`.
3. Khi `ffmpeg` bị kẹt trong lúc probe stream hoặc chờ keyframe, tiến trình không thoát hẳn mà cũng không ghi đủ `2,764,800 bytes/frame` ra `pipe:1` $\rightarrow$ thread `rtsp-camera_junction` bị treo vĩnh viễn, không kích hoạt được fallback sang `hevc_cuvid` hay `OpenCV`.

### Lỗi 2: `ffmpeg` hệ thống không parse được luồng H.264 từ `go2rtc/1.9.15` (cả khi tăng `probesize` & `analyzeduration`)
Khi chạy kiểm tra trực tiếp `ffmpeg` CLI trên server `aiot` (cả với cấu hình mặc định lẫn cấu hình tăng `-probesize 5000000 -analyzeduration 5000000`):

```bash
URL="rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect"
ffmpeg -rtsp_transport tcp -probesize 5000000 -analyzeduration 5000000 -hwaccel cuda -c:v h264_cuvid -resize 1280x720 -i "$URL" -frames:v 5 -f null -
```

Log lỗi thu được từ `ffmpeg`:
```text
[h264 @ 0x63b645d3db40] a feature which has not been implemented.
[h264 @ 0x63b645d3db40] If you want to help, upload a sample of this file to https://streams.videolan.org/upload/ and contact the ffmpeg-devel mailing list. (ffmpeg-devel@ffmpeg.org)
[h264 @ 0x63b645d3db40] no frame!
[rtsp @ 0x63b645d383c0] decoding for stream 0 failed
[rtsp @ 0x63b645d383c0] Could not find codec parameters for stream 0 (Video: h264, none): unspecified size
Consider increasing the value for the 'analyzeduration' (5000000) and 'probesize' (5000000) options
Input #0, rtsp, from 'rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect':
  Metadata:
    title           : go2rtc/1.9.15
  Duration: N/A, bitrate: N/A
  Stream #0:0: Video: h264, none, 90k tbr, 90k tbn, 180k tbc
Stream mapping:
  Stream #0:0 -> #0:0 (h264 (h264_cuvid) -> wrapped_avframe (native))
Cannot determine format of input stream 0:0 after EOF
```

---

## 3. Phân Tích Nguyên Nhân Gốc Rễ

1. **Thiếu `SPS/PPS` / kích thước khung hình trong SDP của `go2rtc/1.9.15`:**
   - Luồng RTSP do `go2rtc/1.9.15` phát lại trả về `Video: h264, none` (`unspecified size`).
   - Bộ giải mã phần cứng **`h264_cuvid`** bắt buộc phải xác định được kích thước khung hình và định dạng pixel ngay khi khởi tạo NVDEC (đặc biệt khi kết hợp `-resize 1280x720`), nên không khởi tạo được decoder trên luồng thiếu thông số này.
2. **Phiên bản `/usr/bin/ffmpeg` trên Ubuntu 22.04 (FFmpeg 4.4.x) gặp lỗi parser H.264 với luồng `go2rtc`:**
   - Parser `[h264]` trong bản `ffmpeg` hệ thống báo `a feature which has not been implemented.` và `no frame!`.
   - Trong khi đó, `cv2.VideoCapture(..., cv2.CAP_FFMPEG)` trong `poc/backend/.venv` đọc được chính URL này bình thường vì wheel `opencv-python` trên PyPI đóng gói kèm **thư viện FFmpeg nội bộ đời mới hơn** (`libavcodec`/`libavformat`).

---

## 4. Giải Pháp Đã Áp Dụng Tạm Thời (`e04414a`)

1. **Chống treo vĩnh viễn trong `StreamReader` ([stream_reader.py](../../poc/backend/ai/ingestion/stream_reader.py)):**
   - Thêm `-nostdin` và `stdin=subprocess.DEVNULL`.
   - Nâng `-probesize 500000 -analyzeduration 500000`.
   - Thêm `_read_frame_bytes()` dùng `select.select` trên Linux với timeout `self.timeout_s` (`5.0s`): tự động kill `ffmpeg`, ghi log lỗi `stderr` và fallback qua `hevc_cuvid` $\rightarrow$ `ffmpeg_cpu` $\rightarrow$ `OpenCV` nếu không nhận được frame.
2. **Đặt mặc định Staging sang `RTSP_BACKEND=opencv` ([`integrate-stg/.env.example`](../.env.example), [`04_IMPLEMENTATION_AND_RUN_GUIDE.md`](./04_IMPLEMENTATION_AND_RUN_GUIDE.md)):**
   - Tránh mất ~10–15s chờ timeout fallback mỗi lần khởi động worker trên luồng `go2rtc/1.9.15`.
   - **Vẫn giữ nguyên toàn bộ 4 tối ưu còn lại:**
     - `OPENCV_FFMPEG_CAPTURE_OPTIONS` (`rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|probesize;32768|analyzeduration;0|stimeout;5000000`).
     - `cv2.INTER_LINEAR` thay cho `cv2.INTER_AREA` khi hạ từ `2560x1440` xuống `1280x720`.
     - Khử trễ pha Kalman Filter trong `CameraTracker` (`_snap_box_to_raw()`) + hạ `TRACK_ACTIVATION_CONF=0.25`.
     - Tách nhánh song song `process_fast()` (publish BBox ngay sau YOLO) và `_macro_loop()` (tính `MOG2 + Farneback + StateMachine` trên CPU không chặn BBox).

---

## 5. Hướng Khắc Phục Triệt Để Để Bật Lại `FFmpeg + NVDEC/CUDA`

Để sử dụng được giải mã phần cứng NVDEC trên `go2rtc/1.9.15` mà vẫn tuân thủ tuyệt đối quy tắc cô lập `.venv` của `AGENTS.md` (*No Global Scope Spillage*):

1. **Cài `ffmpeg` 7.x static build (BtbN GPL build) cục bộ vào `poc/backend/.venv/bin/ffmpeg` trên server `aiot`:**
   - Không nâng cấp `/usr/bin/ffmpeg` của Ubuntu 22.04 để tránh ảnh hưởng tới các service khác trên server chung.
   - FFmpeg bản static (`ffnvcodec`) tự động gọi `dlopen("libcuda.so.1")` và `dlopen("libnvcuvid.so.1")` từ NVIDIA Driver của hệ thống nên giao tiếp đầy đủ với RTX A400.
   ```bash
   # Chạy trực tiếp tại thư mục gốc dự án: ~/projects/tien/atin_traffic_congestion_evaluation
   mkdir -p /tmp/ffmpeg-btbn
   curl -fL https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz -o /tmp/ffmpeg.tar.xz && \
   tar -xf /tmp/ffmpeg.tar.xz --strip-components=1 -C /tmp/ffmpeg-btbn && \
   cp /tmp/ffmpeg-btbn/bin/ffmpeg poc/backend/.venv/bin/ffmpeg && \
   cp /tmp/ffmpeg-btbn/bin/ffprobe poc/backend/.venv/bin/ffprobe && \
   chmod +x poc/backend/.venv/bin/ffmpeg poc/backend/.venv/bin/ffprobe && \
   rm -rf /tmp/ffmpeg.tar.xz /tmp/ffmpeg-btbn && \
   poc/backend/.venv/bin/ffmpeg -version | head -n 2
   ```
2. **Kiểm chứng cả 2 lệnh CLI (Lệnh A: `h264_cuvid` vs Lệnh B: `-hwaccel cuda` native) trên `aiot`:**
   - **Lệnh A (`h264_cuvid` + `-resize` phần cứng):**
     ```bash
     poc/backend/.venv/bin/ffmpeg -hide_banner -loglevel info -rtsp_transport tcp \
       -probesize 2000000 -analyzeduration 2000000 \
       -hwaccel cuda -c:v h264_cuvid -resize 1280x720 \
       -i "rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect" \
       -frames:v 10 -f null -
     ```
   - **Lệnh B (`-hwaccel cuda` native — không ép `-c:v h264_cuvid` trước `-i` để vượt qua lỗi `unspecified size` của `go2rtc`):**
     ```bash
     poc/backend/.venv/bin/ffmpeg -hide_banner -loglevel info -rtsp_transport tcp \
       -fflags nobuffer -flags low_delay -probesize 1000000 -analyzeduration 1000000 \
       -hwaccel cuda \
       -i "rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect" \
       -vf "scale=1280:720:flags=fast_bilinear" -frames:v 10 -f null -
     ```
3. **Cập nhật code đã triển khai sẵn:**
   - `poc/backend/ai/ingestion/stream_reader.py`: Thêm `_resolve_ffmpeg_bin()` ưu tiên `Path(sys.executable).parent / "ffmpeg"` (`.venv/bin/ffmpeg`) trước `shutil.which("ffmpeg")` và thêm mode `"cuda_hwaccel"` (Lệnh B) vào chuỗi fallback `["h264_cuvid", "cuda_hwaccel", "hevc_cuvid", "ffmpeg_cpu"]`.
   - `integrate-stg/src/config.py`: Đồng bộ `OPENCV_FFMPEG_CAPTURE_OPTIONS` có đủ `probesize;32768|analyzeduration;0` khớp với `stream_reader.py`.
   - Sau khi xác nhận Lệnh A hoặc Lệnh B chạy thành công trên `aiot`, đổi `RTSP_BACKEND=auto` trong `integrate-stg/.env` để kích hoạt NVDEC.
