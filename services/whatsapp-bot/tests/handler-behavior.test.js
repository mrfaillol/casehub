"use strict";

// Verification follow-up (Frente 7 coverage gap): the disconnected/change_state
// handlers were only guarded by a source-introspection check that "_classifyReason("
// appears — which does NOT prove the result is USED. Mutation testing showed two
// real regressions slipping past the whole suite: (5) swallowing a FATAL
// LOGOUT/NAVIGATION as a blip when the socket looks live, and (6) change_state no
// longer zeroing _lastInboundMs on a fatal state (weakening invariant #5). These
// tests fire the REAL handlers through the StubClient EventEmitter to lock the
// behavior, not the spelling.

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

// Boot a client so the real handlers are wired on the StubClient EventEmitter,
// then silence the background watchdog so it cannot promote/mutate state.
async function bootedClient(orgId = 4) {
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-hb-"));
  const c = new WhatsAppClient({ orgId, dataBase });
  await c.initialize();
  if (c._healthTimer) { clearInterval(c._healthTimer); c._healthTimer = null; }
  if (c._readyTimeout) { clearTimeout(c._readyTimeout); c._readyTimeout = null; }
  c._monitorGen = (c._monitorGen || 0) + 1;
  return c;
}

function makeLiveReady(c) {
  c.isReady = true;
  c.status = "ready";
  c.connectionState = "CONNECTED";
  c._touchActivity();           // recent inbound => _isLive() true
  assert.ok(c._isLive(), "precondition: session should look live");
}

test("disconnected: a FATAL reason (NAVIGATION) is NOT swallowed even when the socket looks live", async () => {
  const c = await bootedClient();
  makeLiveReady(c);
  c.client.emit("disconnected", "NAVIGATION");
  assert.strictEqual(c.status, "disconnected", "a fatal disconnect must demote even when live");
  assert.strictEqual(c.isReady, false);
});

test("disconnected: a known transient blip (TIMEOUT) IS ignored while the socket is live", async () => {
  const c = await bootedClient();
  makeLiveReady(c);
  c.client.emit("disconnected", "TIMEOUT");
  assert.strictEqual(c.status, "ready", "a transient blip on a live socket must be ignored");
  assert.strictEqual(c.isReady, true);
});

test("change_state: a FATAL state (UNPAIRED) zeros liveness (invariant #5) and demotes", async () => {
  const c = await bootedClient();
  makeLiveReady(c);
  c.client.emit("change_state", "UNPAIRED");
  assert.strictEqual(c._isLive(), false, "fatal change_state must zero _lastInboundMs (no ghost-connected)");
  assert.strictEqual(c.status, "disconnected");
  assert.strictEqual(c.isReady, false);
});

test("change_state: CONNECTED promotes a down session to ready", async () => {
  const c = await bootedClient();
  c.isReady = false;
  c.status = "disconnected";
  c.client.emit("change_state", "CONNECTED");
  assert.strictEqual(c.status, "ready");
  assert.strictEqual(c.isReady, true);
});

test("invariant #7: a LOGOUT teardown (disconnected/change_state) never writes the intentional-down marker", async () => {
  const c = await bootedClient();
  makeLiveReady(c);
  c.client.emit("disconnected", "LOGOUT");
  assert.strictEqual(c._isIntentionalDown(), false, "a transient/logout teardown must not set intentional-down");
  const c2 = await bootedClient(5);
  makeLiveReady(c2);
  c2.client.emit("change_state", "LOGOUT");
  assert.strictEqual(c2._isIntentionalDown(), false, "change_state LOGOUT must not set intentional-down");
});
