# HƯỚNG DẪN Ý NGHĨA & CÁCH TINH CHỈNH BỘ THAM SỐ NGƯỠNG (V2 — CHUẨN HÓA VÙNG 18–22M & LOẠI BỎ NGƯỠNG CỨNG `W`)

> Tài liệu giải thích trực quan ý nghĩa của từng nhóm tham số trong `.env` / `config.py` sau đợt đánh giá thực tế cùng PM (xem thêm [09-parameter-and-system-evaluation.md](./09-parameter-and-system-evaluation.md) và [10-threshold-and-event-lifecycle-spec.md](./10-threshold-and-event-lifecycle-spec.md)).

---

### 1. Quy ước Vùng `Poly Zone` (`18 – 22m`) & Mở rộng Vùng Tính Độ Phủ (`FLOW_ZONE_EXTEND_RATIO = 0.20`)

1. **Cách vẽ `Poly Zone` trên giao diện:**
   - Vẽ đa giác bao phủ các làn đường theo chiều xe chạy với độ dài khoảng **`3 vạch sơn + 2–3 khoảng trống`** (tương đương **`18 – 22 mét`** thực tế).
2. **Tách 2 vùng đo tự động bên trong AI:**
   - **Vùng `zone_px` (Poly Zone gốc bạn vẽ):** Dùng để đo thời gian xe đi xuyên qua vùng (`T50`), thời gian xe bị giữ chân trong vùng (`D85`), và lá chắn che khuất xe buýt (`OcclusionShield`).
   - **Vùng `flow_zone_px` (Mở rộng dọc trục đường `+20%` ở cả cạnh trên và cạnh dưới — `FLOW_ZONE_EXTEND_RATIO=0.20`):** Dùng để đo **Độ phủ mặt đường (`O_vis`)** và **Tốc độ dòng chảy (`Flow`)**, đồng thời làm khung cắt `ROI` cho YOLO để quan sát được ngữ cảnh đầy đủ hơn ở cả đầu vào và đầu ra của vùng.

---

### 2. Vai Trò Mới Của Trọng Số Xe (`WEIGHT_*` & `W_SANITY_MIN`) — Không Còn Dùng `W` Làm Ngưỡng Chặn Cứng

- **Tại sao bỏ bộ ngưỡng `W_CLEAR / W_CONGESTED / W_GRIDLOCK` và ẩn `W` khỏi thẻ Live View?**
  - Vì `W` là tổng điểm tuyệt đối (phụ thuộc vào diện tích vùng vẽ to hay nhỏ) và khi lên môi trường Production (nơi số lượng BBox bắt được có thể thấp), `W` sẽ bị tụt thấp giả tạo. Trong khi đó, **Độ phủ `O_vis (%)`** đã tự chia cho diện tích vùng và kết hợp cả `MOG2 + BBox` nên ổn định hơn rất nhiều.
- **Vậy giữ lại `WEIGHT_2W=1.0`, `WEIGHT_CAR=3.0`, `WEIGHT_HEAVY=6.0` để làm gì?**
  1. **Làm Cổng Kiểm Chứng Có Xe Thật (`W_SANITY_MIN = 3.0`):** Chỉ cần trong vùng có tổng trọng số `>= 3.0` (tương đương **1 ô tô** hoặc **3 xe máy**) là xác nhận có phương tiện thật trên đường, giúp chặn báo giả vào ban đêm trời mưa khi đèn pha rọi xuống mặt đường ướt làm `MOG2` báo `O_vis` cao.
  2. **Cộng Điểm Tự Tin (`state_conf` $\in [0.55 .. 0.98]$):** Khi trọng số phương tiện `W_total` và các chỉ số thời gian `T50 / D85` đồng thuận với `O_vis + Flow`, hệ thống cộng thưởng vào độ tự tin `state_conf` của trạng thái và sự kiện.

---

### 3. Nhóm Độ Phủ Mặt Đường `O_*` (`O_CLEAR`, `O_CONGESTED`, `O_GRIDLOCK`) — Trụ Cột Số 1

`O_vis` được tính từ phần diện tích xe do `MOG2` (vật thể nổi trên nền đường, đã bỏ bóng râm `127`) gộp với khung `BBox` của YOLO, chia cho diện tích vùng `flow_zone_px`. Hiển thị trên UI dạng `Phủ: xx%`, cấu hình trong `.env` dạng `0..1`:

- **`O_CLEAR = 0.40` (`< 40%`):**
  - Mặt đường bị chiếm chỗ dưới `40%` (và `Flow > 10 px/s`) $\longrightarrow$ Đường vắng/thoáng, chốt ngay **`CLEAR`**.
  - Khi **`40% <= O_vis < 70%`**: Đường đông xe vừa phải; nếu dòng chảy lưu thông trung bình (`10 <= Flow <= 35 px/s`) và thời gian `T50 / D85` nằm trong ngưỡng thoát nhanh thì vẫn là **`CLEAR`**.
- **`O_CONGESTED = 0.70` (`70% <= O_vis < 85%`):**
  - Mặt đường bị lấp đầy từ `70%` đến dưới `85%`, mật độ phương tiện rất cao $\longrightarrow$ Đạt điều kiện độ phủ để xét **`CONGESTED` (`Đường ùn tắc`)**.
- **`O_GRIDLOCK = 0.85` (`O_vis >= 85%`):**
  - Mặt đường gần như kín đặc hoàn toàn (`>= 85%`, phần còn lại chỉ là khe hở nhỏ giữa các xe) $\longrightarrow$ Đạt điều kiện độ phủ để xét **`GRIDLOCKED` (`Kẹt xe / Tắc đường`)**.

---

### 4. Nhóm Tốc Độ Dòng Chảy `Flow` (`V_CLEAR_MIN`, `V_CONGESTED_MAX`, `V_GRIDLOCK_MAX`, `V_STALL`) — Trụ Cột Số 2

Đo tốc độ dịch chuyển trung bình (`px/s` trên khung chuẩn `320x180`) của đám đông phương tiện trong vùng:
- **Đường vắng / Lưu thông trung bình (`CLEAR`):**
  - Khi `O_vis < 40%` và `Flow > 10 px/s` (`V_CLEAR_MIN = 10.0`).
  - Hoặc khi đường đông (`40% <= O_vis < 70%`), `10 <= Flow <= 35 px/s` và các xe đi qua vùng trong thời gian ngắn (`T50 / D85` đạt chuẩn `CLEAR`).
- **Đường đông di chuyển chậm (`CONGESTED`):**
  - `6 <= Flow <= 25 px/s` (`V_CONGESTED_MAX = 25.0`, hoặc `Flow <= 18.0 px/s` khi `T50/D85` bị `None` ở chế độ Macro-only).
- **Đường kẹt cứng / Nhích từng chút một `< 5 km/h` (`GRIDLOCKED`):**
  - Khi có `T50 / D85` xác nhận xe bị chôn chân lâu: cho phép `0 <= Flow <= 15 px/s` (`V_GRIDLOCK_MAX = 15.0`).
  - Khi `T50 / D85` bị `None` (chỉ xét Macro `O_vis + Flow`): yêu cầu `Flow <= 6.0 px/s` (`V_STALL = 6.0`) để tránh báo nhầm dòng xe đang chạy chậm thành kẹt cứng.

---

### 5. Nhóm Thời Gian Vượt Vùng `T50` & Thời Gian Lưu Trú `D85` (Cho Vùng `18 – 22m`, `ZONE_WINDOW_S = 30.0s`)

Vì vùng `Poly Zone` mới dài `18 – 22m`, cửa sổ trượt gom mẫu `T50` được đặt là **`ZONE_WINDOW_S = 30.0` giây**:

| Trạng thái | Ngưỡng cho Xe 4 Bánh (`4W`: Ô tô, Buýt, Tải) | Ngưỡng cho Xe 2 Bánh (`2W`: Xe máy) | Giải thích Thực tế (Vùng `18 – 22m`) |
| :--- | :--- | :--- | :--- |
| **`CLEAR`**<br>*(Lưu thông tốt)* | • `T50_4W <= 5.5s`<br>• `D85_4W <= 6.5s` | • `T50_2W <= 4.5s`<br>• `D85_2W <= 5.0s` | Dù đường đông (`40% <= O_vis < 70%`) nhưng xe đi vào và thoát ra khỏi đoạn `18–22m` chỉ mất `4 – 6 giây`. |
| **`CONGESTED`**<br>*(Ùn tắc, xe chạy chậm)* | • `5.5s < T50_4W <= 16.0s`<br>• `6.5s < D85_4W <= 20.0s`<br>*(Cấu hình: `CONGESTED_T50_4W_S=5.5`, `CONGESTED_D85_4W_S=6.5`)* | • `4.5s < T50_2W <= 13.5s`<br>• `5.0s < D85_2W <= 17.0s`<br>*(Cấu hình: `CONGESTED_T50_2W_S=4.5`, `CONGESTED_D85_2W_S=5.0`)* | Mặt đường rất đông (`O_vis >= 70%`), xe vẫn di chuyển nhưng thoát chậm, mất từ `6 – 19 giây` trong vùng. |
| **`GRIDLOCKED`**<br>*(Kẹt cứng `< 5 km/h`)* | • **`T50_4W > 16.0s`** (`GRIDLOCK_T50_4W_S=16.0`)<br>• **`D85_4W > 20.0s`** (`GRIDLOCK_D85_4W_S=20.0`) | • **`T50_2W > 13.5s`** (`GRIDLOCK_T50_2W_S=13.5`)<br>• **`D85_2W > 17.0s`** (`GRIDLOCK_D85_2W_S=17.0`) | Độ phủ `>= 85%`, xe đứng yên hoặc nhích từng chút một khiến thời gian nằm trong vùng vượt quá `16 – 20 giây`. |

---

### 6. Quy Trình Xác Nhận & Bắn Thông Báo Sự Kiện (`3 Phút → +2 Phút (5p) → Mỗi +15 Phút` & Chuyển Trạng Thái)

1. **Bộ đếm Đèn đỏ `90 giây` (`RED_LIGHT_HOLD_S = 90.0`):**
   - Với camera tích chọn `Có đèn tín hiệu (has_traffic_light = true)`, hệ thống hiểu `90 giây` dừng chờ đầu tiên là nhịp đèn đỏ bình thường.
2. **Xác nhận Sự kiện Ban đầu (`CONFIRM_STATE_S = 180.0` = `3 phút`):**
   - Tình trạng `CONGESTED` hoặc `GRIDLOCKED` phải diễn ra liên tục trong vòng **3 phút (`180s`)** mới xác nhận tự tin và **bắn bản tin Sự kiện lần 1 (`CONFIRMED_3M`)**.
3. **Nhắc lại sau `+2 phút` (Tổng `5 phút` — `FOLLOWUP_AFTER_CONFIRM_S = 120.0`):**
   - Nếu sau mốc 3 phút, tình trạng ùn tắc/kẹt xe kéo dài thêm **2 phút nữa (tổng 5 phút = `300s`)**, hệ thống **bắn thêm 1 bản tin nhắc (`FOLLOWUP_5M`)**.
4. **Nhắc lại định kỳ mỗi `+15 phút` (`PERIODIC_REMINDER_S = 900.0`):**
   - Sau mốc 5 phút, cứ mỗi **15 phút (`900s` — tại các mốc `20p, 35p, 50p...`)** mà sự kiện vẫn chưa kết thúc, hệ thống **bắn tiếp 1 bản tin thông báo (`PERIODIC_15M`)** để người giám sát biết tuyến đường vẫn đang ùn tắc.
5. **Bắn Ngay Khi Xác Nhận Chuyển Trạng Thái (`Transition Alert` sau mốc 3 phút):**
   - Từ sau phút thứ 3 (khi tuyến đường đã được xác nhận là đang ùn tắc/kẹt xe), nếu tuyến đường chuyển sang trạng thái khác (`CLEAR` hoặc `GRIDLOCKED`) và **giữ ổn định trạng thái mới đó đủ 3 phút (`180s`)**, hệ thống **lập tức bắn ngay 1 bản tin Chuyển trạng thái** (`TRANSITION` hoặc `RECOVERED_CLEAR`) mà không cần chờ bộ đếm 2p/15p cũ!
   - *(Khi bật `DEMO_MODE=1` để test nhanh: các mốc `180s / +120s / +900s` tự động rút xuống còn **`30s / +20s / +90s`**).*
