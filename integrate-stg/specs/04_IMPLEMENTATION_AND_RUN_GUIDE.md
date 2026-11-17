# HƯỚNG DẪN THAO TÁC TRÊN SERVER `aiot` QUA TERMIUS (TÍCH HỢP STAGING)

> **Áp dụng cho:** Server GPU PoC **`aiot`** (Ubuntu 22.04.5 LTS, NVIDIA RTX A400 4GB, user `tts`, IP `192.168.1.170`), thư mục dự án **`~/projects/tien/atin_traffic_congestion_evaluation`**.
>
> **Nguyên tắc:** Toàn bộ mã nguồn mới nằm trong `integrate-stg/`, gọi trực tiếp lõi AI từ `poc/backend/ai/` và dùng chung môi trường ảo `poc/backend/.venv` (`uv`) + model `models/vehicle_n_best.pt` đã có sẵn trên server.

---

## Tổng Quan Luồng Chạy Trên Server `aiot`

- **Không cần mở thêm Port Forwarding trên Termius** cho Staging (vì kết nối từ server `aiot` lên `aioc-stg.atin.vn:443` là kết nối đi ra Internet, còn bạn xem kết quả trực tiếp trên trình duyệt tại **`https://aioc-stg.atin.vn/`**).
- **Lưu ý VRAM RTX A400 (4 GB):** Nếu server đang chạy phiên `tmux` của PoC (`poc`), nên kiểm tra `nvidia-smi` hoặc tạm dừng phiên `poc` (`tmux kill-session -t poc`) trước khi chạy Staging nếu muốn dành toàn bộ VRAM cho test Staging.

---

## Bước 1: Đẩy Code Mới Lên Git (Trên Máy Cá Nhân)

Từ máy cá nhân (`E:\ATIN\traffic_congestion_evaluation`), kiểm tra `git status` (đảm bảo không dính `.env`, `.venv`, `models/`), rồi commit và push lên repo để server `aiot` kéo về:

```powershell
git status
git add integrate-stg
git commit -m "feat(stg): add AIOC staging integration adapter and specs"
git push
```

---

## Bước 2: SSH Vào Server `aiot` Bằng Termius & Kéo Code Về

1. Bật **OpenVPN Connect** trên laptop.
2. Mở **Termius**, SSH vào `tts@192.168.1.170`.
3. Kéo code mới về và thoát môi trường conda `(base)` (nếu đang bật):

```bash
conda deactivate 2>/dev/null || true
cd ~/projects/tien/atin_traffic_congestion_evaluation
git pull
```

---

## Bước 3: Cài Thư Viện Bổ Sung Vào `poc/backend/.venv`

Trên server `aiot` đã có sẵn `uv` và `poc/backend/.venv` (PyTorch CUDA, Ultralytics, OpenCV). Chỉ cần cài thêm `paho-mqtt` và `requests` vào đúng `.venv` đó:

```bash
cd ~/projects/tien/atin_traffic_congestion_evaluation
uv pip install --python poc/backend/.venv/bin/python -r integrate-stg/requirements.txt
```

Kiểm tra nhanh model và GPU vẫn OK:

```bash
ls -lh models/vehicle_n_best.pt
poc/backend/.venv/bin/python -c "import paho.mqtt.client, torch; print('MQTT OK | CUDA:', torch.cuda.is_available())"
```

---

## Bước 4: Tạo & Cấu Hình `integrate-stg/.env`

```bash
cd ~/projects/tien/atin_traffic_congestion_evaluation/integrate-stg
cp .env.example .env
nano .env
```

Kiểm tra/chỉnh các dòng sau trong `integrate-stg/.env` (giữ nguyên các thông số AI V2 còn lại):

```ini
MQTT_HOST=aioc-stg.atin.vn
MQTT_PORT=443
MQTT_WS_PATH=/mqtt
MQTT_USER=atin
MQTT_PASS=Atin@2026#
MQTT_CLIENT_ID=ai_edge_congestion_junction_01

TARGET_CAMERA_CODE=camera_junction
FALLBACK_RTSP_URL=rtsp://192.168.1.198:28537/tshtest

BBOX_AI_MODULE=PLATE
EVENT_PUBLISH_MODE=NONE
MODEL_PATH=models/vehicle_n_best.pt
DEVICE=cuda:0
FORCE_LOCAL_ROI=false
FALLBACK_ROI_POINTS=[{"x":0.0247,"y":0.5172},{"x":0.4374,"y":0.3009},{"x":0.8836,"y":0.3574},{"x":0.9065,"y":0.884}]
```

> **Lưu ý về Polyzone (`FORCE_LOCAL_ROI=false`):** Mặc định worker sẽ nhận `ai_zones` hot-reload từ Web STG (khi bạn xóa vùng cũ trên Web STG, trong lúc chưa kịp vẽ lại thì worker tự dùng `FALLBACK_ROI_POINTS`; ngay khi bạn vẽ lại vùng mới trên Web STG thì worker tự cập nhật theo vùng mới). Nếu muốn tạm khóa dùng cứng vùng local thì đổi `FORCE_LOCAL_ROI=true`.

Lưu và thoát `nano`: bấm `Ctrl + O` $\rightarrow$ `Enter` $\rightarrow$ `Ctrl + X`.

---

## Bước 5: Chạy Probe Lấy Thông Tin `camera_junction` Từ Staging

```bash
cd ~/projects/tien/atin_traffic_congestion_evaluation
poc/backend/.venv/bin/python integrate-stg/scripts/step1_probe_camera.py
```

**Đọc kết quả in ra màn hình (và trong `integrate-stg/scripts/probe_result.json`):**

1. Lấy 3 giá trị thực tế của `camera_junction`:
   - `id` (UUID) $\rightarrow$ điền vào `TARGET_CAMERA_ID=...`
   - `org_id` $\rightarrow$ điền vào `ORGANIZATION_ID=...`
   - `zone_id` $\rightarrow$ điền vào `ZONE_ID=...`
2. Kiểm tra dòng **`[WARNING - EXISTING BBOX TRAFFIC]`**:
   - Nếu **không thấy dòng cảnh báo này** (`[OK] Không có worker khác đang bắn BBox...`): có thể chạy đè BBox/HUD lên module `PLATE` thoải mái.
   - Nếu **có worker khác đang bắn**: ghi nhận lại để tránh đụng khung hình trên Web.
3. Kiểm tra dòng **`[RTSP OK]`**: xác nhận server `aiot` đọc được frame từ MediaMTX (`192.168.1.250:18554/...`) hoặc `rtsp://192.168.1.198:28537/tshtest`.

Sau đó mở lại `integrate-stg/.env` để điền `TARGET_CAMERA_ID`, `ORGANIZATION_ID`, `ZONE_ID` vừa tìm được:

```bash
nano ~/projects/tien/atin_traffic_congestion_evaluation/integrate-stg/.env
```

---

## Bước 6: Smoke Test Hiển Thị Trên Web `https://aioc-stg.atin.vn/`

Chạy script test bắn BBox + HUD giả lập trong 10 giây và upload ảnh snapshot:

```bash
cd ~/projects/tien/atin_traffic_congestion_evaluation
poc/backend/.venv/bin/python integrate-stg/scripts/step2_smoke_test.py
```

Ngay trong lúc terminal chạy 10 giây, mở trình duyệt trên laptop vào **`https://aioc-stg.atin.vn/monitoring`**:
1. Chọn hiển thị **Junction Camera** (`camera_junction`).
2. Bật nút **Phát hiện AI**.
3. Ở góc ô video, chọn dropdown **"AI: ..."** là **Giám sát phương tiện (`PLATE`)**.
4. Xác nhận thấy khung chữ nhật `car 0.92` + dòng chữ HUD màu vàng cam **`SMOKE TEST: CONGESTED...`** hiện trên video.
5. Copy link `[VERIFY URL]` ở terminal dán vào trình duyệt để xác nhận ảnh upload lên MinIO Staging xem được bình thường.

*(Nếu muốn test bắn kèm 1 sự kiện tạm qua `PLATE`, đặt `EVENT_PUBLISH_MODE=PLATE` trong `.env` và thêm cờ `--publish-event`.)*

---

## Bước 7: Chạy Chính Thức Trong `tmux` Trên Server `aiot`

Tạo phiên `tmux` riêng tên `stg` để chạy ngầm 24/7 (không bị tắt khi đóng Termius):

```bash
tmux new -s stg
cd ~/projects/tien/atin_traffic_congestion_evaluation/integrate-stg
../poc/backend/.venv/bin/python -m src.main
```

**Quan sát log chuẩn:**
```text
[INFO] main: [ORCHESTRATOR] Kết nối MQTT aioc-stg.atin.vn:443 ...
[INFO] main: [MQTT CONNECTED] rc=0 -> Subscribing camera & zone topics (C01)...
[INFO] main: [C02] Camera 'camera_junction' (id=..., org=...) đã bật PLATE -> Khởi tạo Worker...
[INFO] main: [STATS cam=camera_junction] state=CLEAR | FPS=15.0 | Infer=16.5ms | BBoxSent=50 | EvLogged=0 | EvPub=0
```

- **Thoát `tmux` nhưng vẫn giữ chạy ngầm:** bấm **`Ctrl + B`**, thả tay, rồi bấm **`D`**.
- **Xem lại log sau khi đóng/mở lại Termius:**
  ```bash
  tmux attach -t stg
  ```
- **Theo dõi GPU RTX A400:**
  ```bash
  watch -n 2 nvidia-smi
  ```

---

## Bước 8: Điều Chỉnh Chế Độ Sự Kiện & Dọn Dẹp Khi Test Xong

### Chuyển đổi chế độ gửi Sự kiện (`EVENT_PUBLISH_MODE` trong `integrate-stg/.env`)
- `EVENT_PUBLISH_MODE=NONE` *(mặc định)*: Chỉ hiện **BBox + HUD** realtime lên Web Staging, sự kiện xác nhận chỉ ghi log trong `tmux` (`[CONFIRMED EVENT]`).
- `EVENT_PUBLISH_MODE=PLATE`: Upload ảnh + gửi sự kiện xác nhận tạm vào kênh `PLATE`.
- `EVENT_PUBLISH_MODE=ZONE` hoặc `CROWD_DETECTION`: Chỉ dùng sau khi đã bật thêm module tương ứng cho `camera_junction` trên Web STG (nhớ chờ 60 giây đồng bộ cache).
- Khi cần test nhanh sự kiện xác nhận (rút ngắn ngưỡng 3 phút xuống 30 giây), đặt `DEMO_MODE=1` trong `integrate-stg/.env` rồi khởi động lại worker.

### Dừng phiên Staging khi test xong
```bash
tmux kill-session -t stg
nvidia-smi
```
