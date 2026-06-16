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

    // metrics
    const payload = gw.payload || {};
    const hw = payload.hardware || {};
    const dk = payload.docker || {};
    const s = (payload.pipeline || {}).summary || {};

    setMetric(card, "load",       hw.load_1m != null ? `${hw.load_1m}/${hw.load_5m}/${hw.load_15m}` : null);
    setMetric(card, "ram",        hw.ram_available_mb != null ? `${hw.ram_available_mb}MB avail` : null);
    setMetric(card, "swap",       hw.swap_used_pct != null ? `${hw.swap_used_pct}%` : null);
    setMetric(card, "disk",       hw.disk_used_pct != null ? `${hw.disk_used_pct}%` : null);
    setMetric(card, "temp",       hw.temp_celsius != null ? `${hw.temp_celsius}°C` : hw.temp_celsius === null ? "UNKNOWN" : null);
    setMetric(card, "workers",    dk.workers_total != null ? `${dk.workers_up}/${dk.workers_total} up` : null);
    setMetric(card, "scpacs24h",   s.sc_published_24h ?? null);
    setMetric(card, "img24h",     s.images_last_24h  ?? null);
    setMetric(card, "img15m",     s.images_last_15m ?? null);
    setMetric(card, "proc15m",    s.processed_15m ?? null);
    setMetric(card, "failed15m",  s.failed_15m ?? null, !!s.failed_15m);
    setMetric(card, "pending2h",  s.pending_older_2h ?? null, !!s.pending_older_2h);
    setMetric(card, "last-task",  s.last_successful_task_at ? s.last_successful_task_at.slice(0, 19) : null);
    setMetric(card, "last-image", s.last_image_created_at  ? s.last_image_created_at.slice(0, 19)  : null);

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

  function setMetric(card, name, value, warn) {
    const el = card.querySelector(`[data-metric="${name}"]`);
    if (!el) return;
    el.textContent = value != null ? value : "—";
    if (warn !== undefined) {
      el.classList.toggle("metric--warning", !!warn);
    }
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
