# Changelog Cập Nhật Ngưỡng & Logic AI Pipeline

> Tài liệu ghi nhận theo ngày các thay đổi về logic xử lý và bộ ngưỡng trong mã nguồn thực tế, phục vụ đối chiếu và cập nhật ngược lại các tài liệu thiết kế/báo cáo trong `poc/implement/`.

---

## [16/11/2026] Hiệu chỉnh ngưỡng cho Poly Zone mở rộng & tách `flow_zone_px`

- **Commit tham chiếu:** `e14cb45b19c40403ba98aaff218c11c0b5575713` (`2026-11-16 10:32:40 +0700`)
- **Commit message:** `poc: calibrate thresholds for expanded zone and extend flow/occupancy zone longitudinally`
- **Phạm vi file thay đổi:**
  - [poc/.env.example](file:///E:/ATIN/traffic_congestion_evaluation/poc/.env.example)
  - [poc/backend/ai/config.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/config.py)
  - [poc/backend/ai/geometry.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/geometry.py)
  - [poc/backend/ai/engine/camera_processor.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/engine/camera_processor.py)
  - [poc/backend/ai/tests/test_geometry.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/tests/test_geometry.py)

---

## 1. Thay đổi về Logic AI Pipeline

### 1.1. Tách vùng đo Phương án 2 (`flow_zone_px`) mở rộng dọc trục đường

Trước ngày 16/11/2026, cả Phương án 1 (`ZoneTimeAnalyzer`), Phương án 2 (`FlowOccupancy`), `OcclusionShield` và vùng cắt YOLO (`self.roi`) đều dùng chung một đa giác `self.zone_px`.

Từ commit `e14cb45`:
1. **Hàm mới [`extend_zone_longitudinal`](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/geometry.py#L69-L97):**
   - Xác định trục dọc của Poly Zone từ trung điểm 2 đỉnh trên (`top_mid`) đến trung điểm 2 đỉnh dưới (`bot_mid`).
   - Chiếu các đỉnh lên vector đơn vị trục đường `unit` và chỉ kéo giãn thành phần dọc trục ở cả hai đầu thêm `ratio` (mặc định `0.20` = **+20% đầu trên & +20% đầu dưới**, tổng chiều dài dọc trục tăng lên `1.4x`).
   - **Giữ nguyên hoàn toàn bề ngang 2 bên** (không phình sang lề đường/vỉa hè) và clamp tọa độ trong `[0, w - 1] × [0, h - 1]`.
   - Nếu `ratio <= 0.0` hoặc `zone_px` không hợp lệ thì trả về nguyên `zone_px`.
2. **Tham số cấu hình mới trong [`AIConfig`](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/config.py#L93):**
   - `flow_zone_extend_ratio: float` đọc từ biến môi trường `FLOW_ZONE_EXTEND_RATIO` (mặc định `0.20`).
3. **Phân tách vùng sử dụng trong [`CameraProcessor`](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/engine/camera_processor.py#L72-L125):**
   - `self.zone_px` (Poly Zone gốc người dùng vẽ): dùng cho **`ZoneTimeAnalyzer`** (`W_total`, `T50`, `D85`) và **`OcclusionShield`**.
   - `self.flow_zone_px` (Poly Zone mở rộng dọc trục): dùng cho **`FlowOccupancy`** (`O_vis`, `V_flow`), danh sách **`in_zone_boxes`** truyền vào `FlowOccupancy.update()`, và **`self.roi`** (vùng cắt khung hình chạy YOLO để phát hiện được cả xe ở 2 đầu mở rộng).
4. **Unit test bổ sung:**
   - [`test_extend_zone_longitudinal_preserves_width_and_extends_axis`](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/tests/test_geometry.py#L66-L78) trong `poc/backend/ai/tests/test_geometry.py`.

---

## 2. Thay đổi về Bộ Ngưỡng (`.env.example`)

Bối cảnh hiệu chỉnh: giảm cảnh báo `CONGESTED` giả trên thực tế và đồng bộ cho cấu hình Poly Zone mở rộng (~18–22m dọc đường).

> **Lưu ý khi đối chiếu code:** Giá trị fallback mặc định trong [`AIConfig`](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/config.py#L84-L125) (khi chạy không có `.env`) vẫn giữ bộ cũ; bộ ngưỡng mới được khai báo trong [`poc/.env.example`](file:///E:/ATIN/traffic_congestion_evaluation/poc/.env.example#L40-L115) để copy sang `.env` vận hành.

### Bảng đối chiếu thông số thay đổi

| Biến `.env` | Trước (`ab55f20`) / Fallback `AIConfig` | Mới (`poc/.env.example` - `e14cb45`) | Nhóm / Ghi chú |
| :--- | :---: | :---: | :--- |
| `FLOW_ZONE_EXTEND_RATIO` | *(chưa có)* | `0.20` | Mở rộng vùng đo `O_vis` / `V_flow` +20% mỗi đầu |
| `ZONE_MIN_DWELL_S` | `1.5` | `2.0` | Thời gian lưu tối thiểu (s) để tính `D85` |
| `W_CLEAR` | `12.0` | `18.0` | Ngưỡng mật độ vùng `CLEAR` |
| `O_CLEAR` | `0.35` | `0.40` | Ngưỡng độ phủ vùng `CLEAR` |
| `W_CONGESTED` | `15.0` | `25.0` | Ngưỡng mật độ `CONGESTED` |
| `O_CONGESTED` | `0.45` | `0.55` | Ngưỡng độ phủ `CONGESTED` |
| `W_GRIDLOCK` | `24.0` | `38.0` | Ngưỡng mật độ `GRIDLOCKED` |
| `O_GRIDLOCK` | `0.65` | `0.72` | Ngưỡng độ phủ `GRIDLOCKED` |
| `O_MACRO_STALL` | `0.70` | `0.75` | Độ phủ dự phòng nhánh `GRIDLOCKED` |
| `W_RESCUE` | `18.0` | `28.0` | Ngưỡng mật độ Macro Rescue (`>= W_CONGESTED`) |
| `O_RESCUE` | `0.75` | `0.80` | Ngưỡng độ phủ Macro Rescue |
| `CONGESTED_T50_4W_S` | `3.0` | `5.0` | `T50` xe 4B cho `CONGESTED` (s) |
| `CONGESTED_D85_4W_S` | `5.0` | `7.5` | `D85` xe 4B cho `CONGESTED` (s) |
| `CONGESTED_T50_2W_S` | `3.0` | `4.5` | `T50` xe 2B cho `CONGESTED` (s) |
| `CONGESTED_D85_2W_S` | `4.5` | `7.0` | `D85` xe 2B cho `CONGESTED` (s) |
| `GRIDLOCK_T50_4W_S` | `7.0` | `9.0` | `T50` xe 4B cho `GRIDLOCKED` (s) |
| `GRIDLOCK_D85_4W_S` | `10.0` | `14.0` | `D85` xe 4B cho `GRIDLOCKED` (s) |
| `GRIDLOCK_T50_2W_S` | `5.0` | `7.5` | `T50` xe 2B cho `GRIDLOCKED` (s) |
| `GRIDLOCK_D85_2W_S` | `8.0` | `12.0` | `D85` xe 2B cho `GRIDLOCKED` (s) |
| `GRIDLOCK_T50_2W_ONLY_S` | `5.5` | `8.5` | `T50` thuần xe máy (`n_4w < 2`) (s) |
| `GRIDLOCK_D85_2W_ONLY_S` | `8.5` | `13.0` | `D85` thuần xe máy (`n_4w < 2`) (s) |
| `HEAVY_AREA_RATIO` | `0.35` | `0.45` | Tỷ lệ diện tích xe buýt/tải che zone kích `HOLD` |
| `BBOX_DROP_RATIO` | `0.60` | `0.65` | Tỷ lệ tụt bbox đột ngột kích `HOLD` |
| `OCC_O_VIS` | `0.70` | `0.72` | Ngưỡng `O_vis` đi kèm tụt bbox |
| `OCC_HOLD_MAX_S` | `30.0` | `40.0` | Thời gian giữ `HOLD` tối đa trước khi về `UNKNOWN` (s) |

### Ghi chú bổ sung về State Machine (giữ nguyên logic, làm rõ trong `.env.example`)
- `CONFIRM_CONGESTED_S`, `CONFIRM_CONGESTED_LIGHT_S`, `CONFIRM_GRIDLOCK_S` vẫn để comment trong `.env.example` để tự nhận theo `DEMO_MODE`:
  - `DEMO_MODE=0`: `60s` (`CONGESTED`), `90s` (`CONGESTED` có đèn giao thông), `120s` (`GRIDLOCKED`).
  - `DEMO_MODE=1`: `15s` / `20s` / `30s`.

---

## 3. Danh sách tài liệu cần đối chiếu & cập nhật lại sau này

Khi đồng bộ ngược tài liệu trong `poc/implement/`, cần kiểm tra và cập nhật các mục liên quan tại:
- [poc/implement/00-overview-and-decisions.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/00-overview-and-decisions.md)
- [poc/implement/02-ai-pipeline.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/02-ai-pipeline.md) (mô tả ROI / `flow_zone_px` tách khỏi `zone_px` và bảng ngưỡng mới)
- [poc/implement/06-implementation-report.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/06-implementation-report.md)
- [poc/implement/thredsold.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/thredsold.md)
- [poc/implement/show/index.html](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/show/index.html) (nếu cần đồng bộ số ngưỡng minh họa trên slide)


---

## [16/11/2026 — Bản Cập Nhật Đặc Tả V2] Loại bỏ ngưỡng cứng `W`, Chốt Bộ Ngưỡng V2 (`O_vis 40%/70%/85%`, `Flow`, `T50/D85`), Điểm Tự Tin `state_conf` & Chu Kỳ Sự Kiện (`3p → +2p (5p) → mỗi +15p`)

- **Tài liệu phân tích & đặc tả tham chiếu:**
  - [poc/implement/09-parameter-and-system-evaluation.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/09-parameter-and-system-evaluation.md)
  - [poc/implement/10-threshold-and-event-lifecycle-spec.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/10-threshold-and-event-lifecycle-spec.md)
  - [poc/implement/thredsold.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/thredsold.md)
  - [poc/implement/00-overview-and-decisions.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/00-overview-and-decisions.md)
  - [poc/implement/02-ai-pipeline.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/02-ai-pipeline.md)
  - [poc/implement/04-frontend.md](file:///E:/ATIN/traffic_congestion_evaluation/poc/implement/04-frontend.md)

### 1. Bối cảnh & Lý do Thay đổi (Sau họp đánh giá với PM & Quan sát thực tế)
1. **Quy chuẩn vùng vẽ `Poly Zone`:** Tăng chiều dài vùng gốc lên **`3 vạch sơn + 2–3 khoảng trống` (`18 – 22m`)** và giữ nguyên cơ chế mở rộng dọc trục đường **`+20%` ở cả 2 cạnh trên/dưới (`FLOW_ZONE_EXTEND_RATIO = 0.20`)** từ đợt cập nhật trước để tính `O_vis` và `Flow` bao quát đủ ngữ cảnh.
2. **Loại bỏ bộ ngưỡng cứng `W_*` (`W_CLEAR`, `W_CONGESTED`, `W_GRIDLOCK`, `W_RESCUE`) và ẩn `W` trên thẻ Live View:**
   - `W` phụ thuộc vào kích thước vùng vẽ và bị tụt thấp sai lệch trên môi trường Production khi số lượng BBox bắt được thấp.
   - Giữ lại trọng số phương tiện (`WEIGHT_2W=1.0, WEIGHT_CAR=3.0, WEIGHT_HEAVY=6.0`) để làm **Cổng xác nhận có xe thật (`W_SANITY_MIN = 3.0`)** chống nhiễu đèn pha đêm mưa và kết hợp cùng `T50 / D85` để tính **Điểm tự tin (`state_conf` $\in [0.55 .. 0.98]$)**.
3. **Chốt Bộ Ngưỡng V2 (`O_vis`, `Flow`, `T50`, `D85`) cho vùng `18 – 22m`:**
   - **Độ phủ `O_vis`:**
     - `O_CLEAR = 0.40` (`< 40%`: đường vắng/thoáng; `40% <= O_vis < 70%`: đường đông lưu thông trung bình).
     - `O_CONGESTED = 0.70` (`70% <= O_vis < 85%`: đường ùn tắc).
     - `O_GRIDLOCK = 0.85` (`>= 85%`: đường kẹt cứng — hạ từ mức đề xuất ban đầu `90%` xuống `85%` để bù cho khe hở vật lý giữa các xe và phần bóng râm `127` bị loại bỏ).
   - **Tốc độ dòng chảy `Flow (px/s)`:**
     - Lưu thông bình thường (`CLEAR`): `V_CLEAR_MIN = 10.0 px/s` (dải lưu thông trung bình `10 – 35 px/s`).
     - Lưu thông chậm (`CONGESTED`): `V_CONGESTED_MAX = 25.0 px/s` khi có `T50/D85` xác nhận chậm (hoặc `V_CONGESTED_MACRO = 18.0 px/s` khi `T50/D85` bị `None`).
     - Kẹt cứng (`GRIDLOCKED`): `V_GRIDLOCK_MAX = 15.0 px/s` khi có `T50/D85` xác nhận kẹt (hoặc `V_STALL = 6.0 px/s` khi `T50/D85` bị `None`).
   - **Thời gian vượt vùng `T50` & Lưu trú `D85` (với cửa sổ trượt `ZONE_WINDOW_S = 30.0s`):**
     - Ranh giới `CLEAR` $\leftrightarrow$ `CONGESTED`: `CONGESTED_T50_4W_S = 5.5`, `CONGESTED_D85_4W_S = 6.5`, `CONGESTED_T50_2W_S = 4.5`, `CONGESTED_D85_2W_S = 5.0`.
     - Ranh giới `CONGESTED` $\leftrightarrow$ `GRIDLOCKED`: `GRIDLOCK_T50_4W_S = 16.0`, `GRIDLOCK_D85_4W_S = 20.0`, `GRIDLOCK_T50_2W_S = 13.5`, `GRIDLOCK_D85_2W_S = 17.0`.

### 2. Bảng Đối Chiếu Thay Đổi Tham Số (Từ Commit `e14cb45` $\rightarrow$ Đặc Tả V2)

| Tham số Cấu hình | Giá trị Commit `e14cb45` (Trước) | Giá trị Đặc Tả V2 (Chốt Mới) | Ghi chú Thay đổi |
| :--- | :---: | :---: | :--- |
| `ZONE_WINDOW_S` | `15.0` | **`30.0`** | Tăng lên 30s để giữ đủ mẫu xe đi chậm mất 15–20s trên vùng 18–22m |
| `ZONE_MIN_COMPLETED_SAMPLES` | `3` | **`2`** | Giúp `T50` có giá trị sớm hơn khi ít BBox |
| `W_CLEAR / W_CONGESTED / W_GRIDLOCK / W_RESCUE` | `18 / 25 / 38 / 28` | **Loại bỏ (Thay bằng `W_SANITY_MIN = 3.0`)** | Không dùng `W` làm ngưỡng chặn cứng; chỉ dùng lọc nhiễu đêm mưa & cộng `state_conf` |
| `O_CLEAR` | `0.40` | **`0.40` (`40%`)** | Giữ nguyên |
| `O_CONGESTED` | `0.55` | **`0.70` (`70%`)** | Tăng lên 70% theo quan sát thực tế trên vùng mở rộng |
| `O_GRIDLOCK` | `0.72` | **`0.85` (`85%`)** | Chốt ở mức 85% (hạ từ 90% xuống 85%) |
| `V_CLEAR_MIN` / `V_CONGESTED_MAX` / `V_GRIDLOCK_MAX` / `V_STALL` | `V_CLEAR=6.0`, `V_STALL=1.0` | **`10.0` / `25.0` (Macro `18.0`) / `15.0` / `6.0`** | Phân tách rõ ngưỡng Flow khi có `T50/D85` và khi Macro-only |
| `CONGESTED_T50_4W_S` / `CONGESTED_D85_4W_S` | `5.0` / `7.5` | **`5.5` / `6.5`** | Ranh giới trên của `CLEAR` (bắt đầu vào `CONGESTED`) cho xe 4B |
| `CONGESTED_T50_2W_S` / `CONGESTED_D85_2W_S` | `4.5` / `7.0` | **`4.5` / `5.0`** | Ranh giới trên của `CLEAR` (bắt đầu vào `CONGESTED`) cho xe 2B |
| `GRIDLOCK_T50_4W_S` / `GRIDLOCK_D85_4W_S` | `9.0` / `14.0` | **`16.0` / `20.0`** | Ranh giới vào `GRIDLOCKED` cho xe 4B trên vùng 18–22m |
| `GRIDLOCK_T50_2W_S` / `GRIDLOCK_D85_2W_S` | `7.5` / `12.0` | **`13.5` / `17.0`** | Ranh giới vào `GRIDLOCKED` cho xe 2B trên vùng 18–22m |

### 3. Thay Đổi Về Chu Kỳ Xác Nhận & Bắn Thông Báo Sự Kiện (`StateMachine` V2)
- **Bộ đếm chờ đèn đỏ (`RED_LIGHT_HOLD_S = 90.0s`):** Dành cho các khu vực bật cờ `has_traffic_light = True`.
- **Xác nhận sự kiện lần 1 (`CONFIRM_STATE_S = 180.0s` = `3 phút`):** Duy trì liên tục 3 phút $\rightarrow$ Bắn sự kiện `event_stage = "CONFIRMED_3M"`.
- **Nhắc lại lần 1 sau `+2 phút` (`FOLLOWUP_AFTER_CONFIRM_S = 120.0s`, tổng `5 phút = 300s`):** Nếu sự kiện vẫn còn $\rightarrow$ Bắn sự kiện `event_stage = "FOLLOWUP_5M"`.
- **Nhắc lại định kỳ mỗi `+15 phút` (`PERIODIC_REMINDER_S = 900.0s`, tại các mốc `20p, 35p, 50p...`):** Nếu sự kiện vẫn còn $\rightarrow$ Bắn sự kiện `event_stage = "PERIODIC_15M"`.
- **Bắn ngay khi xác nhận Chuyển trạng thái (Sau mốc 3 phút đầu):** Khi đã ở trạng thái xác nhận (`CONGESTED` hoặc `GRIDLOCKED`) mà tuyến đường chuyển sang trạng thái khác (`CLEAR` hoặc `GRIDLOCKED`) và giữ ổn định trạng thái mới đủ **3 phút (`180s`)** $\rightarrow$ Bắn ngay bản tin chuyển trạng thái (`event_stage = "TRANSITION"` hoặc `"RECOVERED_CLEAR"`).
- *(Khi `DEMO_MODE=1`: rút tỷ lệ thời gian xuống `30s` xác nhận / `+20s` nhắc lần 1 / `+90s` định kỳ).*
