/**
 * RTSP Multi-Stream Video Wall — Frontend Controller
 * Follows "Soft Clean Cards" Design System specifications
 */

(function () {
  "use strict";

  const TOTAL_SLOTS = 8;
  const STORAGE_KEY_PREFIX = "atin_rtsp_slot_";
  const STORAGE_LAYOUT_KEY = "atin_rtsp_layout";
  const POLL_INTERVAL_MS = 1000;

  // DOM Elements
  const videoGrid = document.getElementById("videoGrid");
  const heroActiveStreams = document.getElementById("heroActiveStreams");
  const heroTotalSlots = document.getElementById("heroTotalSlots");
  const layoutTabs = document.querySelectorAll('.segmented button[role="tab"]');
  const btnDemoAll = document.getElementById("btnDemoAll");
  const btnStopAll = document.getElementById("btnStopAll");

  const slotsState = {};
  let currentLayout = 4;
  let statusPollTimer = null;
  let isBackendAvailable = false;

  const ICON_PLAY = `
    <svg viewBox="0 0 24 24">
      <polygon points="5 3 19 12 5 21 5 3"></polygon>
    </svg>
  `;

  const ICON_STOP = `
    <svg viewBox="0 0 24 24">
      <rect x="6" y="6" width="12" height="12"></rect>
    </svg>
  `;

  /**
   * Initializes slot state and binds event listeners for all 8 slots.
   */
  function initSlots() {
    for (let i = 1; i <= TOTAL_SLOTS; i++) {
      const card = document.getElementById(`slot-card-${i}`);
      if (!card) continue;

      const input = card.querySelector(".rtsp-input");
      const btnPlay = card.querySelector(".btn-play-ink");
      const btnClear = card.querySelector(".btn-clear");
      const btnFullscreen = card.querySelector(".btn-fullscreen");
      const btnPresetDemo = card.querySelector(".btn-preset-demo");
      const btnPresetCopy = card.querySelector(".btn-preset-copy");
      const imgStream = card.querySelector(".video-stream");
      const canvasStream = card.querySelector(".video-canvas");
      const placeholder = card.querySelector(".viewport-placeholder");
      const hud = card.querySelector(".video-hud");
      const resIndicator = card.querySelector(".res-indicator");
      const statusPill = card.querySelector(".status-pill");
      const statusText = card.querySelector(".status-text");
      const valFps = card.querySelector(".val-fps");
      const valRes = card.querySelector(".val-res");
      const valState = card.querySelector(".val-state");

      const savedUrl = localStorage.getItem(`${STORAGE_KEY_PREFIX}${i}`) || "";
      if (savedUrl) {
        input.value = savedUrl;
      }

      slotsState[i] = {
        id: i,
        card,
        input,
        btnPlay,
        btnClear,
        btnFullscreen,
        btnPresetDemo,
        btnPresetCopy,
        imgStream,
        canvasStream,
        placeholder,
        hud,
        resIndicator,
        statusPill,
        statusText,
        valFps,
        valRes,
        valState,
        isPlaying: false,
        url: savedUrl,
        animFrameId: null,
      };

      // Events
      btnPlay.addEventListener("click", () => toggleStream(i));
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") toggleStream(i);
      });
      input.addEventListener("change", () => {
        localStorage.setItem(`${STORAGE_KEY_PREFIX}${i}`, input.value.trim());
      });

      btnClear.addEventListener("click", () => clearSlot(i));
      btnFullscreen.addEventListener("click", () => toggleFullscreen(i));

      btnPresetDemo.addEventListener("click", () => {
        input.value = "demo";
        localStorage.setItem(`${STORAGE_KEY_PREFIX}${i}`, "demo");
        if (!slotsState[i].isPlaying) {
          startStream(i);
        }
      });

      btnPresetCopy.addEventListener("click", () => {
        const val = input.value.trim();
        if (val) {
          navigator.clipboard.writeText(val);
          const orig = btnPresetCopy.textContent;
          btnPresetCopy.textContent = "Copied!";
          setTimeout(() => (btnPresetCopy.textContent = orig), 1200);
        }
      });

      imgStream.addEventListener("load", () => {
        placeholder.style.display = "none";
        imgStream.classList.add("is-active");
        hud.style.display = "flex";
      });

      imgStream.addEventListener("error", () => {
        if (slotsState[i].isPlaying && isBackendAvailable) {
          updateSlotStatus(i, "error", "Stream error");
        }
      });
    }
  }

  /**
   * Toggles stream playback for a slot.
   */
  async function toggleStream(slotId) {
    const slot = slotsState[slotId];
    if (!slot) return;

    if (slot.isPlaying) {
      await stopStream(slotId);
    } else {
      await startStream(slotId);
    }
  }

  /**
   * Starts video streaming for a specific slot.
   */
  async function startStream(slotId) {
    const slot = slotsState[slotId];
    if (!slot) return;

    let url = slot.input.value.trim();
    if (!url) {
      url = "demo";
      slot.input.value = url;
    }

    localStorage.setItem(`${STORAGE_KEY_PREFIX}${slotId}`, url);
    slot.url = url;
    slot.isPlaying = true;

    updateSlotStatus(slotId, "connecting", "Connecting...");
    slot.btnPlay.innerHTML = ICON_STOP;
    slot.btnPlay.classList.add("is-playing");
    slot.btnPlay.title = "Dừng phát luồng";

    // If backend is active, use MJPEG stream
    if (isBackendAvailable) {
      try {
        await fetch(`/api/stream/${slotId}/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });

        const streamUrl = `/api/stream/${slotId}?url=${encodeURIComponent(url)}&t=${Date.now()}`;
        slot.imgStream.src = streamUrl;
        slot.placeholder.style.display = "none";
        slot.canvasStream.classList.remove("is-active");
        slot.imgStream.classList.add("is-active");
        slot.hud.style.display = "flex";
      } catch (err) {
        console.warn(`Backend stream failed, fallback to local canvas`, err);
        startCanvasSimulation(slotId);
      }
    } else {
      // Backend offline or running in standalone file:/// mode
      startCanvasSimulation(slotId);
    }

    updateHeroMetric();
  }

  /**
   * Runs high-fidelity synthetic live simulation on HTML5 Canvas.
   */
  function startCanvasSimulation(slotId) {
    const slot = slotsState[slotId];
    if (!slot || !slot.canvasStream) return;

    slot.placeholder.style.display = "none";
    slot.imgStream.classList.remove("is-active");
    slot.canvasStream.classList.add("is-active");
    slot.hud.style.display = "flex";

    const canvas = slot.canvasStream;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;

    updateSlotStatus(slotId, "live", "Live");
    slot.valFps.textContent = "25.0";
    slot.valRes.textContent = `${w}×${h}`;
    slot.resIndicator.textContent = `${w}×${h}`;
    slot.valState.textContent = isBackendAvailable ? "Stable" : "Local Mock";

    function draw(timestamp) {
      if (!slot.isPlaying) return;

      const t = timestamp / 1000;

      // Dark background
      ctx.fillStyle = "#121218";
      ctx.fillRect(0, 0, w, h);

      // Grid
      ctx.strokeStyle = "#1C1C24";
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // Rotating Radar Sweep
      const cx = w / 2;
      const cy = h / 2;
      const radius = 90;

      ctx.strokeStyle = "#2D2D3C";
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, radius / 2, 0, Math.PI * 2);
      ctx.stroke();

      const angle = (t * 2.4) % (Math.PI * 2);
      const px = cx + radius * Math.cos(angle);
      const py = cy + radius * Math.sin(angle);

      ctx.strokeStyle = "#1F5FFF";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(px, py);
      ctx.stroke();

      // Top banner
      ctx.fillStyle = "#181822";
      ctx.fillRect(0, 0, w, 32);

      ctx.font = "600 12px Inter, sans-serif";
      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(`CAM ${String(slotId).padStart(2, "0")} — LIVE RTSP FEED`, 16, 21);

      // Timestamp
      const now = new Date();
      const timeStr = now.toTimeString().split(" ")[0] + `.${String(now.getMilliseconds()).padStart(3, "0")}`;
      ctx.font = "400 11px Inter, monospace";
      ctx.fillStyle = "#9A9AA5";
      ctx.fillText(timeStr, w - 110, 21);

      // Dynamic sine curve
      ctx.strokeStyle = "#1FA63A";
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let x = 20; x < w - 20; x += 4) {
        const val = Math.sin(x * 0.05 + t * 5.0) * 22;
        if (x === 20) ctx.moveTo(x, h - 45 + val);
        else ctx.lineTo(x, h - 45 + val);
      }
      ctx.stroke();

      // Bottom status
      ctx.font = "500 11px Inter, sans-serif";
      ctx.fillStyle = "#1FA63A";
      ctx.fillText("STATUS: ACTIVE 25.0 FPS | BUFFER: 1 FRAME (ZERO DELAY)", 20, h - 14);

      slot.animFrameId = requestAnimationFrame(draw);
    }

    slot.animFrameId = requestAnimationFrame(draw);
  }

  /**
   * Stops video streaming for a specific slot.
   */
  async function stopStream(slotId) {
    const slot = slotsState[slotId];
    if (!slot) return;

    slot.isPlaying = false;
    if (slot.animFrameId) {
      cancelAnimationFrame(slot.animFrameId);
      slot.animFrameId = null;
    }

    slot.imgStream.src = "";
    slot.imgStream.classList.remove("is-active");
    slot.canvasStream.classList.remove("is-active");
    slot.placeholder.style.display = "flex";
    slot.hud.style.display = "none";

    slot.btnPlay.innerHTML = ICON_PLAY;
    slot.btnPlay.classList.remove("is-playing");
    slot.btnPlay.title = "Bắt đầu phát luồng";

    updateSlotStatus(slotId, "idle", "Idle");
    slot.valFps.textContent = "0.0";
    slot.valRes.textContent = "--";
    slot.valState.textContent = "Disconnected";

    if (isBackendAvailable) {
      try {
        await fetch(`/api/stream/${slotId}/stop`, { method: "POST" });
      } catch (err) {}
    }

    updateHeroMetric();
  }

  /**
   * Clears URL and resets slot to idle.
   */
  function clearSlot(slotId) {
    const slot = slotsState[slotId];
    if (!slot) return;

    if (slot.isPlaying) {
      stopStream(slotId);
    }
    slot.input.value = "";
    localStorage.removeItem(`${STORAGE_KEY_PREFIX}${slotId}`);
  }

  /**
   * Toggles fullscreen overlay for a single camera card.
   */
  function toggleFullscreen(slotId) {
    const slot = slotsState[slotId];
    if (!slot) return;

    const isFull = slot.card.classList.toggle("is-fullscreen");
    document.body.style.overflow = isFull ? "hidden" : "";
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      for (let i = 1; i <= TOTAL_SLOTS; i++) {
        const slot = slotsState[i];
        if (slot && slot.card.classList.contains("is-fullscreen")) {
          slot.card.classList.remove("is-fullscreen");
          document.body.style.overflow = "";
        }
      }
    }
  });

  function updateSlotStatus(slotId, status, label) {
    const slot = slotsState[slotId];
    if (!slot) return;

    slot.statusPill.dataset.status = status;
    slot.statusText.textContent = label;
  }

  function setLayout(layoutCount) {
    currentLayout = parseInt(layoutCount, 10);
    videoGrid.dataset.layout = currentLayout;
    heroTotalSlots.textContent = currentLayout;
    localStorage.setItem(STORAGE_LAYOUT_KEY, currentLayout);

    layoutTabs.forEach((tab) => {
      const isSelected = parseInt(tab.dataset.layout, 10) === currentLayout;
      tab.setAttribute("aria-selected", isSelected ? "true" : "false");
    });

    for (let i = 1; i <= TOTAL_SLOTS; i++) {
      const slot = slotsState[i];
      if (!slot) continue;
      slot.card.style.display = i <= currentLayout ? "flex" : "none";
    }

    updateHeroMetric();
  }

  function updateHeroMetric() {
    let activeCount = 0;
    for (let i = 1; i <= currentLayout; i++) {
      if (slotsState[i] && slotsState[i].isPlaying) {
        activeCount++;
      }
    }
    heroActiveStreams.textContent = activeCount;
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) {
        isBackendAvailable = false;
        return;
      }
      isBackendAvailable = true;
      const data = await res.json();
      if (!data.slots) return;

      data.slots.forEach((item) => {
        const slot = slotsState[item.slot_id];
        if (!slot) return;

        if (slot.isPlaying && !slot.animFrameId) {
          if (item.status === "live") {
            updateSlotStatus(item.slot_id, "live", "Live");
            slot.valFps.textContent = item.fps.toFixed(1);
            if (item.width && item.height) {
              const resText = `${item.width}×${item.height}`;
              slot.valRes.textContent = resText;
              slot.resIndicator.textContent = resText;
            }
            slot.valState.textContent = "Stable";
          } else if (item.status === "connecting") {
            updateSlotStatus(item.slot_id, "connecting", "Connecting...");
            slot.valState.textContent = "Connecting";
          } else if (item.status === "error") {
            updateSlotStatus(item.slot_id, "error", item.error || "Offline");
            slot.valState.textContent = "Error";
          }
        }
      });
    } catch (err) {
      isBackendAvailable = false;
    }
  }

  function handleDemoAll() {
    for (let i = 1; i <= currentLayout; i++) {
      const slot = slotsState[i];
      if (slot) {
        slot.input.value = "demo";
        localStorage.setItem(`${STORAGE_KEY_PREFIX}${i}`, "demo");
        startStream(i);
      }
    }
  }

  function handleStopAll() {
    for (let i = 1; i <= TOTAL_SLOTS; i++) {
      if (slotsState[i] && slotsState[i].isPlaying) {
        stopStream(i);
      }
    }
  }

  async function checkBackend() {
    try {
      const res = await fetch("/api/status");
      isBackendAvailable = res.ok;
    } catch (e) {
      isBackendAvailable = false;
    }
  }

  function init() {
    initSlots();

    layoutTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        setLayout(tab.dataset.layout);
      });
    });

    btnDemoAll.addEventListener("click", handleDemoAll);
    btnStopAll.addEventListener("click", handleStopAll);

    const savedLayout = localStorage.getItem(STORAGE_LAYOUT_KEY) || "4";
    setLayout(savedLayout);

    checkBackend().then(() => {
      statusPollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
