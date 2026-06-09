/* Watchtower dashboard JS — no external dependencies */

(function () {
  "use strict";

  // ── Clock ──────────────────────────────────────────────────────────
  function updateClock() {
    const el = document.getElementById("clock");
    if (el) el.textContent = new Date().toUTCString().slice(0, 25) + " UTC";
  }
  setInterval(updateClock, 1000);
  updateClock();

  // ── Exported init ──────────────────────────────────────────────────
  window.initDashboard = function ({ refreshInterval = 30000 } = {}) {
    refreshStatus();
    setInterval(refreshStatus, refreshInterval);
  };

  // ── Scheduler controls ────────────────────────────────────────────
  window.triggerCheck = function () {
    post("/api/scheduler/trigger").then(() => {
      showFlash("Check triggered");
      setTimeout(refreshStatus, 3000);
    });
  };

  let _paused = false;
  window.toggleScheduler = function () {
    const url = _paused ? "/api/scheduler/resume" : "/api/scheduler/pause";
    post(url).then(() => {
      _paused = !_paused;
      const btn = document.getElementById("pause-btn");
      if (btn) btn.textContent = _paused ? "▶ Resume" : "⏸ Pause";
    });
  };

  // ── Poll /api/status and update DOM ───────────────────────────────
  function refreshStatus() {
    fetch("/api/status")
      .then((r) => r.json())
      .then((data) => {
        updateTshBadge(data.teleport_active);
        updateSchedulerBadge(data.scheduler);
        updateSchedulerInfo(data.scheduler);
        updateSummaryBar(data.gateways);
        data.gateways.forEach(updateCard);
      })
      .catch((err) => console.warn("Status poll failed:", err));
  }

  function updateTshBadge(active) {
    const el = document.getElementById("tsh-badge");
    if (!el) return;
    el.className = "badge badge--" + (active ? "ok" : "critical");
    el.textContent = active ? "TSH ✓" : "TSH ✗";
  }

  function updateSchedulerBadge(sched) {
    const el = document.getElementById("sched-badge");
    if (!el || !sched) return;
    if (sched.in_progress) {
      el.className = "badge badge--warning";
      el.textContent = "Checking…";
    } else if (!sched.running) {
      el.className = "badge badge--unknown";
      el.textContent = "Paused";
    } else {
      el.className = "badge badge--ok";
      el.textContent = "Scheduler ✓";
    }
  }

  function updateSchedulerInfo(sched) {
    if (!sched) return;
    const lr = document.getElementById("last-run");
    const nr = document.getElementById("next-run");
    if (lr) lr.textContent = formatTs(sched.last_run) || "—";
    if (nr) nr.textContent = formatTs(sched.next_run) || "—";
  }

  function updateSummaryBar(gateways) {
    const counts = { ok: 0, warning: 0, critical: 0, unknown: 0 };
    gateways.forEach((g) => {
      const s = (g.overall_status || "unknown").toLowerCase();
      if (s in counts) counts[s]++;
      else counts.unknown++;
    });
    setText("stat-ok",       counts.ok + " OK");
    setText("stat-warning",  counts.warning + " WARN");
    setText("stat-critical", counts.critical + " CRIT");
    setText("stat-unknown",  counts.unknown + " UNKN");
  }

  function updateCard(gw) {
    const id = "card-" + (gw.host || "").replace(/\./g, "-");
    const card = document.getElementById(id);
    if (!card) return;

    const status = (gw.overall_status || "unknown").toLowerCase();
    card.className = "gateway-card status-" + status;

    // uptime
    const uptimeEl = card.querySelector(".card-uptime");
    if (uptimeEl) uptimeEl.textContent = gw.uptime_short || "—";

    // badges
    setBadge(card, ".card-badges .badge:nth-child(1)", gw.ssh_status);
    setBadge(card, ".card-badges .badge:nth-child(2)", gw.docker_status);
    setBadge(card, ".card-badges .badge:nth-child(3)", gw.postgres_status);
    setBadge(card, ".card-badges .badge:nth-child(4)", gw.pipeline_status);

    // status dot + overall
    const dot = card.querySelector(".status-dot");
    if (dot) dot.className = "status-dot status-dot--" + status;
    const ov = card.querySelector(".overall-status");
    if (ov) ov.textContent = (gw.overall_status || "UNKNOWN");

    // last seen
    const ls = card.querySelector(".last-seen");
    if (ls) ls.textContent = formatTs(gw.timestamp) || "never";

    // error
    let errEl = card.querySelector(".card-error");
    if (gw.error_message) {
      if (!errEl) {
        errEl = document.createElement("div");
        errEl.className = "card-error";
        card.appendChild(errEl);
      }
      errEl.textContent = gw.error_message.slice(0, 120);
    } else if (errEl) {
      errEl.remove();
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────
  function post(url) {
    return fetch(url, { method: "POST" }).then((r) => r.json());
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setBadge(parent, selector, status) {
    const el = parent.querySelector(selector);
    if (!el) return;
    const s = (status || "unknown").toLowerCase();
    el.className = "badge badge--" + s;
  }

  function formatTs(ts) {
    if (!ts) return null;
    return ts.replace("T", " ").slice(0, 19) + " UTC";
  }

  function showFlash(msg) {
    const el = document.createElement("div");
    el.style.cssText =
      "position:fixed;bottom:20px;right:20px;background:#388bfd;color:#fff;padding:8px 16px;border-radius:6px;font-size:12px;z-index:999;";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2500);
  }
})();
