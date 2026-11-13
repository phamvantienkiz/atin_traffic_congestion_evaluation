# 04 — PHÂN HỆ FRONTEND (`poc/frontend/`) — GIAI ĐOẠN G4

> Đọc trước: [00](./00-overview-and-decisions.md) mục 4 (hợp đồng dữ liệu) và bảng API ở [03](./03-backend.md) mục 8.
> Công nghệ: HTML + CSS + Vanilla JS (ES modules), không build tool. Được backend phục vụ tại `http://localhost:8080/`.

## 1. Cấu trúc file

```text
poc/frontend/
├── index.html
├── styles.css           # copy design tokens từ scripts/RTSP/styles.css + phần mới
└── js/
    ├── main.js          # khởi tạo, layout, vòng render
    ├── api.js           # fetch wrapper cho REST
    ├── ws.js            # WebSocket client tự kết nối lại
    ├── camera-card.js   # 1 ô camera: video + canvas + badge + metrics
    ├── overlay.js       # vẽ zone/bbox/badge lên canvas
    ├── zone-editor.js   # chế độ vẽ Poly Zone
    └── events-panel.js  # danh sách sự kiện + modal ảnh
```

## 2. Bố cục trang

```text
┌───────────────────────────────────────────────────────────────────────┐
│ Header: "ATIN Traffic Congestion — PoC" | [4][6][8] | ● WS | DEMO     │
│        | [+ Thêm camera]                                               │
├──────────────────────────────────────────────────────┬────────────────┤
│ Lưới camera (2x2 / 3x2 / 4x2)                        │ Sự kiện        │
│ ┌────────────────────┐ ┌────────────────────┐        │ ┌────────────┐ │
│ │ cam1  Tên  [✏️][📷][⚙]│ │ ...                │        │ │ ảnh | KẸT  │ │
│ │  video + canvas     │ │                    │        │ │ cam1 17:30 │ │
│ │           [KẸT XE]◢ │ │                    │        │ └────────────┘ │
│ ├────────────────────┤ │                    │        │ ...            │
│ │ W 30 | 2B 18 | 4B 4 │ │                    │        │                │
│ │ T50 4B 8.4s 2B 4.1s │ │                    │        │                │
│ │ D85 4B 14s  2B 5.0s │ │                    │        │                │
│ │ Phủ 72% Flow 0.3    │ │                    │        │                │
│ └────────────────────┘ └────────────────────┘        │                │
└──────────────────────────────────────────────────────┴────────────────┘
```
Màu trạng thái (dùng chung zone, badge, thẻ sự kiện):
`CLEAR #22c55e "THÔNG THOÁNG"`, `CONGESTED #f59e0b "ÙN TẮC"`, `GRIDLOCKED #ef4444 "KẸT XE"`, `UNKNOWN #9ca3af "MẤT TÍN HIỆU"`; khi `occlusion_hold=true` thêm nhãn phụ `"(che khuất)"` màu `#3b82f6`.

## 3. Bước F1 — Khung trang & style
- Copy biến CSS (`--bg-page`, `--radius-xl`, `--border-card`, `--shadow-card`, `--ink`, font) từ `scripts/RTSP/styles.css`.
- `.grid[data-layout="4"] {grid-template-columns: repeat(2,1fr)}`, `6 → 3 cột`, `8 → 4 cột`. Lưu layout vào `localStorage`.
- Ô video: `.viewport {position:relative; aspect-ratio:16/9; background:#111; overflow:hidden}`; con `iframe, img, canvas {position:absolute; inset:0; width:100%; height:100%; border:0}`; `canvas {pointer-events:none}` (bật `auto` khi vẽ zone); `iframe {pointer-events:none}`.
- Badge: `.state-badge {position:absolute; right:12px; bottom:12px; padding:6px 12px; border-radius:999px; font-weight:700; color:#fff}` — **nằm trong DOM (không vẽ canvas)** để chữ sắc nét.

**Xong khi:** mở trang thấy lưới 4/6/8 ô trống, chuyển layout được.

## 4. Bước F2 — `api.js`, `ws.js`
```js
// api.js
export const api = {
  config: () => get('/api/config'),
  cameras: () => get('/api/cameras'),
  addCamera: (body) => send('POST', '/api/cameras', body),
  updateCamera: (id, body) => send('PUT', `/api/cameras/${id}`, body),
  deleteCamera: (id) => send('DELETE', `/api/cameras/${id}`),
  saveZone: (id, points) => send('PUT', `/api/cameras/${id}/zone`, { points }),
  events: () => get('/api/events'),
};
// send/get: ném Error(detail) khi !res.ok; caller hiển thị toast.

// ws.js
export function connectWs(onMessage, onStatus) {
  // new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`)
  // onopen -> onStatus(true); onclose -> onStatus(false), setTimeout(reconnect, 2000)
  // onmessage -> onMessage(JSON.parse(e.data))
}
```

## 5. Bước F3 — `camera-card.js`: video
```js
export class CameraCard {
  constructor(cam, cfg) // tạo DOM; this.latest = null (CameraResult mới nhất)
  setVideoMode(mode)    // 'webrtc' | 'mjpeg'
}
```
- **webrtc (mặc định):** `iframe.src = http://${location.hostname}:${cfg.webrtc_port}/${cam.id}/?controls=false&muted=true&autoplay=true&playsinline=true`.
- **mjpeg (fallback):** `img.src = /api/cameras/${cam.id}/mjpeg`.
- Nút ⚙ trong card có toggle "Video: WebRTC / MJPEG" (lưu `localStorage`). Dùng MJPEG khi camera là H.265 hoặc WebRTC không lên.
- Lưu ý căn khớp: cả video và canvas đều phủ đúng khung 16:9. Nếu camera không phải 16:9, trang MediaMTX tự letterbox → bbox lệch. Quy định PoC: **chỉ dùng camera 16:9** (thông báo ở README). MJPEG luôn là 1280x720 nên luôn khớp.

## 6. Bước F4 — `overlay.js`: vẽ canvas
Vòng render dùng `requestAnimationFrame` toàn trang (1 vòng cho mọi card), mỗi card:
```js
function draw(card) {
  const c = card.canvas, dpr = devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  if (c.width !== w*dpr) { c.width = w*dpr; c.height = h*dpr; }
  const g = c.getContext('2d'); g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,w,h);
  const r = card.latest;
  // 1. Zone: polygon từ card.cam.zone (x*w, y*h), stroke 3px màu state, fill màu state alpha 0.12
  // 2. Nếu r && Date.now()/1000 - r.ts < 1.0: vẽ bbox (stroke 2px; 2W = #38bdf8, 4W = #a78bfa),
  //    nhãn `${tid} ${group}` nền đen alpha 0.6 phía trên bbox, chấm tròn foot (bottom-center) r=3.
  //    Quá 1s không có dữ liệu mới -> không vẽ bbox (tránh bbox "đóng băng").
  // 3. Nếu card.zoneEditor.active: vẽ điểm đang chấm (xem F6)
}
```
Cập nhật DOM badge + metrics **khi nhận gói WS** (không phải mỗi frame): `fmt(v) = v==null ? '–' : v.toFixed(1)+'s'`; `o_vis` hiển thị `%`.

**Xong khi:** bbox bám theo xe trên video với độ lệch mắt thường chấp nhận được (< 0.3 s).

## 7. Bước F5 — `main.js`: luồng dữ liệu
1. `cfg = await api.config()`, `cams = await api.cameras()` → tạo `CameraCard` cho từng camera theo thứ tự id; ô trống hiển thị nút "+ Thêm camera".
2. `connectWs(msg => { if (msg.type==='results') msg.data.forEach(r => cards[r.camera_id]?.update(r)); if (msg.type==='event') eventsPanel.prepend(msg.data); }, setWsDot)`.
3. `eventsPanel.load(await api.events())`.
4. Header hiển thị chip `DEMO` nếu `cfg.demo_mode`.

## 8. Bước F6 — `zone-editor.js`: vẽ Poly Zone trực tiếp
Luồng thao tác:
1. Bấm **✏️** → `active=true`, `canvas.style.pointerEvents='auto'`, card thêm viền xanh dương, hiện thanh nhỏ: `[↶ Hoàn tác] [🗑 Xóa] [💾 Lưu] [✕ Hủy]` + hướng dẫn "Click các điểm bao đoạn đường dài ~2 vạch sơn + 2 khoảng trống (12–16 m), tối thiểu 3 điểm".
2. Để dễ nhìn khi vẽ: đặt ảnh nền tĩnh `snapshot.jpg?t=now` lên một `<img>` tạm phía trên video (tránh xe chạy gây rối mắt); xóa khi kết thúc.
3. `click`: `points.push({x: +(e.offsetX/w).toFixed(4), y: +(e.offsetY/h).toFixed(4)})`; vẽ đỉnh + đường nối + đường nét đứt về điểm đầu.
4. **Lưu**: `points.length >= 3` → `api.saveZone(id, points)` → cập nhật `card.cam.zone` → thoát chế độ. **Xóa** → lưu `[]`.
5. Phím `Esc` = Hủy, `Ctrl+Z` = Hoàn tác.
6. Import JSON (trong menu ⚙): textarea dán `[{x,y},...]` chuẩn hóa, **hoặc** JSON Roboflow dạng pixel `{"points":[{"x":..,"y":..}], "image_width":W,"image_height":H}` → chia W/H. Kiểm tra hợp lệ rồi gọi `saveZone`.

Nút **📷**: mở `/api/cameras/{id}/snapshot.jpg` trong tab mới (tải ảnh 1280x720 cho Roboflow/báo cáo).

## 9. Bước F7 — Quản lý camera (modal ⚙ / + Thêm)
Form: Tên, RTSP URL, checkbox "Có đèn tín hiệu", checkbox "Bật". Nút Lưu → `addCamera`/`updateCamera`; nút Xóa (confirm) → `deleteCamera`. Sau khi lưu: tải lại danh sách camera và dựng lại card (iframe cần reload vì MediaMTX restart — `setTimeout(reloadIframe, 3000)`).

## 10. Bước F8 — `events-panel.js`
- Mỗi thẻ: thumbnail `snapshot_url`, badge state, tên camera, giờ `HH:mm:ss`, "kéo dài Xs", 1 dòng chỉ số chính (`T50 4B`, `D85 4B`, `Phủ`).
- Click thumbnail → modal ảnh lớn.
- Sự kiện mới: highlight 3 s + phát âm thanh ngắn (`new Audio('data:audio/wav;base64,...')` hoặc `AudioContext` beep 0.2 s; bật/tắt bằng nút 🔔 ở header vì trình duyệt chặn autoplay cho tới khi người dùng click).
- Đồng thời viền card camera tương ứng nhấp nháy màu state 5 s.

## Checklist hoàn thành Frontend
- [ ] 4/6/8 ô hiển thị WebRTC qua SSH tunnel; fallback MJPEG hoạt động.
- [ ] Zone + bbox + badge góc dưới phải cập nhật theo WS; mất WS → chấm đỏ, tự kết nối lại.
- [ ] Vẽ/xóa/import zone lưu được, F5 trang vẫn còn.
- [ ] Sự kiện hiện kèm ảnh, âm thanh, highlight card.
- [ ] Không lỗi console trên Chrome/Edge bản mới.
