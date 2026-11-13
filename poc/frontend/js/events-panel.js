import { STATE_META } from './overlay.js';

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 880;
    gain.gain.value = 0.08;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.18);
  } catch (_) {}
}

export class EventsPanel {
  constructor(listEl, countEl, modalEl, modalImgEl, modalTitleEl) {
    this.listEl = listEl;
    this.countEl = countEl;
    this.modalEl = modalEl;
    this.modalImgEl = modalImgEl;
    this.modalTitleEl = modalTitleEl;
    this.soundEnabled = false;
    this.items = [];
  }

  load(items) {
    this.items = items || [];
    this.render();
  }

  prepend(evt, flashCardFn) {
    this.items.unshift(evt);
    if (this.items.length > 200) this.items.pop();
    this.render(evt.id);
    if (this.soundEnabled) playBeep();
    flashCardFn?.(evt.camera_id);
  }

  render(highlightId = null) {
    this.countEl.textContent = String(this.items.length);
    if (!this.items.length) {
      this.listEl.innerHTML = '<div class="empty-hint">Chưa có sự kiện ùn tắc / kẹt xe.</div>';
      return;
    }

    this.listEl.innerHTML = '';
    for (const ev of this.items) {
      const meta = STATE_META[ev.state] || STATE_META.UNKNOWN;
      const tStr = new Date(ev.ts * 1000).toLocaleTimeString('vi-VN', { hour12: false });
      const m = ev.metrics || {};
      const t50 = m.t50_4w != null ? `${m.t50_4w.toFixed(1)}s` : '–';
      const d85 = m.d85_4w != null ? `${m.d85_4w.toFixed(1)}s` : '–';
      const ovis = m.o_vis != null ? `${Math.round(m.o_vis * 100)}%` : '–';

      const row = document.createElement('div');
      row.className = `event-item${ev.id === highlightId ? ' is-new' : ''}`;
      row.innerHTML = `
        <img class="event-thumb" src="${ev.snapshot_url}" alt="${ev.state}" loading="lazy" />
        <div class="event-meta">
          <span class="event-badge" style="background:${meta.color}">${meta.label}</span>
          <div class="event-title">${ev.camera_name || ev.camera_id}</div>
          <div class="event-sub">${tStr} · kéo dài ${ev.duration_s}s</div>
          <div class="event-sub">T50 4B: ${t50} · D85 4B: ${d85} · Phủ: ${ovis}</div>
        </div>
      `;
      row.addEventListener('click', () => {
        this.modalTitleEl.textContent = `${ev.camera_name || ev.camera_id} — ${meta.label} (${tStr})`;
        this.modalImgEl.src = ev.snapshot_url;
        this.modalEl.classList.remove('hidden');
      });
      this.listEl.appendChild(row);
    }
  }
}
