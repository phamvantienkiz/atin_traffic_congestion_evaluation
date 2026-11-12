# ATIN Traffic Congestion Evaluation

> **Hệ thống đánh giá và phân loại trạng thái ùn tắc giao thông thông minh từ camera giám sát (RTSP stream).**  
> Dự án được phát triển và sở hữu độc quyền bởi **[ATIN Joint Stock Company](https://atin.com.vn/)**.

---

## 1. Giới thiệu tổng quan

**ATIN Traffic Congestion Evaluation** là mô-đun AI xử lý dữ liệu video từ luồng camera giám sát giao thông thực tế nhằm:
- Nhận diện và đếm các phương tiện giao thông (ô tô, xe máy, xe buýt, xe tải, v.v.) theo thời gian thực.
- Phân tích mật độ lưu thông và đo lường vận tốc di chuyển trung bình qua từng vùng giám sát (ROI).
- Tự động đánh giá và cảnh báo mức độ ùn tắc giao thông theo 3 mức độ tiêu chuẩn:
  - **Thông thoáng (Clear)**
  - **Đông đúc / Ùn ứ (Congested)**
  - **Tắc nghẽn nghiêm trọng (Gridlocked)**
- Kết nối và truyền tải bản tin trạng thái, cảnh báo qua giao thức thời gian thực (MQTT / WebSocket) phục vụ tích hợp hệ thống điều hành giao thông thông minh (ITS).

---

## 2. Kiến trúc & Công nghệ

- **Ngôn ngữ & Runtime:** Python 3.10+
- **Backend API & Service:** FastAPI, Uvicorn, AsyncIO
- **AI & Computer Vision:** PyTorch, OpenCV, YOLO (Ultralytics), NVIDIA CUDA
- **Giao thức & Truyền dẫn:** RTSP, WebRTC, WebSocket, MQTT
- **Quản lý môi trường & gói:** `uv` / virtualenv (`.venv`)

---

## 3. Cấu trúc thư mục

```text
atin_traffic_congestion_evaluation/
├── .agents/              # Cấu hình AI agent & MCP tools
├── models/               # Thư mục lưu trữ model weights (weights được ignore khỏi git)
├── poc/                  # Proof of Concept (AI pipelines, backend, frontend)
│   ├── ai/               # Xử lý mô hình thị giác máy tính
│   ├── backend/          # Dịch vụ backend API & WebSocket
│   └── frontend/         # Giao diện demo giám sát
├── scripts/              # Các kịch bản chạy thử nghiệm, RTSP player & streaming server
│   └── RTSP/             # Máy chủ streaming RTSP & Web viewer
├── .gitignore            # Cấu hình bỏ qua file tạm, weights, môi trường
├── AGENTS.md             # Bộ quy chuẩn phát triển cho Agent & Developers
├── LICENSE               # Giấy phép sở hữu độc quyền ATIN
└── README.md             # Tài liệu giới thiệu dự án
```

---

## 4. Hướng dẫn cài đặt & Khởi chạy

### 4.1. Yêu cầu hệ thống
- Hệ điều hành: Windows / Linux
- Python 3.10+
- GPU NVIDIA hỗ trợ CUDA (khuyến nghị cho suy luận thời gian thực)
- Công cụ quản lý gói: `uv` (hoặc `venv` tiêu chuẩn)

### 4.2. Thiết lập môi trường ảo
Tuân thủ nguyên tắc cách ly môi trường (không cài đặt vào global system):

```bash
# Sử dụng uv (khuyến nghị)
uv venv .venv
# Kích hoạt trên Windows PowerShell:
.venv\Scripts\Activate.ps1
# Hoặc trên Linux/macOS:
source .venv/bin/activate
```

### 4.3. Cài đặt thư viện phụ thuộc
```bash
uv pip install -r scripts/RTSP/requirements.txt
```

### 4.4. Cấu hình Model Weights
Tải các file trọng số mô hình (VD: `vehicle_n_best.pt`) và đặt vào thư mục `models/`:
```text
models/
└── vehicle_n_best.pt
```

### 4.5. Khởi chạy RTSP Test Server / Viewer
```bash
cd scripts/RTSP
python server.py
```
Truy cập giao diện web tại: `http://localhost:8000`

---

## 5. Bản quyền & Sở hữu trí tuệ

**BẢN QUYỀN THUỘC VỀ CÔNG TY CỔ PHẦN CÔNG NGHỆ THÔNG TIN ATIN (https://atin.com.vn/). TẤT CẢ CÁC QUYỀN ĐƯỢC BẢO LƯU.**

Nghiêm cấm mọi hành vi sao chép, chỉnh sửa, phân phối, dịch ngược (reverse engineer), hoặc sử dụng mã nguồn này dưới bất kỳ hình thức nào (dù là mục đích cá nhân hay doanh nghiệp thương mại) khi chưa có sự đồng ý bằng văn bản từ **ATIN**.

Chi tiết xem tại tệp [LICENSE](LICENSE).
