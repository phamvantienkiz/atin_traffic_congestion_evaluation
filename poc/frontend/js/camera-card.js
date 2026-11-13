import { STATE_META } from './overlay.js';
import { ZoneEditor } from './zone-editor.js';

const fmt = (v) => (v == null ? '–' : `${Number(v).toFixed(1)}s`);

export class CameraCard {
  constructor(cam, cfg, { onEditCam, onNotify }) {
    this.cam = cam;
    this.cfg = cfg;
    this.latest = null;
    this.videoMode = localStorage.getItem(`video_mode_${cam.id}`) || 'mjpeg';

    this.el = document.createElement('article');
    this.el.className = 'cam-card';
    this.el.innerHTML = `
      <div class="cam-card-head">
        <div class="cam-title">
          <span class="cam-id-tag">${cam.id}</span>
          <span class="cam-name" title="${cam.name}">${cam.name || cam.id}</span>
        </div>
        <div class="cam-actions">
          <button type="button" class="btn btn-xs btn-zone" title="Vẽ Poly Zone">✏️</button>
          <a class="btn btn-xs" href="/api/cameras/${cam.id}/snapshot.jpg" target="_blank" title="Cap ảnh 720p">📷</a>
          <button type="button" class="btn btn-xs btn-cfg" title="Cài đặt camera">⚙</button>
        </div>
      </div>
      <div class="zone-toolbar hidden">
        <span class="zone-hint">Click các điểm bao đoạn đường ~2 vạch sơn + 2 khoảng trống (12–16 m), tối thiểu 3 điểm.</span>
        <button type="button" class="btn btn-xs z-undo">↶ Hoàn tác</button>
        <button type="button" class="btn btn-xs btn-danger z-clear">🗑 Xóa</button>
        <button type="button" class="btn btn-xs btn-primary z-save">💾 Lưu</button>
        <button type="button" class="btn btn-xs z-cancel">✕ Hủy</button>
      </div>
      <div class="viewport">
        <iframe class="vid-webrtc" allow="autoplay"></iframe>
        <img class="vid-mjpeg hidden" alt="MJPEG stream" />
        <img class="zone-bg hidden" alt="Snapshot nền vẽ zone" />
        <canvas></canvas>
        <div class="state-badge">MẤT TÍN HIỆU</div>
      </div>
      <div class="cam-metrics">
        <div>W: <strong class="m-w">–</strong> · 2B: <strong class="m-2w">–</strong> · 4B: <strong class="m-4w">–</strong></div>
        <div>Phủ: <strong class="m-ovis">–</strong> · Flow: <strong class="m-flow">–</strong></div>
        <div>T50 4B: <strong class="m-t4">–</strong> · 2B: <strong class="m-t2">–</strong></div>
        <div>D85 4B: <strong class="m-d4">–</strong> · 2B: <strong class="m-d2">–</strong></div>
      </div>
    `;

    this.iframe = this.el.querySelector('.vid-webrtc');
    this.mjpegImg = this.el.querySelector('.vid-mjpeg');
    this.zoneBg = this.el.querySelector('.zone-bg');
    this.zoneBg.addEventListener('error', () => this.zoneBg.classList.add('hidden'));
    this.canvas = this.el.querySelector('canvas');
    this.badge = this.el.querySelector('.state-badge');
    this.zoneToolbar = this.el.querySelector('.zone-toolbar');

    this.zoneEditor = new ZoneEditor(this, onNotify);
    this.canvas.addEventListener('click', (e) => this.zoneEditor.handleClick(e));

    this.el.querySelector('.btn-zone').addEventListener('click', () => this.zoneEditor.start());
    this.el.querySelector('.z-undo').addEventListener('click', () => this.zoneEditor.undo());
    this.el.querySelector('.z-clear').addEventListener('click', () => this.zoneEditor.clear());
    this.el.querySelector('.z-save').addEventListener('click', () => this.zoneEditor.save());
    this.el.querySelector('.z-cancel').addEventListener('click', () => this.zoneEditor.cancel());
    this.el.querySelector('.btn-cfg').addEventListener('click', () => onEditCam(this));

    this.setVideoMode(this.videoMode);
  }

  setVideoMode(mode) {
    this.videoMode = mode === 'mjpeg' ? 'mjpeg' : 'webrtc';
    localStorage.setItem(`video_mode_${this.cam.id}`, this.videoMode);
    if (this.videoMode === 'mjpeg') {
      this.iframe.classList.add('hidden');
      this.iframe.removeAttribute('src');
      this.mjpegImg.classList.remove('hidden');
      this.mjpegImg.src = `/api/cameras/${this.cam.id}/mjpeg`;
    } else {
      this.mjpegImg.classList.add('hidden');
      this.mjpegImg.removeAttribute('src');
      this.iframe.classList.remove('hidden');
      this.reloadIframe();
    }
  }

  reloadIframe() {
    if (this.videoMode !== 'webrtc') return;
    this.iframe.src = `http://${location.hostname}:${this.cfg.webrtc_port}/${this.cam.id}/?controls=false&muted=true&autoplay=true&playsinline=true`;
  }

  destroy() {
    this.zoneEditor.stop();
    this.iframe.removeAttribute('src');
    this.mjpegImg.removeAttribute('src');
  }

  flashAlert() {
    this.el.classList.remove('flash-alert');
    void this.el.offsetWidth;
    this.el.classList.add('flash-alert');
  }

  update(res) {
    this.latest = res;
    const meta = STATE_META[res.state] || STATE_META.UNKNOWN;
    this.badge.style.background = meta.color;
    this.badge.innerHTML = res.occlusion_hold
      ? `${meta.label} <span class="occ-tag">(che khuất)</span>`
      : meta.label;

    const m = res.metrics || {};
    this.el.querySelector('.m-w').textContent = m.w_total != null ? Number(m.w_total).toFixed(1) : '–';
    this.el.querySelector('.m-2w').textContent = m.n_2w ?? '–';
    this.el.querySelector('.m-4w').textContent = m.n_4w ?? '–';
    this.el.querySelector('.m-ovis').textContent = m.o_vis != null ? `${Math.round(m.o_vis * 100)}%` : '–';
    this.el.querySelector('.m-flow').textContent = m.v_flow != null ? Number(m.v_flow).toFixed(1) : '–';
    this.el.querySelector('.m-t4').textContent = fmt(m.t50_4w);
    this.el.querySelector('.m-t2').textContent = fmt(m.t50_2w);
    this.el.querySelector('.m-d4').textContent = fmt(m.d85_4w);
    this.el.querySelector('.m-d2').textContent = fmt(m.d85_2w);
  }
}
