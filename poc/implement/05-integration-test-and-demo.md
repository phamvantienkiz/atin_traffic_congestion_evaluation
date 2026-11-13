# 05 — TÍCH HỢP, KIỂM THỬ, TINH CHỈNH NGƯỠNG & KỊCH BẢN DEMO — GIAI ĐOẠN G5

> Đọc trước: [00](./00-overview-and-decisions.md). Dùng công cụ `ai/tools/run_video.py` ([02](./02-ai-pipeline.md) B11).

## 1. Chuẩn bị dữ liệu thật (làm song song từ G1)
1. Chọn 4–8 camera có đủ tình huống: đường nhiều làn hỗn hợp, gần nút có đèn, có trạm xe bus gần camera, có bóng cây.
2. Ghi video 10–15 phút mỗi camera ở 3 khung: thấp điểm (10h), cao điểm (7h–8h / 17h–18h30), tối (19h–20h):
   ```bash
   ffmpeg -rtsp_transport tcp -i rtsp://127.0.0.1:8554/cam1 -t 900 -c copy samples/cam1_peak.mp4
   ```
   (Nếu không có ffmpeg trên server: dùng OpenCV `VideoWriter` trong một script nhỏ.)
3. Với mỗi video, ghi chú thủ công nhãn thực tế theo mốc thời gian vào `samples/labels.csv`: `video,start_s,end_s,label` (`CLEAR/CONGESTED/GRIDLOCKED`). Mỗi đoạn ≥ 30 s. Mục tiêu tổng ≥ 2 giờ video có nhãn.

## 2. Tinh chỉnh ngưỡng (offline)
1. Chạy `run_video.py` cho mọi video → có `*_metrics.csv`.
2. Viết `ai/tools/evaluate.py`: ghép `metrics.csv` với `labels.csv` theo thời gian, in **confusion matrix** 3 lớp (bỏ `UNKNOWN`), accuracy, và bảng thống kê `median/p10/p90` của `t50_4w, d85_4w, t50_2w, d85_2w, o_vis, v_flow, w_total` theo từng nhãn.
3. Từ bảng thống kê, chỉnh ngưỡng trong `config.py` sao cho các nhãn tách nhau rõ nhất. Thứ tự chỉnh: `w_clear/o_clear` → `v_stall/v_clear` → ngưỡng thời gian → `o_gridlock`.
4. Lặp lại tới khi đạt mục tiêu mục 4. Ghi lại bộ ngưỡng cuối và lý do vào `poc/implement/tuning-log.md`.

> Lưu ý: `v_flow` (px/s) phụ thuộc góc camera. Nếu một camera lệch quá nhiều, cho phép ghi đè ngưỡng theo camera: thêm trường tùy chọn `"overrides": {"v_clear": 4.0}` trong `cameras.json` và `CameraProcessor` dùng `dataclasses.replace(CFG, **overrides)`. Chỉ làm nếu thật cần.

## 3. Kiểm thử hệ thống (online, trên server)

| # | Kịch bản | Cách làm | Kỳ vọng |
| :-: | :-- | :-- | :-- |
| T1 | Tải 8 camera | Chạy 30 phút, theo dõi log batcher + `nvidia-smi -l 5` | FPS/cam ≥ 13, batch ≤ 45 ms, VRAM ≤ 2.5 GB, RAM không tăng dần |
| T2 | Mất luồng | Xóa/ sửa sai URL 1 camera hoặc rút mạng camera | Ô đó `MẤT TÍN HIỆU` ≤ 6 s, ô khác bình thường; khôi phục tự động |
| T3 | Restart AI | Ctrl+C rồi chạy lại `run.sh` | Cấu hình & zone còn; video trong iframe tự lên lại sau reload |
| T4 | Đường vắng ban đêm | Video tối có xe đỗ ven đường | Không có event giả |
| T5 | Đèn đỏ | Camera có đèn, `has_traffic_light=true` | Không có event trong chu kỳ đèn bình thường |
| T6 | Xe bus che | Camera cạnh trạm bus | Badge giữ trạng thái cũ + nhãn "(che khuất)", không nhảy về THÔNG THOÁNG |
| T7 | Kẹt cứng | Video cao điểm kẹt | Badge KẸT XE ≤ 10 s sau khi xe đứng; event sau ngưỡng xác nhận |
| T8 | Laptop qua tunnel | Chỉ dùng Termius tunnel, không IP trực tiếp | WebRTC + WS chạy; băng thông laptop ≤ 5 Mbps cho 8 cam |

## 4. Tiêu chí nghiệm thu PoC Phase 1
- [ ] Accuracy 3 lớp trên tập nhãn ≥ **80%**; nhầm `CLEAR ↔ GRIDLOCKED` ≤ **3%**.
- [ ] Event giả ≤ **1 / camera / giờ** trong khung thấp điểm.
- [ ] Độ trễ badge (từ lúc tình trạng đổi trên video tới lúc badge đổi) ≤ **10 s**.
- [ ] T1–T8 đạt.

## 5. Kịch bản demo cho cấp trên (≈ 15 phút)
**Chuẩn bị trước 30 phút:** bật VPN + tunnel, `tmux attach -t poc` kiểm tra server chạy, mở `http://localhost:8080` trên Chrome, bật 🔔, chọn layout 8, `DEMO_MODE=1` (xác nhận 15 s/30 s). Mở sẵn tab dự phòng video debug (`out/*_debug.mp4`) trên laptop phòng khi mạng lỗi.

1. **(2 phút) Bối cảnh:** lưới 8 camera thật real-time; luồng xem đi qua MediaMTX WebRTC, AI xử lý luồng 720p@15FPS riêng trên GPU A400 — giống kiến trúc ATIN.
2. **(3 phút) Vẽ zone trực tiếp:** chọn 1 camera, bấm ✏️, chấm 4 điểm theo 2 vạch + 2 khoảng trống, Lưu → chỉ số bắt đầu chạy ngay.
3. **(4 phút) Giải thích chỉ số trên card:** W (mật độ), T50 (thời gian qua vùng của xe đã đi qua), D85 (thời gian xe đang kẹt trong vùng), Phủ & Flow (phương án bổ trợ). Chỉ ra camera ô tô đứng nhưng xe máy vẫn lách → ÙN TẮC chứ không phải KẸT XE.
4. **(3 phút) Sự kiện:** chờ/chỉ một camera đang ùn tắc → thẻ sự kiện có ảnh xuất hiện, chuông kêu.
5. **(2 phút) Độ bền:** xe bus đi qua → badge giữ nguyên "(che khuất)"; (tùy chọn) ngắt 1 camera → MẤT TÍN HIỆU, không báo thông thoáng sai.
6. **(1 phút) Tài nguyên:** cửa sổ Termius chạy `nvidia-smi` → 8 camera chỉ dùng ~2 GB VRAM trên card 4 GB; lộ trình mở rộng 40 camera.

## 6. Sau demo
- Tắt `DEMO_MODE`. Ghi kết quả, góp ý vào `poc/implement/demo-feedback.md`.
- Commit checkpoint (không commit `cameras.json` chứa mật khẩu RTSP, snapshot, video mẫu).
