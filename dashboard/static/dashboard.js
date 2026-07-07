/* ================================================================
   EcoWell Dashboard — dashboard.js
   Real-time polling, command dispatch, UI updates
   ================================================================ */

const POLL_INTERVAL_MS = 1500;  // how often we refresh from backend

let _eventsCache  = [];   // accumulate so clear-view works
let _clearView    = false;

// ── Utility helpers ────────────────────────────────────────────────

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function pct(v, lo, hi) {
  return ((clamp(v, lo, hi) - lo) / (hi - lo) * 100).toFixed(1) + "%";
}

// ── Toast ──────────────────────────────────────────────────────────

let _toastTimer = null;
function showToast(msg, type = "ok") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `toast show toast-${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { t.classList.remove("show"); }, 3500);
}

// ── Command dispatch ───────────────────────────────────────────────

async function sendCommand(cmd) {
  const fb = document.getElementById("cmdFeedback");

  // Mark all ctrl-btns as loading
  document.querySelectorAll(".ctrl-btn").forEach(b => b.classList.add("loading"));
  fb.textContent = "⏳ Sending command…";
  fb.className   = "cmd-feedback";

  try {
    const res = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd }),
    });
    const data = await res.json();

    if (res.ok) {
      fb.textContent = `✅ Command '${cmd}' sent successfully`;
      fb.className   = "cmd-feedback ok";
      showToast(`✅ Command sent: ${cmd}`, "ok");
    } else {
      fb.textContent = `❌ Rejected: ${data.detail || data.error || "Unknown error"}`;
      fb.className   = "cmd-feedback fail";
      showToast(`❌ Rejected: ${data.detail || data.error}`, "fail");
    }
  } catch (err) {
    fb.textContent = `❌ Network error: ${err.message}`;
    fb.className   = "cmd-feedback fail";
    showToast(`❌ Network error`, "fail");
  } finally {
    document.querySelectorAll(".ctrl-btn").forEach(b => b.classList.remove("loading"));
    setTimeout(() => { fb.textContent = ""; fb.className = "cmd-feedback"; }, 5000);
  }
}

// ── Clear events view ──────────────────────────────────────────────

function clearEventsView() {
  _clearView = true;
  _eventsCache = [];
  document.getElementById("eventsList").innerHTML =
    '<li class="no-events">View cleared. New events will appear below.</li>';
}

// ── State color helpers ────────────────────────────────────────────

const STATE_COLORS = {
  IDLE:                   "#8fa3c0",
  MONITORING:             "#22d86e",
  REGENERATION_REQUIRED:  "#ffb020",
  REGENERATION_RUNNING:   "#3b9dff",
  FAULT:                  "#ff4e6a",
};

const STATE_ICONS = {
  IDLE:                   "😴",
  MONITORING:             "📡",
  REGENERATION_REQUIRED:  "⚠️",
  REGENERATION_RUNNING:   "🔄",
  FAULT:                  "🚨",
};

// ── Health-bar color ──────────────────────────────────────────────

function healthColor(score) {
  if (score >= 85) return "#22d86e";
  if (score >= 70) return "#00e5c3";
  if (score >= 50) return "#ffb020";
  if (score >= 30) return "#ff8c42";
  return "#ff4e6a";
}

// ── Safety checks ─────────────────────────────────────────────────

function updateSafety(sensors, state) {
  const pass = (id, ok) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `safety-item ${ok ? "pass" : "fail"}`;
    el.querySelector(".safety-icon").textContent = ok ? "✅" : "❌";
  };

  const salt     = sensors?.salt_level_pct   ?? 100;
  const pressure = sensors?.water_pressure_bar ?? 5;
  const power    = sensors?.power_status       ?? true;

  pass("s-salt",     salt     >  15);
  pass("s-pressure", pressure >= 1.0);
  pass("s-power",    power);
  pass("s-state",    state !== "FAULT" && state !== "REGENERATION_RUNNING");
  // timeout is always a static pass (implemented in firmware)
}

// ── Alerts panel ──────────────────────────────────────────────────

function updateAlerts(alerts) {
  const list  = document.getElementById("alertsList");
  const badge = document.getElementById("alertCount");

  if (!alerts || alerts.length === 0) {
    list.innerHTML  = '<li class="no-alerts">✅ All systems nominal</li>';
    badge.textContent = "0";
    badge.className   = "alert-count zero";
    return;
  }

  badge.textContent = alerts.length;
  badge.className   = "alert-count";

  list.innerHTML = alerts.map(a => {
    const icon = a.level === "FAULT" ? "🚨" : a.level === "ALERT" ? "⚠️" : "🔔";
    return `<li class="alerts-list ${a.level === "WARN" ? "alert-WARN" : "alert-" + a.level}">
      <span>${icon}</span>
      <div>
        <div style="font-weight:600">${a.message}</div>
        <div style="font-size:0.72rem;color:#5a7291;margin-top:2px">${fmtTime(a.time)}</div>
      </div>
    </li>`;
  }).join("");
}

// ── Events panel ──────────────────────────────────────────────────

const EVENT_ICON = { INFO: "ℹ️", ALERT: "⚠️", FAULT: "🚨" };

function updateEvents(events) {
  if (!events || events.length === 0) return;

  // Merge new events only
  const existingTimes = new Set(_eventsCache.map(e => e.time + e.message));
  const newEvents = events.filter(e => !existingTimes.has(e.time + e.message));
  if (newEvents.length === 0) return;

  _eventsCache = [..._eventsCache, ...newEvents].slice(-200);

  const list = document.getElementById("eventsList");
  if (_eventsCache.length === 0) {
    list.innerHTML = '<li class="no-events">No events yet.</li>';
    return;
  }

  list.innerHTML = [..._eventsCache].reverse().map(e => {
    const icon = EVENT_ICON[e.level] || "ℹ️";
    return `<li class="event-item event-${e.level}">
      <span class="event-icon">${icon}</span>
      <div>
        <div class="event-msg">${e.message}</div>
        <div class="event-time">${fmtTime(e.time)}</div>
      </div>
    </li>`;
  }).join("");
}

// ── Sensor card coloring ───────────────────────────────────────────

function colorSensor(cardId, valueEl, value, warnThresh, critThresh, inverted = false) {
  const card = document.getElementById(cardId);
  const el   = document.getElementById(valueEl);
  if (!card || !el) return;

  const bad  = inverted ? (value < critThresh) : (value > critThresh);
  const warn = inverted ? (value < warnThresh) : (value > warnThresh);

  card.classList.remove("alert-warn", "alert-crit");
  el.style.color = "";

  if (bad) {
    card.classList.add("alert-crit");
    el.style.color = "var(--accent-red)";
  } else if (warn) {
    card.classList.add("alert-warn");
    el.style.color = "var(--accent-amber)";
  } else {
    el.style.color = "var(--accent-teal)";
  }
}

// ── Main update cycle ─────────────────────────────────────────────

async function loadDashboard() {
  try {
    const res  = await fetch("/api/dashboard");
    const data = await res.json();

    const t       = data.telemetry || {};
    const events  = data.events    || [];
    const alerts  = data.alerts    || [];
    const health  = data.health    || {};
    const sensors = t.sensors      || {};

    if (Object.keys(t).length === 0) {
      setLiveStatus(false, "No data");
      return;
    }

    setLiveStatus(true, "Live");

    // ── State badge ──────────────────────────────────────────────
    const stateBadge = document.getElementById("stateBadge");
    const state       = t.state || "IDLE";
    const icon        = STATE_ICONS[state] || "⚙️";
    stateBadge.textContent = `${icon} ${state.replace(/_/g, " ")}`;
    stateBadge.className   = `state-badge badge-${state}`;

    const fr = document.getElementById("faultReason");
    fr.textContent = t.fault_reason ? `⚠ ${t.fault_reason}` : "";

    // ── Power ────────────────────────────────────────────────────
    const power = sensors.power_status;
    document.getElementById("powerIcon").textContent  = power ? "🔌" : "⚡";
    document.getElementById("powerValue").textContent = power ? "ON ✅" : "OFF ❌";
    document.getElementById("powerValue").style.color = power ? "var(--accent-green)" : "var(--accent-red)";

    // ── Regen status ─────────────────────────────────────────────
    document.getElementById("regenValue").textContent = t.regen_status || "—";

    // ── Last update ──────────────────────────────────────────────
    document.getElementById("lastUpdate").textContent = fmtTime(t.time);

    // ── Health score ─────────────────────────────────────────────
    if (health.score !== null && health.score !== undefined) {
      document.getElementById("healthScore").textContent = health.score;
      document.getElementById("healthGrade").textContent = health.grade || "";
      const bar  = document.getElementById("healthBar");
      bar.style.width      = health.score + "%";
      bar.style.background = healthColor(health.score);
      document.getElementById("healthScore").style.color = healthColor(health.score);
    }

    // ── Flow ─────────────────────────────────────────────────────
    const flow = sensors.water_flow_lpm ?? 0;
    document.getElementById("flowValue").textContent = flow.toFixed(1);
    document.getElementById("flowBar").style.setProperty("--pct", pct(flow, 0, 15));
    colorSensor("flowCard", "flowValue", flow, 1, 0.5, true); // inverted: low flow is bad

    // ── Pressure ─────────────────────────────────────────────────
    const pres = sensors.water_pressure_bar ?? 0;
    document.getElementById("pressureValue").textContent = pres.toFixed(2);
    document.getElementById("pressureBar").style.setProperty("--pct", pct(pres, 0, 6));
    colorSensor("pressureCard", "pressureValue", pres, 1.5, 1.0, true);

    // ── Salt ─────────────────────────────────────────────────────
    const salt = sensors.salt_level_pct ?? 0;
    document.getElementById("saltValue").textContent = salt.toFixed(1);
    document.getElementById("saltBar").style.setProperty("--pct", pct(salt, 0, 100));
    colorSensor("saltCard", "saltValue", salt, 25, 15, true);

    // ── TDS ──────────────────────────────────────────────────────
    const tds = sensors.tds_ppm ?? 0;
    document.getElementById("tdsValue").textContent = Math.round(tds);
    document.getElementById("tdsBar").style.setProperty("--pct", pct(tds, 50, 1000));
    colorSensor("tdsCard", "tdsValue", tds, 350, 500);

    // ── Panels ───────────────────────────────────────────────────
    updateAlerts(alerts);
    updateEvents(events);
    updateSafety(sensors, state);



  } catch (err) {
    setLiveStatus(false, "Connection error");
    console.warn("Dashboard fetch error:", err);
  }
}

function setLiveStatus(ok, label) {
  const dot   = document.getElementById("liveDot");
  const lbl   = document.getElementById("liveLabel");
  dot.className = "live-dot " + (ok ? "connected" : "error");
  lbl.textContent = label;
}

// ── Boot ──────────────────────────────────────────────────────────
loadDashboard();
setInterval(loadDashboard, POLL_INTERVAL_MS);