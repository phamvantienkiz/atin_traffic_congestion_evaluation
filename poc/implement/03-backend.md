# 03 — PHÂN HỆ BACKEND (`poc/backend/`) — GIAI ĐOẠN G3

> Đọc trước: [00](./00-overview-and-decisions.md) mục 2 (D1, D2, D11–D13, D16) và mục 4 (hợp đồng dữ liệu).
> Backend = FastAPI 1 tiến trình: quản lý cấu hình camera, MediaMTX, chạy `TrafficEngine` (từ `poc/ai`), phát WebSocket, lưu snapshot, phục vụ frontend tĩnh.

## 1. Cấu trúc file

```text
poc/backend/
├── __init__.py
├── main.py              # FastAPI app, lifespan, routes
├── settings.py          # đọc .env
├── camera_store.py      # đọc/ghi data/cameras.json (thread-safe)
├── mediamtx.py          # sinh mediamtx.yml + quản lý tiến trình con MediaMTX
├── events.py            # lưu event + snapshot
├── ws_hub.py            # quản lý client WebSocket + vòng broadcast 5Hz
├── schemas.py           # Pydantic models
└── data/
    ├── cameras.json     # tự tạo nếu chưa có: {"cameras": []}
    └── snapshots/
```

## 2. `settings.py`
```python
from dotenv import load_dotenv; load_dotenv()
POC_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = POC_DIR / "backend" / "data"
SNAP_DIR = DATA_DIR / "snapshots"
FRONTEND_DIR = POC_DIR / "frontend"
MEDIAMTX_BIN = POC_DIR / os.getenv("MEDIAMTX_BIN", "mediamtx/mediamtx")
MEDIAMTX_CONFIG = POC_DIR / os.getenv("MEDIAMTX_CONFIG", "mediamtx/mediamtx.yml")
MEDIAMTX_WEBRTC_PORT = 8889
WS_PUSH_HZ = 5
MAX_CAMERAS = 8
```

## 3. `schemas.py`
```python
class Point(BaseModel):
    x: float = Field(ge=0, le=1); y: float = Field(ge=0, le=1)

class CameraIn(BaseModel):
    name: str = ""
    rtsp_url: str
    enabled: bool = True
    has_traffic_light: bool = False

class Camera(CameraIn):
    id: str                      # cam1..cam8
    zone: list[Point] = []

class ZoneIn(BaseModel):
    points: list[Point]          # 0 (xóa) hoặc >= 3 điểm; validator kiểm tra
```

## 4. `mediamtx.py` — sinh cấu hình + chạy tiến trình con

```python
BASE = { ...các khóa giống mẫu ở 01 mục 5 trừ paths... }

class MediaMTX:
    def __init__(self, bin_path, cfg_path): self.proc = None
    def write_config(self, cameras: list[Camera]) -> None:
        paths = {c.id: {"source": c.rtsp_url, "rtspTransport": "tcp", "sourceOnDemand": False}
                 for c in cameras if c.enabled}
        yaml.safe_dump({**BASE, "paths": paths or {"all_others": None}}, open(cfg_path, "w"))
    def start(self) -> None:   # subprocess.Popen([bin, cfg]), log stdout vào logger "mediamtx"
    def restart(self) -> None: # terminate -> wait(5) -> start
    def stop(self) -> None
```
Quyết định đơn giản: **mỗi khi thêm/sửa/xóa camera → ghi lại yml và restart MediaMTX** (mất ~1 s hình, chấp nhận ở PoC; không dùng Control API). Cấu hình `paths` rỗng: dùng `{}` nếu MediaMTX chấp nhận, nếu lỗi thì bỏ khóa `paths`.

Nếu `MEDIAMTX_BIN` không tồn tại → log warning và bỏ qua (cho phép người dùng tự chạy MediaMTX riêng).

## 5. `camera_store.py`
- `load() -> list[Camera]`, `save(list[Camera])` (ghi file tạm rồi `os.replace` để không hỏng file), `next_id()` trả `camN` nhỏ nhất chưa dùng (tối đa 8 → lỗi 400).
- Bảo vệ bằng `threading.Lock`.

## 6. `events.py`
```python
class EventStore:
    def __init__(self): self.items = deque(maxlen=200)
    def add(self, partial: dict, frame: np.ndarray, cam: Camera) -> dict:
        # id = f"evt_{cam.id}_{int(time.time())}"
        # vẽ lên bản sao frame: zone (màu state), bbox đang có (lấy từ partial['detections']), chữ state + thời gian
        # cv2.imwrite(SNAP_DIR / f"{id}.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        # event = {id, camera_id, camera_name, state, ts, duration_s, snapshot_url: f"/snapshots/{id}.jpg", metrics}
        # items.appendleft(event); return event
    def list(self) -> list[dict]
```
Ghi ảnh chạy trong `asyncio.to_thread` để không chặn event loop.

## 7. `ws_hub.py`
```python
class WsHub:
    def __init__(self): self.clients: set[WebSocket] = set()
    async def connect(self, ws): await ws.accept(); self.clients.add(ws)
    def disconnect(self, ws): self.clients.discard(ws)
    async def broadcast(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try: await ws.send_text(data)
            except Exception: self.disconnect(ws)

async def push_loop(engine, hub, events, store):
    while True:
        await hub.broadcast({"type": "results", "data": engine.latest_results()})
        for partial, frame in engine.pop_events():
            ev = await asyncio.to_thread(events.add, partial, frame, store.get(partial["camera_id"]))
            await hub.broadcast({"type": "event", "data": ev})
        await asyncio.sleep(1 / WS_PUSH_HZ)
```

## 8. `main.py` — app, lifespan, routes

```python
@asynccontextmanager
async def lifespan(app):
    cams = store.load()
    mtx.write_config(cams); mtx.start()
    await asyncio.sleep(2)                 # chờ MediaMTX kéo luồng
    engine.start()
    for c in cams:
        if c.enabled: engine.upsert_camera(c.model_dump())
    task = asyncio.create_task(push_loop(engine, hub, events, store))
    yield
    task.cancel(); engine.stop(); mtx.stop()

app = FastAPI(lifespan=lifespan)
```

### Bảng API

| Method | Path | Body | Trả về | Hành vi |
| :-- | :-- | :-- | :-- | :-- |
| GET | `/api/health` | – | `{"ok": true, "gpu": "...", "cameras": n}` | |
| GET | `/api/config` | – | `{"webrtc_port": 8889, "demo_mode": bool}` | Frontend dùng để dựng URL iframe |
| GET | `/api/cameras` | – | `list[Camera]` | |
| POST | `/api/cameras` | `CameraIn` | `Camera` | gán id → save → `mtx.write_config+restart` → `engine.upsert_camera` |
| PUT | `/api/cameras/{id}` | `CameraIn` | `Camera` | đổi URL → restart MediaMTX; chỉ đổi tên/cờ đèn → không restart |
| DELETE | `/api/cameras/{id}` | – | `{"ok": true}` | `engine.remove_camera` → save → restart MediaMTX |
| PUT | `/api/cameras/{id}/zone` | `ZoneIn` | `Camera` | save → `engine.upsert_camera` (engine chỉ set_zone, **không** restart MediaMTX) |
| GET | `/api/cameras/{id}/snapshot.jpg` | – | `image/jpeg` | `engine.latest_frame` 1280x720 (nút "Cap ảnh" & nền vẽ zone) ; 404 nếu chưa có frame |
| GET | `/api/cameras/{id}/mjpeg` | – | `multipart/x-mixed-replace` | Fallback video: lấy `engine.latest_frame` ~10 FPS, JPEG q=70 (tái dùng generator ở `scripts/RTSP/server.py`) |
| GET | `/api/events` | – | `list[Event]` | |
| WS | `/ws` | – | xem 00 mục 4.3 | Gửi ngay 1 gói `results` khi kết nối |
| static | `/snapshots/*` | – | ảnh | `app.mount("/snapshots", StaticFiles(directory=SNAP_DIR))` |
| static | `/` | – | frontend | `app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True))` — **mount cuối cùng** |

Lỗi: dùng `HTTPException` với `detail` tiếng Việt rõ ràng (404 camera không tồn tại, 400 zone < 3 điểm, 400 vượt 8 camera). Endpoint đồng bộ nặng (ghi file, restart MediaMTX) gọi qua `asyncio.to_thread`.

## 9. Kiểm thử backend (Xong khi)

```bash
cd poc && ./run.sh
curl -X POST localhost:8080/api/cameras -H 'Content-Type: application/json' \
     -d '{"name":"Test","rtsp_url":"rtsp://user:pass@10.0.0.11:554/stream1"}'
curl localhost:8080/api/cameras
curl -X PUT localhost:8080/api/cameras/cam1/zone -H 'Content-Type: application/json' \
     -d '{"points":[{"x":0.1,"y":0.35},{"x":0.9,"y":0.37},{"x":0.95,"y":0.85},{"x":0.05,"y":0.83}]}'
curl -o s.jpg localhost:8080/api/cameras/cam1/snapshot.jpg
uv run python -c "import asyncio,websockets;asyncio.run((lambda: None)())"  # hoặc dùng wscat / trình duyệt
```
- [ ] WebSocket nhận gói `results` 5 lần/giây đúng hợp đồng 4.2.
- [ ] Restart server → camera & zone còn nguyên (đọc từ `cameras.json`).
- [ ] Bật `DEMO_MODE=1`, cho camera kẹt → có gói `event` + file ảnh trong `data/snapshots/`.
- [ ] Tắt hẳn MediaMTX binary → server vẫn chạy, camera báo `UNKNOWN`, không crash.
