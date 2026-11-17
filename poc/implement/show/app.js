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
  } else if (e.key >= '1' && e.key <= '9') {
    const idx = Number(e.key) - 1;
    if (idx < slides.length) goToSlide(idx);
  } else if (e.key === '0' && slides.length >= 10) {
    goToSlide(9);
  }
});

// Exact Python classify() V2 logic from poc/backend/ai/decision/classifier.py & config.py
const inO = document.getElementById('in-o');
const inV = document.getElementById('in-v');
const inT4 = document.getElementById('in-t4');
const inD4 = document.getElementById('in-d4');
const inT2 = document.getElementById('in-t2');
const inW = document.getElementById('in-w');
const presetBtns = Array.from(document.querySelectorAll('.preset-btn'));

const PRESETS = {
  clear_fast: { o: 55, v: 18.0, t4: 4.8, d4: 0, t2: 3.8, w: 20, n2: 8, n4: 4 },
  night_glare: { o: 80, v: 2.0, t4: 0, d4: 0, t2: 0, w: 0, n2: 0, n4: 0 },
  congested: { o: 78, v: 14.0, t4: 10.5, d4: 0, t2: 8.0, w: 20, n2: 8, n4: 4 },
  local_stall: { o: 55, v: 8.0, t4: 0, d4: 22.0, t2: 0, w: 12, n2: 0, n4: 4 },
  gridlocked: { o: 88, v: 4.5, t4: 0, d4: 24.0, t2: 0, w: 30, n2: 15, n4: 5 },
  macro_only: { o: 88, v: 4.0, t4: 0, d4: 0, t2: 0, w: 6, n2: 0, n4: 2 },
};

let simN2 = 8;
let simN4 = 4;

function runClassify(m) {
  const gt = (x, th) => x !== null && x > th;
  const hasTime = [m.t2, m.t4, m.d2, m.d4].some((x) => x !== null);
  const hasVehicles = m.w >= 3.0 || hasTime;

  const timeClear =
    hasTime &&
    [
      [m.t4, 5.5],
      [m.d4, 6.5],
      [m.t2, 4.5],
      [m.d2, 5.0],
    ].every(([x, th]) => x === null || x <= th);

  const hasT50Congested = gt(m.t4, 5.5) || gt(m.t2, 4.5);
  const hasD85Congested =
    (m.t4 === null && gt(m.d4, 6.5)) || (m.t2 === null && gt(m.d2, 5.0));
  const timeCongested = hasT50Congested || (hasD85Congested && m.v <= 15.0);

  const timeGridlock =
    gt(m.t4, 16.0) || gt(m.d4, 20.0) || gt(m.t2, 13.5) || gt(m.d2, 17.0);

  // 1. Empty / clear road or no real vehicles (blocks night rain headlight glare)
  if (m.o < 0.40 || !hasVehicles) {
    const conf = Math.min(0.98, 0.85 + (m.v > 10.0 ? 0.10 : 0.0));
    const why = !hasVehicles
      ? 'W < 3.0 và chưa có T50/D85 → Sanity Gate chặn nhiễu đèn pha/nền.'
      : 'Độ phủ O_vis < 40% (đường thoáng).';
    return { state: 'CLEAR', conf: Number(conf.toFixed(2)), reason: why };
  }

  // 1b. High-flow override: dense traffic actively discharging is CLEAR, not congested
  if (m.v > 18.0) {
    const conf = Math.min(0.98, 0.84 + (timeClear ? 0.12 : 0.0));
    return {
      state: 'CLEAR',
      conf: Number(conf.toFixed(2)),
      reason: 'V_flow > 18.0 px/s (lưu lượng đang thoát nhanh) → ép về CLEAR dù O_vis cao.',
    };
  }

  // 2. GRIDLOCKED
  if (m.o >= 0.85) {
    if ((timeGridlock && m.v <= 15.0) || (!hasTime && m.v <= 6.0)) {
      const conf = Math.min(
        0.98,
        0.75 + (timeGridlock ? 0.13 : 0.0) + (m.w >= 24.0 ? 0.10 : 0.0)
      );
      const why = timeGridlock
        ? 'O_vis ≥ 85%, V_flow ≤ 15 px/s kèm T50/D85 vượt ngưỡng kẹt (>16s/20s 4B).'
        : 'O_vis ≥ 85%, V_flow ≤ 6.0 px/s (nhánh Macro-only khi mất T50/D85).';
      return { state: 'GRIDLOCKED', conf: Number(conf.toFixed(2)), reason: why };
    }
  }

  // 3. CONGESTED
  if (m.o >= 0.70) {
    if ((timeCongested && m.v <= 18.0) || (!hasTime && m.v <= 14.0)) {
      const conf = Math.min(
        0.98,
        0.72 + (timeCongested ? 0.14 : 0.0) + (m.w >= 15.0 ? 0.10 : 0.0)
      );
      const why = timeCongested
        ? 'O_vis ≥ 70%, V_flow ≤ 18.0 px/s kèm T50 chậm (hoặc D85 khi chưa có T50 & Flow ≤ 15).'
        : 'O_vis ≥ 70%, V_flow ≤ 14.0 px/s (nhánh Macro-only khi mất T50/D85).';
      return { state: 'CONGESTED', conf: Number(conf.toFixed(2)), reason: why };
    }
  } else if (timeGridlock && m.v <= 15.0) {
    return {
      state: 'CONGESTED',
      conf: 0.82,
      reason: '40% ≤ O_vis < 70% nhưng T50/D85 vượt ngưỡng kẹt nặng & Flow ≤ 15 px/s (kẹt cục bộ).',
    };
  }

  // 4. CLEAR (busy road moving smoothly)
  const conf = Math.min(
    0.98,
    0.75 + (timeClear ? 0.12 : 0.0) + (m.v >= 10.0 ? 0.08 : 0.0)
  );
  return {
    state: 'CLEAR',
    conf: Number(conf.toFixed(2)),
    reason: 'Đông xe nhưng lưu thông ổn định (T50/D85 nhanh hoặc V_flow cao).',
  };
}

function updateSim() {
  if (!inO) return;
  const oPct = Number(inO.value);
  const v = Number(inV.value);
  const t4 = Number(inT4.value) || null;
  const d4 = Number(inD4.value) || null;
  const t2 = Number(inT2.value) || null;
  const w = Number(inW.value);
  const d2 = d4 ? Math.max(0, d4 - 3.0) : null;

  document.getElementById('val-o').textContent = `${oPct}%`;
  document.getElementById('val-v').textContent = v.toFixed(1);
  document.getElementById('val-t4').textContent = t4 ? `${t4.toFixed(1)}s` : '–';
  document.getElementById('val-d4').textContent = d4 ? `${d4.toFixed(1)}s` : '–';
  document.getElementById('val-t2').textContent = t2 ? `${t2.toFixed(1)}s` : '–';
  document.getElementById('val-w').textContent = w.toFixed(1);

  const res = runClassify({ w, o: oPct / 100, v, t4, d4, t2, d2 });
  const badge = document.getElementById('mock-badge');
  const labels = {
    CLEAR: ['THÔNG THOÁNG', '#1FA63A'],
    CONGESTED: ['ÙN TẮC', '#FF8A1F'],
    GRIDLOCKED: ['KẸT CỨNG', '#E5483D'],
  };
  const [lbl, col] = labels[res.state];
  badge.textContent = lbl;
  badge.style.background = col;

  const confPct = `${Math.round(res.conf * 100)}%`;
  document.getElementById('m-conf').textContent = confPct;
  document.getElementById('sim-reason').innerHTML = `Nhánh kích hoạt: <strong>${res.state} (${confPct})</strong> — ${res.reason}`;
  document.getElementById('mock-counts').textContent = `${simN2} xe máy · ${simN4} ô tô`;
  document.getElementById('m-o').textContent = `${oPct}%`;
  document.getElementById('m-v').textContent = `${v.toFixed(1)} px/s`;
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
    inO.value = p.o;
    inV.value = p.v;
    inT4.value = p.t4;
    inD4.value = p.d4;
    inT2.value = p.t2;
    inW.value = p.w;
    simN2 = p.n2;
    simN4 = p.n4;
    updateSim();
  });
});

[inO, inV, inT4, inD4, inT2, inW].forEach((el) => {
  if (!el) return;
  el.addEventListener('input', () => {
    presetBtns.forEach((b) => b.classList.remove('active'));
    updateSim();
  });
});

setActivePill(0);
updateSim();
