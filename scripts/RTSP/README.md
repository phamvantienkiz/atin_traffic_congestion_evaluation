# RTSP Multi-Stream Video Wall (Soft Clean Cards)

Giao diện Web & Backend Gateway nhận các luồng RTSP camera và phát trực tiếp trên cùng một màn hình (tùy chọn 4, 6 hoặc 8 video), tuân thủ nghiêm ngặt Design System **"Soft Clean Cards"** (`soft-clean-cards.md`).

---

## 1. Cấu Trúc Thư Mục

```
scripts/RTSP/
├── server.py              # Backend FastAPI & OpenCV bufferless RTSP streaming gateway
├── index.html             # Giao diện Web Semantic 4-8 slots
├── styles.css             # CSS Design System Soft Clean Cards (Design tokens chuẩn)
├── app.js                 # Frontend Controller quản lý luồng, LocalStorage, Fullscreen
├── requirements.txt       # Danh sách thư viện phụ thuộc
├── run.bat                # Script chạy server nhanh trên Windows
├── soft-clean-cards.md    # Source of truth về Design System
└── README.md              # Hướng dẫn sử dụng
```

---

## 2. Đặc Điểm Kỹ Thuật

1. **Hạ Tầng Backend (`server.py`)**:
   - Sử dụng **FastAPI** và **OpenCV Headless** (`cv2.VideoCapture`).
   - Kỹ thuật **Bufferless capture**: `CAP_PROP_BUFFERSIZE = 1` kết hợp cờ FFmpeg TCP `rtsp_transport;tcp` để triệt tiêu hiện tượng dồn buffer và trễ hình (latency < 150ms).
   - Mỗi slot camera (1 đến 8) chạy trong một **Thread độc lập**, cách ly hoàn toàn, một camera mất kết nối hoặc chập chờn không làm gián đoạn các luồng khác.
   - Endpoint `/api/stream/{slot_id}` phát dạng chuẩn **HTTP Multipart MJPEG** (`multipart/x-mixed-replace; boundary=frame`) tương thích 100% với thẻ `<img>` và HTML5 trên mọi trình duyệt hiện đại (Chrome, Edge, Firefox, Safari) mà không cần cài đặt thêm VLC plugin hay thiết lập WebRTC STUN/TURN phức tạp.
   - Tích hợp sẵn bộ sinh tín hiệu **Synthetic Test Pattern** (nhập `demo` hoặc bấm nút *Test demo* / *Demo all*) để kiểm thử ngay lập tức cả 8 luồng mà không bắt buộc phải có sẵn camera IP thật.

2. **Giao Diện Frontend (`index.html`, `styles.css`, `app.js`)**:
   - **Tuân thủ chuẩn Design System "Soft Clean Cards"**:
     - Nền trang xám chuyển nhẹ `--bg-page: #F5F5F7`
     - Card bo tròn lớn 28px (`--radius-xl`), viền 1px mờ (`--border-card: #E9E9EE`), đổ bóng rất nhẹ (`--shadow-card`).
     - Điểm nhấn chính (Hero Metric): Con số lớn căn giữa hiển thị số lượng camera đang phát trực tiếp.
     - Nút phát chính: Nút tròn đen Ink 44x44 (`--ink: #111114`) với `--shadow-primary`.
     - Segmented Control chuẩn mực: chuyển đổi mượt mà giữa các chế độ **4 Cameras**, **6 Cameras**, và **8 Cameras**.
     - Metric Row 3 cột: Nhãn trên, giá trị dưới (`Frame rate`, `Resolution`, `Connection`).
   - Tự động lưu các URL RTSP vào `LocalStorage`, tải lại trang không bị mất cấu hình.
   - Tính năng xem phóng to **Fullscreen** cho từng camera riêng biệt bằng icon button tròn.

---

## 3. Cách Cài Đặt & Chạy

### Cách 1: Chạy bằng `run.bat` (Khuyến nghị trên Windows)
Nhấp đúp chuột vào file `scripts/RTSP/run.bat` hoặc chạy từ PowerShell:
```powershell
.\scripts\RTSP\run.bat
```

### Cách 2: Chạy thủ công với `.venv` hoặc `uv`
```powershell
# Chạy trực tiếp qua môi trường ảo .venv đã được chuẩn bị
.\.venv\Scripts\python.exe scripts\RTSP\server.py

# Hoặc thông qua uv
uv run python scripts\RTSP\server.py
```

Sau khi server khởi động:
- Mở trình duyệt web truy cập: **`http://localhost:8080`**

---

## 4. Hướng Dẫn Sử Dụng Trên Web

1. **Chọn số lượng màn hình**: Bấm vào Segmented Control ở thanh tiêu đề để chọn xem **4 Cameras**, **6 Cameras** hoặc **8 Cameras**.
2. **Nhập luồng RTSP**:
   - Dán URL RTSP camera của bạn vào ô input (ví dụ: `rtsp://admin:123456@192.168.1.100:554/live/ch0`).
   - Nhấn nút tròn đen Play (hoặc phím Enter) để bắt đầu xem.
3. **Chế độ kiểm thử Demo không cần camera thật**:
   - Bấm nút **"Test demo"** ở từng card hoặc nút **"Demo all"** ở góc trên bên phải để giả lập phát đồng thời cả 4 - 8 màn hình với đồng hồ thời gian thực và radar quét động.
4. **Xem toàn màn hình**: Bấm biểu tượng 4 mũi tên ở góc trên bên phải card để phóng to toàn màn hình; nhấn phím `ESC` để quay lại lưới.
