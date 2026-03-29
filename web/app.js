const API_BASE = "/api";

const presenceText = document.getElementById("presence-text");
const presenceDot = document.getElementById("presence-dot");
const agentBubbleEl = document.getElementById("agent-bubble");
const assistantLogEl = document.getElementById("assistant-log");
const voiceBarsEl = document.getElementById("voice-bars");
const avatarCanvasEl = document.getElementById("avatar-canvas");
const controlListenEl = document.getElementById("control-listen");
const controlVoiceEl = document.getElementById("control-voice");
const controlStopEl = document.getElementById("control-stop");
const helpBtnEl = document.getElementById("help-btn");
const controlDevicesEl = document.getElementById("control-devices");
const confirmModalEl = document.getElementById("confirm-modal");
const confirmTitleEl = document.getElementById("confirm-title");
const confirmMessageEl = document.getElementById("confirm-message");
const confirmYesEl = document.getElementById("confirm-yes");
const confirmNoEl = document.getElementById("confirm-no");
const devicePanelEl = document.getElementById("device-panel");
const deviceListEl = document.getElementById("device-list");
const closeDevicesEl = document.getElementById("close-devices");
const avatarStatusEl = document.getElementById("avatar-status");
const orbCanvasEl = document.getElementById("orb-canvas");

let processingTurn = false;
let speechEnabled = true;
let speaking = false;
let micPermissionGranted = false;
let selectedVoice = null;
let manualListeningEnabled = true;
let devicesCache = null;
let pendingConfirmation = null;

let mediaStream = null;
let mediaRecorder = null;
let audioContext = null;
let analyser = null;
let vadTimer = null;
let recordingChunks = [];
let recordingStartedAt = 0;
let speechDetectedAt = 0;
let lastSpeechAt = 0;
let listeningActive = false;
let discardCapture = false;

let voiceState = "booting";
let mouthLevel = 0;
let mouthTarget = 0;
let mouthFrame = null;
let mouthShape = "rest";
let ttsPulse = 0;
let ttsPulseAt = 0;

let avatarCtx = null;
let avatarFrame = null;
let blinkLevel = 0;
let blinkTarget = 0;
let nextBlinkAt = 0;

let orbCtx = null;
let orbFrame = null;
let orbParticles = [];

const VOICE_STATE_TRANSITIONS = {
  booting: ["requesting_mic", "idle", "recovering"],
  requesting_mic: ["idle", "recovering"],
  idle: ["listening", "requesting_mic", "recovering", "thinking", "speaking"],
  listening: ["transcribing", "idle", "recovering", "speaking"],
  transcribing: ["thinking", "recovering", "idle"],
  thinking: ["speaking", "idle", "recovering"],
  speaking: ["idle", "recovering"],
  recovering: ["idle", "requesting_mic", "listening"],
};

const VOICE_PROFILES = {
  desktop: {
    vadThreshold: 0.023,
    silenceStopMs: 1250,
    noSpeechStopMs: 3800,
    maxRecordingMs: 11000,
    mouthSensitivity: 4.4,
    mouthFloor: 0.02,
    mouthSmooth: 0.34,
  },
  mobile: {
    vadThreshold: 0.03,
    silenceStopMs: 1550,
    noSpeechStopMs: 5200,
    maxRecordingMs: 13500,
    mouthSensitivity: 3.2,
    mouthFloor: 0.03,
    mouthSmooth: 0.28,
  },
};

let activeVoiceProfile = VOICE_PROFILES.desktop;

function reportStage(stage, status, meta = {}) {
  console.info("[nestra-voice]", { stage, status, state: voiceState, ...meta });
}

function detectVisemeFromBoundary(text, index) {
  if (!text || typeof index !== "number") {
    return "rest";
  }

  const windowText = text.slice(Math.max(0, index), Math.min(text.length, index + 4)).toLowerCase();
  if (!windowText) {
    return "rest";
  }

  if (/[ou]/.test(windowText)) {
    return "O";
  }
  if (/[ei]/.test(windowText)) {
    return "E";
  }
  if (/[a]/.test(windowText)) {
    return "A";
  }
  return "rest";
}

function setAgentBubble(text) {
  if (agentBubbleEl && text) {
    agentBubbleEl.textContent = text;
  }
}

function setPresence(status, text) {
  if (presenceText && text) {
    presenceText.textContent = text;
  }
  if (!presenceDot) {
    return;
  }
  presenceDot.classList.remove("connected", "degraded");
  if (status === "connected" || status === "degraded") {
    presenceDot.classList.add(status);
  }
}

function addSpeechLine(role, text) {
  if (!assistantLogEl) {
    return;
  }
  const line = document.createElement("div");
  line.className = `speech-line ${role}`;
  line.textContent = text;
  assistantLogEl.appendChild(line);
  assistantLogEl.scrollTop = assistantLogEl.scrollHeight;
}

// Accessibility: announce avatar state
function setAvatarStatus(text) {
  if (avatarStatusEl && text) {
    avatarStatusEl.textContent = text;
  }
}

// Haptic feedback for mobile
function haptic(type = "light") {
  if (navigator.vibrate) {
    const patterns = {
      light: [10],
      medium: [20],
      heavy: [40],
      success: [30, 50, 30],
      error: [100, 50, 100],
    };
    navigator.vibrate(patterns[type] || patterns.light);
  }
}

// Help modal
function openHelp() {
  document.getElementById("help-modal").hidden = false;
  haptic("light");
}
function closeHelp() {
  document.getElementById("help-modal").hidden = true;
}

// Confirmation modal for device actions
function showConfirmation(title, message, onConfirm) {
  if (!confirmModalEl) return Promise.reject(new Error("Modal not available"));
  confirmTitleEl.textContent = title;
  confirmMessageEl.textContent = message;
  pendingConfirmation = onConfirm;
  confirmModalEl.hidden = false;
  haptic("medium");
  return new Promise((resolve) => {
    const cleanup = () => {
      hideConfirmation();
      if (resolve) resolve();
    };
    confirmYesEl.onclick = () => { if (pendingConfirmation) pendingConfirmation(); cleanup(); };
    confirmNoEl.onclick = cleanup;
  });
}
function hideConfirmation() {
  confirmModalEl.hidden = true;
  pendingConfirmation = null;
}

// Device panel
async function fetchDevices() {
  try {
    const res = await apiFetch("/devices");
    return await res.json();
  } catch (err) {
    console.error("Failed to fetch devices", err);
    return { items: [] };
  }
}
function renderDevices(devices) {
  if (!deviceListEl) return;
  deviceListEl.innerHTML = "";
  devices.items.forEach((dev) => {
    const card = document.createElement("div");
    card.className = "device-card";
    card.innerHTML = `
      <h4>${dev.name}</h4>
      <div class="meta">${dev.type} · ${dev.room || "unknown room"}</div>
      <div class="state ${dev.online ? "" : "offline"}">${dev.online ? "Online" : "Offline"}</div>
    `;
    card.addEventListener("click", async () => {
      // Could expand to show controls; for now, just highlight
      haptic("light");
    });
    deviceListEl.appendChild(card);
  });
}
function toggleDevicePanel(show) {
  if (devicePanelEl) {
    devicePanelEl.hidden = !show;
    if (show) {
      fetchDevices().then((data) => renderDevices(data));
    }
  }
}


function transitionVoiceState(nextState, detail = "") {
  const allowed = VOICE_STATE_TRANSITIONS[voiceState] || [];
  if (voiceState !== nextState && !allowed.includes(nextState)) {
    reportStage("state_transition", "coerced", { from: voiceState, to: nextState, detail });
  }
  voiceState = nextState;
  reportStage("state_transition", "ok", { to: nextState, detail });

  // Accessibility status announcements
  const statusMap = {
    listening: "Listening for your command",
    speaking: "Speaking",
    thinking: "Thinking",
    idle: "Ready",
    transcribing: "Transcribing speech",
  };
  if (statusMap[nextState]) {
    setAvatarStatus(statusMap[nextState]);
  }

  // Adjust blink timing based on state
  const now = performance.now();
  if (nextState === "listening") {
    nextBlinkAt = now + 4000 + Math.random() * 3000;
  } else if (nextState === "speaking") {
    nextBlinkAt = now + 2000 + Math.random() * 2000;
  } else if (nextState === "thinking") {
    nextBlinkAt = now + 3500 + Math.random() * 2500;
  } else {
    nextBlinkAt = now + 2600 + Math.random() * 2800;
  }
}

function setAvatarSpeaking(active) {
  if (voiceBarsEl) {
    voiceBarsEl.classList.toggle("active", active);
  }
}

function updateControlStates() {
  if (controlListenEl) {
    controlListenEl.textContent = manualListeningEnabled ? "Pause mic" : "Resume mic";
    controlListenEl.setAttribute("aria-pressed", String(!manualListeningEnabled));
  }
  if (controlVoiceEl) {
    controlVoiceEl.textContent = speechEnabled ? "Mute voice" : "Unmute voice";
    controlVoiceEl.setAttribute("aria-pressed", String(!speechEnabled));
  }
}

function stopNow() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  speaking = false;
  mouthShape = "rest";
  ttsPulse = 0;
  setAvatarSpeaking(false);
  if (listeningActive) {
    stopVoiceCapture("manual");
  }
  transitionVoiceState("idle", "manual-stop");
  setAgentBubble("Stopped. Standing by for your next instruction.");
  haptic("medium");
}

function setSpeechEnabled(nextEnabled) {
  speechEnabled = nextEnabled;
  if (!speechEnabled) {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    speaking = false;
    mouthShape = "rest";
    ttsPulse = 0;
    setAvatarSpeaking(false);
    if (voiceState === "speaking") {
      transitionVoiceState("idle", "voice-muted");
      restartListeningSoon();
    }
    setAgentBubble("Voice output muted. Text responses remain active.");
    haptic("light");
  } else {
    setAgentBubble("Voice output restored.");
    restartListeningSoon();
    haptic("light");
  }
  updateControlStates();
}

function setManualListeningEnabled(nextEnabled) {
  manualListeningEnabled = nextEnabled;
  if (!manualListeningEnabled) {
    if (listeningActive) {
      stopVoiceCapture("manual");
    }
    if (voiceState === "listening" || voiceState === "requesting_mic") {
      transitionVoiceState("idle", "manual-listen-paused");
    }
    setAgentBubble("Microphone paused. Use Resume mic to listen again.");
    haptic("light");
  } else {
    setAgentBubble("Microphone resumed. Listening for your command.");
    restartListeningSoon();
    haptic("light");
  }
  updateControlStates();
}

function bindControlEvents() {
  if (controlListenEl) {
    controlListenEl.addEventListener("click", () => setManualListeningEnabled(!manualListeningEnabled));
  }
  if (controlVoiceEl) {
    controlVoiceEl.addEventListener("click", () => setSpeechEnabled(!speechEnabled));
  }
  if (controlStopEl) {
    controlStopEl.addEventListener("click", stopNow);
  }
  if (helpBtnEl) {
    helpBtnEl.addEventListener("click", openHelp);
  }
  if (controlDevicesEl) {
    controlDevicesEl.addEventListener("click", () => toggleDevicePanel());
  }
  if (closeDevicesEl) {
    closeDevicesEl.addEventListener("click", () => toggleDevicePanel(false));
  }

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement) {
      const tag = target.tagName.toLowerCase();
      if (target.isContentEditable || tag === "input" || tag === "textarea" || tag === "select") {
        return;
      }
    }

    if (event.code === "KeyL") {
      event.preventDefault();
      setManualListeningEnabled(!manualListeningEnabled);
      return;
    }
    if (event.code === "KeyM") {
      event.preventDefault();
      setSpeechEnabled(!speechEnabled);
      return;
    }
    if (event.code === "Escape") {
      event.preventDefault();
      stopNow();
      hideConfirmation();
      return;
    }
    if (event.code === "KeyD" || event.code === "Digit1") {
      event.preventDefault();
      toggleDevicePanel();
      return;
    }
    if (event.code === "Question") {
      event.preventDefault();
      openHelp();
      return;
    }
  });
}

function detectVoiceProfile() {
  const ua = navigator.userAgent || "";
  const smallScreen = window.matchMedia("(max-width: 900px)").matches;
  const touch = navigator.maxTouchPoints > 0;
  const mobileUa = /android|iphone|ipad|ipod|mobile/i.test(ua);
  const mobile = mobileUa || (smallScreen && touch);
  activeVoiceProfile = mobile ? VOICE_PROFILES.mobile : VOICE_PROFILES.desktop;
}

function chooseVoice() {
  if (!window.speechSynthesis) {
    return;
  }
  const voices = window.speechSynthesis.getVoices();
  if (!voices?.length) {
    return;
  }
  const english = voices.filter((voice) => voice.lang?.toLowerCase().startsWith("en"));
  const candidates = english.length ? english : voices;
  const maleHint = /(male|david|guy|mark|alex|daniel|james|ryan|aaron|fred|tom|google uk english male|microsoft.*david|microsoft.*guy)/i;
  selectedVoice = candidates.find((voice) => maleHint.test(voice.name)) || candidates[0] || null;
}

function cleanupVadTimer() {
  if (vadTimer) {
    window.clearInterval(vadTimer);
    vadTimer = null;
  }
}

function detectRmsLevel() {
  if (!analyser) {
    return 0;
  }
  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);
  let sum = 0;
  for (let i = 0; i < data.length; i += 1) {
    const centered = (data[i] - 128) / 128;
    sum += centered * centered;
  }
  return Math.sqrt(sum / data.length);
}

function chooseRecorderMimeType() {
  if (!window.MediaRecorder) {
    return "";
  }
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return options.find((value) => MediaRecorder.isTypeSupported(value)) || "";
}

function fitAvatarCanvas() {
  if (!avatarCanvasEl || !avatarCtx) {
    return;
  }
  const width = avatarCanvasEl.clientWidth || window.innerWidth;
  const height = avatarCanvasEl.clientHeight || window.innerHeight;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  avatarCanvasEl.width = Math.round(width * ratio);
  avatarCanvasEl.height = Math.round(height * ratio);
  avatarCtx.setTransform(ratio, 0, 0, ratio, 0, 0);

  // Also fit orb canvas
  if (orbCanvasEl && orbCtx) {
    const orbWidth = orbCanvasEl.clientWidth || window.innerWidth;
    const orbHeight = orbCanvasEl.clientHeight || window.innerHeight;
    const orbRatio = Math.min(window.devicePixelRatio || 1, 2);
    orbCanvasEl.width = Math.round(orbWidth * orbRatio);
    orbCanvasEl.height = Math.round(orbHeight * orbRatio);
    orbCtx.setTransform(orbRatio, 0, 0, orbRatio, 0, 0);
    // Reinitialize particles for new size
    initOrbParticles(orbWidth, orbHeight);
  }
}

function drawProceduralAvatar(width, height, now) {
  if (!avatarCtx) {
    return;
  }

  const cx = width * 0.5;
  const bob = Math.sin(now / 780) * Math.min(width, height) * 0.005;
  const headY = height * 0.34 + bob;
  const headR = Math.min(width, height) * 0.20; // larger head for presence
  const stateIntent =
    voiceState === "listening" ? 1 : voiceState === "thinking" ? 0.6 : voiceState === "speaking" ? 0.4 : 0;
  // Thinking pose: slight head tilt and upward gaze shift
  const tiltAngle = voiceState === "thinking" ? 0.05 : 0; // radians
  const gazeShift = voiceState === "thinking" ? { dx: -0.015, dy: -0.025 } : { dx: 0, dy: 0 };

  const bg = avatarCtx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "#0d2039");
  bg.addColorStop(1, "#050812");
  avatarCtx.fillStyle = bg;
  avatarCtx.fillRect(0, 0, width, height);

  avatarCtx.fillStyle = "rgba(35, 53, 91, 0.65)";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx, height * 0.98, headR * 1.65, headR * 0.45, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.fillStyle = "#1c2a45";
  avatarCtx.beginPath();
  avatarCtx.moveTo(cx - headR * 1.2, height);
  avatarCtx.lineTo(cx + headR * 1.2, height);
  avatarCtx.lineTo(cx + headR * 0.76, headY + headR * 0.62);
  avatarCtx.lineTo(cx - headR * 0.76, headY + headR * 0.62);
  avatarCtx.closePath();
  avatarCtx.fill();

  avatarCtx.fillStyle = "#e8b995";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx, headY, headR * 0.78, headR, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.fillStyle = "rgba(121, 73, 60, 0.36)";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx, headY + headR * 0.18, headR * 0.62, headR * 0.55, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.fillStyle = "#d49e7f";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx - headR * 0.82, headY, headR * 0.08, headR * 0.18, 0, 0, Math.PI * 2);
  avatarCtx.ellipse(cx + headR * 0.82, headY, headR * 0.08, headR * 0.18, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.fillStyle = "#2b1f1c";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx, headY - headR * 0.42, headR * 0.86, headR * 0.64, 0, Math.PI, Math.PI * 2);
  avatarCtx.fill();
  avatarCtx.beginPath();
  avatarCtx.moveTo(cx - headR * 0.73, headY - headR * 0.22);
  avatarCtx.lineTo(cx - headR * 0.33, headY + headR * 0.17);
  avatarCtx.lineTo(cx - headR * 0.86, headY + headR * 0.04);
  avatarCtx.closePath();
  avatarCtx.fill();
  avatarCtx.beginPath();
  avatarCtx.moveTo(cx + headR * 0.73, headY - headR * 0.22);
  avatarCtx.lineTo(cx + headR * 0.34, headY + headR * 0.17);
  avatarCtx.lineTo(cx + headR * 0.87, headY + headR * 0.05);
  avatarCtx.closePath();
  avatarCtx.fill();

  const eyeY = headY - headR * 0.12;
  const eyeXOffset = headR * 0.28;
  const eyeW = headR * 0.11;
  const eyeH = Math.max(1.5, headR * (0.08 - blinkLevel * 0.06));
  const eyeColor = voiceState === "listening" ? "#224f7c" : "#2e2a28";
  // Combine natural micro-movement, state intent, and thinking gaze shift
  const pupilDriftX = headR * 0.016 * Math.sin(now / 760) + stateIntent * headR * 0.01 + gazeShift.dx * headR;
  const pupilDriftY = headR * 0.01 * Math.cos(now / 940) - stateIntent * headR * 0.006 + gazeShift.dy * headR;
  avatarCtx.fillStyle = eyeColor;
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx - eyeXOffset, eyeY, eyeW, eyeH, 0, 0, Math.PI * 2);
  avatarCtx.ellipse(cx + eyeXOffset, eyeY, eyeW, eyeH, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.fillStyle = voiceState === "listening" ? "#9fd3ff" : "#6e8cb5";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx - eyeXOffset + pupilDriftX, eyeY + pupilDriftY, eyeW * 0.34, eyeH * 0.45, 0, 0, Math.PI * 2);
  avatarCtx.ellipse(cx + eyeXOffset + pupilDriftX, eyeY + pupilDriftY, eyeW * 0.34, eyeH * 0.45, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.fillStyle = "rgba(214, 236, 255, 0.72)";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx - eyeXOffset + eyeW * 0.18, eyeY - eyeH * 0.24, eyeW * 0.12, eyeH * 0.2, 0, 0, Math.PI * 2);
  avatarCtx.ellipse(cx + eyeXOffset + eyeW * 0.18, eyeY - eyeH * 0.24, eyeW * 0.12, eyeH * 0.2, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  const browLift = voiceState === "thinking" ? -headR * 0.04 : 0;
  avatarCtx.strokeStyle = "rgba(40, 28, 24, 0.72)";
  avatarCtx.lineWidth = Math.max(2, headR * 0.03);
  avatarCtx.lineCap = "round";
  avatarCtx.beginPath();
  avatarCtx.moveTo(cx - eyeXOffset - eyeW * 1.15, eyeY - eyeH * 2.8 + browLift);
  avatarCtx.lineTo(cx - eyeXOffset + eyeW * 1.1, eyeY - eyeH * 3.2 + browLift);
  avatarCtx.moveTo(cx + eyeXOffset - eyeW * 1.1, eyeY - eyeH * 3.2 + browLift * 0.5);
  avatarCtx.lineTo(cx + eyeXOffset + eyeW * 1.15, eyeY - eyeH * 2.8 + browLift * 0.5);
  avatarCtx.stroke();

  avatarCtx.fillStyle = "rgba(201, 142, 120, 0.7)";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx - headR * 0.3, headY + headR * 0.12, headR * 0.12, headR * 0.07, 0, 0, Math.PI * 2);
  avatarCtx.ellipse(cx + headR * 0.3, headY + headR * 0.12, headR * 0.12, headR * 0.07, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.strokeStyle = "rgba(154, 83, 70, 0.75)";
  avatarCtx.lineWidth = Math.max(1.2, headR * 0.016);
  avatarCtx.beginPath();
  avatarCtx.moveTo(cx, headY - headR * 0.03);
  avatarCtx.quadraticCurveTo(cx + headR * 0.04, headY + headR * 0.09, cx, headY + headR * 0.17);
  avatarCtx.stroke();

  const idleBob = Math.sin(now / 320) * 0.04;
  const open = Math.max(0.02, mouthLevel + idleBob * (speaking ? 0.8 : 0.2));
  const mouthY = headY + headR * 0.28;
  const viseme = {
    A: { widthBias: -0.012, heightBoost: 0.07 },
    E: { widthBias: 0.028, heightBoost: -0.012 },
    O: { widthBias: -0.03, heightBoost: 0.03 },
    rest: { widthBias: 0, heightBoost: 0 },
  }[mouthShape] || { widthBias: 0, heightBoost: 0 };

  const mouthW = headR * (0.14 - open * 0.03 + viseme.widthBias);
  const mouthH = headR * (0.03 + open * 0.16 + viseme.heightBoost);

  avatarCtx.fillStyle = "rgba(106, 44, 47, 0.78)";
  avatarCtx.beginPath();
  avatarCtx.ellipse(cx, mouthY, mouthW, mouthH, 0, 0, Math.PI * 2);
  avatarCtx.fill();

  avatarCtx.strokeStyle = "rgba(72, 31, 36, 0.86)";
  avatarCtx.lineWidth = Math.max(1.2, headR * 0.012);
  avatarCtx.beginPath();
  avatarCtx.moveTo(cx - mouthW * 0.98, mouthY);
  avatarCtx.quadraticCurveTo(cx, mouthY + mouthH * 0.22, cx + mouthW * 0.98, mouthY);
   avatarCtx.stroke();
 }

 // === Orb Particle System ===
 class OrbParticle {
   constructor(cx, cy, radius, size, speed) {
     this.cx = cx;
     this.cy = cy;
     this.radius = radius;
     this.size = size;
     this.speed = speed;
     this.angle = Math.random() * Math.PI * 2;
     this.yaw = Math.acos(2 * Math.random() - 1); // spherical distribution
     this.baseAlpha = 0.2 + Math.random() * 0.6;
     this.alpha = this.baseAlpha;
   }
   update(now, pulseFactor) {
     this.angle += this.speed * 0.001;
     const yaw = this.yaw;
     const r = this.radius * (0.9 + 0.2 * Math.sin(now / 1500 + this.speed));
     const x = this.cx + r * Math.sin(yaw) * Math.cos(this.angle);
     const y = this.cy + r * Math.cos(yaw);
     const visualRadius = this.size * (0.8 + 0.4 * pulseFactor);
     this.alpha = this.baseAlpha * (0.6 + 0.4 * Math.abs(Math.sin(now / 800 + this.speed)));
     this.x = x;
     this.y = y;
     this.visualRadius = visualRadius;
   }
   draw(ctx) {
     const { x, y, visualRadius, alpha } = this;
     const gradient = ctx.createRadialGradient(x, y, 0, x, y, visualRadius);
     gradient.addColorStop(0, `rgba(66, 245, 176, ${alpha})`);
     gradient.addColorStop(1, `rgba(66, 245, 176, 0)`);
     ctx.fillStyle = gradient;
     ctx.beginPath();
     ctx.arc(x, y, visualRadius, 0, Math.PI * 2);
     ctx.fill();
   }
 }

 function initOrbParticles(width, height) {
   orbParticles = [];
   const cx = width * 0.5;
   const cy = height * 0.35;
   const radius = Math.min(width, height) * 0.22;
   const count = 120;
   for (let i = 0; i < count; i++) {
     const size = 3 + Math.random() * 4;
     const speed = 0.3 + Math.random() * 0.8;
     orbParticles.push(new OrbParticle(cx, cy, radius, size, speed));
   }
 }

 function drawOrb(now) {
   if (!orbCtx) return;
   const width = orbCanvasEl.clientWidth || window.innerWidth;
   const height = orbCanvasEl.clientHeight || window.innerHeight;
   orbCtx.clearRect(0, 0, width, height);
   // Pulse factor based on voice state
   let pulseFactor = 0;
   if (speaking) {
     pulseFactor = Math.abs(ttsPulse);
   } else if (listeningActive) {
     const rms = detectRmsLevel();
     const threshold = activeVoiceProfile.vadThreshold;
     const normalized = Math.max(0, (rms - threshold * 0.55) / (threshold * activeVoiceProfile.mouthSensitivity));
     pulseFactor = Math.max(0.2, normalized);
   } else {
     pulseFactor = 0.2 + 0.1 * Math.sin(now / 2000);
   }
   orbParticles.forEach((p) => {
     p.update(now, pulseFactor);
     p.draw(orbCtx);
   });
 }

 function startOrbLoop() {
   if (orbFrame) return;
   const loop = () => {
     const now = performance.now();
     drawOrb(now);
     orbFrame = window.requestAnimationFrame(loop);
   };
   orbFrame = window.requestAnimationFrame(loop);
 }

 function renderAvatarFrame() {
  if (!avatarCtx || !avatarCanvasEl) {
    return;
  }

  const width = avatarCanvasEl.clientWidth || window.innerWidth;
  const height = avatarCanvasEl.clientHeight || window.innerHeight;
  drawProceduralAvatar(width, height, performance.now());
}

function startAvatarLoop() {
  if (avatarFrame) {
    return;
  }
  const loop = () => {
    const now = performance.now();
    if (now > nextBlinkAt) {
      blinkTarget = 1;
      nextBlinkAt = now + 2600 + Math.random() * 2800;
    }
    if (blinkTarget === 1) {
      blinkLevel += 0.2;
      if (blinkLevel >= 1) {
        blinkLevel = 1;
        blinkTarget = 0;
      }
    } else {
      blinkLevel += (0 - blinkLevel) * 0.28;
    }

    renderAvatarFrame();
    avatarFrame = window.requestAnimationFrame(loop);
  };
  avatarFrame = window.requestAnimationFrame(loop);
}

async function initAvatarRuntime() {
  if (!avatarCanvasEl) {
    return false;
  }

  avatarCtx = avatarCanvasEl.getContext("2d", { alpha: true });
  if (!avatarCtx) {
    return false;
  }

  // Initialize orb canvas
  if (orbCanvasEl) {
    orbCtx = orbCanvasEl.getContext("2d", { alpha: true });
    if (orbCtx) {
      fitAvatarCanvas(); // fits both canvases
      initOrbParticles(orbCanvasEl.clientWidth || window.innerWidth, orbCanvasEl.clientHeight || window.innerHeight);
      startOrbLoop();
    }
  }

  window.addEventListener("resize", fitAvatarCanvas);
  nextBlinkAt = performance.now() + 1200;
  startAvatarLoop();
  reportStage("avatar", "ready", { engine: "procedural-male" });
  return true;
}

function beginMouthLoop() {
  if (mouthFrame) {
    return;
  }
  const tick = () => {
    const now = performance.now();
    if (listeningActive) {
      const rms = detectRmsLevel();
      const threshold = activeVoiceProfile.vadThreshold;
      const normalized = Math.max(0, (rms - threshold * 0.55) / (threshold * activeVoiceProfile.mouthSensitivity));
      mouthTarget = Math.max(activeVoiceProfile.mouthFloor, Math.min(1, normalized));
    } else if (speaking) {
      const sincePulse = now - ttsPulseAt;
      const decay = Math.max(0, 1 - sincePulse / 210);
      const rhythmic = 0.28 + Math.abs(Math.sin(now / 92)) * 0.44;
      mouthTarget = Math.min(1, Math.max(rhythmic, ttsPulse * decay));
    } else {
      mouthTarget = 0;
    }

    mouthLevel += (mouthTarget - mouthLevel) * activeVoiceProfile.mouthSmooth;
    if (Math.abs(mouthLevel) < 0.001 && mouthTarget === 0) {
      mouthLevel = 0;
    }
    mouthFrame = window.requestAnimationFrame(tick);
  };
  mouthFrame = window.requestAnimationFrame(tick);
}

async function initMicrophone() {
  if (mediaStream) {
    return true;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setAgentBubble("Browser does not support live microphone capture.");
    return false;
  }

  try {
    transitionVoiceState("requesting_mic", "request-user-media");
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { noiseSuppression: true, echoCancellation: true, autoGainControl: true },
    });
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioContext.createMediaStreamSource(mediaStream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    micPermissionGranted = true;
    transitionVoiceState("idle", "microphone-ready");
    return true;
  } catch (_err) {
    micPermissionGranted = false;
    transitionVoiceState("recovering", "microphone-denied");
    setAgentBubble("Microphone permission is required. Tap once and allow microphone.");
    return false;
  }
}

function restartListeningSoon() {
  if (!manualListeningEnabled || !micPermissionGranted || listeningActive || processingTurn || speaking) {
    return;
  }
  window.setTimeout(() => {
    if (manualListeningEnabled && !listeningActive && !processingTurn && !speaking) {
      startVoiceCapture();
    }
  }, 550);
}

function stopVoiceCapture(reason) {
  if (!mediaRecorder || mediaRecorder.state !== "recording") {
    return;
  }
  if (reason === "manual") {
    discardCapture = true;
  }
  mediaRecorder.stop();
  cleanupVadTimer();
  listeningActive = false;

  if (reason === "silence") {
    transitionVoiceState("transcribing", "speech-silence-stop");
    setAgentBubble("Processing your speech...");
  } else if (reason === "timeout") {
    transitionVoiceState("transcribing", "recording-timeout");
    setAgentBubble("Listening window ended. Processing...");
  } else if (reason === "no-speech") {
    transitionVoiceState("idle", "no-speech");
    setAgentBubble("No speech detected. Recalibrating and waiting for your next command.");
  } else if (reason === "manual") {
    transitionVoiceState("idle", "manual-stop-capture");
  }
}

async function transcribeAudio(blob) {
  const form = new FormData();
  form.append("file", blob, "voice-capture.webm");

  const response = await fetch(`${API_BASE}/voice/transcribe`, { method: "POST", body: form });
  if (!response.ok) {
    let detail = `Voice transcription failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = payload.detail?.message || payload.detail || detail;
    } catch (_err) {
      // keep fallback detail
    }
    throw new Error(detail);
  }

  const payload = await response.json();
  const text = String(payload.text || "").trim();
  if (!text) {
    throw new Error("Empty transcript from speech backend");
  }
  return text;
}

async function startVoiceCapture() {
  if (!manualListeningEnabled || listeningActive || processingTurn || speaking) {
    return;
  }

  const ready = await initMicrophone();
  if (!ready || !mediaStream) {
    return;
  }

  const mimeType = chooseRecorderMimeType();
  try {
    mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);
  } catch (_err) {
    setAgentBubble("Could not start recorder on this browser.");
    return;
  }

  recordingChunks = [];
  recordingStartedAt = Date.now();
  speechDetectedAt = 0;
  lastSpeechAt = 0;
  listeningActive = true;
  transitionVoiceState("listening", "capture-started");
  setAgentBubble("Listening...");

  mediaRecorder.ondataavailable = (event) => {
    if (event.data?.size > 0) {
      recordingChunks.push(event.data);
    }
  };

  mediaRecorder.onerror = () => {
    listeningActive = false;
    cleanupVadTimer();
    transitionVoiceState("recovering", "recorder-error");
    setAgentBubble("Recorder error. Retrying microphone...");
    restartListeningSoon();
  };

  mediaRecorder.onstop = async () => {
    cleanupVadTimer();
    listeningActive = false;

    const blob = new Blob(recordingChunks, { type: recordingChunks[0]?.type || "audio/webm" });
    recordingChunks = [];

    if (discardCapture) {
      discardCapture = false;
      transitionVoiceState("idle", "capture-discarded");
      return;
    }

    if (blob.size < 1200 || !speechDetectedAt) {
      transitionVoiceState("idle", "empty-capture");
      restartListeningSoon();
      return;
    }

    try {
      const transcript = await transcribeAudio(blob);
      transitionVoiceState("thinking", "transcript-ready");
      setAgentBubble(`Heard: ${transcript}`);
      await runCommand(transcript);
    } catch (err) {
      const failure = `I could not transcribe speech: ${err.message}`;
      addSpeechLine("agent", failure);
      setAgentBubble(failure);
      speak(failure);
      transitionVoiceState("recovering", "transcription-failed");
      restartListeningSoon();
    }
  };

  mediaRecorder.start(220);
  haptic("light"); // Haptic: started listening

  vadTimer = window.setInterval(() => {
    const now = Date.now();
    const elapsed = now - recordingStartedAt;
    const rms = detectRmsLevel();
    const threshold = activeVoiceProfile.vadThreshold;

    if (rms >= threshold) {
      if (!speechDetectedAt) {
        speechDetectedAt = now;
      }
      lastSpeechAt = now;
      setAgentBubble("Listening: speech detected...");
    }

    if (!speechDetectedAt && elapsed >= activeVoiceProfile.noSpeechStopMs) {
      stopVoiceCapture("no-speech");
      return;
    }
    if (speechDetectedAt && now - lastSpeechAt >= activeVoiceProfile.silenceStopMs) {
      stopVoiceCapture("silence");
      return;
    }
    if (elapsed >= activeVoiceProfile.maxRecordingMs) {
      stopVoiceCapture("timeout");
    }
  }, 120);
}

function speak(text) {
  if (!speechEnabled || !window.speechSynthesis || !text) {
    return;
  }

  if (!selectedVoice) {
    chooseVoice();
  }

  const utterance = new SpeechSynthesisUtterance(text);
  if (selectedVoice) {
    utterance.voice = selectedVoice;
  }
  utterance.rate = 0.96;
  utterance.pitch = 0.82;

  utterance.onstart = () => {
    speaking = true;
    mouthShape = "A";
    ttsPulse = 0.9;
    ttsPulseAt = performance.now();
    setAvatarSpeaking(true);
    transitionVoiceState("speaking", "tts-start");
    if (listeningActive) {
      stopVoiceCapture("silence");
    }
    setAgentBubble(text);
    haptic("success");
  };
  utterance.onboundary = (event) => {
    ttsPulse = 1;
    ttsPulseAt = performance.now();
    mouthShape = detectVisemeFromBoundary(text, event.charIndex ?? 0);
  };
  utterance.onend = () => {
    speaking = false;
    mouthShape = "rest";
    ttsPulse = 0;
    setAvatarSpeaking(false);
    transitionVoiceState("idle", "tts-end");
    restartListeningSoon();
  };
  utterance.onerror = () => {
    speaking = false;
    mouthShape = "rest";
    ttsPulse = 0;
    setAvatarSpeaking(false);
    transitionVoiceState("recovering", "tts-error");
    restartListeningSoon();
  };

  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const payload = await res.json();
      detail = payload.detail?.message || payload.detail || detail;
    } catch (_err) {
      // keep fallback detail
    }
    throw new Error(detail);
  }
  return res;
}

async function summarizeHomeStatus() {
  const [ctx, devices, audit] = await Promise.all([
    apiFetch("/household/context").then((r) => r.json()),
    apiFetch("/devices").then((r) => r.json()),
    apiFetch("/audit-events").then((r) => r.json()),
  ]);

  const deviceItems = devices.items || [];
  const online = deviceItems.filter((item) => item.online).length;
  const blocked = (audit.items || []).filter((item) => item.outcome !== "allowed").length;

  return `${ctx.household.name}: ${online}/${deviceItems.length} devices online, ${blocked} blocked unsafe actions in recent logs.`;
}

async function runCommand(inputText) {
  const text = (inputText || "").trim();
  if (!text || processingTurn) {
    return;
  }

  processingTurn = true;
  transitionVoiceState("thinking", "assistant-turn");
  addSpeechLine("user", text);
  setAgentBubble("Processing...");

  try {
    const result = await apiFetch("/assistant/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => r.json());

    const rawResponse = result.reply_text || "Request processed.";
    // Strip action tags for speech output
    const cleanResponse = rawResponse.replace(/\[DEVICE:[^\]]+\]/g, '').trim();
    addSpeechLine("agent", rawResponse);
    setAgentBubble(rawResponse);
    speak(cleanResponse);

    // Handle executed actions (e.g., device state changes)
    if (result.executed_actions && Array.isArray(result.executed_actions) && result.executed_actions.length > 0) {
      result.executed_actions.forEach((act) => {
        const line = `✓ ${act.message}`;
        addSpeechLine("agent", line);
      });
    }

    // Handle clarifying question (pending confirmation)
    if (result.clarifying_question) {
      // Show modal and wait for user confirmation
      await showConfirmation("Confirm", result.clarifying_question, async () => {
        // Resubmit with confirm via a new endpoint or same with confirm flag (not implemented yet)
        setAgentBubble("Confirmation flow not implemented yet.");
      });
    }
  } catch (err) {
    const failure = `I could not complete that request: ${err.message}`;
    addSpeechLine("agent", failure);
    setAgentBubble(failure);
    speak(failure);
    transitionVoiceState("recovering", "assistant-failed");
    haptic("error");
  } finally {
    processingTurn = false;
    restartListeningSoon();
  }
}

(async () => {
  detectVoiceProfile();
  window.addEventListener("resize", detectVoiceProfile);
  beginMouthLoop();
  bindControlEvents();
  updateControlStates();
  transitionVoiceState("booting", "app-start");
  setPresence("", "Connecting to home context");

  if (window.speechSynthesis) {
    chooseVoice();
    window.speechSynthesis.onvoiceschanged = chooseVoice;
  }

  const avatarReady = await initAvatarRuntime();
  if (!avatarReady) {
    setAgentBubble("Avatar engine is unavailable on this device. Voice pipeline remains fully available.");
  }

  document.addEventListener(
    "pointerdown",
    async () => {
      if (!manualListeningEnabled || processingTurn || speaking || listeningActive) {
        return;
      }
      await startVoiceCapture();
    },
    { passive: true }
  );

  const micReady = await initMicrophone();
  if (micReady) {
    startVoiceCapture();
  }

  try {
    const summary = await summarizeHomeStatus();
    const greeting = `Hello, I am Nestra Assistant. ${summary}`;
    setPresence("connected", "Live data connected");
    setAgentBubble(greeting);
    addSpeechLine("agent", greeting);
    speak(greeting);
  } catch (_err) {
    const fallback =
      "Hello, I am Nestra Assistant. Live data is unavailable right now. Voice channel remains available for guided mode.";
    setPresence("degraded", "Simulated mode (live API unreachable)");
    setAgentBubble(fallback);
    addSpeechLine("agent", fallback);
    speak(fallback);
  }
})();
