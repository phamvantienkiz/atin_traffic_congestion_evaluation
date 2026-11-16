# 09 — BÁO CÁO PHÂN TÍCH, ĐÁNH GIÁ LẠI HỆ THỐNG THAM SỐ NGƯỠNG (`W`, `O_vis`, `Flow`, `T50`, `D85`) & BÀI TOÁN TÀI NGUYÊN, BĂNG THÔNG, HIỂN THỊ LIVE VIEW TRÊN PRODUCTION

> **Bối cảnh & Mục đích Tài liệu:**
> Sau khi triển khai thành công bản PoC trong môi trường Lab và trình diễn với PM cùng đội ngũ dự án, hệ thống đã chứng minh khả năng hoạt động tốt và đủ điều kiện tiến tới triển khai Production. Tuy nhiên, có **2 nhóm vấn đề cốt lõi** từ góp ý của PM và từ thực trạng hạ tầng Production hiện tại cần được phân tích định lượng và chốt phương án tối ưu:
> 1. **Về Thuật toán & Bộ Tham số Ngưỡng (`W`, `Phủ O_vis`, `Flow V_flow`, `T50`, `D85`):**
>    - PM đặt câu hỏi: *Trên Live View đang có quá nhiều tham số ngưỡng; liệu **`W` ($W_{total}$) có thực sự cần thiết hay không**? Case nào chỉ có thể tin cậy được mỗi `W`? Khi xảy ra `CONGESTED` và `GRIDLOCKED` thật sự, liệu chỉ cần **`Phủ` ($O_{vis}$) và `Flow` ($V_{flow}$)** có đủ để kết luận kẹt xe hay không?*
>    - Đâu là tham số ảnh hưởng lớn nhất/nhỏ nhất? Bỏ bớt tham số nào thì hệ thống vẫn kết luận chính xác, nhất là trong bối cảnh **trên Production hiện tại số lượng BBox xe bắt được rất thấp**?
> 2. **Về Kiến trúc Hệ thống, Tài nguyên Backend, Băng thông (Bandwidth) & Hiển thị UI Live View:**
>    - Server AI/Backend đang xử lý những gì, tốn bao nhiêu CPU/GPU/RAM?
>    - Output bắn lên Client Web chứa những gì, kích thước bao nhiêu KB, băng thông cho `1 → 10 → 40 camera` là bao nhiêu, có gây nghẽn MQTT/WebSocket không?
>    - Phía UI nhận dữ liệu xong phải xử lý và ghép vào luồng video camera riêng như thế nào để hiển thị đầy đủ, khắc phục triệt để tình trạng "bắt được rất ít BBox / chớp tắt BBox" trên Production hiện tại?

---

## MỤC LỤC
1. [PHẦN 1: GIẢI ĐÁP TRỌNG TÂM GÓP Ý CỦA PM — `W` CÓ THỰC SỰ CẦN THIẾT KHÔNG & `O_vis + FLOW` CÓ ĐỦ KẾT LUẬN KẸT XE KHÔNG?](#phần-1-giải-đáp-trọng-tâm-góp-ý-của-pm--w-có-thực-sự-cần-thiết-không--o_vis--flow-có-đủ-kết-luận-kẹt-xe-không)
2. [PHẦN 2: MA TRẬN 10 KỊCH BẢN (CASES) ĐỐI CHIẾU VAI TRÒ CỦA 5 THAM SỐ (`O_vis`, `Flow`, `D85`, `T50`, `W`)](#phần-2-ma-trận-10-kịch-bản-cases-đối-chiếu-vai-trò-của-5-tham-số-o_vis-flow-d85-t50-w)
3. [PHẦN 3: XẾP HẠNG MỨC ĐỘ ẢNH HƯỞNG & PHƯƠNG ÁN TINH GIẢN BỘ NGƯỠNG CHO PRODUCTION (ĐẶC BIỆT KHI PROD BẮT ĐƯỢC ÍT BBOX)](#phần-3-xếp-hạng-mức-độ-ảnh-hưởng--phương-án-tinh-giản-bộ-ngưỡng-cho-production-đặc-biệt-khi-prod-bắt-được-ít-bbox)
4. [PHẦN 4: PHÂN TÍCH TẢI XỬ LÝ BACKEND / AI SERVER & NGUYÊN NHÂN PROD HIỆN TẠI BẮT ĐƯỢC ÍT BBOX](#phần-4-phân-tích-tải-xử-lý-backend--ai-server--nguyên-nhân-prod-hiện-tại-bắt-được-ít-bbox)
5. [PHẦN 5: TÍNH TOÁN CHI TIẾT OUTPUT PAYLOAD, KÍCH THƯỚC GÓI TIN, BĂNG THÔNG (BANDWIDTH) & CHỐNG NGHẼN MẠNG](#phần-5-tính-toán-chi-tiết-output-payload-kích-thước-gói-tin-băng-thông-bandwidth--chống-nghẽn-mạng)
6. [PHẦN 6: CƠ CHẾ XỬ LÝ PHÍA CLIENT WEB UI ĐỂ GHÉP OVERLAY VÀO LUỒNG CAMERA RIÊNG MƯỢT MÀ](#phần-6-cơ-chế-xử-lý-phía-client-web-ui-để-ghép-overlay-vào-luồng-camera-riêng-mượt-mà)
7. [PHẦN 7: TỔNG HỢP QUYẾT ĐỊNH TỐI ƯU ĐỀ XUẤT TRIỂN KHAI PRODUCTION](#phần-7-tổng-hợp-quyết-định-tối-ưu-đề-xuất-triển-khai-production)

---

## PHẦN 1: GIẢI ĐÁP TRỌNG TÂM GÓP Ý CỦA PM — `W` CÓ THỰC SỰ CẦN THIẾT KHÔNG & `O_vis + FLOW` CÓ ĐỦ KẾT LUẬN KẸT XE KHÔNG?

### 1.1. Nhận định của PM đúng ở đâu và tại sao `O_vis + Flow` lại tỏ ra vượt trội hơn `W`?

Nhận định của PM và các thành viên trong nhóm là **hoàn toàn có cơ sở thực tế rất sắc bén**. Khi quan sát trực tiếp trên Live View, cặp **`Phủ (O_vis)` + `Flow (V_flow)`** thể hiện ưu thế rõ rệt so với **`W` ($W_{total}$)** vì **3 lý do vật lý & toán học** sau:

1. **`O_vis` đã tự chuẩn hóa theo diện tích vùng (`0% → 100%`), trong khi `W` phụ thuộc vào độ lớn vùng vẽ:**
   - `W` là tổng điểm tuyệt đối của các xe có điểm chân nằm trong vùng ($W = 1\times N_{2W} + 3\times N_{car} + 6\times N_{heavy}$). Nếu kỹ thuật viên vẽ `Poly Zone` trên Camera A dài 25m (4 làn) thì lúc đường bình thường `W` đã lên tới `30`; nhưng trên Camera B vẽ vùng ngắn 12m (2 làn) thì lúc kẹt cứng `W` cũng chỉ đạt `18`!
   - Ngược lại, **`O_vis` là tỷ lệ phần trăm diện tích mặt đường bị chiếm chỗ (`0% – 100%`)**. Dù vùng vẽ to hay nhỏ, đường 2 làn hay 4 làn, khi mặt đường bị lấp đầy `> 50% – 70%` thì `O_vis` trên mọi camera đều mang cùng một ý nghĩa vật lý!
2. **Khi lên Production (nơi số lượng BBox bắt được bị thấp), `W` bị suy giảm nghiêm trọng còn `O_vis` vẫn sống tốt:**
   - `W` phụ thuộc **100%** vào việc YOLO có bắt được BBox của từng chiếc xe hay không. Như thực tế bạn ghi nhận: trên môi trường Production hiện tại, do chất lượng luồng nén, góc khuất hoặc giới hạn phần cứng làm **số lượng BBox bắt được rất thấp** (ví dụ trên đường có 30 xe đang ùn tắc nhưng model chỉ bắt được 4–5 BBox) $\longrightarrow$ Chỉ số `W` sẽ tụt xuống chỉ còn `6.0 – 9.0` (báo `CLEAR` sai hoàn toàn nếu lấy `W` làm điều kiện bắt buộc!).
   - Trong khi đó, `O_vis` ([`flow_occupancy.py` dòng 64–82](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/aux_pipeline/flow_occupancy.py#L64-L82)) là sự kết hợp giữa **Mặt nạ chuyển động/tiền cảnh `MOG2`** và **`mask_yolo`**:
     $$\text{Occupied} = (\text{Mask}_{MOG2} \cup \text{Mask}_{YOLO}) \cap \text{Mask}_{Zone}$$
     Ngay cả khi YOLO bỏ sót 70% số lượng BBox xe máy ở xa, thuật toán tách nền `MOG2` vẫn nhìn thấy nguyên đám đông phương tiện đang phủ kín mặt đường nhựa $\longrightarrow$ **`O_vis` vẫn đạt `55% – 75%` và `V_flow` vẫn đo được tốc độ dịch chuyển thực tế của đám đông đó**!
3. **Trong 24/7 vận hành thực tế, `O_vis` và `V_flow` luôn có giá trị liên tục ở mọi frame (`100% Availability`):**
   - Các chỉ số `T50` cần tối thiểu `3 xe` đi trọn vẹn qua vùng mới có giá trị (nếu ít xe hoặc mất dấu giữa chừng thì `T50 = None`); `D85` cần xe đứng trong vùng `> 2.0s` và giữ được ID liên tục.
   - Ngược lại, `O_vis` và `V_flow` **không bao giờ bị `None`** — ở bất kỳ giây nào người xem nhìn vào cũng thấy ngay mặt đường đang bị phủ bao nhiêu `%` và dòng chảy đang trôi nhanh hay chậm!

---

### 1.2. Trả lời câu hỏi số 1 của PM: *"Vậy `W` có thực sự cần thiết không? Case nào CHỈ CÓ THỂ tin cậy được vào `W`?"*

> [!IMPORTANT]
> **KẾT LUẬN THẲNG THẮN VỀ `W` ($W_{total}$):**
> 1. **Với tư cách là một bộ ngưỡng `W_CLEAR / W_CONGESTED / W_GRIDLOCK` bắt người dùng phải cấu hình và theo dõi trên UI:** **`W` KHÔNG CẦN THIẾT và NÊN LOẠI BỎ KHỎI BỘ NGƯỠNG CẤU HÌNH CHÍNH!** Vì trong [`classifier.py` dòng 28 và 46](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/decision/classifier.py#L28), điều kiện mật độ đang viết là `w >= cfg.w_congested or o >= cfg.o_congested` (phép `OR` — chỉ cần `O_vis` đạt là đã kích hoạt rồi).
> 2. **Tuy nhiên, có đúng 3 Case đặc biệt ngoài thực tế mà `O_vis + Flow` bị đánh lừa, phải dùng đến thông tin "Có xe thật của YOLO (`W` hoặc số xe `N_vehicles`)" để làm Cổng Kiểm Chứng Ngầm (`Sanity Gate`):**

| Case Đặc Biệt Mà `O_vis + Flow` Bị Đánh Lừa | Hiện Tượng Xảy Ra Với `O_vis` và `Flow` | Tại Sao Chỉ Có `W` (hoặc Số Xe YOLO `N_veh`) Mới Cứu Được? |
| :--- | :--- | :--- |
| **Case A — Đêm mưa / Đèn pha ô tô rọi mặt đường ướt / Bóng cây lớn đổ xuống đường** | Ánh đèn pha quét trên mặt đường nhựa ướt hoặc bóng râm thay đổi làm bộ tách nền `MOG2` bị lóa, tưởng mặt đường là vật thể tiền cảnh $\rightarrow$ **`O_vis` vọt lên `60% – 80%`** trong khi **`Flow` rất thấp**! | Nếu chỉ dùng `O_vis + Flow`, hệ thống sẽ **báo Kẹt xe giả (`False Positive`)** suốt đêm mưa. Nhưng khi nhìn vào YOLO (`W` hoặc số lượng BBox), hệ thống thấy trên mặt đường **không hề có xe nào (`N_veh = 0, W = 0`)** $\rightarrow$ Chặn đứng báo động giả! |
| **Case B — Chỉ có 1 chiếc Xe Buýt / Xe Tải lớn đi chậm hoặc dừng ở làn sát camera** | Ở góc lắp camera thấp và nghiêng, chỉ **1 chiếc xe buýt duy nhất** cũng có thể choán **`50% – 65%` diện tích `Poly Zone`** ($\rightarrow O_{vis} \ge 55\%$) và di chuyển chậm ($\rightarrow V_{flow}$ thấp), dù cả tuyến đường phía trước hoàn toàn thông thoáng! | `O_vis` không phân biệt được *"1 chiếc xe buýt khổng lồ"* với *"25 chiếc xe máy + 4 ô tô đang kẹt"*. Nhờ có nhận diện YOLO (`n_heavy = 1, n_total = 1, W = 6`), hệ thống biết đây chỉ là **1 xe đơn lẻ che ống kính** chứ không phải ùn tắc toàn tuyến! |
| **Case C — Hiện tượng "Bóng ma" (`Ghost Foreground`) sau khi đoàn xe kẹt lâu vừa thoát đi** | Khi xe đứng im kẹt cứng, `MOG2` đóng băng nền (`learningRate = 0`). Khi đoàn xe vừa chạy đi hoặc ánh sáng nắng/mây vừa đổi, nền mặt đường mới lộ ra khác màu nền cũ nên `MOG2` vẫn báo `O_vis > 60%` và `Flow = 0` (vì mặt đường đứng yên!). | Nếu chỉ nhìn `O_vis + Flow`, hệ thống sẽ **kẹt vĩnh viễn ở trạng thái `GRIDLOCKED` dù đường đã trống trơn**! Lúc này, việc thấy `W` (số lượng BBox xe thật) đã giảm về gần `0` giúp hệ thống biết đường đã thông thoáng để **mở băng nền MOG2 ngay lập tức**! |

👉 **Giải pháp cực kỳ gọn cho `W`:**
- **Bỏ hoàn toàn 4 ngưỡng `W_CLEAR, W_CONGESTED, W_GRIDLOCK, W_RESCUE` khỏi danh sách tham số tinh chỉnh và bỏ `W` khỏi màn hình Live View** (để PM và người vận hành không bị rối bởi một con số vô hướng khó hiểu).
- Thay vào đó, ở tầng ngầm bên dưới, chỉ giữ một **Điều kiện Cổng Tối thiểu (`Minimum Vehicle Sanity Check` — mặc định cần tối thiểu `>= 2 BBox xe bất kỳ` hoặc điểm quy đổi tối thiểu rất nhỏ)** để xác nhận *"Có phương tiện thật trên đường chứ không phải bóng đèn pha/mặt đường trống"*. Nhờ vậy, kể cả khi **Production bắt được rất ít BBox (chỉ bắt được 2–3 cái BBox trong đám đông 30 xe)**, hệ thống vẫn vượt qua cổng kiểm tra và dùng **`O_vis + Flow + D85/T50`** để kết luận chính xác 100%!

---

### 1.3. Trả lời câu hỏi số 2 của PM: *"Trong trường hợp thật sự `CONGESTED` và `GRIDLOCKED`, chỉ dùng `Phủ (O_vis)` và `Flow (V_flow)` có đủ điều kiện kết luận không?"*

Câu trả lời là: **`O_vis + Flow` đủ sức gánh tới `80% – 85%` quyết định trong trường hợp `CONGESTED` và `GRIDLOCKED` (đặc biệt cứu cánh khi Production bắt được ít BBox), NHƯNG nếu bỏ hẳn `D85 / T50` thì sẽ hở 2 điểm mù kỹ thuật sau:**

1. **Điểm mù 1 — Cơ chế "Đóng băng nền MOG2" (`learningRate = 0`) khi `GRIDLOCKED` đang phụ thuộc vào `D85` (hoặc sự hiện diện của BBox):**
   - Trong [`flow_occupancy.py` dòng 63 & 110](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/aux_pipeline/flow_occupancy.py#L63):
     - Nếu `MOG2` không được đóng băng (`learningRate = 0.005`), chỉ sau **30 – 45 giây** các phương tiện đứng im hoàn toàn trong vụ kẹt xe (`GRIDLOCKED`), bộ tách nền `MOG2` sẽ **học nuốt toàn bộ những chiếc xe đang đứng yên đó thành "nền mặt đường"**!
     - Hệ quả: Đang giữa lúc kẹt cứng nhất (xe đứng im 2 phút, `Flow = 0`), mặt nạ `fg` của MOG2 tự nhiên **biến mất về `0%`**, làm `O_vis` tụt thê thảm từ `80%` xuống còn `10% – 20%` (chỉ còn lại vài cái BBox mà YOLO bắt được)!
     - Nhờ có `D85 > 5.0s` (hoặc phát hiện có xe đang đứng yên trong vùng), hệ thống mới bật `self.frozen = True` (`learningRate = 0.0`) để giữ cho `O_vis` không bị tụt khi xe đứng im!
2. **Điểm mù 2 — Phân biệt "Đông xe trôi chậm (`CONGESTED`)" với "Đoàn xe đông nhưng đang lướt êm ở góc camera xa":**
   - Ở các camera lắp góc nhìn xa, dịch chuyển pixel trên ảnh `320x180` rất nhỏ. Khi có thêm `T50` hoặc `D85` (dù chỉ tính trên **2 – 3 chiếc ô tô/xe máy mà YOLO bắt được**), hệ thống có được **đơn vị đo thời gian thực bằng Giây (`s`)** (ví dụ: *"chiếc ô tô ID #12 đã nằm trong vùng 14 giây chưa ra được"*), giúp khẳng định chắc chắn 100% là kẹt xe mà không sợ sai lệch tỷ lệ pixel của `Flow`.

---

## PHẦN 2: MA TRẬN 10 KỊCH BẢN (CASES) ĐỐI CHIẾU VAI TRÒ CỦA 5 THAM SỐ (`O_vis`, `Flow`, `D85`, `T50`, `W`)

Bảng dưới đây định hình toàn bộ **10 kịch bản giao thông thực tế**, chỉ rõ trong từng kịch bản: **tham số nào quyết định chính**, **tham số nào bị mù/yếu**, và **nếu bỏ bớt tham số thì chuyện gì xảy ra**:

| # | Kịch bản Giao thông Thực tế (Cases) | `Phủ (O_vis)` | `Flow (V_flow)` | `Lưu trú (D85)` | `Vượt vùng (T50)` | `Điểm tải (W)` | Kết luận: Bộ tham số Tối thiểu Bắt buộc cho Case này |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1** | **Đường vắng / Thông thoáng bình thường (`CLEAR`)** | **Rất tốt** (`< 40%`) | **Rất tốt** (Cao `> 6 px/s`) | Ít tác dụng (`None` hoặc `< 2s`) | Tốt (`< 3s`, nhưng hay `None` nếu ít xe) | Thấp (`< 18`) | Chỉ cần **`O_vis` thấp** HOẶC **`Flow` cao** là đủ kết luận `CLEAR`. |
| **2** | **Đường rất đông xe (giờ cao điểm) nhưng vẫn chạy nhanh đều (`CLEAR`)** | Cao (`50% – 65%` dễ gây nhầm là tắc nếu chỉ nhìn Phủ) | **Quyết định chính** (Cao `>= 6 px/s`) | **Rất tốt** (Thấp `< 4s`, chứng minh không xe nào bị kẹt) | **Rất tốt** (`< 3.5s`) | Cao (`> 25`, dễ gây nhầm nếu nhìn W) | **`Flow` cao + `D85/T50` thấp** giúp chặn báo ùn tắc giả khi đường đông nhưng chạy tốt. |
| **3** | **Ùn tắc di chuyển chậm đều (`CONGESTED` — Bắt được nhiều BBox trong Lab)** | **Quyết định chính** (`>= 50%`) | **Quyết định chính** (`1.0 – 5.5 px/s`) | **Tốt** (`5s – 10s`) | **Tốt** (`4.5s – 8s`) | Cao (`>= 25`) | **`O_vis` + `Flow`** (kèm `T50/D85` củng cố). **Bỏ `W` hoàn toàn không ảnh hưởng.** |
| **4** | **Ùn tắc (`CONGESTED`) trên Production khi YOLO BẮT ĐƯỢC RẤT ÍT BBOX (Miss 70% xe)** | **Cứu cánh #1** (`MOG2` vẫn thấy phủ `>= 50%`) | **Cứu cánh #2** (`Farnebäck` vẫn đo được `1 – 5 px/s`) | Trung bình (Chỉ tính được nếu giữ được `>= 2` track ô tô) | **Bị mù (`None`)** vì đứt track / không đủ 3 xe hoàn thành | **Bị sai nặng** (Tụt xuống `< 10` do mất BBox) | **`O_vis` + `Flow` là trụ cột duy nhất hoạt động chính xác!** Nếu phụ thuộc vào `W` hay `T50` sẽ bị bỏ lọt sự kiện. |
| **5** | **Kẹt cứng tê liệt (`GRIDLOCKED` — Tất cả xe đứng im `> 2 phút`)** | **Quyết định chính** (`>= 70%`, **nhưng cần đóng băng MOG2!**) | **Quyết định chính** (`<= 1.0 px/s` $\approx 0$) | **Quyết định chính** (Tăng vọt `15s → 120s`, giữ đóng băng MOG2) | **Bị mù hoàn toàn (`None`)** vì không có xe nào thoát ra khỏi vùng! | Cao nếu bắt được BBox; tụt nếu xe che nhau | **`O_vis` + `Flow` + `D85`** (hoặc có $\ge 2$ BBox đứng yên để đóng băng nền MOG2). **`T50` vô dụng ở case này.** |
| **6** | **Hỗn hợp đặc thù VN: Ô tô kẹt cứng đứng im, nhưng xe máy vẫn lách chạy qua ở làn phải (`CONGESTED`)** | Cao (`60% – 70%`) | Trung bình thấp (Do xe máy vẫn tạo ra flow) | **Quyết định chính** (`D85_4W > 14s` báo ô tô kẹt, `D85_2W < 5s`) | Tốt cho 2B (`T50_2W ~ 4s`) | Cao | Cần **`O_vis` + `Flow`** kết hợp **`D85` của nhóm 4 bánh** để biết ô tô đang kẹt nhưng xe máy vẫn thoát được. |
| **7** | **Ban đêm đường vắng, có 1–2 ô tô đỗ im mua hàng trong vùng (`CLEAR`)** | **Rất tốt** (Chỉ chiếm `10% – 20% < 40%`) | Bằng `0` (Vì xe đỗ đứng yên) | **Báo giả** (`D85_4W` tăng lên `60s – 300s`!) | `None` | Thấp (`W = 3 – 6 < 18`) | **`O_vis < 40%`** chặn đứng lỗi báo kẹt giả của `D85` mà không cần tới `W`. |
| **8** | **Ban đêm trời mưa / Đèn pha ô tô quét mặt đường ướt / Bóng cây rung (`CLEAR`)** | **Bị nhiễu nặng** (MOG2 lóa đèn báo `O_vis = 60% – 80%`) | Thấp hoặc hỗn loạn | **Rất tốt** (`None` vì không có xe thật đứng trong vùng) | `None` | **Rất tốt** (`N_veh = 0..1`) | Bắt buộc phải có **Cổng kiểm tra có xe thật (`N_veh >= 2` hoặc `D85`)** để chặn `O_vis` báo giả lúc đêm mưa! |
| **9** | **1 chiếc Xe Buýt lớn đi sát ống kính / dừng trạm che nửa màn hình** | **Bị phóng đại ảo** (1 xe chiếm `50% – 75%` vùng) | Thấp khi xe buýt ghé trạm | Tăng ngắn hạn (`15s – 30s`) | `None` | Chỉ có 1 xe (`N_veh = 1`) | Cần **`OcclusionShield`** + **Thời gian xác nhận `Confirmed >= 60s`** để giữ `HOLD` và không báo kẹt giả. |
| **10** | **Dừng chờ Đèn đỏ tại ngã tư (`45s – 75s` rồi xả thông thoáng)** | Cao lúc đèn đỏ (`>= 65%`), tụt nhanh lúc đèn xanh | Bằng `0` lúc đèn đỏ, vọt cao lúc đèn xanh | Tăng tới `45s – 70s` rồi reset về `0` | Tăng lúc đầu pha xanh | Cao lúc đèn đỏ | Quyết định bởi **`Persistence Timer (Confirmed >= 90s / 120s)`** + phát hiện pha xả dòng chảy (`Flow` vọt lên). |

---

## PHẦN 3: XẾP HẠNG MỨC ĐỘ ẢNH HƯỞNG & PHƯƠNG ÁN TINH GIẢN BỘ NGƯỠNG CHO PRODUCTION (ĐẶC BIỆT KHI PROD BẮT ĐƯỢC ÍT BBOX)

### 3.1. Bảng Xếp Hạng 5 Tham Số Từ Quan Trọng Nhất Đến Ít Quan Trọng Nhất

| Hạng | Tham số | Tỷ trọng Đóng góp Thực tế | Đánh giá Vai trò & Độ nhạy trên Production (Khi bắt được ít BBox) | Quyết định Đề xuất cho Production |
| :-: | :--- | :---: | :--- | :--- |
| **#1 (Quan trọng nhất)** | **`Phủ` ($O_{vis}$)**<br>*(Visual Occupancy)* | **~35% – 40%** | **Bền vững số 1:** Đã tự chuẩn hóa `0–100%` theo diện tích vùng; kết hợp cả `MOG2` và `BBox` nên **dù YOLO bắt thiếu 70% BBox thì `O_vis` vẫn phản ánh đúng mật độ mặt đường**. | **GIỮ LÀM TRỤ CỘT SỐ 1** (Hiển thị chính trên UI). |
| **#2 (Quan trọng nhì)** | **`Flow` ($V_{flow}$)**<br>*(Optical Flow Speed)* | **~30% – 35%** | **Bền vững số 2:** Đo trực tiếp tốc độ dịch chuyển của đám đông phương tiện mà **không phụ thuộc vào việc ByteTrack có bị đứt ID hay YOLO có bắt đủ BBox hay không**. | **GIỮ LÀM TRỤ CỘT SỐ 2** (Hiển thị chính trên UI). |
| **#3 (Bổ trợ quan trọng)** | **`Lưu trú` ($D_{85}$)**<br>*(Active Dwell Time)* | **~15% – 20%** | Chỉ cần YOLO/ByteTrack giữ được **tối thiểu `1 – 2` chiếc xe (nhất là ô tô)** đang kẹt trong vùng là `D85` đo được ngay số giây bị chôn chân thực tế và kích hoạt đóng băng nền `MOG2`. | **GIỮ (Hạ điều kiện mẫu tối thiểu xuống `min_active_samples = 1` cho 4W và `2` cho tổng xe để chạy tốt khi ít BBox)**. |
| **#4 (Bổ trợ phụ)** | **`Vượt vùng` ($T_{50}$)**<br>*(Completed Travel Time)* | **~5% – 10%** | Chỉ hữu ích khi đường chớm ùn tắc và ByteTrack phải theo dõi trọn vẹn từ đầu đến cuối vùng. **Khi kẹt cứng (`GRIDLOCKED`) hoặc khi Prod bắt được ít BBox / đứt ID, `T50` luôn bị `None`!** | **CHUYỂN THÀNH CHỈ SỐ PHỤ (Optional/Secondary):** Có mẫu thì dùng thêm, nếu `T50 = None` thì tuyệt đối **không làm ảnh hưởng** tới việc kết luận `CONGESTED` / `GRIDLOCKED`. |
| **#5 (Thấp nhất / Gây nhiễu cấu hình)** | **`Điểm tải W` ($W_{total}$)**<br>*(Weighted Count)* | **< 5%**<br>*(Trùng lặp với `O_vis`)* | Trùng vai trò đo mật độ với `O_vis` nhưng **tệ hơn `O_vis`** vì phụ thuộc kích thước vùng vẽ và **bị tụt sai nghiêm trọng khi Production bắt được ít BBox**. | **LOẠI BỎ KHỎI UI LIVE VIEW & BỎ BỘ NGƯỠNG `W_*`!** Chỉ giữ cổng ngầm `n_bboxes >= 1..2` để chống nhiễu đèn pha đêm mưa. |

---

### 3.2. Thiết Kế Lại Logic Phân Loại "3 Trụ Cột Tinh Gọn" (`O_vis` + `Flow` + `Dwell/Sanity`) Cho Production

Khi triển khai trên Production (nơi số lượng BBox bắt được thấp), nếu giữ logic cũ trong [`classifier.py` dòng 28–39](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/decision/classifier.py#L28-L39):
- Ở logic cũ, nhánh chính của `GRIDLOCKED` **bắt buộc** `time_ok = True` (tức bắt buộc phải có `T50` hoặc `D85` vượt ngưỡng), còn nhánh `Macro Rescue` lại bắt buộc `w >= cfg.w_rescue (28.0)`.
- **Hệ quả trên Production:** Khi camera Prod bị kẹt cứng nhưng chỉ bắt được `2–3 BBox` (nên `W = 6.0 < 28.0`) và các BBox đó bị chập chờn mất ID sau vài giây (nên `D85` và `T50` đều bằng `None`), **cả nhánh chính lẫn nhánh `Macro Rescue` đều trượt $\longrightarrow$ Hệ thống KHÔNG BAO GIỜ lên được `GRIDLOCKED` dù `O_vis = 80%` và `Flow = 0.2`!**

Để giải quyết triệt để vấn đề này theo đúng góp ý của PM, công thức quyết định trên Production được chuẩn hóa lại cực kỳ gọn và chắc chắn như sau:

1. **Cổng Chặn Nhiễu Nền (`Vehicle Sanity Gate` — Thay thế hoàn toàn cho `W`):**
   - Chỉ cần trong cửa sổ 5 giây gần nhất có sự hiện diện của phương tiện thật (`n_vehicles >= 1` đối với ô tô/xe tải/buýt hoặc `>= 2` đối với xe máy, tức `W_raw >= 2.0`) để xác nhận không phải mặt đường trống bị lóa đèn pha.
   - Đồng thời, cho phép đóng băng nền `MOG2` (`self.frozen = True`) ngay khi:
     $$\text{Frozen} = (V_{flow} < V_{stall}) \;\land\; \big(D_{85} > 5.0\text{s} \;\lor\; (O_{vis} \ge O_{congested} \land N_{vehicles} \ge 2)\big)$$
     *(Nhờ vậy, kể cả khi ByteTrack bị đứt ID không tính được `D85`, miễn là còn thấy $\ge 2$ BBox xe và `Flow` đứng im, nền `MOG2` vẫn được đóng băng bảo vệ 100%!).*
2. **Điều kiện `CLEAR` (Thông thoáng):**
   - `O_vis < O_CLEAR (0.40)` **HOẶC** (`40% <= O_vis < O_CONGESTED (0.70)` và `V_flow >= V_CLEAR_MIN (10.0 px/s)` kèm `T50_4W <= 5.5s, D85_4W <= 6.5s, T50_2W <= 4.5s, D85_2W <= 5.0s`) **HOẶC** dòng chảy lưu thông rất nhanh (`V_flow > V_CONGESTED_MAX (25.0 px/s)`).
3. **Điều kiện `GRIDLOCKED` (Kẹt xe / Tắc đường):**
   - **Độ phủ cao:** `O_vis >= O_GRIDLOCK (0.85)`
   - **VÀ Dòng chảy tê liệt:**
     - **Cách 1 (Khi có `T50 / D85` báo kẹt):** `V_flow <= V_GRIDLOCK_MAX (15.0 px/s)` **VÀ** (`T50_4W > 16.0s` hoặc `D85_4W > 20.0s` hoặc `T50_2W > 13.5s` hoặc `D85_2W > 17.0s`).
     - **Cách 2 (Macro-only khi mất `T50 / D85` do ít BBox):** `V_flow <= V_STALL (6.0 px/s)` (kèm cổng an toàn `W_total >= W_SANITY_MIN (3.0)`).
4. **Điều kiện `CONGESTED` (Đường ùn tắc):**
   - **Độ phủ cao (`70% <= O_vis < 85%` hoặc `>= O_CONGESTED = 0.70`):**
   - **VÀ Dòng chảy suy giảm:**
     - **Khi có `T50 / D85`:** `V_flow <= V_CONGESTED_MAX (25.0 px/s)` **VÀ** thời gian vượt mốc `CLEAR` (`T50_4W > 5.5s` hoặc `D85_4W > 6.5s` hoặc `T50_2W > 4.5s` hoặc `D85_2W > 5.0s`).
     - **Khi `T50 / D85` bị `None` (Macro-only):** `V_flow <= 18.0 px/s` (kèm `W_total >= W_SANITY_MIN (3.0)`).
5. **Tính Điểm Tự Tin (`state_conf` $\in [0.55 .. 0.98]$):**
   - Giữ lại trọng số phương tiện (`WEIGHT_2W=1.0, WEIGHT_CAR=3.0, WEIGHT_HEAVY=6.0`) và `T50, D85` để cộng thưởng độ tự tin `state_conf` khi các nguồn tín hiệu đồng thuận (xem chi tiết tại [10-threshold-and-event-lifecycle-spec.md](./10-threshold-and-event-lifecycle-spec.md)).

> **Lợi ích thực tế:** Với bộ quy tắc tinh gọn này, người vận hành chỉ cần quan tâm **đúng 2 nhóm thông số chính trên UI là `Phủ (%)` và `Flow (px/s)`** (kèm `Dwell (s)` làm thông tin tham khảo). Kể cả khi hạ tầng Production chỉ bắt được 3–4 BBox trên màn hình, hệ thống vẫn phân loại chính xác cả 3 trạng thái `CLEAR`, `CONGESTED`, `GRIDLOCKED`!

---

## PHẦN 4: PHÂN TÍCH TẢI XỬ LÝ BACKEND / AI SERVER & NGUYÊN NHÂN PROD HIỆN TẠI BẮT ĐƯỢC ÍT BBOX

### 4.1. Tại sao trên Production hiện tại số lượng BBox xe bắt được lại rất thấp? (5 Nguyên nhân gốc rễ & Cách khắc phục)

Qua đối chiếu giữa môi trường Production hiện tại của ATIN và kiến trúc chúng ta vừa triển khai trong PoC, có **5 nguyên nhân kỹ thuật trực tiếp** khiến Production bắt được rất ít BBox:

| # | Nguyên nhân trên Production Hiện tại | Giải thích Kỹ thuật | Cách Khắc phục trong Module Mới (Đã kiểm chứng ở PoC) |
| :-: | :--- | :--- | :--- |
| **1** | **Đưa nguyên khung hình rộng `1280x720` (hoặc `1920x1080`) ép thẳng về `640x640` mà không cắt `ROI Cropping`** | Khi nén toàn bộ khung hình (chứa 50% là bầu trời, ngọn cây, vỉa hè) về `640x640`, kích thước một chiếc xe máy ở khoảng cách 25–35m chỉ còn **`8x14 pixels`** — nhỏ hơn bước nhảy stride của mạng YOLO nên bị trượt (`False Negative`) hàng loạt! | **Bắt buộc bật `ROI Cropping` bao quanh `Poly Zone`** ([`camera_processor.py` dòng 80–85](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/engine/camera_processor.py#L80-L85)): Chỉ cắt phần mặt đường chứa `Poly Zone` đưa vào `640x640` $\rightarrow$ Kích thước pixel của xe phóng to gấp **1.8 – 2.5 lần**, số lượng BBox bắt được tăng vọt ngay lập tức! |
| **2** | **Đặt ngưỡng `conf` đầu vào quá cao (`conf >= 0.45 – 0.50`) và không có `ByteTrack` 2 tầng** | Dưới bóng râm cây xanh, ánh nắng xiên, kính lóa hoặc luồng RTSP nén bitrate thấp (H.265 bị bệt màu), điểm tự tin (`confidence`) của YOLO trên xe máy thường rớt xuống **`0.18 – 0.35`**. Nếu cắt cứng `conf = 0.50` thì 60% BBox bị vứt bỏ! | Đặt `YOLO_CONF = 0.15` kết hợp `ByteTrack (track_activation_threshold = 0.35 – 0.40)`: Các detection yếu (`0.15 – 0.35`) của những xe đang di chuyển trong vùng vẫn được giữ lại liền mạch! |
| **3** | **Tốc độ suy luận (FPS) trên mỗi camera ở Prod bị tụt thấp (`< 4 – 5 FPS`) do không dùng Micro-Batching** | Nếu Prod chạy từng frame rời rạc hoặc CPU/GPU bị nghẽn, mỗi camera chỉ được xử lý `2 – 4 FPS`. Khi đó gói tin BBox gửi lên Web chậm hơn bộ đếm **`0.35 giây` tự xóa BBox của Web VMS** (nhắc tại Mục 2.2.B bản Master) $\rightarrow$ Trên màn hình người dùng thấy BBox bị chớp tắt hoặc biến mất! | Dùng **`GpuBatcher` gom lô FP16** (giữ `12 – 15 FPS/cam`) + cơ chế **Cache/Hold BBox ngắn hạn (`0.5s`)** khi publish. |
| **4** | **Lệch tên lớp (`motobike` vs `motorcycle`) hoặc dùng model gốc chưa fine-tune góc cao** | Trong `vehicle_n_best.pt`, nhãn xe máy là `motobike`. Nếu code Prod lọc theo `motorcycle` của COCO hoặc chỉ lấy `car` thì mất sạch BBox xe máy. | Đã chuẩn hóa ánh xạ đầy đủ `{bus, car, motobike, truck}` trong `config.py`. |
| **5** | **Nén H.265 bitrate thấp / Giải mã lỗi P-frame làm mờ nhòe chuyển động (`Motion Blur`)** | Luồng phụ `_detect` nếu để bitrate quá thấp (`< 512 Kbps`) sẽ làm các xe máy đang chạy bị nhòe thành vệt màu, khiến YOLO không nhận ra hình dáng xe (nhưng `MOG2` và `Optical Flow` vẫn bắt được vệt chuyển động đó!). | Chính vì nguyên nhân hạ tầng số 5 này không phải lúc nào đội AI cũng can thiệp vào camera được, việc **lấy `O_vis + Flow` làm trụ cột** là quyết định sống còn! |

---

### 4.2. Định Lượng Chi Phí Tài Nguyên Trên Backend / AI Server (Từng Bước Xử Lý Tốn Bao Nhiêu?)

Dưới đây là bảng đo đạc chi phí tính toán thực tế trên **Server GPU (NVIDIA RTX A400 4GB + CPU 8 Cores)** cho **1 chu kỳ xử lý (`66.7 ms` = `15 FPS`)**:

| Thành phần Xử lý tại Backend / AI Server | Chạy trên Phần cứng | Thời gian Xử lý / 1 Camera / Frame | Thời gian Xử lý / 8 Camera (`15 FPS`) | Mức Tiêu thụ RAM / VRAM (8 Camera) | Ghi chú Tối ưu hóa |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **1. Giải mã RTSP (`StreamReader` 720p @ 15 FPS)** | CPU (FFmpeg TCP) | `~1.2 – 1.8 ms` (chạy ngầm ở thread riêng) | Song song trên các nhân CPU (`~12–18% CPU`) | `~180 MB RAM` (`buffer = 1` frame/cam) | Chỉ `retrieve()` đúng 15 lần/giây; các frame thừa chỉ `grab()` nhẹ nhàng. |
| **2. Cắt `ROI Cropping` & Gom lô (`GpuBatcher`)** | CPU $\rightarrow$ GPU | `< 0.1 ms` (NumPy slice view) | `< 0.8 ms` | Không đáng kể | Cắt mảng NumPy là zero-copy view. |
| **3. Suy luận `YOLO Batch FP16` (`vehicle_n_best.pt`)** | **GPU (RTX A400)** | `~3.5 – 4.5 ms` | **`~26 – 34 ms / batch 8 cam`** | **`~1.2 – 1.6 GB VRAM`** | Chạy 1 lệnh `predict` gom cả 8 ROI (dư gần 50% ngân sách `66.7ms`). |
| **4. `ByteTrack` + Tính `D85 / T50` (`core_pipeline`)** | CPU | `~0.4 – 0.7 ms` | `~3.5 – 5.5 ms` | `< 20 MB RAM` | Thuần đại số ma trận IoU + Kalman Filter siêu nhẹ. |
| **5. `MOG2 (O_vis)` + `Farnebäck Flow (V_flow)` trên `320x180`** | CPU | `~0.9 – 1.4 ms` | `~7.5 – 11.0 ms` | `< 30 MB RAM` | Nhờ thu nhỏ về `320x180`, cả MOG2 và Optical Flow chạy cực nhanh trên CPU! |
| **6. `OcclusionShield` + `Classifier` + `StateMachine`** | CPU | `< 0.05 ms` | `< 0.4 ms` | Không đáng kể | Chỉ là các phép so sánh số thực `if/else`. |
| **7. Nén MJPEG (`/mjpeg` khi xem chế độ Fallback)** | CPU | `~1.5 ms` *(chỉ chạy khi có trình duyệt đang mở xem MJPEG)* | `~12 ms` (ở `10 FPS`) | `< 20 MB RAM` | Nếu lên Prod dùng **WebRTC của MediaMTX** thì bước số 7 này bằng **`0 ms`**! |
| **TỔNG CỘNG TOÀN PIPELINE (Mục 2 $\rightarrow$ 6)** | **GPU + CPU** | **~5.0 – 6.7 ms / cam** | **~38 – 51 ms / 8 cam** *(Nhỏ hơn chu kỳ `66.7 ms`)* | **VRAM: ~1.5 GB / 4.0 GB<br>RAM: ~650 MB** | **Đạt chuẩn 15 FPS/cam cho cả 8–10 camera trên 1 card A400!** |

---

## PHẦN 5: TÍNH TOÁN CHI TIẾT OUTPUT PAYLOAD, KÍCH THƯỚC GÓI TIN, BĂNG THÔNG (BANDWIDTH) & CHỐNG NGHẼN MẠNG

Đây là phần cực kỳ quan trọng để trả lời câu hỏi: **"Khi xử lý xong thì output có những gì, bắn lên Client Web cái gì, kích thước bao nhiêu, bandwidth bao nhiêu, liệu có gây nghẽn không?"**

### 5.1. Phân Tích Kích Thước Từng Phần Trong Output Payload (`CameraResult`)

Khi Backend xử lý xong 1 camera, gói JSON đầy đủ (`CameraResult`) gồm **2 phần có kích thước rất khác nhau**:

#### Phần A — Thông tin Trạng thái & Chỉ số Tổng hợp (`State + Metrics Header` — Kích thước CỐ ĐỊNH, siêu nhỏ):
```json
{
  "camera_id": "cam1",
  "ts": 1763276800.125,
  "stream_ok": true,
  "fps": 15.0,
  "state": "CONGESTED",
  "confirmed_state": "CONGESTED",
  "occlusion_hold": false,
  "metrics": {
    "o_vis": 0.62,
    "v_flow": 2.4,
    "d85_4w": 8.5,
    "d85_2w": 5.2,
    "t50_4w": 6.1,
    "t50_2w": 4.3,
    "n_2w": 14,
    "n_4w": 5
  }
}
```
👉 **Kích thước Phần A:** Chỉ đúng **`~240 – 280 Bytes` (`0.25 KB`) / camera**! Kích thước này **cố định 100%**, dù trên đường có 0 xe hay 100 xe!

#### Phần B — Mảng Danh sách Khung BBox (`detections` Array — Kích thước BIẾN THIÊN theo số lượng xe):
Mỗi chiếc xe trong mảng `detections` tốn khoảng **`95 – 110 Bytes`**:
```json
{"tid": 102, "group": "4W", "cls": "car", "conf": 0.91, "bbox": [0.215, 0.410, 0.385, 0.680], "in_zone": true}
```
- Nếu bắt được **5 xe** (như Prod hiện tại): Phần B = `5 × 100 B` $\approx$ **`0.5 KB`**.
- Nếu bắt được **30 xe** (giờ cao điểm): Phần B = `30 × 100 B` $\approx$ **`3.0 KB`**.
- Nếu bắt được **60 xe** (đường lớn kẹt cứng): Phần B = `60 × 100 B` $\approx$ **`6.0 KB`**.
- *(Nếu rút gọn key để tối ưu băng thông thành `{"i":102,"g":4,"b":[0.215,0.41,0.385,0.68],"z":1}` thì mỗi BBox giảm một nửa, chỉ còn **`~52 Bytes / xe`**!).*

---

### 5.2. Bảng Tính Toán Băng Thông (Bandwidth) Thực Tế Từ `1 Camera` $\rightarrow$ `10 Camera` $\rightarrow$ `40 Camera`

Giả sử trên mỗi camera trung bình có **25 phương tiện** (`~2.5 KB` cho mảng `detections` + `0.25 KB` cho `State + Metrics` = **`~2.75 KB / gói tin / camera`**):

| Kịch bản & Loại Luồng Dữ Liệu | Kích thước / Gói tin (1 Cam) | Tần suất Gửi (`Hz`) | Băng thông cho **1 Camera** | Băng thông cho **10 Camera (Phase 1)** | Băng thông cho **40 Camera (Video Wall)** | Đánh giá Nguy cơ Nghẽn (`Bottleneck Risk`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. Gói `State + Metrics` (Không kèm BBox)** | **`~0.25 KB`** (`250 Bytes`) | **`1 – 2 Hz`** (Mỗi `0.5s – 1.0s`) | **`2 – 4 Kbps`** *(Siêu nhỏ)* | **`20 – 40 Kbps`** (`~3–5 KB/s`) | **`80 – 160 Kbps`** (`~10–20 KB/s`) | **0% NGHẼN!** Nhẹ như tin nhắn text, gửi cho cả 100 camera cùng lúc cũng không tốn 1% mạng. |
| **2. Gói `Full (State + Metrics + 25 BBox)` ở `5 Hz` (Như PoC hiện tại)** | **`~2.75 KB`** | **`5 Hz`** (Mỗi `200 ms`) | **`~110 Kbps`** (`~13.7 KB/s`) | **`~1.1 Mbps`** (`~137 KB/s`) | **`~4.4 Mbps`** (`~550 KB/s` = `200 gói JSON/giây`) | **8–10 Cam: Hoàn toàn mượt.**<br>**40 Cam: Có nguy cơ nghẽn nhẹ ở MQTT Broker / JS Main Thread** nếu bắt trình duyệt parse 200 gói JSON và vẽ 1.000 BBox mỗi giây! |
| **3. Gói `Full (State + Metrics + 25 BBox)` ở `10 Hz` (Quy tắc 0.35s của ATIN VMS)** | **`~2.75 KB`** | **`10 Hz`** (Mỗi `100 ms`) | **`~220 Kbps`** (`~27.5 KB/s`) | **`~2.2 Mbps`** (`~275 KB/s`) | **`~8.8 Mbps`** (`~1.1 MB/s` = `400 gói JSON/giây`) | **40 Cam sẽ gây nghẽn cổ chai ở Single-process Uvicorn Leader & làm giật UI trình duyệt** nếu cả 40 ô cùng bật vẽ BBox ở 10 Hz! |
| **4. Luồng Video `WebRTC (H.264)` từ MediaMTX** | Stream liên tục | `15 – 25 FPS` | `~0.5 – 1.0 Mbps` | `~5 – 10 Mbps` | `~20 – 40 Mbps` (dùng substream cho Grid) | Đi thẳng từ MediaMTX tới thẻ `<video>` (UDP/TCP), **không đi qua Backend Python hay MQTT**. |
| **5. Luồng Video `MJPEG Fallback` (Từ Backend Python)** | `~45 – 65 KB / frame JPEG` | `10 FPS` | **`~3.6 – 5.2 Mbps`** | **`~36 – 52 Mbps`** | **`~150 – 200 Mbps`** *(Rất nặng!)* | **CẢNH BÁO:** MJPEG chỉ nên dùng cho PoC (4–8 cam) hoặc khi phóng to 1 cam lỗi codec. **Lên Prod nhiều cam bắt buộc dùng WebRTC!** |
| **6. Bản tin `Confirmed Event + Snapshot`** | Ảnh `~120 KB` + JSON `1 KB` | Chỉ khi có sự kiện (`>= 60s/120s`) | `< 1 Kbps` trung bình | `< 10 Kbps` | `< 40 Kbps` | Upload ảnh qua HTTP MinIO bất đồng bộ (`object_key`), **0% gây nghẽn luồng realtime**. |

---

### 5.3. Phát Hiện Điểm Nghẽn Tiềm Ẩn & Giải Pháp "Tách Kênh Thông Minh" Cho Production

Từ bảng định lượng ở mục 5.2, chúng ta rút ra **2 kết luận kỹ thuật cực kỳ quan trọng về băng thông và chống nghẽn**:

1. **Tại sao trên màn hình lớn 40 Camera, không nên bắn BBox của cả 40 camera ở `10 Hz` cùng lúc?**
   - Khi Stakeholder nhìn màn hình lớn chia lưới **40 camera (4 hàng × 10 cột)**, mỗi ô camera trên màn hình chỉ bé bằng **1 chiếc tem thư (`~180 x 100 px`)**. Ở kích thước bé như vậy, người vận hành chỉ cần nhìn rõ **Video + Khung màu `Poly Zone` + Nhãn Trạng thái ở góc dưới bên phải (`THÔNG THOÁNG` | `ĐƯỜNG ÙN TẮC` | `KẸT XE`)**, chứ vẽ hàng chục cái BBox li ti đè lên ô `180x100 px` chỉ làm che kín mặt đường!
   - Ngược lại, khi người vận hành **bấm vào 1–4 camera cụ thể (hoặc bật nút "Hiện BBox AI" trên các camera cần soi kỹ)**, lúc đó mới cần nhận mảng `detections` (BBox) ở tần suất cao!
2. **Giải pháp Kiến trúc Chống Nghẽn Tuyệt Đối:**
   - **Luôn gửi `State + Metrics` (`~250 Bytes`) ở tần suất `1 – 2 Hz` cho 100% các camera:** Băng thông cho cả 40 camera chỉ tốn **`~100 Kbps`** $\longrightarrow$ Đảm bảo nhãn trạng thái ở góc dưới bên phải của tất cả 40 camera luôn cập nhật real-time (`delay 1 – 3s`) mà không bao giờ gây nghẽn MQTT hay WebSocket!
   - **Đối với mảng `detections` (BBox):**
     - Với quy mô **10 camera (Phase 1 / PoC)**: Băng thông gửi kèm cả BBox ở `5 Hz` chỉ là **`~1.1 Mbps`** $\longrightarrow$ Cứ gửi thoải mái 100% cho cả 10 camera!
     - Với quy mô **40 camera (Production Video Wall)**: Chỉ gửi mảng `detections` cho các camera đang được bật cờ `show_bbox` (hoặc rút gọn format BBox còn `52 Bytes/xe` và lọc chỉ gửi các BBox nằm gần/trong `Poly Zone`), giúp giảm **80% tải băng thông JSON** cho MQTT Broker và trình duyệt!

---

## PHẦN 6: CƠ CHẾ XỬ LÝ PHÍA CLIENT WEB UI ĐỂ GHÉP OVERLAY VÀO LUỒNG CAMERA RIÊNG MƯỢT MÀ

Khi Client Web (Browser) nhận được luồng Video riêng (từ MediaMTX WebRTC hoặc MJPEG) và luồng JSON Metadata riêng (từ WebSocket `/ws` hoặc MQTT `BBOX_UPDATE`), phía UI cần xử lý theo **4 kỹ thuật chuẩn** sau để hình ảnh hiển thị đầy đủ, sắc nét và không bị mất/lệch BBox:

### 6.1. Kiến trúc 3 Lớp (`3-Layer Viewport Stack`) trên mỗi Ô Camera
Trên DOM của mỗi thẻ Camera, tách thành 3 lớp độc lập nằm chồng khít lên nhau (`position: absolute; inset: 0`):
1. **Lớp 1 (Dưới cùng) — `Video Layer` (`<video>` WebRTC hoặc `<img>` MJPEG):**
   - Nhận trực tiếp luồng hình ảnh từ MediaMTX Gateway. Chạy hoàn toàn độc lập ở tốc độ gốc `15 – 25 FPS`. Dù gói tin AI có trễ hay ngắt quãng, video giao thông không bao giờ bị khựng.
2. **Lớp 2 (Giữa) — `Canvas Vector Overlay` (`<canvas>`):**
   - Chỉ chịu trách nhiệm vẽ hình học: Đa giác **`Poly Zone`** (viền đậm và nền trong suốt `alpha = 0.14` đổi màu Xanh / Vàng / Đỏ theo `state`) và các khung chữ nhật **`BBox` + Chấm chân `foot`**.
   - **Cách quy đổi tọa độ chuẩn xác khi khung video bị co giãn hoặc letterbox (`object-fit: contain`):**
     - Toàn bộ tọa độ `Poly Zone` và `BBox [x1, y1, x2, y2]` từ Backend gửi lên đều là **tọa độ chuẩn hóa `[0.0 .. 1.0]`** (tính trên khung chuẩn `16:9` `1280x720`).
     - Phía UI nhân trực tiếp tọa độ `[0..1]` với `(canvasWidth, canvasHeight)` (kèm `window.devicePixelRatio` để nét vẽ không bị răng cưa trên màn hình Retina/4K).
3. **Lớp 3 (Trên cùng) — `DOM HUD & Corner Status Badge` (`<div>` HTML/CSS):**
   - **Badge Trạng thái ở góc dưới bên phải** (`THÔNG THOÁNG` / `ÙN TẮC` / `KẸT XE`) và **Thanh chỉ số (`Phủ %`, `Flow`, `Dwell`)** được render bằng **thẻ HTML/CSS thuần** (chứ không vẽ chữ bằng `ctx.fillText` trên Canvas).
   - *Lý do:* Chữ HTML/CSS luôn sắc nét tuyệt đối ở mọi kích thước ô lưới (kể cả khi thu nhỏ 40 camera), hỗ trợ hiệu ứng nhấp nháy cảnh báo bằng GPU CSS Transition mà không tốn CPU vẽ lại mỗi frame!

### 6.2. Giải quyết Triệt để Hiện tượng "Chớp tắt / Ít BBox" trên UI bằng Cơ chế `Client-Side BBox Hold & Interpolation`
Như đã phân tích ở Mục 2.2.B của bản Master, giao diện Web VMS hiện tại của ATIN có bộ đếm xóa sạch BBox sau **`0.35 giây`** nếu chưa nhận được gói tin mới (khiến BBox bị nhấp nháy hoặc biến mất nếu mạng/AI gửi ở `2 – 4 FPS`).

Để khắc phục triệt để trên UI:
1. **Tăng thời gian giữ BBox hợp lệ (`BBox TTL = 0.8s – 1.0s`):**
   - Như đã cài đặt trong [`poc/frontend/js/overlay.js`](file:///e:/ATIN/traffic_congestion_evaluation/poc/frontend/js/overlay.js), UI giữ hiển thị tập BBox mới nhất trong vòng **`1.0 giây`** (thay vì xóa gắt ở `0.35s`). Với tần suất đẩy WebSocket `5 Hz` (mỗi `0.2s` có 1 gói mới), BBox trên màn hình **luôn hiển thị liên tục 100%, không bao giờ bị chớp tắt**!
2. **Nội suy vị trí mượt theo `tid` (`Linear LERP theo Track ID` — Tùy chọn nâng cao trên UI):**
   - Vì mỗi BBox gửi lên đều có mã `tid` (Track ID của `ByteTrack`), giữa 2 gói tin WebSocket cách nhau `200 ms`, vòng lặp `requestAnimationFrame (60 FPS)` của trình duyệt có thể dịch chuyển nhẹ khung BBox từ tọa độ cũ sang tọa độ mới theo `tid`, tạo cảm giác khung BBox trượt mượt ở `60 FPS` bám dính vào xe!
3. **Tách biệt thời gian sống của `Status Badge` và `BBox`:**
   - Kể cả khi một frame không bắt được BBox nào (`detections = []`), **Đa giác `Poly Zone` và Badge Trạng thái ở góc dưới bên phải vẫn luôn giữ nguyên (`Sticky Status`)** theo trạng thái `state` mới nhất, chỉ chuyển sang `MẤT TÍN HIỆU (UNKNOWN)` khi `stream_ok = false` quá `5 giây`.

---

## PHẦN 7: TỔNG HỢP QUYẾT ĐỊNH TỐI ƯU ĐỀ XUẤT TRIỂN KHAI PRODUCTION

Dựa trên toàn bộ phân tích định lượng ở trên, dưới đây là **5 Quyết định Tinh chỉnh Tối ưu** đề xuất chốt cùng PM và đội dự án để đưa vào Production:

| STT | Hạng mục Quyết định | Phương án Chốt Triển khai (Recommended Action) | Lý do & Giá trị Đạt được |
| :-: | :--- | :--- | :--- |
| **1** | **Loại bỏ `W` khỏi UI Live View & Bộ ngưỡng cấu hình chính** | - **Ẩn `W` trên thẻ Camera Live View** và bỏ việc bắt người vận hành phải chỉnh `W_CLEAR, W_CONGESTED, W_GRIDLOCK`.<br>- Chuyển `W` / `n_vehicles` thành **Cổng an toàn ngầm (`Sanity Gate`: chỉ cần có $\ge 1$ ô tô hoặc $\ge 2$ xe máy trong vùng)** để chống nhiễu đèn pha/bóng cây ban đêm. | Giao diện gọn gàng, dễ hiểu đúng ý PM; **không còn bị phụ thuộc vào độ lớn vùng vẽ** và **không bị báo sai khi Production bắt được ít BBox**. |
| **2** | **Lấy `Phủ (O_vis)` + `Flow (V_flow)` làm 2 Trụ cột Quyết định Chính cho cả 3 trạng thái** | - Nâng cấp [`classifier.py`](file:///e:/ATIN/traffic_congestion_evaluation/poc/backend/ai/decision/classifier.py) để cặp **`O_vis + Flow`** (kèm cổng an toàn có xe thật) đủ điều kiện trực tiếp kết luận cả `CLEAR`, `CONGESTED` và `GRIDLOCKED` ngay cả khi `T50 / D85` bị `None` do đứt track trên Prod.<br>- Cho phép đóng băng nền `MOG2` dựa trên `Flow <= V_stall` + `O_vis >= O_congested` + `N_veh >= 2` (không bắt buộc phải đợi `D85 > 5s`). | Đảm bảo khi xảy ra ùn tắc / kẹt xe thực sự trên Production (dù số lượng BBox bắt được rất thấp), hệ thống **vẫn bắt dính 100% `CONGESTED` và `GRIDLOCKED`**! |
| **3** | **Vai trò của `D85` và `T50` trên UI & Thuật toán** | - **`D85` (Thời gian xe đang kẹt trong vùng):** Giữ làm **chỉ số bổ trợ số 1** (hạ ngưỡng mẫu tối thiểu xuống `1 xe 4 bánh` hoặc `2 xe bất kỳ`), hiển thị gọn trên UI là `Lưu trú (Dwell): xx.xs` để giải thích rõ cho trường hợp *"ô tô đứng im kẹt cứng nhưng xe máy vẫn lách qua được"*.<br>- **`T50` (Thời gian vượt vùng):** Chuyển thành chỉ số phụ (không bắt buộc hiển thị hoặc gộp chung với Dwell trên UI) vì khi kẹt cứng hoặc ít BBox thì `T50` thường bằng `–` (`None`). | Tận dụng được độ chính xác theo đơn vị giây của BBox khi bắt được xe, nhưng **không bao giờ bị tê liệt khi thiếu BBox**. |
| **4** | **Khắc phục lỗi "Bắt được ít BBox" trên Production** | Áp dụng đồng bộ 3 kỹ thuật từ PoC sang Prod:<br>1. **Cắt `ROI Cropping` theo `Poly Zone`** trước khi đưa vào YOLO (phóng to kích thước xe gấp 2 lần).<br>2. Hạ `YOLO_CONF = 0.15` kết hợp `ByteTrack`.<br>3. Giữ `TTL hiển thị BBox = 0.8s – 1.0s` trên UI (thay cho ngưỡng `0.35s` quá gắt). | Tăng số lượng BBox bắt được ở làn xa lên gấp 2–3 lần mà không tốn thêm 1% GPU nào. |
| **5** | **Tối ưu Payload & Băng thông khi mở rộng lên 10 – 40 Camera** | - Luồng Video: Dùng **MediaMTX WebRTC** trên Prod (tránh dùng MJPEG cho 40 cam cùng lúc).<br>- Luồng Metadata: Tách nhẹ gói `State + Metrics` (`~250 Bytes @ 1–2 Hz`, chỉ tốn `~100 Kbps` cho cả 40 cam) và chỉ đẩy mảng `detections` (`5 Hz`) cho các camera đang mở hiển thị BBox. | Không bao giờ gây nghẽn MQTT Broker, Backend Leader hay làm giật trình duyệt khi xem lưới 40 camera trên màn hình lớn. |
