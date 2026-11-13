import { api } from './api.js';
import { CameraCard } from './camera-card.js';
import { EventsPanel } from './events-panel.js';
import { drawCardOverlay } from './overlay.js';
import { connectWs } from './ws.js';
import { parseZoneJson } from './zone-editor.js';

const gridEl = document.getElementById('camera-grid');
const wsPill = document.getElementById('ws-status');
const demoChip = document.getElementById('demo-chip');
const soundBtn = document.getElementById('btn-sound');
const toastEl = document.getElementById('toast');

const camModal = document.getElementById('cam-modal');
const camForm = document.getElementById('cam-form');
const camModalTitle = document.getElementById('cam-modal-title');
const camIdInput = document.getElementById('cam-id');
const camNameInput = document.getElementById('cam-name');
const camRtspInput = document.getElementById('cam-rtsp');
const camLightInput = document.getElementById('cam-light');
const camEnabledInput = document.getElementById('cam-enabled');
const camExtraTools = document.getElementById('cam-extra-tools');
const camVideoMode = document.getElementById('cam-video-mode');
const camZoneJson = document.getElementById('cam-zone-json');
const btnDeleteCam = document.getElementById('btn-delete-cam');
const btnImportZone = document.getElementById('btn-import-zone');

const snapModal = document.getElementById('snap-modal');
const eventsPanel = new EventsPanel(
  document.getElementById('events-list'),
  document.getElementById('event-count'),
  snapModal,
  document.getElementById('snap-modal-img'),
  document.getElementById('snap-modal-title'),
);

let appCfg = { webrtc_port: 28889, demo_mode: false };
let cards = {};
let layoutCount = Number(localStorage.getItem('grid_layout') || 4);
let toastTimer = null;

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.add('hidden'), 3000);
}

function setLayout(n) {
  layoutCount = n;
  localStorage.setItem('grid_layout', String(n));
  gridEl.dataset.layout = String(n);
  document.querySelectorAll('.btn-seg').forEach((btn) => {
    btn.classList.toggle('active', Number(btn.dataset.layout) === n);
  });
  renderEmptySlots();
}

function renderEmptySlots() {
  gridEl.querySelectorAll('.empty-slot').forEach((el) => el.remove());
  const camCount = Object.keys(cards).length;
  for (let i = camCount; i < layoutCount; i++) {
    const slot = document.createElement('div');
    slot.className = 'empty-slot';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn';
    btn.textContent = '+ Thêm camera';
    btn.addEventListener('click', () => openCamModal(null));
    slot.appendChild(btn);
    gridEl.appendChild(slot);
  }
}

function openCamModal(card) {
  if (card) {
    camModalTitle.textContent = `Cài đặt ${card.cam.id}`;
    camIdInput.value = card.cam.id;
    camNameInput.value = card.cam.name;
    camRtspInput.value = card.cam.rtsp_url;
    camLightInput.checked = Boolean(card.cam.has_traffic_light);
    camEnabledInput.checked = Boolean(card.cam.enabled);
    camVideoMode.value = card.videoMode;
    camZoneJson.value = JSON.stringify(card.cam.zone || []);
    camExtraTools.classList.remove('hidden');
    btnDeleteCam.classList.remove('hidden');
  } else {
    camModalTitle.textContent = 'Thêm camera';
    camIdInput.value = '';
    camNameInput.value = '';
    camRtspInput.value = '';
    camLightInput.checked = false;
    camEnabledInput.checked = true;
    camExtraTools.classList.add('hidden');
    btnDeleteCam.classList.add('hidden');
  }
  camModal.classList.remove('hidden');
}

async function reloadCameras(delayIframeReload = false) {
  const cams = await api.cameras();
  cams.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  gridEl.innerHTML = '';
  cards = {};
  for (const cam of cams) {
    const card = new CameraCard(cam, appCfg, {
      onEditCam: (c) => openCamModal(c),
      onNotify: showToast,
    });
    cards[cam.id] = card;
    gridEl.appendChild(card.el);
  }
  renderEmptySlots();
  if (delayIframeReload) {
    setTimeout(() => Object.values(cards).forEach((c) => c.reloadIframe()), 3000);
  }
}

// Event listeners
document.querySelectorAll('.btn-seg').forEach((btn) => {
  btn.addEventListener('click', () => setLayout(Number(btn.dataset.layout)));
});

document.getElementById('btn-add-cam').addEventListener('click', () => openCamModal(null));

soundBtn.addEventListener('click', () => {
  eventsPanel.soundEnabled = !eventsPanel.soundEnabled;
  soundBtn.textContent = eventsPanel.soundEnabled ? '🔔' : '🔕';
  showToast(eventsPanel.soundEnabled ? 'Đã bật âm thanh cảnh báo' : 'Đã tắt âm thanh');
});

document.querySelectorAll('[data-close]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.getElementById(btn.dataset.close).classList.add('hidden');
  });
});

camForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = camIdInput.value;
  const payload = {
    name: camNameInput.value.trim(),
    rtsp_url: camRtspInput.value.trim(),
    has_traffic_light: camLightInput.checked,
    enabled: camEnabledInput.checked,
  };
  try {
    if (id) {
      await api.updateCamera(id, payload);
      cards[id]?.setVideoMode(camVideoMode.value);
      showToast(`Đã cập nhật ${id}`);
    } else {
      await api.addCamera(payload);
      showToast('Đã thêm camera');
    }
    camModal.classList.add('hidden');
    await reloadCameras(true);
  } catch (err) {
    showToast(err.message);
  }
});

btnDeleteCam.addEventListener('click', async () => {
  const id = camIdInput.value;
  if (!id || !confirm(`Xóa camera ${id}?`)) return;
  try {
    await api.deleteCamera(id);
    camModal.classList.add('hidden');
    await reloadCameras(true);
    showToast(`Đã xóa ${id}`);
  } catch (err) {
    showToast(err.message);
  }
});

btnImportZone.addEventListener('click', async () => {
  const id = camIdInput.value;
  if (!id) return;
  try {
    const pts = parseZoneJson(camZoneJson.value);
    const updated = await api.saveZone(id, pts);
    if (cards[id]) cards[id].cam.zone = updated.zone;
    camModal.classList.add('hidden');
    showToast(`Đã import ${pts.length} điểm zone`);
  } catch (err) {
    showToast(err.message);
  }
});

function renderLoop() {
  for (const card of Object.values(cards)) {
    drawCardOverlay(card);
  }
  requestAnimationFrame(renderLoop);
}

async function init() {
  try {
    appCfg = await api.config();
    if (appCfg.demo_mode) demoChip.classList.remove('hidden');
  } catch (_) {}

  setLayout(layoutCount);
  await reloadCameras(false);
  try {
    eventsPanel.load(await api.events());
  } catch (_) {}

  connectWs(
    (msg) => {
      if (msg.type === 'results') {
        for (const r of msg.data || []) cards[r.camera_id]?.update(r);
      } else if (msg.type === 'event') {
        eventsPanel.prepend(msg.data, (cid) => cards[cid]?.flashAlert());
      }
    },
    (online) => {
      wsPill.classList.toggle('online', online);
      wsPill.classList.toggle('offline', !online);
    },
  );

  requestAnimationFrame(renderLoop);
}

init();
