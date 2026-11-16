# 11 — KẾ HOẠCH CẬP NHẬT POC LÊN ĐẶC TẢ V2 (NGƯỠNG `18–22m`, `state_conf` & CHU KỲ SỰ KIỆN `3p → 5p → 15p`)

> **Mục tiêu:** Đồng bộ toàn bộ mã nguồn PoC hiện tại (`poc/.env.example`, `poc/backend/`, `poc/frontend/`, unit tests và công cụ offline) theo bộ tài liệu đặc tả V2 mới nhất sau khi thống nhất với PM:
> - [00-overview-and-decisions.md](./00-overview-and-decisions.md) (D7, D15, D20 & Hợp đồng dữ liệu mục 4.2, 4.4)
> - [02-ai-pipeline.md](./02-ai-pipeline.md) (B1, B8, B9, B10)
> - [04-frontend.md](./04-frontend.md) (F1, F6, F8)
> - [07-changelog.md](./07-changelog.md) (Bản cập nhật Đặc tả V2 — 16/11/2026)
> - [09-parameter-and-system-evaluation.md](./09-parameter-and-system-evaluation.md)
> - [10-threshold-and-event-lifecycle-spec.md](./10-threshold-and-event-lifecycle-spec.md)
> - [thredsold.md](./thredsold.md)

---

## 1. Tóm tắt các thay đổi cốt lõi từ PoC V1 (Commit `e14cb45`) $\rightarrow$ V2

| Hạng mục | PoC hiện tại (Code đang chạy) | Đặc tả V2 cần cập nhật |
| :--- | :--- | :--- |
| **Vai trò `W` ($W_{total}$)** | Dùng ngưỡng cứng `W_CLEAR=18`, `W_CONGESTED=25`, `W_GRIDLOCK=38`, `W_RESCUE=28`; hiển thị `W` trên Live View. | **Loại bỏ hoàn toàn `W_*` khỏi ngưỡng cứng và ẩn `W` trên Live View.** Giữ trọng số xe (`1.0 / 3.0 / 6.0`) làm cổng an toàn `W_SANITY_MIN = 3.0` (chống nhiễu đèn pha đêm mưa) và cộng điểm tự tin `state_conf`. |
| **Độ phủ `O_vis`** | `O_CLEAR=0.40`, `O_CONGESTED=0.55`, `O_GRIDLOCK=0.72`, `O_MACRO_STALL=0.75`, `O_RESCUE=0.80`. | Chuẩn hóa cho vùng `18–22m` + mở rộng `+20%`: **`O_CLEAR=0.40`**, **`O_CONGESTED=0.70`**, **`O_GRIDLOCK=0.85`** (bỏ `O_MACRO_STALL`, `O_RESCUE`). |
| **Dòng chảy `Flow (px/s)`** | Chỉ có `V_STALL=1.0` và `V_CLEAR=6.0`. | Phân tách rõ chế độ có `T50/D85` và Macro-only: **`V_STALL=6.0`**, **`V_CLEAR_MIN=10.0`**, **`V_GRIDLOCK_MAX=15.0`**, **`V_CONGESTED_MACRO=18.0`**, **`V_CONGESTED_MAX=25.0`**. |
| **Cửa sổ & Ngưỡng `T50 / D85`** | `ZONE_WINDOW_S=15.0`, `ZONE_MIN_COMPLETED_SAMPLES=3`; `CONGESTED` `5.0/7.5` (4W) & `4.5/7.0` (2W); `GRIDLOCK` `9.0/14.0` (4W) & `7.5/12.0` (2W) + nhánh `2W_ONLY`. | **`ZONE_WINDOW_S=30.0`**, **`ZONE_MIN_COMPLETED_SAMPLES=2`**. Ranh giới `CLEAR ↔ CONGESTED`: **`5.5 / 6.5`** (4W) & **`4.5 / 5.0`** (2W). Ranh giới `CONGESTED ↔ GRIDLOCKED`: **`16.0 / 20.0`** (4W) & **`13.5 / 17.0`** (2W). Bỏ nhánh `2W_ONLY`. |
| **Điểm tự tin `state_conf`** | Chưa có (`classify()` chỉ trả về `str`). | `classify()` trả về `(raw_state, state_conf)` với `state_conf ∈ [0.55 .. 0.98]`; đẩy trong `CameraResult` (top-level + `metrics.state_conf`) và trong `Event.confidence`. |
| **Đóng băng nền MOG2** | `stalled_hint = (d85_max > 5.0)` — nếu `D85` bị `None` khi ít BBox thì MOG2 không đóng băng. | Bổ sung fallback: đóng băng khi `v_flow < v_stall` VÀ (`d85_max > 5.0` HOẶC có đủ xe trong vùng `n_2w + n_4w >= 2` / `w_total >= w_sanity_min`). |
| **Bộ máy Sự kiện (`StateMachine`)** | `CONFIRM_CONGESTED=60s`, `LIGHT=90s`, `GRIDLOCK=120s`, `COOLDOWN=60s`; chỉ bắn `CONGESTED`/`GRIDLOCKED`. | Chu kỳ mới: **`RED_LIGHT_HOLD_S=90s`** (nằm gọn trong 3p), **`CONFIRM_STATE_S=180s` (`CONFIRMED_3M`)** $\rightarrow$ **`+120s` (`FOLLOWUP_5M`)** $\rightarrow$ **mỗi `+900s` (`PERIODIC_15M`)**. Đổi trạng thái sau mốc 3p giữ đủ `180s` bắn ngay **`TRANSITION`** hoặc **`RECOVERED_CLEAR`**. (`DEMO_MODE=1`: `30s / +20s / +90s`, đèn đỏ `15s`). |
| **Frontend UI** | Card còn `W: ...`, `.cam-metrics` nằm dưới video, `.state-badge` ở góc dưới phải, hint vẽ zone ghi `12–16 m`; Event panel chưa hiện `event_stage`, `confidence`, `Flow`. | Đưa **toàn bộ thông tin + badge tình trạng** lên **góc trên bên trái trong khung video** (`.hud-overlay` nền tối bán trong suốt, giới hạn `<= 1/3` chiều cao và `<= 1/2` chiều rộng live view), bỏ `.cam-metrics` dưới video; ẩn `W`, hiện độ tin cậy `Conf %`; thay `T50/D85` bằng nhãn tiếng Việt ngắn gọn dễ hiểu (`Qua vùng`, `Lưu lại`, `Độ phủ đường`, `Tốc độ dòng xe`); sửa hint thành `18–22 m`; Event panel hiển thị `event_stage`, `Conf %` và chỉ số tiếng Việt. |

---

## 2. Kế hoạch triển khai chi tiết theo từng Giai đoạn

### Giai đoạn 1 — Cấu hình tập trung (`poc/.env.example` & `poc/backend/ai/config.py`)

**Mục tiêu:** Cập nhật toàn bộ biến môi trường và fallback mặc định trong `AIConfig` khớp 100% với Đặc tả V2.

1. **Cập nhật [poc/backend/ai/config.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/config.py):**
   - **Zone time:**
     - `window_s`: `30.0` (`ZONE_WINDOW_S`)
     - `min_dwell_s`: `2.0` (`ZONE_MIN_DWELL_S`)
     - `min_completed_samples`: `2` (`ZONE_MIN_COMPLETED_SAMPLES`)
   - **Aux Flow:**
     - Thay `v_stall=1.0`, `v_clear=6.0` bằng:
       - `v_stall: float = _env_field("V_STALL", 6.0, float)`
       - `v_gridlock_max: float = _env_field("V_GRIDLOCK_MAX", 15.0, float)`
       - `v_congested_macro: float = _env_field("V_CONGESTED_MACRO", 18.0, float)`
       - `v_congested_max: float = _env_field("V_CONGESTED_MAX", 25.0, float)`
       - `v_clear_min: float = _env_field("V_CLEAR_MIN", 10.0, float)`
   - **Classifier V2:**
     - Xóa `w_clear`, `w_congested`, `w_gridlock`, `w_rescue`, `o_macro_stall`, `o_rescue`, `gridlock_t50_2w_only_s`, `gridlock_d85_2w_only_s`.
     - Thêm `w_sanity_min: float = _env_field("W_SANITY_MIN", 3.0, float)`.
     - Cập nhật fallback mặc định của `O_*`: `o_clear=0.40`, `o_congested=0.70`, `o_gridlock=0.85`.
     - Cập nhật fallback mặc định của `T50 / D85`:
       - `congested_t50_4w_s=5.5`, `congested_d85_4w_s=6.5`, `congested_t50_2w_s=4.5`, `congested_d85_2w_s=5.0`
       - `gridlock_t50_4w_s=16.0`, `gridlock_d85_4w_s=20.0`, `gridlock_t50_2w_s=13.5`, `gridlock_d85_2w_s=17.0`
   - **State Machine V2:**
     - Xóa `confirm_congested_s`, `confirm_congested_light_s`, `confirm_gridlock_s`, `cooldown_s`.
     - Thêm:
       - `red_light_hold_s: float = _env_field("RED_LIGHT_HOLD_S", 15.0 if DEMO_MODE else 90.0, float)`
       - `confirm_state_s: float = _env_field("CONFIRM_STATE_S", 30.0 if DEMO_MODE else 180.0, float)`
       - `followup_after_confirm_s: float = _env_field("FOLLOWUP_AFTER_CONFIRM_S", 20.0 if DEMO_MODE else 120.0, float)`
       - `periodic_reminder_s: float = _env_field("PERIODIC_REMINDER_S", 90.0 if DEMO_MODE else 900.0, float)`

2. **Cập nhật [poc/.env.example](file:///E:/ATIN/traffic_congestion_evaluation/poc/.env.example):**
   - Đồng bộ lại chú thích và các biến mục 2, 3, 4, 5 theo đúng bảng trên.
   - *Lưu ý triển khai:* Nếu server/máy dev đang có file `poc/.env` copy từ bản cũ, cần nhắc đồng bộ hoặc tạo lại từ `poc/.env.example` để các biến cũ không còn hiệu lực gây hiểu nhầm.

---

### Giai đoạn 2 — Classifier V2 & Đóng băng nền MOG2 (`classifier.py` & `camera_processor.py`)

**Mục tiêu:** Chuyển sang logic 3 trụ cột (`O_vis` + `Flow` + `T50/D85`), xử lý triệt để vùng chồng lấp `Flow`, lọc nhiễu đêm mưa bằng `W_SANITY_MIN`, và trả về `state_conf`.

1. **Viết lại [poc/backend/ai/decision/classifier.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/decision/classifier.py):**
   - Chữ ký hàm: `def classify(m: dict[str, float | int | None], cfg: AIConfig) -> tuple[str, float]:`
   - Cài đặt đúng logic đã chốt ở [02-ai-pipeline.md](./02-ai-pipeline.md#L361-L405):
     1. `has_vehicles = (w >= cfg.w_sanity_min) or any(x is not None for x in (t2, t4, d2, d4))`
     2. `o < cfg.o_clear or not has_vehicles` $\rightarrow$ `"CLEAR"`, `conf` $\in [0.85, 0.95]$
     3. `o >= cfg.o_gridlock`: nếu `(time_gridlock and v <= cfg.v_gridlock_max)` hoặc `(not has_time and v <= cfg.v_stall)` $\rightarrow$ `"GRIDLOCKED"`, `conf = min(0.98, 0.75 + 0.13*time_gridlock + 0.10*(w>=24.0))`
     4. `o >= cfg.o_congested`: nếu `(time_congested and v <= cfg.v_congested_max)` hoặc `(not has_time and v <= cfg.v_congested_macro)` $\rightarrow$ `"CONGESTED"`, `conf = min(0.98, 0.72 + 0.14*time_congested + 0.10*(w>=15.0))`
     5. Nhánh bổ sung khi `40% <= o < 70%` nhưng `time_gridlock and v <= cfg.v_gridlock_max` $\rightarrow$ `"CONGESTED"`, `conf = 0.82`
     6. Fallback $\rightarrow$ `"CLEAR"`, `conf = min(0.98, 0.75 + 0.12*time_clear + 0.08*(v>=cfg.v_clear_min))`

2. **Cập nhật điều kiện đóng băng MOG2 trong [poc/backend/ai/engine/camera_processor.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/engine/camera_processor.py#L127-L136):**
   - Hiện tại `stalled_hint=(d85_max > 5.0)`.
   - Cập nhật theo mục 3.2 tài liệu 09:
     ```python
     prev_o = float(self._last_result["metrics"]["o_vis"]) if self._last_result else 0.0
     n_veh = int(zm["n_2w"] or 0) + int(zm["n_4w"] or 0)
     stalled_hint = (d85_max > 5.0) or (prev_o >= self.cfg.o_congested and n_veh >= 2)
     ```
   - Đảm bảo khi Production đứt track (`d85 = None`) nhưng mật độ vẫn cao và có $\ge 2$ xe, `FlowOccupancy` vẫn đóng băng nền MOG2 khi `v_flow < v_stall`.

---

### Giai đoạn 3 — Bộ máy Sự kiện V2 (`state_machine.py`)

**Mục tiêu:** Triển khai đầy đủ chu kỳ `3 phút → +2 phút (5p) → mỗi +15 phút` và bắn ngay khi xác nhận chuyển trạng thái, kèm đèn đỏ `90s`.

1. **Cập nhật [poc/backend/ai/decision/state_machine.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/decision/state_machine.py):**
   - Định nghĩa `@dataclass(frozen=True) class EventTrigger`:
     - `state: str` (`"CONGESTED" | "GRIDLOCKED" | "CLEAR"`)
     - `stage: str` (`"CONFIRMED_3M" | "FOLLOWUP_5M" | "PERIODIC_15M" | "TRANSITION" | "RECOVERED_CLEAR"`)
     - `duration_s: float`
   - Chữ ký `update(...) -> tuple[str, EventTrigger | None]`.
   - **Các biến trạng thái nội bộ cần thiết kế chặt chẽ:**
     - `self.display_state`: giữ logic 5s majority smoothing + `exit_clear_s` (15s) hysteresis như cũ.
     - `self.confirmed_state`: trạng thái sự kiện đã xác nhận hiện tại (`"CLEAR" | "CONGESTED" | "GRIDLOCKED"`).
     - `self._confirmed_since`: thời điểm bắt đầu của sự kiện hiện tại (để tính `duration_s` và các mốc `FOLLOWUP_5M`, `PERIODIC_15M`).
     - `self._next_reminder_at`: mốc thời gian tiếp theo bắn nhắc (`_confirmed_since + confirm_state_s + followup_after_confirm_s` cho lần đầu = 5p, sau đó cộng dồn `+ periodic_reminder_s` = +15p).
     - `self._candidate_state` / `self._candidate_since` / `self._candidate_drop_since`: theo dõi trạng thái `display_state` mới khác với `confirmed_state` (có dung sai `persistence_tolerance_s = 5.0s` khi chớp nhẹ).
   - **Quy tắc chuyển & bắn sự kiện:**
     1. **Đèn đỏ (`has_traffic_light=True`):** Khi `confirmed_state == "CLEAR"`, `red_light_hold_s` (`90s`) nằm gọn trong `confirm_state_s` (`180s`). Trong `90s` đầu tiên không thể bắn cảnh báo; khi duy trì liên tục đủ `confirm_state_s` (`180s > 90s`), chắc chắn đã qua pha đèn đỏ $\rightarrow$ bắn `CONFIRMED_3M`. *(Nếu người dùng cấu hình `confirm_state_s < red_light_hold_s`, lấy `max(confirm_state_s, red_light_hold_s)` khi `has_traffic_light=True` để luôn an toàn).*
     2. **Xác nhận ban đầu (`confirmed_state == "CLEAR"` $\rightarrow$ `CONGESTED` / `GRIDLOCKED`):**
        - Khi `candidate_state` giữ đủ `req_s` (`180s`):
          - `confirmed_state = candidate_state`
          - `_confirmed_since = _candidate_since`
          - `_next_reminder_at = _confirmed_since + confirm_state_s + followup_after_confirm_s` (mốc `300s`)
          - Trả về `EventTrigger(state=confirmed_state, stage="CONFIRMED_3M", duration_s=now - _confirmed_since)`.
     3. **Nhắc lại khi trạng thái không đổi (`confirmed_state` $\in$ `{"CONGESTED", "GRIDLOCKED"}` và `display_state == confirmed_state`):**
        - Nếu `now >= _next_reminder_at`:
          - Nếu đây là lần nhắc đầu (tại mốc `300s`): `stage = "FOLLOWUP_5M"`, cập nhật `_next_reminder_at += periodic_reminder_s`.
          - Các lần sau (`1200s, 2100s...`): `stage = "PERIODIC_15M"`, cập nhật `_next_reminder_at += periodic_reminder_s`.
          - Trả về `EventTrigger(state=confirmed_state, stage=stage, duration_s=now - _confirmed_since)`.
     4. **Chuyển trạng thái sau khi đã xác nhận (`confirmed_state` $\in$ `{"CONGESTED", "GRIDLOCKED"}` và `candidate_state != confirmed_state`):**
        - Khi `candidate_state` giữ ổn định đủ `confirm_state_s` (`180s`):
          - Nếu `candidate_state == "CLEAR"`:
            - `total_dur = now - _confirmed_since`
            - `confirmed_state = "CLEAR"`, reset `_confirmed_since`, `_next_reminder_at`, `_candidate_*`
            - Trả về `EventTrigger(state="CLEAR", stage="RECOVERED_CLEAR", duration_s=total_dur)`.
          - Nếu `candidate_state` là `"GRIDLOCKED"` hoặc `"CONGESTED"`:
            - `confirmed_state = candidate_state`
            - `_confirmed_since = _candidate_since`
            - `_next_reminder_at = _confirmed_since + confirm_state_s + followup_after_confirm_s`
            - Reset `_candidate_*`
            - Trả về `EventTrigger(state=confirmed_state, stage="TRANSITION", duration_s=now - _confirmed_since)`.
   - *Lưu ý edge case:* Khi `stream_ok=False` hoặc `occ == "UNKNOWN_HOLD"`, giữ nguyên bộ đếm (không reset), trả `("UNKNOWN", None)`. Khi `occ == "HOLD"`, trả `(hold_state, None)`.

---

### Giai đoạn 4 — Engine, Backend Events & Tool Offline (`camera_processor.py`, `events.py`, `run_video.py`)

**Mục tiêu:** Đồng bộ hợp đồng dữ liệu `CameraResult` và `Event` mới xuyên suốt Backend.

1. **Cập nhật [poc/backend/ai/engine/camera_processor.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/engine/camera_processor.py):**
   - `raw_state, state_conf = classify(metrics, self.cfg)`
   - Thêm `"state_conf": state_conf` vào `metrics` và top-level `result` (và trong `idle_result()` gán `"state_conf": 0.0`).
   - `display_state, ev_trigger = self.sm.update(...)`
   - Khi `ev_trigger is not None`:
     ```python
     partial = {
         "camera_id": self.cam_id,
         "state": ev_trigger.state,
         "event_stage": ev_trigger.stage,
         "confidence": state_conf,
         "ts": round(ts_wall, 3),
         "duration_s": round(ev_trigger.duration_s),
         "metrics": metrics,
         "detections": detections,
     }
     ```
2. **Cập nhật [poc/backend/events.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/events.py):**
   - Trong `EventStore.add()`:
     - Lấy `stage = partial.get("event_stage", "CONFIRMED_3M")` và `confidence = partial.get("confidence")`.
     - Ghi thêm `"event_stage": stage` và `"confidence": confidence` vào object `event` trả về / lưu `self._items`.
     - Cập nhật text vẽ lên ảnh snapshot: `f"{cam_name} | {state} [{stage}] ({duration_s}s)"`.
3. **Cập nhật [poc/backend/ai/tools/run_video.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/tools/run_video.py):**
   - Unpack `raw_state, state_conf = classify(metrics, CFG)` và `display_state, ev = sm.update(...)`.
   - Hiển thị thêm `conf` lên khung thông số debug và ghi cột `state_conf` vào `*_metrics.csv` (nếu cần đối chiếu).

---

### Giai đoạn 5 — Frontend UI (`camera-card.js`, `events-panel.js`, `styles.css`)

**Mục tiêu:** Đưa toàn bộ thông tin tình trạng & chỉ số lên HUD góc trên bên trái trong khung video (nền tối bán trong suốt, tối đa `1/3` chiều cao × `1/2` chiều rộng), dùng ngôn ngữ tiếng Việt dễ hiểu thay cho thuật ngữ `T50`/`D85`, ẩn `W`, sửa hướng dẫn vẽ Poly Zone `18–22m`, và cập nhật Event Feed.

1. **Cập nhật [poc/frontend/js/camera-card.js](file:///E:/ATIN/traffic_congestion_evaluation/poc/frontend/js/camera-card.js):**
   - Sửa `.zone-hint` (dòng 28) từ `~2 vạch sơn + 2 khoảng trống (12–16 m)` thành `~3 vạch sơn + 2–3 khoảng trống (18–22 m)`.
   - **Bỏ hoàn toàn khối `.cam-metrics` bên dưới `.viewport`** (khung card chỉ còn header + `.viewport` 16:9).
   - **Đưa toàn bộ badge tình trạng + chỉ số vào `.hud-overlay` đặt bên trong `.viewport` (góc trên bên trái):**
     - Dòng 1: `<span class="state-badge">MẤT TÍN HIỆU</span>` + `Tin cậy: <strong class="m-conf">–</strong>` (`state_conf`).
     - Dòng 2: `Độ phủ: <strong class="m-ovis">–</strong> · Dòng xe: <strong class="m-flow">–</strong>` (`o_vis`, `v_flow`).
     - Dòng 3: `Trong vùng: <strong class="m-2w">–</strong> xe máy · <strong class="m-4w">–</strong> ô tô` (`n_2w`, `n_4w`, ẩn hoàn toàn `W`).
     - Dòng 4 (thay `T50`): `Thoát vùng: Ô tô <strong class="m-t4">–</strong> · Xe máy <strong class="m-t2">–</strong>`.
     - Dòng 5 (thay `D85`): `Đang dừng/chậm: Ô tô <strong class="m-d4">–</strong> · Xe máy <strong class="m-d2">–</strong>`.
   - Trong `update(res)`: bỏ cập nhật `.m-w`, cập nhật `.m-conf` (`res.state_conf != null ? `${Math.round(res.state_conf * 100)}%` : '–'`).

2. **Cập nhật [poc/frontend/styles.css](file:///E:/ATIN/traffic_congestion_evaluation/poc/frontend/styles.css):**
   - Thay `.state-badge` (góc dưới phải) và `.cam-metrics` (dưới video) bằng `.hud-overlay`:
     - Vị trí & kích thước: `position: absolute; top: 8px; left: 8px; z-index: 4; max-width: calc(50% - 16px); max-height: calc(33.33% - 16px); overflow: hidden; pointer-events: none;`.
     - Nền tối bán trong suốt cân bằng độ nổi bật và khả năng nhìn xuyên video: `background: rgba(15, 23, 42, 0.72); backdrop-filter: blur(4px); border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 8px; padding: 5px 8px; color: #f1f5f9;`.
     - Typography gọn để vừa khít giới hạn `<= 1/3` cao × `<= 1/2` rộng ở cả layout 4/6/8 camera: `font-size: clamp(9px, 0.72vw, 11px); line-height: 1.32;`.
     - `.state-badge` nằm gọn trên dòng đầu của `.hud-overlay` (`position: static; padding: 2px 8px; font-size: 10px;`).
     - Khi `.cam-card.editing .hud-overlay` đang bật vẽ zone: `opacity: 0.25` (hoặc `display: none`) để người dùng nhìn rõ toàn bộ góc trên trái khi chấm điểm.
   - Điều chỉnh `.empty-slot` (`aspect-ratio` khớp với card mới sau khi bỏ `.cam-metrics` bên dưới).
   - Bổ sung style nhỏ gọn cho badge `event_stage` trong sidebar sự kiện.

3. **Cập nhật [poc/frontend/js/events-panel.js](file:///E:/ATIN/traffic_congestion_evaluation/poc/frontend/js/events-panel.js):**
   - Thêm bảng ánh xạ `STAGE_LABELS`:
     - `CONFIRMED_3M`: `"Xác nhận 3p"`
     - `FOLLOWUP_5M`: `"Nhắc 5p"`
     - `PERIODIC_15M`: `"Định kỳ +15p"`
     - `TRANSITION`: `"Chuyển mức"`
     - `RECOVERED_CLEAR`: `"Đã thông thoáng"`
   - Trên mỗi thẻ sự kiện:
     - Hiển thị badge `meta.label` + nhãn `stage` (`STAGE_LABELS[ev.event_stage]`).
     - Hiển thị độ tin cậy `Tin cậy: ${Math.round(ev.confidence * 100)}%` (nếu có).
     - Thay `T50 4B / D85 4B` bằng nhãn tiếng Việt dễ hiểu: `Độ phủ: ${ovis} · Dòng xe: ${flow} · Dừng/chậm (ô tô): ${d85}`.

---

### Giai đoạn 6 — Cập nhật Unit Tests & Kiểm thử hồi quy

**Mục tiêu:** Đảm bảo 100% test suite pass sau khi chuyển sang V2.

1. **[poc/backend/ai/tests/test_classifier.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/tests/test_classifier.py):**
   - Cập nhật toàn bộ assertion sang `state, conf = classify(...)`.
   - Bỏ test cũ phụ thuộc `W_CLEAR` / `w_congested` / `w_gridlock`.
   - Thêm các test case bắt buộc của V2:
     - Đường vắng (`O_vis=0.25, Flow=18`) $\rightarrow$ `CLEAR`.
     - Đường đông chạy TB (`O_vis=0.55, Flow=18, T50_4W=4.8`) $\rightarrow$ `CLEAR`.
     - Đêm mưa không xe (`O_vis=0.80, Flow=2.0, W=0`) $\rightarrow$ `CLEAR` (chặn bởi `W_SANITY_MIN`).
     - Ùn tắc có `T50/D85` (`O_vis=0.78, Flow=14, T50_4W=10.5`) $\rightarrow$ `CONGESTED` (kiểm tra `conf >= 0.85`).
     - Kẹt cứng có `T50/D85` (`O_vis=0.88, Flow=4.5, D85_4W=24.0`) $\rightarrow$ `GRIDLOCKED` (`conf >= 0.88`).
     - Macro-only khi thiếu `T50/D85` (`O_vis=0.88, Flow=4.0, W=6.0`) $\rightarrow$ `GRIDLOCKED` (`conf ~ 0.75`).
     - Vùng `Flow` chồng lấp (`Flow=12.0` với `T50_4W=4.5` $\rightarrow$ `CLEAR` vs `T50_4W=10.0` $\rightarrow$ `CONGESTED` vs `T50_4W=17.0` $\rightarrow$ `GRIDLOCKED`).

2. **[poc/backend/ai/tests/test_state_machine.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/tests/test_state_machine.py):**
   - Cập nhật test theo `EventTrigger`:
     - Chuỗi `CONGESTED` liên tục: không bắn trước `180s` (kể cả `has_traffic_light=True` trong `90s` đầu), bắn `CONFIRMED_3M` tại `180s`, bắn `FOLLOWUP_5M` tại `300s`, bắn `PERIODIC_15M` tại `1200s` (`20p`) và `2100s` (`35p`).
     - Chuyển từ `CONGESTED` (đã xác nhận) sang `GRIDLOCKED` giữ đủ `180s` $\rightarrow$ bắn ngay `TRANSITION` và reset lịch nhắc `+2p → +15p` cho `GRIDLOCKED`.
     - Chuyển từ `CONGESTED`/`GRIDLOCKED` sang `CLEAR` giữ đủ `180s` $\rightarrow$ bắn ngay `RECOVERED_CLEAR` và dừng bộ đếm nhắc.
     - Dao động ngắn `<= 5.0s` (`persistence_tolerance_s`) không làm reset timer xác nhận.

3. **[poc/backend/ai/tests/test_camera_processor.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/ai/tests/test_camera_processor.py) & [poc/backend/tests/test_api.py](file:///E:/ATIN/traffic_congestion_evaluation/poc/backend/tests/test_api.py):**
   - Kiểm tra `CameraResult` có `state_conf` (top-level & `metrics.state_conf`).
   - Kiểm tra `EventStore` lưu và trả về `event_stage`, `confidence`.

---

## 3. Lệnh kiểm thử xác minh (chạy trong `poc/backend` qua `uv`)

```bash
cd poc/backend
uv run pytest ai/tests tests -v
```

Kiểm tra nhanh video offline sau khi sửa:
```bash
uv run python -m ai.tools.run_video --video <path_to_video.mp4> --zone "0.1,0.35;0.9,0.37;0.95,0.85;0.05,0.83" --out out/v2_check.mp4
```

---

## 4. Checklist hoàn thành cập nhật PoC V2

- [x] **Config & Env:** `poc/.env.example` và `poc/backend/ai/config.py` khớp 100% bảng ngưỡng V2 (`ZONE_WINDOW_S=30.0`, `O_CLEAR=0.40`, `O_CONGESTED=0.70`, `O_GRIDLOCK=0.85`, `V_*`, `T50/D85`, `W_SANITY_MIN=3.0`, bộ đếm `180s / +120s / +900s`).
- [x] **Classifier & MOG2:** `classifier.py` trả về `(raw_state, state_conf)` không dùng ngưỡng cứng `W_*`; `camera_processor.py` có fallback đóng băng MOG2 khi `D85 = None`.
- [x] **State Machine:** `state_machine.py` bắn đủ 5 `event_stage` (`CONFIRMED_3M`, `FOLLOWUP_5M`, `PERIODIC_15M`, `TRANSITION`, `RECOVERED_CLEAR`) và tôn trọng `RED_LIGHT_HOLD_S=90s`.
- [x] **Backend & Tool:** `camera_processor.py`, `events.py`, `run_video.py` đồng bộ schema `state_conf`, `event_stage`, `confidence`.
- [x] **Frontend:** `camera-card.js` & `styles.css` đưa toàn bộ tình trạng + chỉ số vào `.hud-overlay` góc trên trái (`<= 1/3` cao, `<= 1/2` rộng, nền tối bán trong suốt), bỏ `.cam-metrics` dưới video, ẩn `W`, thay `T50/D85` bằng tiếng Việt dễ hiểu, sửa hint `18–22 m`; `events-panel.js` hiển thị `event_stage`, `Tin cậy %`, `Độ phủ`, `Dòng xe`, `Dừng/chậm (ô tô)`.
- [x] **Tests:** `pytest ai/tests tests -v` pass 100% (27/27 AI + 3/3 API).
