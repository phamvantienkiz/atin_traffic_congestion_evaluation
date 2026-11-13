const slides = Array.from(document.querySelectorAll('.slide'));
const pills = Array.from(document.querySelectorAll('.slide-pill'));
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const btnMode = document.getElementById('btn-mode');
const progressEl = document.getElementById('progress-pill');

let currentIdx = 0;

function setActivePill(idx) {
  currentIdx = Math.max(0, Math.min(slides.length - 1, idx));
  pills.forEach((p, i) => p.classList.toggle('active', i === currentIdx));
  if (progressEl) {
    progressEl.textContent = `${String(currentIdx + 1).padStart(2, '0')} / ${String(slides.length).padStart(2, '0')}`;
  }
}

function goToSlide(idx) {
  const clamped = Math.max(0, Math.min(slides.length - 1, idx));
  slides[clamped].scrollIntoView({ behavior: 'smooth', block: 'start' });
  setActivePill(clamped);
}

pills.forEach((p, i) => p.addEventListener('click', () => goToSlide(i)));
if (btnPrev) btnPrev.addEventListener('click', () => goToSlide(currentIdx - 1));
if (btnNext) btnNext.addEventListener('click', () => goToSlide(currentIdx + 1));

if (btnMode) {
  btnMode.addEventListener('click', () => {
    const isDoc = document.body.classList.toggle('doc-mode');
    btnMode.textContent = isDoc ? 'Cuộn tài liệu' : 'Tỷ lệ 16:9';
  });
}

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const idx = slides.indexOf(entry.target);
        if (idx !== -1) setActivePill(idx);
      }
    });
  },
  { threshold: 0.45 }
);
slides.forEach((s) => observer.observe(s));

document.addEventListener('keydown', (e) => {
  if (e.target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    goToSlide(currentIdx + 1);
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    goToSlide(currentIdx - 1);
  } else if (e.key >= '1' && e.key <= '7') {
    goToSlide(Number(e.key) - 1);
  }
});

// Exact Python classify() logic from poc/backend/ai/decision/classifier.py
const inW = document.getElementById('in-w');
const inO = document.getElementById('in-o');
const inV = document.getElementById('in-v');
const inT4 = document.getElementById('in-t4');
const inD4 = document.getElementById('in-d4');
const inT2 = document.getElementById('in-t2');
const presetBtns = Array.from(document.querySelectorAll('.preset-btn'));

const PRESETS = {
  clear_fast: { w: 14.0, o: 42, v: 8.5, t4: 1.8, d4: 0, t2: 1.5, n2: 5, n4: 3 },
  night_parked: { w: 3.0, o: 12, v: 0.2, t4: 0, d4: 12, t2: 0, n2: 0, n4: 1 },
  congested: { w: 18.0, o: 52, v: 3.2, t4: 4.5, d4: 6.0, t2: 3.5, n2: 6, n4: 4 },
  gridlocked: { w: 28.0, o: 72, v: 0.4, t4: 9.0, d4: 13.0, t2: 6.5, n2: 10, n4: 6 },
  rescue: { w: 20.0, o: 82, v: 0.5, t4: 0, d4: 0, t2: 0, n2: 4, n4: 4 },
};
let simN2 = 5;
let simN4 = 3;

function runClassify(m) {
  const gt = (x, th) => x !== null && x > th;
  if (m.w < 12.0 && m.o < 0.35) {
    return { state: 'CLEAR', reason: 'W_total < 12.0 và O_vis < 35% (đường thoáng / ít xe).' };
  }
  const denseG = m.w >= 24.0 || m.o >= 0.65;
  const stall4w = gt(m.t4, 7.0) || gt(m.d4, 10.0);
  const stall2w = gt(m.t2, 5.0) || gt(m.d2, 8.0);
  const timeOk = m.n4 < 2 ? (gt(m.t2, 5.5) || gt(m.d2, 8.5)) : (stall4w && (stall2w || m.n2 === 0));
  const macroOk = m.v <= 1.0 || m.o >= 0.70;
  if (denseG && timeOk && macroOk) {
    return { state: 'GRIDLOCKED', reason: 'Mật độ cao (W ≥ 24 hoặc Phủ ≥ 65%) + dừng lâu (T50/D85) + V_flow ≤ 1.0.' };
  }
  if (m.o >= 0.75 && m.v <= 1.0 && m.w >= 18.0) {
    return { state: 'GRIDLOCKED', reason: 'Nhánh Macro Rescue: Phủ ≥ 75%, V_flow ≤ 1.0 và W ≥ 18.0 (bù gãy track ByteTrack).' };
  }
  const denseC = m.w >= 15.0 || m.o >= 0.45;
  const slow = gt(m.t4, 3.0) || gt(m.d4, 5.0) || gt(m.t2, 3.0) || gt(m.d2, 4.5) || (m.v > 1.0 && m.v < 6.0 && m.o >= 0.45);
  if (denseC && slow) {
    return { state: 'CONGESTED', reason: 'Mật độ đông (W ≥ 15 hoặc Phủ ≥ 45%) kèm di chuyển chậm (T50/D85 hoặc V_flow 1–6).' };
  }
  return { state: 'CLEAR', reason: 'Có xe trong vùng nhưng tốc độ thoát tốt, chưa thỏa điều kiện ùn tắc.' };
}

function updateSim() {
  if (!inW) return;
  const w = Number(inW.value);
  const oPct = Number(inO.value);
  const v = Number(inV.value);
  const t4 = Number(inT4.value) || null;
  const d4 = Number(inD4.value) || null;
  const t2 = Number(inT2.value) || null;
  const d2 = d4 ? Math.max(0, d4 - 2.0) : null;

  document.getElementById('val-w').textContent = w.toFixed(1);
  document.getElementById('val-o').textContent = `${oPct}%`;
  document.getElementById('val-v').textContent = v.toFixed(1);
  document.getElementById('val-t4').textContent = t4 ? `${t4.toFixed(1)}s` : '–';
  document.getElementById('val-d4').textContent = d4 ? `${d4.toFixed(1)}s` : '–';
  document.getElementById('val-t2').textContent = t2 ? `${t2.toFixed(1)}s` : '–';

  const res = runClassify({ w, o: oPct / 100, v, t4, d4, t2, d2, n2: simN2, n4: simN4 });
  const badge = document.getElementById('mock-badge');
  const labels = { CLEAR: ['THÔNG THOÁNG', '#1FA63A'], CONGESTED: ['ÙN Ứ', '#FF8A1F'], GRIDLOCKED: ['KẸT CỨNG', '#E5483D'] };
  const [lbl, col] = labels[res.state];
  badge.textContent = lbl;
  badge.style.background = col;

  document.getElementById('sim-reason').innerHTML = `Nhánh kích hoạt: <strong>${res.state}</strong> — ${res.reason}`;
  document.getElementById('m-w').textContent = w.toFixed(1);
  document.getElementById('m-2w').textContent = simN2;
  document.getElementById('m-4w').textContent = simN4;
  document.getElementById('mock-counts').textContent = `2B: ${simN2} · 4B: ${simN4}`;
  document.getElementById('m-o').textContent = `${oPct}%`;
  document.getElementById('m-v').textContent = v.toFixed(1);
  document.getElementById('m-t4').textContent = t4 ? `${t4.toFixed(1)}s` : '–';
  document.getElementById('m-t2').textContent = t2 ? `${t2.toFixed(1)}s` : '–';
  document.getElementById('m-d4').textContent = d4 ? `${d4.toFixed(1)}s` : '–';
  document.getElementById('m-d2').textContent = d2 ? `${d2.toFixed(1)}s` : '–';
}

presetBtns.forEach((btn) => {
  btn.addEventListener('click', () => {
    presetBtns.forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const p = PRESETS[btn.dataset.preset];
    inW.value = p.w;
    inO.value = p.o;
    inV.value = p.v;
    inT4.value = p.t4;
    inD4.value = p.d4;
    inT2.value = p.t2;
    simN2 = p.n2;
    simN4 = p.n4;
    updateSim();
  });
});

[inW, inO, inV, inT4, inD4, inT2].forEach((el) => {
  if (!el) return;
  el.addEventListener('input', () => {
    presetBtns.forEach((b) => b.classList.remove('active'));
    updateSim();
  });
});

setActivePill(0);
updateSim();
