# KẾ HOẠCH KIẾN TRÚC & TRIỂN KHAI DEMO ĐỘC LẬP (MEDIAMTX GATEWAY + SERVER GPU A400 $\leftrightarrow$ LOCAL LAPTOP)
## MODULE ĐÁNH GIÁ TÌNH TRẠNG GIAO THÔNG (TRAFFIC CONGESTION EVALUATION)

> **Mục tiêu Tài liệu:**
> Giải quyết trọn vẹn bài toán thực thi mã nguồn và trình diễn (Show case) trực tiếp trên **Laptop cá nhân (Local)** cho cấp trên xem theo thời gian thực (`4 – 8 luồng RTSP`), áp dụng **Kiến trúc Tách Luồng Chuẩn ATIN (MediaMTX Gateway / Dual-Path Streaming)**:
> 1. **Luồng Xem Video (`Live View Path`):** Tách riêng luồng **WebRTC (`WHEP`) / Low-Latency Stream** từ **MediaMTX Gateway** đưa thẳng lên trình duyệt Web (hoàn toàn độc lập, **không bao giờ bị gián đoạn hay giật lag bởi quá trình chạy AI**, và không phải truyền ngược ảnh JPEG đã vẽ đè nặng nề từ AI về).
> 2. **Luồng Xử lý AI (`AI Processing Path — _detect`):** Chuẩn hóa đúng đầu vào **`720p @ 15 FPS`** đưa vào `poc/ai/` trên **Server GPU NVIDIA RTX A400 4GB** (xử lý đầy đủ **Lõi Phương án 1 + Bổ trợ Phương án 2** với model [`models/vehicle_n_best.pt`](file:///e:/ATIN/traffic_congestion_evaluation/models/vehicle_n_best.pt)), rồi chỉ đẩy **Metadata JSON siêu nhẹ (`~1–2 KB`: tọa độ BBox, Poly Zone, 5 chỉ số & Trạng thái giao thông)** qua WebSocket lên lớp `<canvas>` nằm đè trên video ở trình duyệt!

---

## MỤC LỤC
1. [PHẦN 1: TẠI SAO TÁCH LUỒNG BẰNG MEDIAMTX (WEBRTC + LUỒNG AI 720p@15FPS) LÀ GIẢI PHÁP TỐI ƯU NHẤT?](#phần-1-tại-sao-tách-luồng-bằng-mediamtx-webrtc--luồng-ai-720p15fps-là-giải-pháp-tối-ưu-nhất)
2. [PHẦN 2: KIẾN TRÚC TÁCH LUỒNG CHUẨN ATIN TRÊN SERVER DEV & KẾT NỐI VỀ LAPTOP LOCAL (PHƯƠNG ÁN 1 NÂNG CẤP)](#phần-2-kiến-trúc-tách-luồng-chuẩn-atin-trên-server-dev--kết-nối-về-laptop-local-phương-án-1-nâng-cấp)
3. [PHẦN 3: CẤU HÌNH MEDIAMTX GATEWAY TỰ ĐỘNG TÁCH LUỒNG WEBRTC & LUỒNG `_detect` (`720p @ 15 FPS`)](#phần-3-cấu-hình-mediamtx-gateway-tự-động-tách-luồng-webrtc--luồng-_detect-720p--15-fps)
4. [PHẦN 4: GIẢI PHÁP VẼ TRỰC TIẾP `POLY ZONE` TRÊN LỚP `<canvas>` ĐÈ LÊN VIDEO WEBRTC](#phần-4-giải-pháp-vẽ-trực-tiếp-poly-zone-trên-lớp-canvas-đè-lên-video-webrtc)
5. [PHẦN 5: THIẾT KẾ CHI TIẾT 3 THƯ MỤC `poc/ai/`, `poc/backend/`, `poc/frontend/` & MODEL `vehicle_n_best.pt`](#phần-5-thiết-kế-chi-tiết-3-thư-mục-pocai-pocbackend-pocfrontend--model-vehicle_n_bestpt)
6. [PHẦN 6: QUY TRÌNH VẬN HÀNH & SHOW DEMO TRÊN LAPTOP LOCAL QUA OPENVPN + TERMIUS](#phần-6-quy-trình-vận-hành--show-demo-trên-laptop-local-qua-openvpn--termius)

---

## PHẦN 1: TẠI SAO TÁCH LUỒNG BẰNG MEDIAMTX (WEBRTC + LUỒNG AI 720p@15FPS) LÀ GIẢI PHÁP TỐI ƯU NHẤT?

Lo ngại của bạn hoàn toàn chính xác về mặt kỹ thuật hệ thống:
- **Nhược điểm nếu bắt AI đọc RTSP, vẽ đè BBox lên từng frame ảnh rồi nén MJPEG truyền ngược về Web:**
  1. **Nặng băng thông qua VPN:** Truyền 8 luồng ảnh MJPEG từ Server qua OpenVPN về Laptop tốn tới `25 – 40 Mbps` liên tục, dễ gây nghẽn mạng VPN.
  2. **Ảnh hưởng luồng xem trực tiếp:** Nếu tiến trình Python AI bận xử lý hoặc restart, luồng video trên giao diện Web cũng bị đứng hình theo!
  3. **Sai khác so với môi trường Production của ATIN:** Khi ghép vào hệ thống thật của ATIN, AI **luôn nhận luồng chuẩn hóa `720p @ 15 FPS` (`_detect`) từ MediaMTX**, còn màn hình Web của người dùng **xem luồng WebRTC trực tiếp từ MediaMTX** và chỉ nhận tọa độ BBox/Trạng thái để vẽ đè lên thẻ `<canvas>`.

Do đó, việc **đưa luôn một instance `MediaMTX Gateway` siêu nhẹ (chỉ 1 file binary / 1 container ~20MB RAM) vào kiến trúc Demo trên Server** mang lại **4 lợi ích tuyệt đối**:
1. **Bảo vệ Camera gốc (1 kết nối RTSP duy nhất):** MediaMTX chỉ mở đúng **1 kết nối RTSP** tới camera gốc rồi tự phân phối (restream) ra nhiều nhánh.
2. **Luồng Xem trên Web (`WebRTC / WHEP`) mượt tuyệt đối, không bao giờ bị AI làm gián đoạn:** Trình duyệt trên Laptop của bạn xem video qua chuẩn **WebRTC (hoặc HLS/LL-HLS/MJPEG fallback)** trực tiếp từ MediaMTX ở tốc độ gốc `25–30 FPS`, siêu nhẹ (nén H.264 chỉ tốn `~1–2 Mbps` cho cả 8 cam qua VPN). Kể cả khi bạn tắt/bật lại `poc/ai`, video trên màn hình vẫn chạy mượt không khựng 1 mili-giây!
3. **Luồng AI (`_detect` chuẩn `720p @ 15 FPS`) giống hệt hệ thống thật của ATIN:** Các thuật toán trong `poc/ai` (`ByteTrack`, `Median Travel Time` $T_{50}$, `Active Dwell` $D_{85}$, `Optical Flow` $V_{flow}$ và `Visual Occupancy` $O_{vis}$) được chạy và căn chỉnh trên đúng chuẩn khung hình **`1280x720 @ 15 FPS`**. Khi thắng thầu và đưa vào hệ thống ATIN VMS thật, **bạn bê nguyên 100% bộ code `poc/ai` sang mà không phải sửa lại bất kỳ tham số nào**!
4. **Truyền từ AI về Laptop siêu nhẹ (`~2 KB JSON / frame`):** Server AI không cần encode lại video để gửi về web; nó chỉ gửi tọa độ `BBox + Poly Zone + Trạng thái góc dưới bên phải + 5 chỉ số` qua **WebSocket** về trình duyệt để thẻ `<canvas>` vẽ đè lên trên thẻ `<video>` WebRTC!

---

## PHẦN 2: KIẾN TRÚC TÁCH LUỒNG CHUẨN ATIN TRÊN SERVER DEV & KẾT NỐI VỀ LAPTOP LOCAL (PHƯƠNG ÁN 1 NÂNG CẤP)

```mermaid
flowchart LR
    subgraph Cam_Source ["1. NGUỒN CAMERA RTSP"]
        RTSP["4 - 8 Camera RTSP Raw\n(1080p/720p @ 25-30 FPS)"]
    end

    subgraph Server_GPU ["2. SERVER DEV CÔNG TY (GPU RTX A400 4GB) - CHẠY TRỌN BỘ poc/"]
        MTX["MediaMTX Gateway\n• RTSP Port: 8554\n• WebRTC (WHEP) Port: 8889\nTự động tách 2 luồng từ 1 nguồn RTSP"]
        
        subgraph AI_Sub ["Phân hệ poc/ai/ (GPU A400)"]
            AI_IN["Đọc luồng _detect\n(Chuẩn hóa 720p @ 15 FPS, Buffer=1)"]
            AI_CORE["Core Pipeline (Phương án 1: YOLO + ByteTrack + T50/D85)\n+ Aux Pipeline (Phương án 2: Optical Flow + MOG2 O_vis)"]
            AI_IN --> AI_CORE
        end

        subgraph BE_Sub ["Phân hệ poc/backend/ (FastAPI :8080)"]
            API["FastAPI Orchestrator & WebSocket Hub\n- Đăng ký URL RTSP vào MediaMTX\n- Lưu cấu hình Poly Zone (zones_config.json)\n- Phát WebSocket JSON (BBox + HUD + Trạng thái)\n- Lưu Snapshot khi Confirmed Event"]
        end

        MTX == "Nhánh 1: Luồng phụ _detect\n(720p @ 15 FPS nội bộ localhost)" ==> AI_IN
        AI_CORE == "Kết quả JSON (BBox + 5 chỉ số + State)" ==> API
        API -. "API thêm/xóa stream" .-> MTX
    end

    subgraph Laptop_Local ["3. LAPTOP LOCAL CỦA BẠN (MỞ TRÌNH DUYỆT XEM REAL-TIME)"]
        subgraph Browser ["Giao diện poc/frontend/ (http://localhost:8080)"]
            VID["Lớp dưới: Thẻ <video> nhận luồng WebRTC (WHEP)\n(Video gốc mượt 100%, không bị AI làm gián đoạn)"]
            CAN["Lớp trên: Thẻ <canvas> trong suốt đè khít lên <video>\n(Vẽ Poly Zone + BBox + Badge Trạng thái Góc Dưới Phải\n+ Cho phép Click chuột vẽ Poly Zone trực tiếp)"]
        end
    end

    RTSP == "1 Kết nối RTSP duy nhất" ==> MTX
    MTX == "Nhánh 2: Luồng WebRTC H.264\n(Siêu nhẹ ~1.5 Mbps cho 8 cam)" ==> VID
    API == "WebSocket JSON (~2KB/tin)\n(Tọa độ chuẩn hóa [0..1] + Trạng thái)" ==> CAN
```

### Điểm đắt giá của Kiến trúc này:
- **Tất cả tọa độ đều chuẩn hóa về `[0.0 .. 1.0]`:**
  - Dù luồng WebRTC hiển thị trên trình duyệt ở độ phân giải gốc (`1080p` hoặc `720p`) và luồng đưa vào AI xử lý cố định ở **`720p @ 15 FPS`**, mọi tọa độ `Poly Zone` và `BBox [x1, y1, x2, y2]` đều dùng hệ tọa độ tỷ lệ phần trăm **`[0.0 .. 1.0]`**.
  - Vì vậy, khung BBox và vùng đa giác `Poly Zone` vẽ trên lớp `<canvas>` ở trình duyệt **luôn khớp khít 100% với chiếc xe trên thẻ `<video>` WebRTC** bất kể kích thước màn hình!

---

## PHẦN 3: CẤU HÌNH MEDIAMTX GATEWAY TỰ ĐỘNG TÁCH LUỒNG WEBRTC & LUỒNG `_detect` (`720p @ 15 FPS`)

Chúng ta có **2 cách cực kỳ gọn** để đảm bảo luồng đưa vào AI luôn đúng chuẩn **`720p @ 15 FPS`** mà không làm ảnh hưởng luồng WebRTC xem trực tiếp:

### Cách 1 (Chuẩn Kiến trúc ATIN): MediaMTX nhận RTSP gốc $\rightarrow$ Phát WebRTC trực tiếp + Tạo nhánh `_detect` (`720p @ 15 FPS`)
Trong thư mục `poc/` sẽ có sẵn file `mediamtx.yml` (chạy bằng 1 container Docker `bluenviron/mediamtx:latest` hoặc 1 file binary duy nhất trên Server):
- Khi bạn nhập URL RTSP của Camera số $i$ (ví dụ `cam_1`), MediaMTX lập tức cung cấp:
  1. **Đường dẫn WebRTC (`WHEP`) cho trình duyệt Web:** `http://<server>:8889/cam_1/whep` (Zero-transcode, lấy nguyên gói H.264 từ camera đẩy thẳng lên thẻ `<video>` trên trình duyệt với độ trễ `< 200ms`).
  2. **Đường dẫn RTSP cho AI (`rtsp://127.0.0.1:8554/cam_1_detect` hoặc đọc từ `rtsp://127.0.0.1:8554/cam_1` kèm bộ chuẩn hóa `720p @ 15 FPS`):**
     - Để tiết kiệm tối đa CPU cho Server (không bắt FFmpeg phải encode lại H.264 một lần nữa rồi Python lại decode ra), **AI Reader (`poc/ai/ingestion/stream_reader.py`)** kết nối vào `rtsp://127.0.0.1:8554/cam_1` của MediaMTX, giải mã phần cứng và **ép bộ lấy mẫu đúng `1280x720 @ 15.0 FPS` (`dt = 66.7ms`)** ngay tại cổng vào của Pipeline AI (hoặc dùng hook `runOnReady` của MediaMTX để tạo đúng stream `cam_1_detect` `720p @ 15 FPS` nếu luồng gốc là 4K/2K nặng).

### Cách 2 (Chế độ Fallback Tự động Không Cần Cài MediaMTX khi Test Nhanh):
- Nếu ở thời điểm nào đó trên Server chưa bật Docker MediaMTX, `poc/backend` vẫn có sẵn **Chế độ Dual-Stream Nội bộ**:
  - Luồng 1 phát video raw không bị chặn về trình duyệt.
  - Luồng 2 chuẩn hóa `720p @ 15 FPS` đưa sang `poc/ai` xử lý độc lập trên thread riêng và bắn kết quả JSON qua WebSocket lên `<canvas>`.
- Như vậy, hệ thống **vừa chạy được chuẩn MediaMTX WebRTC + `720p@15FPS`**, vừa có cơ chế tự động fallback không bao giờ sợ lỗi môi trường khi demo!

---

## PHẦN 4: GIẢI PHÁP VẼ TRỰC TIẾP `POLY ZONE` TRÊN LỚP `<canvas>` ĐÈ LÊN VIDEO WEBRTC

Vì luồng video WebRTC hiển thị ở lớp `<video>` bên dưới và lớp `<canvas>` nằm chồng khít lên trên (với `position: absolute; inset: 0;`), bạn sẽ có công cụ **Vẽ `Poly Zone` Trực Tiếp Trên Video Đang Chạy** mà không cần cap ảnh đem lên Roboflow:

1. **Cách thao tác ngay trên giao diện Demo:**
   - Bấm nút **"✏️ Vẽ Zone"** trên thanh công cụ của Camera.
   - Nhìn vạch kẻ đứt phân làn trên mặt đường trong video, **click chuột 4 điểm** tạo thành đa giác phủ ngang mặt đường với chiều dọc ước lượng **`2 vạch sơn + 2 khoảng trống` (`~12 – 16 mét`)**.
   - Bấm **"💾 Lưu Zone"**: Tọa độ chuẩn hóa `[{"x": 0.12, "y": 0.35}, ...]` được gửi về `poc/backend`, lưu cứng vào file `poc/backend/data/zones_config.json` và đồng bộ tức thời sang `poc/ai`!
2. **Hỗ trợ thêm Nút "📷 Cap ảnh 720p" & "📋 Dán JSON Roboflow":**
   - Nếu bạn vẫn muốn chụp ảnh ra để đem lên Roboflow vẽ hoặc lưu làm tài liệu báo cáo, trên mỗi ô camera có sẵn nút **"📷 Cap ảnh"** (tải ngay ảnh chuẩn `1280x720` về máy) và nút **"📋 Import JSON"** (chấp nhận cả định dạng mảng điểm `[{x, y}]` lẫn định dạng Polygon của Roboflow).

---

## PHẦN 5: THIẾT KẾ CHI TIẾT 3 THƯ MỤC `poc/ai/`, `poc/backend/`, `poc/frontend/` & MODEL `vehicle_n_best.pt`

Toàn bộ mã nguồn triển khai được đặt gọn gàng trong 3 thư mục của [poc/](file:///e:/ATIN/traffic_congestion_evaluation/poc) như sau:

```text
poc/
├── docker-compose.yml                # Khởi chạy MediaMTX Gateway (RTSP 8554 + WebRTC 8889)
├── mediamtx.yml                      # Cấu hình MediaMTX restream & tách luồng chuẩn ATIN
├── implement/
│   └── deployment-and-demo-plan.md   # Tài liệu kiến trúc & kế hoạch triển khai này
│
├── ai/                               # 1. PHÂN HỆ AI ENGINE (NHẬN LUỒNG 720p @ 15 FPS TRÊN GPU A400)
│   ├── engine_manager.py             # Quản lý 4-8 luồng AI Worker chạy độc lập ở chuẩn 720p @ 15 FPS
│   ├── config.py                     # Ngưỡng Core Solution (T50, D85, O_vis, V_flow, W_total)
│   ├── core_pipeline/                # PHƯƠNG ÁN 1 (LÕI XỬ LÝ CHÍNH)
│   │   ├── detector.py               # Load models/vehicle_n_best.pt (hoặc yolo26s.pt) với FP16/TensorRT
│   │   ├── bytetrack_tracker.py      # ByteTrack (Bottom-Center, Buffer 2.5s @ 15FPS, Majority Class Voting)
│   │   └── zone_time_analyzer.py     # Tính W_total, Median Travel Time (T50) & Active Dwell (D85)
│   ├── aux_pipeline/                 # PHƯƠNG ÁN 2 (TÍN HIỆU BỔ TRỢ)
│   │   └── macro_flow_occupancy.py   # MOG2 (O_vis % + Freeze/Unfreeze) & Farnebäck Optical Flow (V_flow)
│   └── decision/
│       ├── occlusion_shield.py       # Chống che khuất Xe Bus (BBox > 35% hoặc Tụt BBox + O_vis > 70%)
│       └── state_machine.py          # Hợp nhất 5 chỉ số -> CLEAR | CONGESTED | GRIDLOCKED + Event Timer
│
├── backend/                          # 2. PHÂN HỆ BACKEND ORCHESTRATOR (FASTAPI :8080)
│   ├── main.py                       # FastAPI Server:
│   │                                 # - Đăng ký luồng RTSP vào MediaMTX & khởi chạy AI Worker (720p@15FPS)
│   │                                 # - Phát WebSocket (/ws/ai-metadata) đẩy BBox + PolyZone + Trạng thái
│   │                                 # - API lưu/đọc Poly Zone, chụp ảnh 720p & danh sách Sự kiện Cảnh báo
│   ├── mediamtx_bridge.py            # Giao tiếp với MediaMTX Control API để quản lý luồng RTSP/WebRTC
│   └── data/
│       ├── zones_config.json         # Lưu tự động URL RTSP + Tọa độ Poly Zone của từng camera
│       └── snapshots/                # Lưu ảnh chụp minh chứng khi xác nhận Ùn tắc / Kẹt xe
│
└── frontend/                         # 3. PHÂN HỆ GIAO DIỆN WEB DEMO (HTML5 + CSS + VANILLA JS)
    ├── index.html                    # Giao diện Soft Clean Cards (4/6/8 Cam) + WebRTC Player + Canvas Overlay
    ├── styles.css                    # Style chuẩn + Badge Trạng thái Góc Dưới Phải + Khung Sự kiện
    └── app.js                        # - Kết nối WebRTC (WHEP) từ MediaMTX (hoặc fallback stream)
                                      # - Nhận WebSocket JSON vẽ BBox + Poly Zone + HUD thời gian thực
                                      # - Công cụ click chuột vẽ Poly Zone trực tiếp trên video
```

### Chiến lược sử dụng Model [`models/vehicle_n_best.pt`](file:///e:/ATIN/traffic_congestion_evaluation/models/vehicle_n_best.pt) & Dự phòng `yolo26s.pt`:
- Mặc định `poc/ai/core_pipeline/detector.py` load trực tiếp [`models/vehicle_n_best.pt`](file:///e:/ATIN/traffic_congestion_evaluation/models/vehicle_n_best.pt) với chế độ `FP16 (half=True)` trên GPU RTX A400 4GB (và hỗ trợ xuất sang TensorRT `.engine`).
- Nếu cần thử nghiệm đối chiếu với `yolo26s.pt` (hoặc bất kỳ model YOLO nào khác), bạn chỉ cần đổi tên file weight trong `poc/ai/config.py` (hoặc chọn trên giao diện Web), bộ ánh xạ lớp (`Class Mapper`) sẽ tự động gom đúng nhóm **Xe 2 bánh (`2W`)** và **Xe 4 bánh (`4W`)**.

---

## PHẦN 6: QUY TRÌNH VẬN HÀNH & SHOW DEMO TRÊN LAPTOP LOCAL QUA OPENVPN + TERMIUS

### 1. Khi Kết nối Mạng Công ty qua OpenVPN (Hỗ trợ WebRTC & WebSocket mượt 100%)
Bởi vì Laptop của bạn đã bật **OpenVPN Connect** vào mạng nội bộ công ty (nơi đặt Server GPU A400), Laptop của bạn có thể nhìn thấy trực tiếp IP nội bộ của Server (ví dụ `10.8.0.x` hoặc `192.168.x.x`):
- **Trường hợp 1 (Mạng VPN mở thông port nội bộ giữa Laptop và Server):**
  - Bạn chỉ cần mở trình duyệt trên Laptop truy cập thẳng `http://<IP_SERVER_TRONG_VPN>:8080`.
  - Lúc này trình duyệt nhận luồng **WebRTC (`UDP/TCP` port `8889`)** từ MediaMTX và **WebSocket JSON (port `8080`)** từ FastAPI cực nhanh mà không cần cấu hình gì thêm!
- **Trường hợp 2 (Server bật Firewall chặn các port phụ, chỉ cho phép SSH port 22 qua Termius):**
  - Trong **Termius**, bạn bật **Local Port Forwarding** cho 2 cổng TCP (`8080` cho Web/WebSocket và `8889` + `8189` cho MediaMTX WebRTC over TCP):
    ```bash
    ssh -L 8080:127.0.0.1:8080 -L 8889:127.0.0.1:8889 -L 8189:127.0.0.1:8189 user@<IP_SERVER>
    ```
  - Trong file `mediamtx.yml`, chúng ta bật sẵn `webrtcICEHostNAT1To1IPs: [127.0.0.1]` và `webrtcLocalTCPAddress: :8189` (ép WebRTC truyền qua kênh TCP `8189` hoặc tự động chuyển sang luồng Low-Latency Stream qua cổng `8080`). Nhờ đó, dù đi qua SSH Tunnel thì video vẫn lên hình 100% mà không bao giờ bị lỗi chặn UDP của WebRTC!

### 2. Trải nghiệm Khi Show Giải pháp cho Cấp trên trên Laptop Local
1. Mở trình duyệt trên Laptop tại **`http://localhost:8080`**.
2. Chọn chế độ xem **4 Cameras**, **6 Cameras** hoặc **8 Cameras**.
3. Luồng video gốc chạy qua **MediaMTX WebRTC** mượt mà ở lớp `<video>`, hoàn toàn không bị gián đoạn.
4. Phía dưới nền, **GPU RTX A400** xử lý luồng **`720p @ 15 FPS`** cho cả 8 camera và bắn tọa độ JSON qua WebSocket lên lớp `<canvas>`:
   - Hiển thị **Poly Zone** đổi màu theo trạng thái (`Xanh` / `Vàng` / `Đỏ`).
   - Hiển thị **BBox + Track ID + Nhãn (`2B` / `4B`)** mượt mà.
   - Hiển thị **Badge Trạng thái giao thông (`THÔNG THOÁNG` | `ĐƯỜNG ÙN TẮC` | `KẸT XE`)** ngay ở **góc dưới bên phải** của từng ô camera (`delay <= 2–5s`).
   - Hiển thị đầy đủ 5 chỉ số thực tế của **Phương án 1 Lõi (`W_total`, `Median T50`, `Active Dwell D85`)** và **Phương án 2 Bổ trợ (`Độ phủ O_vis %`, `Flow Speed V_flow`)** cùng danh sách **Notification / Ảnh chụp Snapshot sự kiện**!
