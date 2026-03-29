const API_BASE = "https://api.nestra.homelabdev.space";

const presenceText = document.getElementById("presence-text");
const presenceDot = document.getElementById("presence-dot");
const humanAgentEl = document.getElementById("human-agent");
const agentStateTextEl = document.getElementById("agent-state-text");
const agentBubbleEl = document.getElementById("agent-bubble");
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

function setAgentBubble(text) {
  if (!agentBubbleEl || !text) {
    return;
  }
  agentBubbleEl.textContent = text;
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
  utterance.onstart = () => {
    setAgentState("speaking");
    setAgentBubble(text);
  };
  utterance.onend = () => setAgentState("idle");
  utterance.onerror = () => {
    setAgentState("error");
    setAgentBubble("I had a voice output issue, but I am still here.");
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
    setAgentBubble("I am listening. Tell me what you need.");
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
    setAgentBubble("I could not hear that clearly. Please try again.");
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

async function runCommand(inputText) {
  const text = (inputText || "").trim();
  if (!text) {
    return;
  }

  addSpeechLine("user", text);
  setAgentBubble(`You said: ${text}`);
  setAgentState("thinking");

  try {
    const result = await apiFetch("/v1/assistant/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => r.json());

    const response = result.reply_text || "I processed your request.";
    addSpeechLine("agent", response);
    setAgentBubble(response);
    speak(response);
  } catch (err) {
    const failure = `I could not complete that request: ${err.message}`;
    addSpeechLine("agent", failure);
    setAgentBubble(failure);
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
  setPresence("", "Connecting to home context...");

  try {
    const summary = await summarizeHomeStatus();
    setPresence("connected", "Live data connected");
    const greeting = `Hello, I am Nestra Assistant. ${summary} You can ask me to optimize EV charging, arm night security, preheat home, or give a status summary.`;
    setAgentBubble(greeting);
    addSpeechLine("agent", greeting);
  } catch (_err) {
    setPresence("degraded", "Simulated mode (live API unreachable)");
    const fallbackGreeting =
      "Hello, I am Nestra Assistant. Live data is unavailable right now. You can still test natural-language commands in guided mode.";
    setAgentBubble(fallbackGreeting);
    addSpeechLine("agent", fallbackGreeting);
  }
})();
