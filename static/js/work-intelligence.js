(function () {
  "use strict";

  if (window.__casehubWorkIntelligenceLoaded) return;
  window.__casehubWorkIntelligenceLoaded = true;

  var root = document.documentElement;
  if (!root || root.getAttribute("data-work-intelligence-enabled") !== "1") return;

  var prefix = window.CASEHUB_PREFIX || "/casehub";
  var endpoint = prefix + "/work-intelligence/api/events";
  var feedbackEndpoint = prefix + "/work-intelligence/api/feedback";
  var maxBatch = 10;
  var maxPayloadBytes = 24 * 1024;
  var heartbeatMs = 60000;
  var queue = [];
  var lastVisibleAt = Date.now();
  var lastHeartbeatAt = 0;

  function nowIso() {
    return new Date().toISOString();
  }

  function sessionId() {
    try {
      var existing = window.sessionStorage.getItem("casehub.wi.session");
      if (existing) return existing;
      var next = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : String(Date.now()) + "." + Math.random();
      window.sessionStorage.setItem("casehub.wi.session", next);
      return next;
    } catch (err) {
      return "";
    }
  }

  function routeOnly(value) {
    var raw = String(value || window.location.pathname || "");
    return raw.split("#")[0].split("?")[0].slice(0, 255);
  }

  function safeToken(value, fallback) {
    var raw = String(value || fallback || "").slice(0, 120);
    return raw.replace(/[^A-Za-z0-9_:/@.\-]+/g, "_").replace(/^_+|_+$/g, "");
  }

  function payloadSize(events) {
    try {
      return new Blob([JSON.stringify({ events: events })]).size;
    } catch (err) {
      return maxPayloadBytes + 1;
    }
  }

  function enqueue(type, data) {
    var event = {
      event_type: safeToken(type),
      route: routeOnly(data && data.route),
      surface: safeToken(data && data.surface),
      occurred_at: nowIso(),
      duration_ms: data && data.duration_ms,
      session_id: sessionId(),
      metadata: data && data.metadata ? data.metadata : {}
    };
    queue.push(event);
    if (queue.length >= maxBatch || payloadSize(queue) >= maxPayloadBytes) {
      flush(false);
    }
  }

  function flush(useBeacon) {
    if (!queue.length) return;
    var events = queue.splice(0, maxBatch);
    var body = JSON.stringify({ events: events });
    if (useBeacon && navigator.sendBeacon) {
      var ok = navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
      if (ok) return;
    }
    window.fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: body,
      keepalive: true
    }).catch(function () {});
  }

  function visibleDurationMs() {
    return Math.max(0, Date.now() - lastVisibleAt);
  }

  enqueue("page_view", {
    route: window.location.pathname,
    surface: "page",
    metadata: { route: routeOnly(window.location.pathname) }
  });

  window.setInterval(function () {
    if (document.visibilityState !== "visible") return;
    var now = Date.now();
    if (now - lastHeartbeatAt < heartbeatMs - 1000) return;
    lastHeartbeatAt = now;
    enqueue("heartbeat", {
      route: window.location.pathname,
      surface: "page",
      duration_ms: visibleDurationMs(),
      metadata: { visible_seconds: Math.round(visibleDurationMs() / 1000) }
    });
  }, heartbeatMs);

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      enqueue("page_hide", {
        route: window.location.pathname,
        surface: "page",
        duration_ms: visibleDurationMs(),
        metadata: { visible_seconds: Math.round(visibleDurationMs() / 1000) }
      });
      flush(true);
    } else {
      lastVisibleAt = Date.now();
      enqueue("visibility", {
        route: window.location.pathname,
        surface: "page",
        metadata: { action_id: "visible" }
      });
    }
  });

  window.addEventListener("pagehide", function () {
    enqueue("page_hide", {
      route: window.location.pathname,
      surface: "page",
      duration_ms: visibleDurationMs(),
      metadata: { visible_seconds: Math.round(visibleDurationMs() / 1000) }
    });
    flush(true);
  });

  document.addEventListener("click", function (event) {
    var target = event.target && event.target.closest ? event.target.closest("[data-work-action], button, a, [role='button']") : null;
    if (!target) return;
    var actionId = target.getAttribute("data-work-action") || target.getAttribute("data-route-key") || target.id || target.getAttribute("name") || target.getAttribute("role") || target.tagName;
    enqueue("action", {
      route: window.location.pathname,
      surface: safeToken(target.getAttribute("data-surface") || target.tagName),
      metadata: {
        action_id: safeToken(actionId),
        action_role: safeToken(target.getAttribute("role") || target.tagName)
      }
    });
  }, true);

  window.addEventListener("error", function (event) {
    var target = event.target || {};
    var kind = target && target.tagName ? "resource_" + String(target.tagName).toLowerCase() : "runtime";
    enqueue("ui_error", {
      route: window.location.pathname,
      surface: "window",
      metadata: { error_kind: safeToken(kind) }
    });
  }, true);

  window.addEventListener("unhandledrejection", function () {
    enqueue("ui_error", {
      route: window.location.pathname,
      surface: "window",
      metadata: { error_kind: "promise_rejection" }
    });
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.matches("[data-work-intelligence-feedback]")) return;
    event.preventDefault();
    var status = form.querySelector("[data-feedback-status]");
    var data = new FormData(form);
    window.fetch(feedbackEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        feedback_type: data.get("feedback_type") || "comment",
        comment: data.get("comment") || ""
      })
    }).then(function () {
      if (status) status.textContent = "Enviado.";
      form.reset();
    }).catch(function () {
      if (status) status.textContent = "Nao foi possivel enviar agora.";
    });
  });
})();
