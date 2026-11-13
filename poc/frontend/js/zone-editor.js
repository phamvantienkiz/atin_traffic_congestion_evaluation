import { api } from './api.js';

export function parseZoneJson(rawText) {
  const parsed = JSON.parse(rawText);
  if (Array.isArray(parsed)) {
    return parsed.map((p) => ({ x: Number(p.x), y: Number(p.y) }));
  }
  if (parsed && Array.isArray(parsed.points) && parsed.image_width && parsed.image_height) {
    const w = Number(parsed.image_width);
    const h = Number(parsed.image_height);
    return parsed.points.map((p) => ({
      x: Number((Number(p.x) / w).toFixed(4)),
      y: Number((Number(p.y) / h).toFixed(4)),
    }));
  }
  throw new Error('Định dạng JSON zone không hợp lệ');
}

export class ZoneEditor {
  constructor(card, onNotify) {
    this.card = card;
    this.onNotify = onNotify;
    this.active = false;
    this.points = [];
    this._onKeyDown = (e) => {
      if (!this.active) return;
      if (e.key === 'Escape') this.cancel();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        this.undo();
      }
    };
  }

  start() {
    if (this.active) return;
    this.active = true;
    this.points = (this.card.cam.zone || []).map((p) => ({ ...p }));
    this.card.el.classList.add('editing');
    this.card.canvas.classList.add('drawing');
    this.card.zoneToolbar.classList.remove('hidden');

    // Load static 720p snapshot behind canvas while drawing
    this.card.zoneBg.src = `/api/cameras/${this.card.cam.id}/snapshot.jpg?t=${Date.now()}`;
    this.card.zoneBg.classList.remove('hidden');
    window.addEventListener('keydown', this._onKeyDown);
  }

  stop() {
    this.active = false;
    this.card.el.classList.remove('editing');
    this.card.canvas.classList.remove('drawing');
    this.card.zoneToolbar.classList.add('hidden');
    this.card.zoneBg.classList.add('hidden');
    this.card.zoneBg.removeAttribute('src');
    window.removeEventListener('keydown', this._onKeyDown);
  }

  handleClick(e) {
    if (!this.active) return;
    const w = this.card.canvas.clientWidth;
    const h = this.card.canvas.clientHeight;
    if (!w || !h) return;
    const x = Math.max(0, Math.min(1, +(e.offsetX / w).toFixed(4)));
    const y = Math.max(0, Math.min(1, +(e.offsetY / h).toFixed(4)));
    this.points.push({ x, y });
  }

  undo() {
    this.points.pop();
  }

  cancel() {
    this.points = [];
    this.stop();
  }

  async clear() {
    try {
      const updated = await api.saveZone(this.card.cam.id, []);
      this.card.cam.zone = updated.zone;
      this.stop();
      this.onNotify('Đã xóa zone');
    } catch (err) {
      this.onNotify(err.message);
    }
  }

  async save() {
    if (this.points.length < 3) {
      this.onNotify('Zone cần tối thiểu 3 điểm');
      return;
    }
    try {
      const updated = await api.saveZone(this.card.cam.id, this.points);
      this.card.cam.zone = updated.zone;
      this.stop();
      this.onNotify('Đã lưu Poly Zone');
    } catch (err) {
      this.onNotify(err.message);
    }
  }
}
