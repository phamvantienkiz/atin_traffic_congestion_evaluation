# Hướng dẫn Test bằng Video Record giả lập RTSP (trên Server)

Tài liệu này hướng dẫn từng bước cách phát 3 video record trong `record/` thành **2 luồng RTSP giả lập** bằng lệnh trực tiếp (không cần `chmod` hay chạy file `.sh`), **không sửa bất kỳ dòng code nào của backend/AI/RTSP ingestion**.

---

## Kiến trúc luồng chạy

```text
poc/records/*.mp4
   │  (FFmpeg -re -stream_loop -1 -c:v copy -an)
   ▼
MediaMTX phụ (:28555)  ──▶  rtsp://127.0.0.1:28555/pdg
                       ──▶  rtsp://127.0.0.1:28555/hvt
   │
   ▼  (Backend PoC đọc như camera RTSP thật)
MediaMTX chính (:28554) ──▶ StreamReader + WebRTC + AI Engine (uv run uvicorn ...)
```

---

## Bước 1: Pull code mới & Upload video lên Server

1. Trên server, kéo code mới về repo:
   ```bash
   git pull
   ```
   Sau khi pull, thư mục đích **`poc/records/`** sẽ tự động có sẵn (và đã được `.gitignore` để không đẩy nhầm file `.mp4` lên Git).

2. Dùng **Termius SFTP** (hoặc `scp`) tải **3 file** từ thư mục `record/` ở máy local lên đúng thư mục **`poc/records/`** trên server:
   - `poc/records/8phandinhgiot_clip.mp4`
   - `poc/records/tram-xe-buyt-247-duong-hoang-van-thu_clip.mp4`
   - `poc/records/tram-xe-buyt-247-duong-hoang-van-thu_clip_2.mp4`

---

## Bước 2: Kiểm tra `ffmpeg` trên Server

```bash
ffmpeg -version
```
Nếu chưa có:
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

---

## Bước 3: Backup cấu hình camera RTSP thật (Khuyến nghị)

Trước khi đổi URL sang RTSP giả lập, sao lưu lại file `cameras.json` (chứa URL camera thật và Poly Zone cũ):
```bash
cp poc/backend/data/cameras.json poc/backend/data/cameras.real.bak.json
```

---

## Bước 4: Khởi chạy 2 Terminal trên Server (bằng `uv run`, Ctrl+C dừng sạch)

### Terminal 1 — Chạy luồng RTSP giả lập (từ thư mục gốc repo)
```bash
uv run --project poc/backend python poc/tools/fake_rtsp/server.py
```
Khi chạy thành công, script sẽ mở MediaMTX phụ tại port `28555` và phát liên tục (loop vô hạn) 2 luồng:
- **Số 8 Phan Đình Giót:** `rtsp://127.0.0.1:28555/pdg`
- **Trạm xe buýt 247 Hoàng Văn Thụ** (tự động nối `clip.mp4` + `clip_2.mp4`): `rtsp://127.0.0.1:28555/hvt`

Khi muốn dừng, nhấn `Ctrl+C` — toàn bộ `ffmpeg` và `MediaMTX` phụ sẽ tự động tắt sạch, không sót tiến trình nền.

*(Có thể kiểm tra nhanh bằng `ffprobe -rtsp_transport tcp -v error -show_streams rtsp://127.0.0.1:28555/pdg`)*

### Terminal 2 — Chạy PoC Server chính
```bash
cd poc/backend
uv run uvicorn main:app --host 0.0.0.0 --port 28080 --timeout-graceful-shutdown 3
```
*(Đừng quên kiểm tra `poc/.env` đã cập nhật các ngưỡng mới từ `poc/.env.example` nếu bạn muốn test bộ ngưỡng mới).*

---

## Bước 5: Cấu hình Link RTSP Fake trên Web UI

Mở giao diện Web PoC trên trình duyệt (`http://<SERVER_IP>:28080`), vào từng camera để sửa (hoặc thêm mới) trường **RTSP URL**:

| Camera | RTSP URL nhập trên UI | Nguồn video phát |
| :--- | :--- | :--- |
| **1. Bus Hoàng Văn Thụ** | `rtsp://127.0.0.1:28555/hvt` | `tram-xe-buyt-247-duong-hoang-van-thu_clip.mp4` + `_clip_2.mp4` |
| **2. Số 8 Phan Đình Giót** | `rtsp://127.0.0.1:28555/pdg` | `8phandinhgiot_clip.mp4` |

Sau khi lưu:
- Live View WebRTC sẽ hiện hình như camera thật.
- Kiểm tra lại (hoặc vẽ lại) Poly Zone cho khớp khung hình video record.

---

## Bước 6: Cách chuyển ngược lại Camera RTSP thật khi có tín hiệu lại

1. Dừng Terminal 2 (`Ctrl+C`) và Terminal 1 (`Ctrl+C`).
2. Khôi phục file backup camera thật:
   ```bash
   cp poc/backend/data/cameras.real.bak.json poc/backend/data/cameras.json
   ```
   *(Hoặc sửa lại RTSP URL trực tiếp trên Web UI).*
3. Chỉ chạy lại Terminal 2 (`uv run uvicorn main:app --host 0.0.0.0 --port 28080 --timeout-graceful-shutdown 3`), không cần chạy `fake_rtsp/server.py`.

---

## Lưu ý khi quan sát AI trên Video Loop

- Tại khoảnh khắc video kết thúc và quay lại frame đầu tiên, khung cảnh thay đổi đột ngột sẽ khiến ByteTrack reset track cũ sau ~1–2.5s và MOG2 lóe nhẹ chuyển động trong ~1–2s rồi ổn định bình thường.
- Nếu cần chỉ chạy 1 trong 2 luồng để tiết kiệm tài nguyên, chỉ cần giữ file `.mp4` tương ứng trong `poc/records/` (script sẽ tự bỏ qua file thiếu và phát file có sẵn).
