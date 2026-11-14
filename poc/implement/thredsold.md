### 1. Nhóm W\_\* (W_CLEAR, W_CONGESTED, W_GRIDLOCK, W_RESCUE) — Điểm tải xe trong Poly Zone

W được tính từ cái gì?

- Ở mỗi khung hình, hệ thống nhìn vào điểm chân (đáy khung bbox) của từng xe. Xe nào có điểm chân nằm
  bên trong Poly Zone thì được cộng điểm theo mức độ chiếm mặt đường: - 1 xe máy / xe đạp = 1 điểm (WEIGHT\*2W=1.0) - 1 ô tô con = 3 điểm (WEIGHT_CAR=3.0) - 1 xe buýt / xe tải = 6 điểm (WEIGHT_HEAVY=6.0)
- Cộng tất cả lại rồi làm mượt nhẹ trong ~3 giây để số không bị nhảy giật khi YOLO chớp tắt 1–2 frame → ra chỉ số W hiển thị dưới ô camera.

- **_Ví dụ_**: Trong Poly Zone đang có 3 ô tô + 6 xe máy → W = 3×3 + 6×1 = 15.0. Ý nghĩa các ngưỡng và cách chỉnh:
  - `W_CLEAR=12.0`: Dưới mức này (và độ phủ cũng thấp) thì xem như đường vắng/thoáng, kết luận ngay CLEAR.
  - `W_CONGESTED=15.0`: Từ mức này trở lên (tương đương ~5 ô tô con, hoặc 3 ô tô + 6 xe máy) là đủ đông để xét ùn tắc (nhưng vẫn phải kiểm tra xem xe có chạy chậm không).
  - `W_GRIDLOCK=24.0`: Mật độ rất cao (tương đương ~8 ô tô con, hoặc 4 ô tô + 12 xe máy) để đủ điều kiện xét kẹt cứng.
  - `W_RESCUE=18.0`: Mức mật độ tối thiểu dùng cho nhánh cứu nguy (Macro Rescue) khi xe xếp kín làm Tracker bị đứt ID.

> Mẹo chỉnh W\*\* theo từng camera: Vì W là tổng điểm tuyệt đối trong Poly Zone (không chia cho diện tích), nên Poly Zone vẽ càng rộng thì W càng cao. Cách chỉnh chuẩn nhất là mở video lúc đường thoáng, lúc hơi ùn, lúc kẹt cứng → nhìn con số W: xx.z hiện ngay dưới ô camera rồi đặt W_CLEAR / W_CONGESTED / W_GRIDLOCK bám theo con số thực tế đó.

### 2. Nhóm O\_\* (O_CLEAR, O_CONGESTED, O_GRIDLOCK, O_MACRO_STALL, O_RESCUE) — Độ phủ mặt đường

O_vis được tính từ cái gì?

- Hệ thống lấy phần diện tích xe do MOG2 (vật thể nổi bật trên nền đường) gộp với khung bbox của YOLO, rồi tính xem phần đó che kín bao nhiêu phần trăm diện tích Poly Zone.
- Trên giao diện hiển thị là Phủ: nm%, còn trong .env viết dạng 0..1 (ví dụ 0.35 = 35%).
- Khác với W, O_vis đã tự chia cho diện tích Poly Zone, nên ít bị lệch hơn khi bạn vẽ zone to hay nhỏ.

Ý nghĩa từng ngưỡng:

- `O_CLEAR=0.35`: Nếu W < 12.0 và độ phủ < 35% → chốt ngay CLEAR (tránh trường hợp ban đêm có 1 chiếc xe đậu im 1 chỗ bị báo kẹt).
- `O_CONGESTED=0.45`: Mặt đường bị che phủ >= 45% là đạt ngưỡng đông của CONGESTED (lưu ý: giữa W >= 15 và O_vis >= 45%, chỉ cần 1 trong 2 đạt là đủ điều kiện mật độ).
- `O_GRIDLOCK=0.65`: Mặt đường bị che phủ >= 65% là đạt ngưỡng đông của `GRIDLOCKED`.
- `O_MACRO_STALL=0.70`: Bình thường để chốt `GRIDLOCKED`, tốc độ dòng chảy phải gần như đứng im (V_flow <=1.0). Nhưng nếu độ phủ đã lên tới >= 70% (rất kín đường), hệ thống vẫn cho phép chốt `GRIDLOCKED` dù chỉ số Flow còn dao động nhẹ.
- `O_RESCUE=0.75`: Khi mặt đường kín đặc >= 75%, W >= 18 và dòng chảy đứng im (V_flow <= 1.0), hệ thống bỏ qua T50/D85 và chốt thẳng `GRIDLOCKE`D` (cứu nguy trường hợp kẹt quá đặc làm ByteTrack mất dấu xe).

### 3. Nhóm CONGESTED*T50*_ và CONGESTED*D85*_ — Thời gian đi qua và thời gian bị giữ chân

Chỉ đông xe (W hoặc O_vis cao) chưa chắc là tắc — nếu dòng xe vẫn chạy nhanh thì vẫn là CLEAR. Vì vậy hệ
thống phải đo thêm tốc độ thoát xe bằng 2 chỉ số thời gian (tính bằng giây):

- `T50` (Thời gian đi xuyên qua zone): Đo những xe đã vào và thoát ra khỏi Poly Zone trong 15 giây gần nhất (cần tối thiểu 3 xe hoàn thành), lấy mức ở giữa (trung vị).
  - `CONGESTED_T50_4W_S=3.0` / `CONGESTED_T50_2W_S=3.0`: Trung bình 1 xe 4 bánh (hoặc 2 bánh) mất hơn 3 giây mới đi hết đoạn Poly Zone.
- `D85` (Thời gian xe đang nằm kẹt bên trong zone): Nhìn những xe vẫn đang kẹt trong zone chưa thoát ra được (nằm trong zone từ 1.5s trở lên, cần tối thiểu 2 xe), lấy mốc 85% (nhóm xe bị kẹt lâu nhất).
  - `CONGESTED_D85_4W_S=5.0` / `CONGESTED_D85_2W_S=4.5`: Có nhóm ô tô đang bị giữ chân trong zone hơn 5 giây (hoặc xe máy hơn 4.5 giây) chưa ra được.

_(Ở nhánh `CONGESTED`, chỉ cần 1 trong 4 ngưỡng `T50/D85` này vượt mức — hoặc Flow nằm trong khoảng chậm `1.0 < Flow < 6.0` khi `Phủ >= 45%` — là hệ thống kết luận `CONGESTED`.)_

> Mẹo chỉnh T50 / D85 theo độ dài Poly Zone:
>
> - Nếu bạn vẽ Poly Zone dài (đoạn đường 40–50m), xe chạy bình thường cũng có thể mất 3–4 giây mới đi hết → nên tăng `CONGESTED_T50_*` lên (ví dụ 4.5–6.0) để tránh báo nhầm lúc đường thoáng.
> - Nếu bạn vẽ Poly Zone ngắn (chỉ khoanh đúng cổ chai 15–20m), xe chạy qua chỉ mất 1–2 giây → giữ 3.0s hoặc giảm nhẹ sẽ bắt ùn tắc nhạy hơn.
