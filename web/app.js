const API_BASE = "https://api.nestra.homelabdev.space";

const presenceText = document.getElementById("presence-text");
const humanAgentEl = document.getElementById("human-agent");
const agentStateTextEl = document.getElementById("agent-state-text");
const assistantLogEl = document.getElementById("assistant-log");

const modeTextBtn = document.getElementById("mode-text");
const modeVoiceBtn = document.getElementById("mode-voice");
const ttsToggleBtn = document.getElementById("tts-toggle");

const textRow = document.getElementById("text-row");
const voiceRow = document.getElementById("voice-row");
const nlInput = document.getElementById("nl-input");
const nlSendBtn = document.getElementById("nl-send-btn");
const voiceBtn = document.getElementById("voice-btn");

let inputMode = "text";
let speechEnabled = true;
let recognition = null;
let recognizing = false;

function setAgentState(state) {
  if (!humanAgentEl || !agentStateTextEl) {
    return;
  }
  humanAgentEl.classList.remove("idle", "listening", "thinking", "speaking", "error");
  humanAgentEl.classList.add(state);
  agentStateTextEl.textContent = state;
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

function speak(text) {
  if (!speechEnabled || !window.speechSynthesis) {
    return;
  }

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1;
  utterance.pitch = 0.98;
  utterance.onstart = () => setAgentState("speaking");
  utterance.onend = () => setAgentState("idle");
  utterance.onerror = () => setAgentState("error");

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

function setInputMode(mode) {
  inputMode = mode;
  modeTextBtn.classList.toggle("active", mode === "text");
  modeVoiceBtn.classList.toggle("active", mode === "voice");

  textRow.classList.toggle("hidden", mode !== "text");
  voiceRow.classList.toggle("hidden", mode !== "voice");
}

function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition || !voiceBtn) {
    voiceBtn.disabled = true;
    voiceBtn.textContent = "Voice unavailable";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    recognizing = true;
    setAgentState("listening");
    voiceBtn.textContent = "Listening...";
  };

  recognition.onend = () => {
    recognizing = false;
    voiceBtn.textContent = "Start listening";
    if (!window.speechSynthesis?.speaking) {
      setAgentState("idle");
    }
  };

  recognition.onerror = () => {
    setAgentState("error");
    addSpeechLine("agent", "I could not capture your voice. Please try again or switch to text.");
  };

  recognition.onresult = async (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript?.trim();
    if (!transcript) {
      return;
    }
    await runCommand(transcript);
  };
}

async function summarizeHomeStatus() {
  const [ctx, devices, audit] = await Promise.all([
    apiFetch("/v1/household/context").then((r) => r.json()),
    apiFetch("/v1/devices").then((r) => r.json()),
    apiFetch("/v1/audit-events").then((r) => r.json()),
  ]);

  const deviceItems = devices.items || [];
  const online = deviceItems.filter((item) => item.online).length;
  const blocked = (audit.items || []).filter((item) => item.outcome !== "allowed").length;

  return `${ctx.household.name}: ${online}/${deviceItems.length} devices online, ${blocked} blocked unsafe actions in recent logs.`;
}

async function submitIntent() {
  const payload = {
    intent_type: "shift_ev_charging_low_tariff_window",
    payload: {
      window_start: "23:00",
      window_end: "05:00",
    },
    confirm: true,
  };

  const res = await apiFetch("/v1/device-intents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function submitScenario(intentType, payload) {
  const res = await apiFetch("/v1/device-intents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intent_type: intentType, payload, confirm: true }),
  });
  return res.json();
}

async function runCommand(inputText) {
  const text = (inputText || "").trim();
  if (!text) {
    return;
  }

  addSpeechLine("user", text);
  setAgentState("thinking");

  const command = text.toLowerCase();

  try {
    if (command.includes("good night") || command.includes("security") || command.includes("arm")) {
      await submitScenario("arm_night_security_sweep", {
        arm_time: "22:30",
        zones: ["entryway", "garage", "living-room"],
      });
      const response = "Night security sweep is armed. Policy checks passed and I logged everything.";
      addSpeechLine("agent", response);
      speak(response);
      return;
    }

    if (command.includes("preheat") || command.includes("i am home") || command.includes("i'm home")) {
      await submitScenario("preheat_home_arrival", {
        arrival_time: "18:00",
        target_temperature_c: 21.5,
      });
      const response = "Comfort preheat is scheduled. I applied guardrails and recorded the action.";
      addSpeechLine("agent", response);
      speak(response);
      return;
    }

    if (command.includes("ev") || command.includes("charge") || command.includes("tariff")) {
      await submitIntent();
      const response = "EV low-tariff plan is applied. I validated the window and created an audit event.";
      addSpeechLine("agent", response);
      speak(response);
      return;
    }

    if (command.includes("status") || command.includes("summary") || command.includes("home")) {
      const response = await summarizeHomeStatus();
      addSpeechLine("agent", response);
      speak(response);
      return;
    }

    const fallback =
      "In this MVP, I can run security sweep, preheat home, optimize EV charging, or read home status. Please try one of those.";
    addSpeechLine("agent", fallback);
    speak(fallback);
    setAgentState("idle");
  } catch (err) {
    const failure = `I could not complete that request: ${err.message}`;
    addSpeechLine("agent", failure);
    speak(failure);
    setAgentState("error");
  }
}

modeTextBtn?.addEventListener("click", () => setInputMode("text"));
modeVoiceBtn?.addEventListener("click", () => setInputMode("voice"));

nlSendBtn?.addEventListener("click", async () => {
  await runCommand(nlInput.value);
  nlInput.value = "";
});

nlInput?.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") {
    return;
  }
  event.preventDefault();
  await runCommand(nlInput.value);
  nlInput.value = "";
});

voiceBtn?.addEventListener("click", () => {
  if (!recognition) {
    return;
  }
  if (recognizing) {
    recognition.stop();
    return;
  }
  recognition.start();
});

ttsToggleBtn?.addEventListener("click", () => {
  speechEnabled = !speechEnabled;
  ttsToggleBtn.textContent = speechEnabled ? "Voice reply on" : "Voice reply off";
  if (!speechEnabled && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
});

(async () => {
  setInputMode("text");
  initSpeechRecognition();
  setAgentState("idle");

  try {
    const summary = await summarizeHomeStatus();
    presenceText.textContent = "Live data connected";
    addSpeechLine(
      "agent",
      `Hello, I am Nestra Assistant. ${summary} You can ask me to optimize EV charging, arm night security, preheat home, or give a status summary.`
    );
  } catch (_err) {
    presenceText.textContent = "Simulated mode (live API unreachable)";
    addSpeechLine(
      "agent",
      "Hello, I am Nestra Assistant. Live data is unavailable right now. You can still test natural-language commands in guided mode."
    );
  }
})();
