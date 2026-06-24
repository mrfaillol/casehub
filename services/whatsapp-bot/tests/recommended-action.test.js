"use strict";

// Frente 2 (Solucao A): every terminal failure state must be OBSERVABLE and
// ACTIONABLE. Today blocked_host falls through to a dead "soft_reconnect" (which
// just re-blocks) and an intentional-down session looks like a plain disconnect.
// And a host-bind marker-write failure is only _warn'd, never recorded as an
// event. These tests pin distinct, actionable recommendations + observability.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const Module = require("node:module");
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  if (request === "whatsapp-web.js") return path.join(__dirname, "stubs", "whatsapp-web-stub.js");
  if (request === "qrcode-terminal" || request === "qrcode") return path.join(__dirname, "stubs", "noop-stub.js");
  return originalResolve.call(this, request, parent, ...rest);
};
const { WhatsAppClient } = require("../whatsapp-client");

function tmpClient(orgId = 4) {
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-rec-"));
  return new WhatsAppClient({ orgId, dataBase });
}

test("blocked_host gets a distinct, host-aware action (never the dead soft_reconnect)", () => {
  const c = tmpClient(4);
  const action = c._recommendedAction("blocked_host");
  assert.notStrictEqual(action, "soft_reconnect", "soft_reconnect just re-blocks a host-bound session");
  assert.match(String(action), /host|bind|rebind/i);
  assert.match(c._nextStep(action), /CASEHUB_WA_SESSION_BINDING|rebind|host/i);
});

test("intentional_down (explicit status arg) recommends an explicit reconnect", () => {
  const c = tmpClient(4);
  const action = c._recommendedAction("intentional_down");
  assert.match(String(action), /reconnect|init|explicit/i);
  assert.match(c._nextStep(action), /reconect|desconect|init|deliberad/i);
});

test("a real intentional-down session (status 'disconnected' + marker) recommends explicit reconnect", () => {
  const c = tmpClient(4);
  c._markIntentionalDown();      // exactly what human disconnect() does
  c.status = "disconnected";     // the real runtime status of an intentional teardown
  c.isReady = false;
  const action = c._recommendedAction();   // no arg -> uses this.status + marker detection
  assert.match(
    String(action),
    /reconnect|init|explicit/i,
    "an intentional-down session must not fall through to the implicit soft path"
  );
});

test("a host-bind marker-write failure is recorded as an observable event, not just logged", () => {
  const c = tmpClient(4);
  const prev = process.env.CASEHUB_WA_SESSION_BINDING;
  process.env.CASEHUB_WA_SESSION_BINDING = "host-secret-x";   // expected truthy, no marker yet
  try {
    // Make the session dir a FILE so writing .host-bind inside it throws (ENOTDIR).
    fs.writeFileSync(c._sessionDir(), "not-a-directory");
    const ok = c._enforceHostBinding();
    assert.strictEqual(ok, true, "marker write is best-effort and must not block the host");
    assert.strictEqual(
      c._lastEvent,
      "host_bind_marker_write_failed",
      "the marker-write failure must surface as an event"
    );
  } finally {
    if (prev === undefined) delete process.env.CASEHUB_WA_SESSION_BINDING;
    else process.env.CASEHUB_WA_SESSION_BINDING = prev;
  }
});
