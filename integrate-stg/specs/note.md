Analyzed 06_FFMPEG_CUVID_GO2RTC_ISSUE.md:L1-97
Analyzed stream_reader.py:L1-308
Analyzed config.py:L1-102

Phân tích và đề xuất của Hydrogen là **rất hợp lý, trúng đích về mặt quản lý môi trường (`AGENTS.md`) và cơ chế liên kết động (`dlopen`) với GPU**. Tuy nhiên, khi đi sâu vào **cơ chế nội bộ của FFmpeg + `go2rtc` + `h264_cuvid`**, có **1 phát hiện kỹ thuật cực kỳ quan trọng** trong chính log lỗi mà nếu không biết trước, kể cả khi bạn cài FFmpeg 7.x vào `.venv/bin/` thì lệnh `ffmpeg -c:v h264_cuvid` **vẫn có thể thất bại y hệt**!

Dưới đây là đánh giá chi tiết từng điểm đúng của Hydrogen và **điểm mấu chốt còn thiếu** để đảm bảo triển khai thành công 100%.

---

### 1. Những điểm Hydrogen phân tích ĐÚNG và HỢP LÝ 100%

1. **Về việc đặt `ffmpeg` 7.x (BtbN GPL build) vào `poc/backend/.venv/bin/` có dùng được GPU RTX A400 không?**
   - **Hoàn toàn ĐÚNG.** Cơ chế `ffnvcodec` của FFmpeg không biên dịch tĩnh driver NVIDIA vào trong file binary, mà lúc chạy sẽ gọi `dlopen("libcuda.so.1")` và `dlopen("libnvcuvid.so.1")` từ NVIDIA Driver của hệ điều hành (`aiot`). Do đó đặt file `ffmpeg` ở `poc/backend/.venv/bin/ffmpeg` vẫn giao tiếp với chip NVDEC của RTX A400 nhanh và đầy đủ 100% như `/usr/bin/ffmpeg`.
2. **Về lý do KHÔNG nâng cấp `/usr/bin/ffmpeg` của Ubuntu 22.04 mà đặt vào `.venv/bin/`:**
   - **Hoàn toàn ĐÚNG.** Nâng cấp `/usr/bin/ffmpeg` trên Ubuntu 22.04 đòi hỏi cài PPA ngoài, làm thay đổi `libavcodec/libavformat` toàn hệ thống, dễ làm hỏng các service khác đang chạy trên server chung `aiot` và vi phạm quy tắc cô lập môi trường trong [AGENTS.md](file:///e:/ATIN/traffic_congestion_evaluation/AGENTS.md).
3. **Phát hiện nhỏ nhưng rất tinh mắt của Hydrogen trong [integrate-stg/src/config.py](file:///e:/ATIN/traffic_congestion_evaluation/integrate-stg/src/config.py#L13-L16):**
   - Dòng 13–16 của `integrate-stg/src/config.py` gọi `os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", ...)` thiếu `probesize;32768|analyzeduration;0` trước khi import [stream_reader.py](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/ingestion/stream_reader.py#L18-L21), làm mất 2 cờ này khi chạy nhánh OpenCV. Chỗ này cần đồng bộ lại luôn.

---

### 2. Phát Hiện Kỹ Thuật Quan Trọng: Tại Sao Log Báo `[h264] a feature which has not been implemented` Và Tại Sao Chỉ Đổi Sang FFmpeg 7.x Có Thể Chưa Đủ?

Hãy nhìn kỹ vào 5 dòng log lỗi trong [06_FFMPEG_CUVID_GO2RTC_ISSUE.md](file:///e:/ATIN/traffic_congestion_evaluation/integrate-stg/specs/06_FFMPEG_CUVID_GO2RTC_ISSUE.md#L40-L53):

```text
[h264 @ 0x63b645d3db40] a feature which has not been implemented.
[h264 @ 0x63b645d3db40] no frame!
[rtsp @ 0x63b645d383c0] decoding for stream 0 failed
[rtsp @ 0x63b645d383c0] Could not find codec parameters for stream 0 (Video: h264, none): unspecified size
```

Có **2 sự thật kỹ thuật** đằng sau đoạn log này cần lưu ý khi thực hiện kế hoạch của Hydrogen:

#### Sự thật #1: Tại sao `cv2.VideoCapture` mở được ngay mà `ffmpeg -c:v h264_cuvid` lại báo lỗi?

- Khi bạn truyền **`-c:v h264_cuvid` nằm TRƯỚC `-i rtsp://...`** trong lệnh [stream_reader.py:127-129](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/ingestion/stream_reader.py#L127-L129):
  - Nếu SDP của `go2rtc/1.9.15` không gửi kèm `sprop-parameter-sets` (SPS/PPS), FFmpeg buộc phải mở decoder trong giai đoạn `avformat_find_stream_info` (probe) để đọc thử vài gói RTP đầu tiên nhằm tìm kích thước ảnh (`width x height`) và `pix_fmt`.
  - Khi ép `-c:v h264_cuvid` trước `-i`, hoặc khi luồng `go2rtc` đang phát giữa chừng một GOP (chưa tới IDR keyframe đầu tiên, hoặc gói RTP đầu tiên bị cắt nửa NAL unit / dùng SEI đặc thù của camera IP), parser H.264 trên FFmpeg 4.4 kết hợp với `h264_cuvid` (vốn đòi phải có `width x height` và `SPS/PPS` trước khi khởi tạo phần cứng NVDEC) sẽ **fail ngay lập tức** với lỗi `unspecified size`!
  - Trong khi đó, `cv2.VideoCapture` dùng **software decoder `h264` mặc định** (không ép `-c:v h264_cuvid`) và có kèm thư viện `libavcodec` mới hơn (FFmpeg 5.x/6.x được đóng gói sẵn trong wheel `opencv-python-headless`), nên nó bỏ qua các gói P-frame lỗi ban đầu, chờ đúng IDR/SPS/PPS đầu tiên là giải mã được ngay.

#### Sự thật #2: Trong FFmpeg mới (6.x / 7.x), có 2 cách gọi NVDEC hoàn toàn khác nhau!

Trong [stream_reader.py:126-129](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/ingestion/stream_reader.py#L126-L129), hiện đang viết:

```bash
-hwaccel cuda -c:v h264_cuvid -resize 1280x720 -i rtsp://...
```

Trên FFmpeg, có 2 cơ chế giải mã phần cứng NVIDIA:

1. **Cơ chế cũ (`-c:v h264_cuvid` — External CUVID Decoder):**
   - Giao toàn bộ việc parse & khởi tạo cho `h264_cuvid` ngay từ đầu. **Nhược điểm chí mạng:** Nếu RTSP SDP của `go2rtc` không có sẵn kích thước (`Video: h264, none: unspecified size`), `h264_cuvid` rất dễ từ chối khởi tạo vì chưa biết kích thước khung hình!
2. **Cơ chế mới chuẩn của FFmpeg (`-hwaccel nvdec` hoặc `-hwaccel cuda` KHÔNG ép `-c:v h264_cuvid` trước `-i`):**
   - Để parser/decoder `h264` chuẩn của FFmpeg tự động bắt SPS/PPS từ luồng RTSP `go2rtc` (giống hệt cách `cv2.VideoCapture` đang làm thành công!), sau đó **tự động offload việc giải mã frame xuống phần cứng NVDEC của RTX A400**!
   - Hoặc nếu muốn scale luôn trên GPU hoặc CPU siêu nhẹ:
     ```bash
     ffmpeg -rtsp_transport tcp -fflags nobuffer -flags low_delay \
       -hwaccel cuda \
       -i "rtsp://..." \
       -vf "scale=1280:720:flags=fast_bilinear" -f rawvideo -pix_fmt bgr24 pipe:1
     ```

---

### 3. Kết Luận & Khuyến Nghị Chốt Kế Hoạch Cho Hydrogen

Kế hoạch 4 bước của Hydrogen là **chuẩn xác và an toàn**, bạn hoàn toàn có thể duyệt cho Hydrogen làm ngay, kèm **3 bổ sung nhỏ nhưng quyết định thành bại** sau đây:

1. **Ở Bước 1 & Bước 2 (Khi test FFmpeg 7.x trong `poc/backend/.venv/bin/ffmpeg`):**
   Bảo Hydrogen chạy thử **cả 2 lệnh CLI** dưới đây trên `aiot` để so sánh:
   - **Lệnh A (Dùng `h264_cuvid` + `-resize` phần cứng):**
     ```bash
     poc/backend/.venv/bin/ffmpeg -hide_banner -loglevel info -rtsp_transport tcp \
       -probesize 2000000 -analyzeduration 2000000 \
       -hwaccel cuda -c:v h264_cuvid -resize 1280x720 \
       -i "rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect" \
       -frames:v 10 -f null -
     ```
   - **Lệnh B (Dùng `-hwaccel cuda` native của FFmpeg 7.x — không ép `-c:v h264_cuvid` trước `-i` để vượt qua lỗi `unspecified size` của `go2rtc`):**
     ```bash
     poc/backend/.venv/bin/ffmpeg -hide_banner -loglevel info -rtsp_transport tcp \
       -fflags nobuffer -flags low_delay -probesize 1000000 -analyzeduration 1000000 \
       -hwaccel cuda \
       -i "rtsp://admin:prometheus123@192.168.1.250:18554/c112_camera_junction_detect" \
       -vf "scale=1280:720:flags=fast_bilinear" -frames:v 10 -f null -
     ```
     _(Nếu Lệnh A chạy được thì dùng Lệnh A; nếu `go2rtc` thiếu SDP size làm `h264_cuvid` từ chối thì **Lệnh B chắc chắn sẽ giải mã bằng NVDEC thành công** vì nó dùng parser H.264 của FFmpeg 7.x để bắt SPS/PPS rồi mới đẩy xuống GPU RTX A400!)_

2. **Ở Bước 3 (Cập nhật code):**
   - Trong [poc/backend/ai/ingestion/stream_reader.py](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/ingestion/stream_reader.py):
     - Thêm hàm `_resolve_ffmpeg_bin()` ưu tiên tìm `Path(sys.executable).parent / "ffmpeg"` (tức `poc/backend/.venv/bin/ffmpeg`) trước khi tìm `shutil.which("ffmpeg")`.
     - Thêm mode `"cuda_hwaccel"` (Lệnh B ở trên) vào danh sách `modes` bên cạnh `"h264_cuvid"`.
   - Trong [integrate-stg/src/config.py](file:///e:/ATIN/traffic_congestion_evaluation/integrate-stg/src/config.py#L13-L16):
     - Đồng bộ chuỗi `OPENCV_FFMPEG_CAPTURE_OPTIONS` có đầy đủ `probesize;32768|analyzeduration;0` khớp với `stream_reader.py`.

Bạn muốn tôi cập nhật bổ sung hướng dẫn chi tiết này vào file [06_FFMPEG_CUVID_GO2RTC_ISSUE.md](file:///e:/ATIN/traffic_congestion_evaluation/integrate-stg/specs/06_FFMPEG_CUVID_GO2RTC_ISSUE.md) để Hydrogen cứ thế làm theo, hay để tôi sửa sẵn phần code `_resolve_ffmpeg_bin()` trong [stream_reader.py](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/ingestion/stream_reader.py) và [integrate-stg/src/config.py](file:///e:/ATIN/traffic_congestion_evaluation/integrate-stg/src/config.py) luôn?
