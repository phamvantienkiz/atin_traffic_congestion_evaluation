export const STATE_META = {
  CLEAR: { color: '#22c55e', label: 'THÔNG THOÁNG' },
  CONGESTED: { color: '#f59e0b', label: 'ÙN TẮC' },
  GRIDLOCKED: { color: '#ef4444', label: 'KẸT XE' },
  UNKNOWN: { color: '#9ca3af', label: 'MẤT TÍN HIỆU' },
};

function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

export function drawCardOverlay(card) {
  const c = card.canvas;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (!w || !h) return;

  const dpr = window.devicePixelRatio || 1;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }

  const g = c.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const r = card.latest;
  const state = r?.state || 'UNKNOWN';
  const meta = STATE_META[state] || STATE_META.UNKNOWN;

  // 1. Saved Poly Zone
  const zone = card.cam.zone;
  if (zone && zone.length >= 3 && !card.zoneEditor.active) {
    g.beginPath();
    zone.forEach((p, idx) => {
      if (idx === 0) g.moveTo(p.x * w, p.y * h);
      else g.lineTo(p.x * w, p.y * h);
    });
    g.closePath();
    g.fillStyle = hexToRgba(meta.color, 0.12);
    g.fill();
    g.lineWidth = 3;
    g.strokeStyle = meta.color;
    g.stroke();
  }

  // 2. BBoxes (discard if older than 1s to prevent frozen boxes)
  const nowSec = Date.now() / 1000;
  if (r && nowSec - r.ts < 1.0 && !card.zoneEditor.active) {
    g.font = '600 11px sans-serif';
    for (const d of r.detections || []) {
      const [bx1, by1, bx2, by2] = d.bbox;
      const x1 = bx1 * w;
      const y1 = by1 * h;
      const bw = (bx2 - bx1) * w;
      const bh = (by2 - by1) * h;
      const boxColor = d.group === '2W' ? '#38bdf8' : '#a78bfa';

      g.lineWidth = 2;
      g.strokeStyle = boxColor;
      g.strokeRect(x1, y1, bw, bh);

      const label = `${d.tid} ${d.group}`;
      const tw = g.measureText(label).width + 8;
      const ly = Math.max(0, y1 - 16);
      g.fillStyle = 'rgba(0,0,0,0.65)';
      g.fillRect(x1, ly, tw, 15);
      g.fillStyle = '#fff';
      g.fillText(label, x1 + 4, ly + 11);

      // Bottom-center foot dot
      g.beginPath();
      g.arc(x1 + bw * 0.5, y1 + bh, 3, 0, Math.PI * 2);
      g.fillStyle = boxColor;
      g.fill();
    }
  }

  // 3. In-progress Zone Editor
  if (card.zoneEditor.active) {
    const pts = card.zoneEditor.points;
    if (pts.length > 0) {
      g.beginPath();
      pts.forEach((p, idx) => {
        if (idx === 0) g.moveTo(p.x * w, p.y * h);
        else g.lineTo(p.x * w, p.y * h);
      });
      g.lineWidth = 2.5;
      g.strokeStyle = '#3b82f6';
      g.stroke();

      if (pts.length >= 2) {
        g.save();
        g.setLineDash([5, 5]);
        g.beginPath();
        g.moveTo(pts[pts.length - 1].x * w, pts[pts.length - 1].y * h);
        g.lineTo(pts[0].x * w, pts[0].y * h);
        g.stroke();
        g.restore();
      }

      for (const p of pts) {
        g.beginPath();
        g.arc(p.x * w, p.y * h, 5, 0, Math.PI * 2);
        g.fillStyle = '#2563eb';
        g.fill();
        g.lineWidth = 1.5;
        g.strokeStyle = '#fff';
        g.stroke();
      }
    }
  }
}
