const API_BASE = "https://api.nestra.homelabdev.space";

const sessionMeta = document.getElementById("session-meta");
const liveChip = document.getElementById("live-chip");
const tenantIdEl = document.getElementById("kpi-household");
const actorIdEl = document.getElementById("kpi-actor");
const savingsEl = document.getElementById("kpi-savings");
const deviceListEl = document.getElementById("device-list");
const auditListEl = document.getElementById("audit-list");
const intentBtn = document.getElementById("intent-btn");
const runSimBtn = document.getElementById("run-sim-btn");
const securityBtn = document.getElementById("scenario-security-btn");
const comfortBtn = document.getElementById("scenario-comfort-btn");
const intentResult = document.getElementById("intent-result");
const scenarioResult = document.getElementById("scenario-result");
const intentStart = document.getElementById("intent-start");
const intentEnd = document.getElementById("intent-end");
const intentConfirm = document.getElementById("intent-confirm");
const tariffTrack = document.getElementById("tariff-track");
const confidenceEl = document.getElementById("kpi-confidence");
const pillMatter = document.getElementById("pill-matter");
const pillHA = document.getElementById("pill-ha");
const pillEnergy = document.getElementById("pill-energy");
const buyerVerdictEl = document.getElementById("buyer-verdict");
const buyerCheckBtn = document.getElementById("buyer-check-btn");

const SPINNER_HTML = `<svg class="spinner" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="60 40"/></svg>`;

function setBusy(button, isBusy, labelBusy) {
  if (!button) {
    return;
  }
  if (isBusy) {
    button.dataset.label = button.textContent;
    button.innerHTML = `${SPINNER_HTML} ${labelBusy}`;
    button.disabled = true;
    return;
  }
  button.innerHTML = button.dataset.label || button.textContent;
  button.disabled = false;
}

function statusClass(status) {
  if (status === "accepted") {
    return "good";
  }
  if (status === "pending_confirmation") {
    return "pending";
  }
  return "warn";
}

function formatWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function htmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const payload = await res.json();
      detail = payload.detail?.message || payload.detail || detail;
    } catch (_err) {
    }
    throw new Error(detail);
  }
  return res;
}

function renderTariffTrack() {
  const blocks = [
    ["20-22", "high"],
    ["22-00", "low"],
    ["00-02", "low"],
    ["02-04", "low"],
    ["04-06", "low"],
    ["06-08", "high"],
    ["08-16", "high"],
    ["16-20", "high"],
  ];
  tariffTrack.innerHTML = blocks
    .map(
      ([label, level]) => `<div class="tariff-block ${level}"><strong>${label}</strong></div>`
    )
    .join("");
}

function renderDevices(items) {
  if (!items.length) {
    deviceListEl.innerHTML = '<div class="row">No devices available</div>';
    return;
  }

  deviceListEl.innerHTML = items
    .map((item) => {
      const stateSummary = Object.entries(item.state || {})
        .filter(([, value]) => value !== null && value !== undefined)
        .map(([key, value]) => `${key}: ${value}`)
        .join(" | ");

      return `
        <div class="row">
          <div class="row-title">
            <span>${htmlEscape(item.name)}</span>
            <span class="pill ${item.online ? "good" : "warn"}">${item.online ? "online" : "offline"}</span>
          </div>
          <div class="row-meta">${htmlEscape(item.type)} · ${htmlEscape(item.room || "unassigned")}</div>
          <div class="row-meta">${htmlEscape(stateSummary || "no active telemetry")}</div>
        </div>
      `;
    })
    .join("");
}

function renderAudit(items) {
  if (!items.length) {
    auditListEl.innerHTML = '<div class="row">No audit events yet</div>';
    return;
  }

  auditListEl.innerHTML = items
    .slice(0, 6)
    .map((item) => {
      const outcomeClass = item.outcome === "allowed" ? "good" : "warn";
      return `
        <div class="row">
          <div class="row-title">
            <span>${htmlEscape(item.action)}</span>
            <span class="pill ${outcomeClass}">${htmlEscape(item.outcome)}</span>
          </div>
          <div class="row-meta">${htmlEscape(formatWhen(item.occurred_at))} · ${htmlEscape(item.actor_id)}</div>
          <div class="row-meta">${htmlEscape(item.reason || "policy satisfied")}</div>
        </div>
      `;
    })
    .join("");
}

function computePolicyPassRate(auditItems) {
  if (!auditItems || auditItems.length === 0) {
    return "--%";
  }
  const allowed = auditItems.filter((e) => e.outcome === "allowed").length;
  const rate = Math.round((allowed / auditItems.length) * 100);
  return `${rate}%`;
}

function computeSavings(start, end, auditItems) {
  const startHour = parseInt(start.split(":", 1)[0], 10);
  const endHour = parseInt(end.split(":", 1)[0], 10);
  const windowHours = endHour > startHour ? endHour - startHour : 24 - startHour + endHour;
  const overlapsLow = startHour >= 22 || endHour <= 7;
  const evActions = auditItems.filter(
    (e) => e.action && e.action.toLowerCase().includes("ev")
  ).length;
  const evBonus = evActions > 0 ? 8 : 0;
  const base = windowHours * 4;
  const tariffBonus = overlapsLow ? windowHours * 2 : 0;
  const estimated = base + tariffBonus + evBonus;
  return `EUR ${Math.max(estimated, 12)}`;
}

function setIntegrationPills(deviceItems, auditItems) {
  const devicesOnline = (deviceItems || []).filter((item) => item.online).length;
  const evActions = (auditItems || []).filter(
    (item) => item.action && item.action.toLowerCase().includes("ev")
  ).length;

  if (pillMatter) {
    pillMatter.className = `pill ${devicesOnline > 0 ? "good" : "warn"}`;
    pillMatter.textContent =
      devicesOnline > 0 ? `${devicesOnline} devices mapped` : "no devices mapped";
  }

  if (pillHA) {
    pillHA.className = "pill pending";
    pillHA.textContent = "demo simulation";
  }

  if (pillEnergy) {
    pillEnergy.className = `pill ${evActions > 0 ? "good" : "pending"}`;
    pillEnergy.textContent = evActions > 0 ? "signal active" : "demo simulation";
  }
}

function renderBuyerVerdict(deviceItems, auditItems) {
  if (!buyerVerdictEl) {
    return;
  }

  const devicesCount = (deviceItems || []).length;
  const passRate = computePolicyPassRate(auditItems || []);
  const blockedActions = (auditItems || []).filter((item) => item.outcome !== "allowed").length;

  const verdict = [];
  verdict.push(`Strength: ${passRate} guardrail pass rate with auditable household actions.`);

  if (devicesCount < 5) {
    verdict.push("Gap: device coverage is shallow; this still looks like a controlled demo.");
  } else {
    verdict.push(`Signal: ${devicesCount} connected devices shown in this household context.`);
  }

  if (blockedActions === 0) {
    verdict.push("Gap: no blocked examples shown; buyers cannot see fail-safe behavior clearly.");
  } else {
    verdict.push(`Trust: ${blockedActions} blocked actions prove guardrails are enforced, not decorative.`);
  }

  verdict.push(
    "Reality check: Home Assistant remains stronger for pure DIY flexibility. Nestra must win on policy, auditability, and multi-home operations."
  );

  buyerVerdictEl.textContent = verdict.join(" ");
}

function setIntentFeedback(data) {
  const status = data.status || data.intent?.status || "unknown";
  const stateClass = statusClass(status);
  const suggestion = data.next_step ? `<br/><span>Next: ${htmlEscape(data.next_step)}</span>` : "";
  intentResult.innerHTML = `
    <span class="pill ${stateClass}">${htmlEscape(status.replaceAll("_", " "))}</span>
    <span>${htmlEscape(data.title || "Action processed")}</span><br/>
    <span>${htmlEscape(data.message || "")}</span><br/>
    <span>Audit: ${htmlEscape(data.audit_event_id || "n/a")}</span>${suggestion}
  `;
}

async function loadDashboard() {
  let ctx = null;
  let devices = [];
  let audit = [];

  try {
    [ctx, devices, audit] = await Promise.all([
      apiFetch("/v1/household/context").then((r) => r.json()),
      apiFetch("/v1/devices").then((r) => r.json()),
      apiFetch("/v1/audit-events").then((r) => r.json()),
    ]);
  } catch (err) {
    liveChip.textContent = "service unavailable";
    liveChip.style.borderColor = "rgba(251,113,133,0.6)";
    liveChip.style.color = "#fecdd3";
    sessionMeta.textContent = "Unable to reach Nestra API";
    intentResult.textContent = `API unreachable: ${err.message}`;
    deviceListEl.innerHTML = '<div class="row warn">Device list unavailable</div>';
    auditListEl.innerHTML = '<div class="row warn">Audit log unavailable</div>';
    if (buyerVerdictEl) {
      buyerVerdictEl.textContent =
        "Honest verdict unavailable because live API signals could not be loaded.";
    }
    return;
  }

  tenantIdEl.textContent = ctx.household.name;
  actorIdEl.textContent = `${ctx.actor.display_name} · ${ctx.actor.role}`;
  sessionMeta.textContent = `${ctx.actor.display_name} in ${ctx.household.name}`;

  renderDevices(devices.items || []);
  renderAudit(audit.items || []);
  setIntegrationPills(devices.items || [], audit.items || []);
  renderBuyerVerdict(devices.items || [], audit.items || []);

  const passRate = computePolicyPassRate(audit.items || []);
  confidenceEl.textContent = passRate;

  const savings = computeSavings(intentStart.value, intentEnd.value, audit.items || []);
  savingsEl.textContent = savings;

  liveChip.textContent = "live demo mode";
  liveChip.style.borderColor = "";
  liveChip.style.color = "";
}

async function submitIntent() {
  intentResult.textContent = "Submitting action...";
  setBusy(intentBtn, true, "Applying EV plan...");
  const payload = {
    intent_type: "shift_ev_charging_low_tariff_window",
    payload: {
      window_start: intentStart.value,
      window_end: intentEnd.value,
    },
    confirm: Boolean(intentConfirm.checked),
  };

  const res = await apiFetch("/v1/device-intents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  setIntentFeedback(data);
  await loadDashboard();
  setBusy(intentBtn, false, "");
}

async function submitScenario(intentType, payload, confirm = true) {
  scenarioResult.textContent = "Executing scenario...";
  const res = await apiFetch("/v1/device-intents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intent_type: intentType, payload, confirm }),
  });
  const data = await res.json();
  const stateClass = statusClass(data.status);
  scenarioResult.innerHTML = `<span class="pill ${stateClass}">${htmlEscape(data.status.replaceAll("_", " "))}</span> ${htmlEscape(data.title)}<br/>${htmlEscape(data.message)}<br/>Audit: ${htmlEscape(data.audit_event_id)}`;
  await loadDashboard();
}

function runSimulation() {
  const res = { items: [] };
  const savings = computeSavings(intentStart.value, intentEnd.value, res.items);
  savingsEl.textContent = savings;
  intentResult.innerHTML =
    '<span class="pill good">simulation</span>Estimated savings based on tariff window and EV charging profile. Apply the plan to create a real auditable action.';
}

runSimBtn?.addEventListener("click", runSimulation);

buyerCheckBtn?.addEventListener("click", async () => {
  setBusy(buyerCheckBtn, true, "Running buyer check...");
  try {
    const [devices, audit] = await Promise.all([
      apiFetch("/v1/devices").then((r) => r.json()),
      apiFetch("/v1/audit-events").then((r) => r.json()),
    ]);
    renderBuyerVerdict(devices.items || [], audit.items || []);
  } catch (err) {
    if (buyerVerdictEl) {
      buyerVerdictEl.textContent = `Buyer check unavailable: ${err.message}`;
    }
  } finally {
    setBusy(buyerCheckBtn, false, "");
  }
});

intentBtn?.addEventListener("click", async () => {
  try {
    await submitIntent();
    const res = await apiFetch("/v1/audit-events").then((r) => r.json());
    const savings = computeSavings(intentStart.value, intentEnd.value, res.items || []);
    savingsEl.textContent = savings;
  } catch (err) {
    intentResult.textContent = err.message || "Action failed";
  } finally {
    setBusy(intentBtn, false, "");
  }
});

securityBtn?.addEventListener("click", async () => {
  setBusy(securityBtn, true, "Running security sweep...");
  try {
    await submitScenario("arm_night_security_sweep", {
      arm_time: "22:30",
      zones: ["entryway", "garage", "living-room"],
    });
  } catch (err) {
    scenarioResult.textContent = err.message || "Scenario failed";
  } finally {
    setBusy(securityBtn, false, "");
  }
});

comfortBtn?.addEventListener("click", async () => {
  setBusy(comfortBtn, true, "Scheduling preheat...");
  try {
    await submitScenario("preheat_home_arrival", {
      arrival_time: "18:00",
      target_temperature_c: 21.5,
    });
  } catch (err) {
    scenarioResult.textContent = err.message || "Scenario failed";
  } finally {
    setBusy(comfortBtn, false, "");
  }
});

renderTariffTrack();
loadDashboard()
  .then(() => {
    liveChip.textContent = "live demo mode";
  })
  .catch((err) => {
    liveChip.textContent = "service unavailable";
    liveChip.style.borderColor = "rgba(251,113,133,0.6)";
    liveChip.style.color = "#fecdd3";
    sessionMeta.textContent = "Unable to load demo context";
    intentResult.textContent = err.message;
  });
