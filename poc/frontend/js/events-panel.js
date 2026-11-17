import { STATE_META } from './overlay.js';

const STAGE_LABELS = {
  CONFIRMED_3M: 'Xác nhận 3p',
  FOLLOWUP_5M: 'Nhắc 5p',
  PERIODIC_15M: 'Định kỳ +15p',
  TRANSITION: 'Chuyển mức',
  RECOVERED_CLEAR: 'Đã thông thoáng',
};

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
  constructor(listEl, countEl, modalEl, modalImgEl, modalTitleEl, btnEl = null, unreadEl = null) {
    this.listEl = listEl;
    this.countEl = countEl;
    this.modalEl = modalEl;
    this.modalImgEl = modalImgEl;
    this.modalTitleEl = modalTitleEl;
    this.btnEl = btnEl;
    this.unreadEl = unreadEl;
    this.soundEnabled = false;
    this.isOpen = false;
    this.unreadCount = 0;
    this.items = [];
  }

  setOpen(open) {
    this.isOpen = open;
    if (open) {
      this.unreadCount = 0;
      this._syncUnread();
    }
  }

  _syncUnread() {
    if (!this.btnEl || !this.unreadEl) return;
    const hasUnread = this.unreadCount > 0;
    this.btnEl.classList.toggle('has-unread', hasUnread);
    this.unreadEl.classList.toggle('hidden', !hasUnread);
    this.unreadEl.textContent = `+${this.unreadCount}`;
  }

  load(items) {
    this.items = items || [];
    this.render();
  }

  prepend(evt, flashCardFn) {
    this.items.unshift(evt);
    if (this.items.length > 200) this.items.pop();
    if (!this.isOpen) {
      this.unreadCount += 1;
      this._syncUnread();
    }
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
      const d85 = m.d85_4w != null ? `${Number(m.d85_4w).toFixed(1)}s` : '–';
      const ovis = m.o_vis != null ? `${Math.round(m.o_vis * 100)}%` : '–';
      const flow = m.v_flow != null ? Number(m.v_flow).toFixed(1) : '–';
      const stageLabel = STAGE_LABELS[ev.event_stage] || ev.event_stage || '';
      const conf = ev.confidence ?? m.state_conf;
      const confStr = conf != null ? ` · Tin cậy ${Math.round(Number(conf) * 100)}%` : '';

      const row = document.createElement('div');
      row.className = `event-item${ev.id === highlightId ? ' is-new' : ''}`;
      row.innerHTML = `
        <img class="event-thumb" src="${ev.snapshot_url}" alt="${ev.state}" loading="lazy" />
        <div class="event-meta">
          <div class="event-badges">
            <span class="event-badge" style="background:${meta.color}">${meta.label}</span>
            ${stageLabel ? `<span class="event-stage">${stageLabel}</span>` : ''}
          </div>
          <div class="event-title">${ev.camera_name || ev.camera_id}</div>
          <div class="event-sub">${tStr} · kéo dài ${ev.duration_s}s${confStr}</div>
          <div class="event-sub">Độ phủ: ${ovis} · Dòng xe: ${flow} · Dừng (ô tô): ${d85}</div>
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
