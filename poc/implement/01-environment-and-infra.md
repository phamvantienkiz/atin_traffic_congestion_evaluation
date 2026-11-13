# 01 — MÔI TRƯỜNG, HẠ TẦNG & KẾT NỐI (GIAI ĐOẠN G0)

> Mục tiêu: Server GPU chạy MediaMTX + môi trường Python; laptop xem được WebRTC của camera qua VPN/SSH tunnel.
> Tiêu chí xong: mở `http://localhost:8889/cam1/` trên laptop thấy video camera 1.

## 1. Cấu trúc thư mục cuối cùng của `poc/`

```text
poc/
├── .env.example              # Biến môi trường mẫu
├── run.sh                    # Khởi động backend (Linux server)
├── mediamtx/
│   ├── mediamtx.yml          # Cấu hình MediaMTX (sinh tự động bởi backend, có bản mẫu)
│   └── README.md             # Cách tải binary
├── backend/                  # Gộp AI + Backend, cô lập bằng backend/.venv (xem 02 & 03)
│   ├── pyproject.toml        # Dependencies Python (dùng chung cho ai + backend)
│   ├── .python-version       # 3.11 / 3.12
│   └── ai/                   # Phân hệ AI (xem 02-ai-pipeline.md)
├── frontend/                 # HTML/CSS/Vanilla JS thuần, không dependency (xem 04-frontend.md)
└── implement/                # Tài liệu kế hoạch
```
`.gitignore` bổ sung: `poc/mediamtx/mediamtx` (binary), `poc/mediamtx/mediamtx.exe`, `poc/backend/data/snapshots/`, `poc/backend/data/cameras.json`, `*.onnx`, `*.engine`. (Thư mục `.venv/` đã được ignore toàn cục.)

## 2. Bước 1 — Kết nối Server (mỗi lần làm việc)

1. Bật **OpenVPN Connect** trên laptop.
2. Mở **Termius** → host server → tab **Port Forwarding** → thêm 2 rule **Local**:
   | Local port | Destination host | Destination port | Dùng cho |
   | :-: | :-: | :-: | :-- |
   | 8080 | 127.0.0.1 | 8080 | Web UI + API + WebSocket |
   | 8889 | 127.0.0.1 | 8889 | Trang WebRTC MediaMTX (HTTP signaling) |
   | 8189 | 127.0.0.1 | 8189 | WebRTC media qua **TCP** |
   Lệnh tương đương: `ssh -L 8080:127.0.0.1:8080 -L 8889:127.0.0.1:8889 -L 8189:127.0.0.1:8189 user@<IP_SERVER>`
3. Nếu VPN cho phép truy cập thẳng IP server, có thể bỏ tunnel và dùng `http://<IP_SERVER>:8080` (khi đó trong `mediamtx.yml` thay `127.0.0.1` ở `webrtcAdditionalHosts` bằng IP server).

> Vì sao cần cổng 8189 TCP: SSH tunnel chỉ chuyển TCP, WebRTC mặc định dùng UDP. Ta ép MediaMTX dùng ICE TCP `:8189` và quảng bá host `127.0.0.1` → trình duyệt kết nối media qua tunnel.

## 3. Bước 2 — Kiểm tra Server (chạy 1 lần)

```bash
nvidia-smi                 # Thấy RTX A400, driver >= 525, CUDA Version >= 12.x
python3 --version          # có hay không đều được, ta dùng uv
which ffmpeg || true       # không bắt buộc
```
Cài `uv` vào thư mục người dùng (không cần sudo, không global system):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # cài vào ~/.local/bin
```

## 4. Bước 3 — Clone repo & tạo môi trường Python

```bash
mkdir -p ~/work && cd ~/work
git clone <repo_url> traffic_congestion_evaluation
cd traffic_congestion_evaluation/poc/backend
uv python install 3.12
uv venv --python 3.12 .venv
```

`poc/backend/pyproject.toml`:
```toml
[project]
name = "traffic-poc"
version = "0.1.0"
requires-python = ">=3.10,<3.12"
dependencies = [
  "ultralytics>=8.3.0",
  "supervision>=0.25.0",
  "opencv-python-headless>=4.9",
  "numpy>=1.26,<2.0",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "pydantic>=2.6",
  "python-dotenv>=1.0",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
onnx = ["onnx>=1.15", "onnxruntime-gpu>=1.17", "onnxslim"]

[tool.uv]
# PyTorch CUDA 12.1 wheel
[[tool.uv.index]]
name = "pytorch-cu121"
url = "https://download.pytorch.org/whl/cu121"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-cu121" }
torchvision = { index = "pytorch-cu121" }
```
Thêm `"torch>=2.2"`, `"torchvision>=0.17"` vào `dependencies`. Cài:
```bash
uv sync
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Kỳ vọng: True NVIDIA RTX A400
```
Nếu driver cũ chỉ hỗ trợ CUDA 11.8: đổi URL index sang `cu118`.

Kiểm tra model:
```bash
uv run python -c "from ultralytics import YOLO; m=YOLO('../models/vehicle_n_best.pt'); print(m.names)"
```
**Kết quả đã xác nhận (đọc metadata checkpoint):** `{0:'bus', 1:'car', 2:'motobike', 3:'truck'}` — lưu ý `motobike` (không phải `motorcycle`). `class_groups` trong `poc/ai/config.py` đã cập nhật theo (xem 02 B1). Trên server vẫn chạy lệnh trên một lần để xác nhận khớp.

> Chưa kiểm tra được trên máy dev Windows: `.venv` của repo hiện **chưa cài `ultralytics`/`torch`**, nên chưa chạy thử được model. Phần cài đặt nằm ở mục 4 (trên server).

### Kiểm tra codec camera (làm trên server, trước G0)
Server `scripts/RTSP` dùng OpenCV giải mã rồi phát MJPEG nên **không chứng minh được codec camera**. Cần kiểm tra thật:
```bash
ffprobe -v error -rtsp_transport tcp -select_streams v:0 \
  -show_entries stream=codec_name,width,height,avg_frame_rate \
  -of default=nw=1 "rtsp://user:pass@IP:554/stream1"
```
- `codec_name=h264` → dùng WebRTC. `hevc` → đổi substream camera sang H.264, nếu không được thì dùng chế độ MJPEG ở frontend.
- Ghi thêm `width/height`: phải là tỉ lệ 16:9 (xem 04 mục 5).
- Nếu server không có `ffprobe`: dùng `cv2.VideoCapture(url).get(cv2.CAP_PROP_FOURCC)` giải mã ra số rồi đổi sang chuỗi, hoặc xem trang cấu hình camera.

## 5. Bước 4 — MediaMTX

1. Tải binary Linux amd64 bản mới nhất (v1.9+) từ https://github.com/bluenviron/mediamtx/releases, giải nén file `mediamtx` vào `poc/mediamtx/`, `chmod +x`.
2. Tạo `poc/mediamtx/mediamtx.yml` mẫu (backend sẽ ghi đè phần `paths` khi lưu camera — xem 03):
```yaml
logLevel: info
api: yes
apiAddress: 127.0.0.1:9997      # Control API cho backend
rtsp: yes
rtspAddress: :8554
protocols: [tcp]
rtmp: no
hls: no
srt: no
webrtc: yes
webrtcAddress: :8889
webrtcLocalUDPAddress: ""        # tắt UDP
webrtcLocalTCPAddress: :8189     # media qua TCP (đi được qua SSH tunnel)
webrtcIPsFromInterfaces: no
webrtcAdditionalHosts: [127.0.0.1]
webrtcAllowOrigin: "*"

paths:
  cam1:
    source: rtsp://user:pass@10.0.0.11:554/stream1
    rtspTransport: tcp
    sourceOnDemand: no
```
3. Chạy thử: `cd poc/mediamtx && ./mediamtx mediamtx.yml`
4. Kiểm tra trên server: `uv run python -c "import cv2;c=cv2.VideoCapture('rtsp://127.0.0.1:8554/cam1');print(c.read()[0])"` → `True`.
5. Kiểm tra trên laptop (đã có tunnel): mở `http://localhost:8889/cam1/` → thấy video.

> Nếu codec camera là **H.265**: WebRTC trên Chrome có thể không phát. Cách xử lý đơn giản nhất: cấu hình camera xuất substream **H.264**. Nếu không đổi được → frontend dùng chế độ fallback MJPEG (file 04, mục 5).

## 6. Bước 5 — Chạy toàn hệ thống (sau khi code xong)

`poc/run.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```
Backend tự khởi động MediaMTX như tiến trình con (xem 03, mục 4) nên chỉ cần chạy `./run.sh`. Để giữ chạy khi tắt Termius: `tmux new -s poc` rồi `./run.sh` (thoát giữ phiên: `Ctrl+B`, `D`).

`poc/.env.example`:
```env
MODEL_PATH=../../models/vehicle_n_best.pt
DEVICE=cuda:0
DEMO_MODE=0
MEDIAMTX_BIN=mediamtx/mediamtx
MEDIAMTX_CONFIG=mediamtx/mediamtx.yml
```

## 7. Chạy trên laptop Windows (tùy chọn, để dev frontend không cần GPU)
- `cd poc/backend; uv venv; uv sync` (torch CPU sẽ tự cài nếu bỏ index CUDA — chấp nhận chậm), đặt `DEVICE=cpu`, tải `mediamtx_windows_amd64.zip`, đặt `MEDIAMTX_BIN=mediamtx/mediamtx.exe`, chạy `uv run uvicorn main:app --port 8080`.
