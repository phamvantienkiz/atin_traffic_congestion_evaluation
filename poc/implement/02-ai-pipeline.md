# 02 — PHÂN HỆ AI (`poc/backend/ai/`) — GIAI ĐOẠN G1 + G2

> Đọc trước: [00-overview-and-decisions.md](./00-overview-and-decisions.md) mục 2 (D3, D5–D10) và mục 4.2 (`CameraResult`).
> Mục tiêu: package Python `ai` (nằm trong `poc/backend/ai/`) nhận URL RTSP + zone, xuất `CameraResult` mỗi chu kỳ cho mọi camera.

## 1. Cấu trúc file

```text
poc/backend/ai/
├── __init__.py
├── config.py                   # B1: toàn bộ ngưỡng & tham số
├── geometry.py                 # B2: zone, ROI crop, chuyển tọa độ
├── ingestion/
│   ├── __init__.py
│   └── stream_reader.py        # B3: đọc RTSP -> 720p, 15 FPS, buffer=1
├── core_pipeline/              # PHƯƠNG ÁN 1
│   ├── __init__.py
│   ├── detector.py             # B4: YOLO batch FP16 (.pt / .onnx)
│   ├── tracker.py              # B5: ByteTrack + Majority Class Voting
│   └── zone_time.py            # B6: W_total, T50, D85
├── aux_pipeline/               # PHƯƠNG ÁN 2
│   ├── __init__.py
│   └── flow_occupancy.py       # B7: O_vis (MOG2) + V_flow (Farneback)
├── decision/
│   ├── __init__.py
│   ├── occlusion.py            # B8: Occlusion shield
│   ├── classifier.py           # B8: luật 3 trạng thái
│   └── state_machine.py        # B9: Provisional + Confirmed + Hysteresis
├── engine/
│   ├── __init__.py
│   ├── camera_processor.py     # B10: ghép mọi thứ cho 1 camera
│   ├── gpu_batcher.py          # B10: vòng lặp 66.7ms đa camera
│   └── engine.py               # B10: API công khai cho backend
└── tools/
    ├── run_video.py            # B11: chạy offline trên file video, xuất video debug
    └── export_onnx.py          # tùy chọn
```

Quy ước: type hints đầy đủ, `logging.getLogger(__name__)`, không `print`. Mọi thời gian nội bộ dùng `time.monotonic()`.

---

## B1. `config.py` — tham số tập trung

```python
import os
from dataclasses import dataclass, field

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

@dataclass(frozen=True)
class AIConfig:
    model_path: str = os.getenv("MODEL_PATH", "../../models/vehicle_n_best.pt")
    device: str = os.getenv("DEVICE", "cuda:0")
    imgsz: int = 640
    conf: float = 0.15            # thấp để ByteTrack dùng detection yếu
    iou: float = 0.5
    frame_w: int = 1280
    frame_h: int = 720
    target_fps: float = 15.0
    roi_padding: float = 0.10

    # ĐÃ XÁC NHẬN từ models/vehicle_n_best.pt: names = {0: 'bus', 1: 'car', 2: 'motobike', 3: 'truck'}
    # Lưu ý tên lớp xe máy trong checkpoint là "motobike" (thiếu chữ r).
    # Giữ kèm "motorcycle", "motorbike", "bicycle" để tương thích tự động nếu đổi sang model dự phòng yolo26s.pt.
    class_groups: dict = field(default_factory=lambda: {
        "motobike": "2W", "motorcycle": "2W", "motorbike": "2W", "bicycle": "2W",
        "car": "4W", "bus": "4W", "truck": "4W",
    })
    class_weights: dict = field(default_factory=lambda: {
        "motobike": 1.0, "motorcycle": 1.0, "motorbike": 1.0, "bicycle": 1.0,
        "car": 3.0, "bus": 6.0, "truck": 6.0,
    })
    heavy_classes: tuple = ("bus", "truck")

    # Tracker
    track_buffer_s: float = 2.5
    track_activation_conf: float = 0.45
    match_thresh: float = 0.8

    # Zone time (cho Poly Zone 18-22m = 3 vạch + 2-3 khoảng trống)
    window_s: float = 30.0            # cửa sổ 30s để giữ đủ mẫu xe đi chậm 15-20s
    min_dwell_s: float = 2.0          # bỏ xe mới vào < 2.0s khỏi D85
    min_travel_ratio: float = 0.45    # dịch chuyển >= 45% chiều dọc zone mới tính Completed
    min_completed_samples: int = 2
    min_active_samples: int = 2
    lost_timeout_s: float = 1.0       # track không thấy > 1s coi là đã rời

    # Aux (trên flow_zone_px mở rộng +20% hai đầu dọc trục đường)
    aux_w: int = 320
    aux_h: int = 180
    flow_zone_extend_ratio: float = 0.20
    mog2_lr_normal: float = 0.005
    flow_noise_px: float = 0.8        # px/frame trên ảnh 320x180
    v_stall: float = 6.0              # px/s (ngưỡng kẹt Macro-only khi thiếu T50/D85)
    v_gridlock_max: float = 15.0      # px/s (ngưỡng Flow tối đa cho GRIDLOCKED khi có T50/D85)
    v_congested_macro: float = 14.0   # px/s (ngưỡng ùn tắc Macro-only khi thiếu T50/D85)
    v_congested_max: float = 18.0     # px/s (ngưỡng Flow tối đa cho CONGESTED khi có T50/D85)
    v_clear_min: float = 10.0         # px/s (ngưỡng Flow lưu thông bình thường)

    # Luật trạng thái V2 (Bỏ ngưỡng cứng W_*, dùng O_vis + Flow + T50/D85; W làm Sanity Gate & Confidence)
    w_sanity_min: float = 3.0         # >= 1 ô tô hoặc >= 3 xe máy để chống nhiễu đèn pha đêm mưa
    o_clear: float = 0.40             # < 40%: đường vắng/thoáng; 40%..70%: đông lưu thông TB
    o_congested: float = 0.70         # >= 70% (70%..85%): độ phủ đường ùn tắc
    o_gridlock: float = 0.85          # >= 85%: độ phủ đường kẹt cứng

    # Ngưỡng thời gian T50 / D85 (giây) ranh giới CLEAR -> CONGESTED
    congested_t50_4w_s: float = 5.5
    congested_d85_4w_s: float = 6.5
    congested_t50_2w_s: float = 4.5
    congested_d85_2w_s: float = 5.0

    # Ngưỡng thời gian T50 / D85 (giây) ranh giới CONGESTED -> GRIDLOCKED
    gridlock_t50_4w_s: float = 16.0
    gridlock_d85_4w_s: float = 20.0
    gridlock_t50_2w_s: float = 13.5
    gridlock_d85_2w_s: float = 17.0

    # Occlusion
    heavy_area_ratio: float = 0.45
    bbox_drop_ratio: float = 0.65
    occ_o_vis: float = 0.72
    occ_hold_max_s: float = 40.0

    # State machine & Chu kỳ bắn sự kiện (3p -> +2p (5p) -> mỗi +15p & Chuyển trạng thái)
    smooth_window_s: float = 5.0
    stream_timeout_s: float = 5.0
    red_light_hold_s: float = 15.0 if DEMO_MODE else 90.0
    confirm_state_s: float = 30.0 if DEMO_MODE else 180.0
    followup_after_confirm_s: float = 20.0 if DEMO_MODE else 120.0
    periodic_reminder_s: float = 90.0 if DEMO_MODE else 900.0
    persistence_tolerance_s: float = 5.0
    exit_clear_s: float = 10.0

CFG = AIConfig()
```

**Xong khi:** `uv run python -c "from ai.config import CFG; print(CFG)"` chạy được (từ thư mục `poc/backend`).

---

## B2. `geometry.py`

Hàm cần viết:
```python
import numpy as np, cv2

def zone_to_px(zone: list[dict], w: int, h: int) -> np.ndarray:
    """[{x,y}] chuẩn hóa -> np.int32 (N,2) pixel."""

def roi_from_zone(zone_px: np.ndarray | None, w: int, h: int, pad: float) -> tuple[int,int,int,int]:
    """Trả (x0,y0,x1,y1). Nếu zone None/<3 điểm -> (0,0,w,h). Mở rộng pad*(kích thước bbox zone), kẹp trong khung."""

def zone_axis_length(zone_px: np.ndarray) -> float:
    """Chiều dọc zone (pixel) = khoảng cách giữa trung điểm cạnh trên và trung điểm cạnh dưới.
    Cách đơn giản: sắp xếp đỉnh theo y; lấy trung bình y của 2 đỉnh nhỏ nhất và 2 đỉnh lớn nhất,
    trung bình x tương ứng; trả khoảng cách Euclid. Dùng cho min_travel_ratio."""

def point_in_zone(zone_px: np.ndarray, pt: tuple[float,float]) -> bool:
    return cv2.pointPolygonTest(zone_px, pt, False) >= 0

def zone_mask(zone_px: np.ndarray | None, w: int, h: int) -> np.ndarray:
    """uint8 mask 0/255. zone None -> toàn 255."""

def extend_zone_longitudinal(zone_px: np.ndarray | None, w: int, h: int, ratio: float = 0.20) -> np.ndarray | None:
    """Kéo giãn đa giác dọc theo trục đường thêm ratio (+20%) ở cả đầu trên và đầu dưới, giữ nguyên bề ngang."""
```

**Xong khi:** viết `poc/backend/ai/tests/test_geometry.py` (pytest) kiểm tra: ROI kẹp biên đúng, point trong/ngoài, axis length của hình chữ nhật 100x200 dọc = 200.

---

## B3. `ingestion/stream_reader.py` — đọc RTSP chuẩn 720p @ 15 FPS

```python
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")

@dataclass
class FramePacket:
    frame: np.ndarray       # BGR 1280x720
    seq: int
    t_mono: float           # monotonic lúc nhận

class StreamReader:
    def __init__(self, camera_id: str, url: str, w=1280, h=720, fps=15.0): ...
    def start(self) -> None   # thread daemon
    def stop(self) -> None
    def latest(self) -> FramePacket | None   # thread-safe, trả bản mới nhất (không copy lại nếu seq cũ)
    @property
    def healthy(self) -> bool  # có frame trong 5s gần nhất
    @property
    def fps(self) -> float     # FPS thực tế sau lấy mẫu
```
Logic vòng lặp:
1. `cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)`; `cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)`.
2. Lặp `cap.grab()` liên tục (để không dồn buffer). Chỉ khi `now - last_emit >= 1/fps - 0.005` mới `cap.retrieve()`, `cv2.resize(..., (1280,720), interpolation=cv2.INTER_AREA)` (bỏ resize nếu đã đúng kích thước), ghi vào `self._latest` dưới `threading.Lock`, `seq += 1`.
3. `grab()` thất bại → release, `sleep(2)`, kết nối lại; log warning. Vòng lặp kết thúc khi `stop()`.

**Xong khi:** script nhỏ đọc `rtsp://127.0.0.1:8554/cam1` trong 10 s cho `fps ≈ 14.5–15`, kích thước `1280x720`.

---

## B4. `core_pipeline/detector.py` — YOLO batch

```python
@dataclass
class Det:
    xyxy: np.ndarray   # (N,4) float32 pixel KHUNG 1280x720 (đã cộng offset ROI)
    conf: np.ndarray   # (N,)
    cls_name: list[str]

class Detector:
    def __init__(self, cfg: AIConfig):
        self.model = YOLO(cfg.model_path)          # .pt hoặc .onnx đều được
        self.half = cfg.device.startswith("cuda") and cfg.model_path.endswith(".pt")
        self.names = self.model.names
        # warmup: predict 1 ảnh đen 640x640

    def detect_batch(self, crops: list[np.ndarray], offsets: list[tuple[int,int]]) -> list[Det]:
        results = self.model.predict(crops, imgsz=cfg.imgsz, conf=cfg.conf, iou=cfg.iou,
                                     half=self.half, device=cfg.device, verbose=False)
        # Với mỗi r: boxes = r.boxes.xyxy.cpu().numpy(); cộng (ox,oy) vào x và y;
        # bỏ các class không nằm trong cfg.class_groups.
        # Khi khởi động: kiểm tra model.names có ít nhất 1 lớp thuộc nhóm "2W" và 1 lớp thuộc nhóm "4W",
        # nếu không khớp -> raise RuntimeError rõ ràng (tránh lặng lẽ mất toàn bộ xe 2 bánh).
```
Lưu ý: list crop có kích thước khác nhau vẫn được Ultralytics letterbox từng ảnh rồi chạy chung 1 batch.

`tools/export_onnx.py` (tùy chọn): `YOLO(path).export(format="onnx", dynamic=True, half=False, simplify=True, imgsz=640)` rồi đặt `MODEL_PATH=...onnx`. (ONNX FP16 + dynamic hay lỗi, dùng FP32 ONNX cho an toàn.)

**Xong khi:** đo `detect_batch` với 8 crop: thời gian ≤ 40 ms trên A400 (log trung bình 100 lần).

---

## B5. `core_pipeline/tracker.py` — ByteTrack + Majority Voting

```python
import supervision as sv

@dataclass
class Track:
    tid: int
    xyxy: np.ndarray
    conf: float
    cls_name: str      # nhãn đã bỏ phiếu
    group: str         # "2W"/"4W"
    foot: tuple[float,float]  # bottom-center pixel

class CameraTracker:
    def __init__(self, cfg, fps=15.0):
        self.bt = sv.ByteTrack(track_activation_threshold=cfg.track_activation_conf,
                               lost_track_buffer=round(cfg.track_buffer_s * fps),
                               minimum_matching_threshold=cfg.match_thresh,
                               frame_rate=round(fps))
        self.votes: dict[int, Counter] = {}   # tid -> Counter(cls_name -> tổng conf)

    def update(self, det: Det) -> list[Track]:
        # sv.Detections(xyxy=det.xyxy, confidence=det.conf, class_id=<map tên->id>)
        # tracked = self.bt.update_with_detections(d)
        # với mỗi tracked: votes[tid][cls] += conf; cls_name = argmax votes
        # foot = ((x1+x2)/2, y2)
        # dọn votes của tid không xuất hiện > 10s (tránh rò RAM)
```
Không cần tự viết ByteTrack. Nếu API `supervision` khác tên tham số theo phiên bản → kiểm tra `help(sv.ByteTrack)` và chỉnh.

---

## B6. `core_pipeline/zone_time.py` — W_total, T50, D85

Trạng thái mỗi track trong zone:
```python
@dataclass
class ZoneVisit:
    tid: int
    group: str
    t_first: float
    t_last: float
    p_first: tuple[float,float]
    p_last: tuple[float,float]
```
```python
class ZoneTimeAnalyzer:
    def __init__(self, cfg): 
        self.active: dict[int, ZoneVisit] = {}
        self.completed: deque[tuple[float, str, float]] = deque()  # (t_done, group, duration)

    def set_zone(self, zone_px): # reset active/completed khi đổi zone

    def update(self, tracks: list[Track], now: float) -> dict:
        # 1. Với track có foot trong zone: tạo/ cập nhật ZoneVisit (t_last=now, p_last=foot)
        # 2. Với visit trong active mà (track không còn trong zone) HOẶC (now - t_last > lost_timeout_s):
        #       travel = dist(p_first, p_last); dur = t_last - t_first
        #       if travel >= min_travel_ratio * axis_len and dur > 0: completed.append((now, group, dur))
        #       xóa khỏi active
        # 3. Bỏ completed cũ hơn window_s
        # 4. Tính:
        #    w_total = tổng class_weights của track đang trong zone (dùng cls_name đã vote)
        #    n_2w, n_4w
        #    t50_g = median(durations của group) nếu số mẫu >= min_completed_samples else None
        #    d85_g = percentile 85 của (now - t_first) với visit active có (now - t_first) >= min_dwell_s,
        #            nếu số mẫu >= min_active_samples else None
        #    W_total làm mượt EMA alpha = 1 - exp(-dt/3.0)
        return {...}  # các khóa đúng hợp đồng metrics 00 mục 4.2 (trừ o_vis, v_flow)
```
**Xong khi:** unit test giả lập: 5 track đi qua zone đều trong 4 s → `t50 ≈ 4.0`; 6 track đứng yên 20 s → `t50=None`, `d85 ≈ 20`.

---

## B7. `aux_pipeline/flow_occupancy.py` — O_vis + V_flow (Chuẩn hóa Không gian Chiếm dụng & Phối cảnh Đa Camera)

```python
class FlowOccupancy:
    def __init__(self, cfg):
        self.mog2 = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16, detectShadows=True)
        self.close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.prev_gray = None
        self.zone_mask_small = None      # 320x180 (từ flow_zone_px đã mở rộng Rail-Aligned +20%)
        self.row_weights = None          # (180, 1) float32: trọng số phối cảnh tự động từ y_min (2.2) -> y_max (0.8)
        self.frozen = False

    def set_zone(self, zone_px_1280):
        # resize mask của flow_zone_px về 320x180; tính row_weights tuyến tính 2.2 -> 0.8 theo [y_min..y_max]; reset prev_gray

    def update(self, frame_1280: np.ndarray, bboxes_1280: np.ndarray, dt: float, stalled_hint: bool) -> tuple[float, float]:
        # bboxes_1280: truyền trực tiếp det.xyxy (conf >= 0.15) từ CameraProcessor (không lọc theo tracks hay t.foot)
        small = cv2.resize(frame, (320,180), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        lr = 0.0 if self.frozen else cfg.mog2_lr_normal
        fg = self.mog2.apply(small, learningRate=lr)
        fg = np.where(fg == 255, 255, 0).astype(np.uint8)         # bỏ bóng (127)
        # Vẽ det.xyxy (scale 0.25) đặc 255 vào mask_yolo; gộp raw_union = fg | mask_yolo
        # Áp dụng MORPH_CLOSE (elip 5x5) lấp khe hở nhỏ giữa các xe máy đi sát nhau -> cắt theo zone_mask_small
        # Tính o_vis có trọng số phối cảnh: sum((occupied > 0) * row_weights) / sum((zone_mask_small > 0) * row_weights)
        # Optical flow
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.linalg.norm(flow, axis=2); mag[mag < cfg.flow_noise_px] = 0
            sel = occupied > 0
            v_flow = (mag[sel].mean() / dt) if sel.any() and dt > 0 else 0.0
        self.prev_gray = gray
        # Đóng/mở băng nền (stalled_hint = d85_max > 5.0 or w_total >= cfg.w_sanity_min)
        self.frozen = (v_flow < cfg.v_stall) and stalled_hint
        return o_vis, v_flow
```
Làm mượt `o_vis`, `v_flow` bằng EMA (alpha 0.3) trước khi trả. (Xem chi tiết tại [10-threshold-and-event-lifecycle-spec.md](./10-threshold-and-event-lifecycle-spec.md) Phần 5).

---

## B8. `decision/occlusion.py` + `decision/classifier.py`

**occlusion.py**
```python
class OcclusionShield:
    def update(self, tracks, zone_px, zone_area, o_vis, now) -> bool:
        # A: diện tích (bbox heavy ∩ zone)/zone_area > heavy_area_ratio
        #    (đơn giản: vẽ bbox heavy lên mask zone rồi đếm pixel; dùng mask 320x180 cho nhanh)
        # B: n_now <= (1 - bbox_drop_ratio) * n_ref  VÀ o_vis > occ_o_vis
        #    n_ref = max số bbox trong zone trong 2s trước (deque (t, n))
        # Kích hoạt -> giữ tới khi điều kiện hết; nếu kéo dài > occ_hold_max_s -> trả "UNKNOWN_HOLD"
        # Trả: "NONE" | "HOLD" | "UNKNOWN_HOLD"
```

**classifier.py** — hàm thuần kết hợp `O_vis + Flow + T50/D85` và trả về `(raw_state, state_conf)`:
```python
def classify(m: dict, cfg) -> tuple[str, float]:
    w = float(m["w_total"] or 0.0)
    o = float(m["o_vis"] or 0.0)
    v = float(m["v_flow"] or 0.0)
    t2, t4, d2, d4 = m["t50_2w"], m["t50_4w"], m["d85_2w"], m["d85_4w"]
    gt = lambda x, th: x is not None and float(x) > th
    le = lambda x, th: x is not None and float(x) <= th

    has_vehicles = (w >= cfg.w_sanity_min) or any(x is not None for x in (t2, t4, d2, d4))
    has_time = any(x is not None for x in (t2, t4, d2, d4))

    time_clear = has_time and all(
        x is None or float(x) <= th
        for x, th in ((t4, cfg.congested_t50_4w_s), (d4, cfg.congested_d85_4w_s),
                      (t2, cfg.congested_t50_2w_s), (d2, cfg.congested_d85_2w_s))
    )
    has_t50_congested = gt(t4, cfg.congested_t50_4w_s) or gt(t2, cfg.congested_t50_2w_s)
    has_d85_congested = (
        (t4 is None and gt(d4, cfg.congested_d85_4w_s))
        or (t2 is None and gt(d2, cfg.congested_d85_2w_s))
    )
    time_congested = has_t50_congested or (has_d85_congested and v <= cfg.v_gridlock_max)
    time_gridlock = (gt(t4, cfg.gridlock_t50_4w_s) or gt(d4, cfg.gridlock_d85_4w_s)
                     or gt(t2, cfg.gridlock_t50_2w_s) or gt(d2, cfg.gridlock_d85_2w_s))

    # 1. Đường vắng / thoáng (O_vis < 40%) hoặc không có phương tiện thật (lọc nhiễu đèn pha đêm mưa)
    if o < cfg.o_clear or not has_vehicles:
        conf = 0.85 + (0.10 if v > cfg.v_clear_min else 0.0)
        return "CLEAR", round(min(0.98, conf), 2)

    # 1b. High-flow override: mật độ cao nhưng dòng xe đang thoát nhanh -> CLEAR
    if v > cfg.v_congested_max:
        conf = 0.84 + (0.12 if time_clear else 0.0)
        return "CLEAR", round(min(0.98, conf), 2)

    # 2. GRIDLOCKED: O_vis >= 85% và (Flow <= 15 px/s kèm T50/D85 vượt ngưỡng kẹt HOẶC Macro-only Flow <= 6 px/s)
    if o >= cfg.o_gridlock:
        if (time_gridlock and v <= cfg.v_gridlock_max) or (not has_time and v <= cfg.v_stall):
            conf = 0.75 + (0.13 if time_gridlock else 0.0) + (0.10 if w >= 24.0 else 0.0)
            return "GRIDLOCKED", round(min(0.98, conf), 2)

    # 3. CONGESTED: O_vis >= 70% và (Flow <= 18 px/s kèm T50 chậm (hoặc D85 khi thiếu T50 & Flow <= 15) HOẶC Macro-only Flow <= 14 px/s)
    #    (Hoặc khi 40% <= O_vis < 70% nhưng cả T50/D85 đều báo kẹt nặng time_gridlock)
    if o >= cfg.o_congested:
        if (time_congested and v <= cfg.v_congested_max) or (not has_time and v <= cfg.v_congested_macro):
            conf = 0.72 + (0.14 if time_congested else 0.0) + (0.10 if w >= 15.0 else 0.0)
            return "CONGESTED", round(min(0.98, conf), 2)
    elif time_gridlock and v <= cfg.v_gridlock_max:
        return "CONGESTED", 0.82

    # 4. CLEAR (Đông xe 40% <= O_vis < 70% nhưng lưu thông tốc độ trung bình 10..35 px/s, T50/D85 thấp)
    conf = 0.75 + (0.12 if time_clear else 0.0) + (0.08 if v >= cfg.v_clear_min else 0.0)
    return "CLEAR", round(min(0.98, conf), 2)
```
**Xong khi:** `tests/test_classifier.py` kiểm tra đầy đủ: đường vắng (`O_vis=0.25, Flow=18`) → `CLEAR`; đường đông chạy TB (`O_vis=0.55, Flow=18, T50_4W=4.8`) → `CLEAR`; đêm mưa không xe (`O_vis=0.80, Flow=2.0, W=0`) → `CLEAR`; ùn tắc (`O_vis=0.78, Flow=14, T50_4W=10.5`) → `CONGESTED`; kẹt cứng (`O_vis=0.88, Flow=4.5, D85_4W=24.0`) → `GRIDLOCKED`; Macro-only khi thiếu `T50/D85` (`O_vis=0.88, Flow=4.0, W=6.0`) → `GRIDLOCKED`.

---

## B9. `decision/state_machine.py` — Chu kỳ Sự kiện `3p → +2p (5p) → mỗi +15p` & Chuyển trạng thái

```python
@dataclass
class EventTrigger:
    state: str          # "CONGESTED" | "GRIDLOCKED" | "CLEAR"
    stage: str          # "CONFIRMED_3M" | "FOLLOWUP_5M" | "PERIODIC_15M" | "TRANSITION" | "RECOVERED_CLEAR"
    duration_s: float

class StateMachine:
    def __init__(self, cfg, has_traffic_light: bool): ...
    def update(self, raw: str, now: float, stream_ok: bool, occ: str) -> tuple[str, EventTrigger | None]:
        """Trả (display_state, EventTrigger | None)."""
```
Logic:
1. `stream_ok=False` (không frame > 5 s) → `display="UNKNOWN"`, không reset timer xác nhận, không sinh event.
2. `occ == "HOLD"` → dùng lại `display` trước đó (không cập nhật lịch sử). `"UNKNOWN_HOLD"` → `display="UNKNOWN"`.
3. **Làm mượt `display_state` (5s majority smoothing + Exit hysteresis 15s)** và **Giữ đèn đỏ `90s` (`red_light_hold_s`)**:
   - Nếu `has_traffic_light=True` và `confirmed_state == "CLEAR"`, trong `90s` đầu tiên kể từ khi chớm dừng chờ đèn đỏ, chưa phát cảnh báo.
4. **Chu kỳ Xác nhận `3 phút (180s)` $\rightarrow$ Nhắc `+2 phút (mốc 5p = 300s)` $\rightarrow$ Định kỳ `+15 phút (900s)`:**
   - Theo dõi thời gian duy trì liên tục của trạng thái hiện tại `candidate_state` (với dung sai dao động ngắn `persistence_tolerance_s = 5.0s`).
   - **Khi `confirmed_state == "CLEAR"` và `candidate_state` là `"CONGESTED"` hoặc `"GRIDLOCKED"`:**
     - Đủ `confirm_state_s` (`180s`): chốt `confirmed_state = candidate_state`, bắn sự kiện lần 1 `stage = "CONFIRMED_3M"`.
   - **Khi đang ở `confirmed_state` (`"CONGESTED"` hoặc `"GRIDLOCKED"`) và trạng thái không đổi:**
     - Tại mốc `confirm_state_s + followup_after_confirm_s` (`180s + 120s = 300s` = **5 phút**): bắn sự kiện nhắc `stage = "FOLLOWUP_5M"`.
     - Sau mốc 5 phút, cứ mỗi `+periodic_reminder_s` (`+900s` = **+15 phút**: mốc `20p, 35p, 50p...`): bắn sự kiện định kỳ `stage = "PERIODIC_15M"`.
   - **Khi đã ở `confirmed_state` (`"CONGESTED"` hoặc `"GRIDLOCKED"`, tức đã qua 3 phút đầu) mà chuyển sang trạng thái mới (`"CLEAR"`, `"GRIDLOCKED"` hoặc `"CONGESTED"`):**
     - Khi trạng thái mới duy trì ổn định đủ `confirm_state_s` (`180s` = **3 phút**):
       - Nếu trạng thái mới là `"CLEAR"`: đổi `confirmed_state = "CLEAR"`, **bắn ngay sự kiện giải tỏa `stage = "RECOVERED_CLEAR"`** và dừng bộ đếm nhắc lại.
       - Nếu trạng thái mới là `"GRIDLOCKED"` (hoặc `"CONGESTED"`): đổi `confirmed_state = candidate_state`, **bắn ngay sự kiện chuyển trạng thái `stage = "TRANSITION"`** và bắt đầu chu kỳ nhắc `+2p → +15p` mới cho trạng thái đó!

**Xong khi:** unit test chuỗi thời gian giả kiểm tra đủ 4 mốc: `180s` (`CONFIRMED_3M`) → `300s` (`FOLLOWUP_5M`) → `1200s` (`PERIODIC_15M`) → chuyển sang `CLEAR` hoặc `GRIDLOCKED` giữ đủ `180s` bắn ngay `RECOVERED_CLEAR` / `TRANSITION`.

---

## B10. Engine: `camera_processor.py`, `gpu_batcher.py`, `engine.py`

**CameraProcessor** (1 cho mỗi camera; giữ toàn bộ trạng thái):
```python
class CameraProcessor:
    def __init__(self, cam: dict, cfg): # tạo StreamReader, CameraTracker, ZoneTimeAnalyzer, FlowOccupancy, OcclusionShield, StateMachine
    def set_zone(self, zone: list[dict]) -> None   # gọi geometry -> cập nhật zone_px, roi, các module con (thread-safe bằng Lock)
    def prepare(self) -> tuple[np.ndarray, tuple[int,int]] | None
        # lấy reader.latest(); nếu seq == last_seq -> None; lưu frame hiện tại; trả crop ROI + offset
    def process(self, det: Det, now: float) -> dict   # CameraResult theo hợp đồng
        # tracks = tracker.update(det); zm = zone_time.update(tracks, now)
        # o_vis, v_flow = flow.update(frame, bboxes_in_zone, dt, stalled_hint=(zm d85 max > 5))
        # occ = occlusion.update(...); raw = classify(metrics)
        # display, ev = sm.update(raw, now, reader.healthy, occ)
        # nếu ev -> self.pending_event = (ev, frame.copy(), metrics)
        # build detections: bbox chuẩn hóa /1280, /720, in_zone
    def idle_result(self, now) -> dict  # khi không có frame mới: trả kết quả cũ, cập nhật stream_ok
```

**GpuBatcher**:
```python
class GpuBatcher(threading.Thread):
    def run(self):
        period = 1.0 / cfg.target_fps
        while not self.stop_evt.is_set():
            t0 = time.monotonic()
            items = [(p, p.prepare()) for p in engine.processors()]
            ready = [(p, x) for p, x in items if x is not None]
            if ready:
                dets = detector.detect_batch([x[0] for _, x in ready], [x[1] for _, x in ready])
                for (p, _), d in zip(ready, dets):
                    store.set(p.cam_id, p.process(d, time.monotonic()))
                    # nếu p.pending_event: đẩy vào store.events_queue
            for p, x in items:
                if x is None: store.set(p.cam_id, p.idle_result(time.monotonic()))
            # log mỗi 10s: thời gian batch trung bình, FPS mỗi cam
            time.sleep(max(0.0, period - (time.monotonic() - t0)))
```
Bọc toàn bộ thân vòng lặp trong `try/except Exception` → `logger.exception`, tiếp tục vòng sau (không để thread chết).

**engine.py — API duy nhất mà backend dùng:**
```python
class TrafficEngine:
    def __init__(self, cfg=CFG)
    def start(self) -> None                       # load model, start batcher
    def stop(self) -> None
    def upsert_camera(self, cam: dict) -> None    # thêm / đổi URL (restart reader) / đổi zone (set_zone)
    def remove_camera(self, cam_id: str) -> None
    def latest_results(self) -> list[dict]        # CameraResult mới nhất của mọi camera
    def pop_events(self) -> list[tuple[dict, np.ndarray]]  # (event_partial, frame BGR) — backend lưu snapshot
    def latest_frame(self, cam_id: str) -> np.ndarray | None  # cho snapshot/MJPEG fallback
```
URL mà engine đọc: `rtsp://127.0.0.1:8554/{cam_id}` (qua MediaMTX), **không** phải URL gốc camera.

---

## B11. `tools/run_video.py` — kiểm thử offline (làm SỚM, ngay sau B6)

```bash
uv run python -m ai.tools.run_video --video samples/cam1.mp4 --zone "0.1,0.35;0.9,0.37;0.95,0.85;0.05,0.83" --out out/cam1_debug.mp4
```
- Đọc file video, lấy mẫu 15 FPS theo `CAP_PROP_POS_MSEC`, chạy pipeline 1 camera đồng bộ (không thread).
- Vẽ: zone (màu theo state), bbox + `tid` + `2W/4W`, chấm foot, bảng chỉ số góc trên trái, badge state góc dưới phải.
- Ghi thêm `out/cam1_metrics.csv` (ts, các metrics, raw_state, state) để vẽ biểu đồ khi tinh chỉnh ngưỡng.

Đây là công cụ chính để tinh chỉnh ngưỡng ở G5 mà không cần web.

## Checklist hoàn thành phân hệ AI
- [ ] Unit test `geometry`, `zone_time`, `classifier`, `state_machine` pass (`uv run pytest ai/tests`).
- [ ] `run_video.py` xuất video debug đúng trên ≥ 3 video (thoáng / ùn / kẹt).
- [ ] 8 camera RTSP: batch ≤ 45 ms, FPS mỗi cam ≥ 13, VRAM ≤ 2.5 GB (`nvidia-smi`).
- [ ] Ngắt 1 camera → camera đó `stream_ok=false`, `state=UNKNOWN`, các camera khác không ảnh hưởng.
