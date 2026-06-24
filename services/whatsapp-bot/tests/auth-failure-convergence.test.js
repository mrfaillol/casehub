"use strict";

// Verification follow-up (Frente 3 hardening): preserving __lastgood on EVERY
// auth_failure means a GENUINE phone-side logout re-restores the dead backup on
// every container restart (restore-on-boot -> auth_failure -> wipe -> QR), paying
// a wasted cycle each boot instead of converging straight to QR. Fix: track when
// the live session was just RESTORED from __lastgood; if THAT session auth-fails,
// the backup is proven dead -> discard it (converge to QR). A non-restored
// (transient) auth_failure still preserves __lastgood for self-cure.

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

async function waitFor(cond, timeoutMs = 5000) {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) throw new Error("waitFor: condition not met in time");
    await new Promise((r) => setTimeout(r, 20));
  }
}

// Boot a client so the real event handlers are wired on the StubClient
// EventEmitter, then silence the background watchdog so it cannot mutate state
// mid-assertion or keep the process alive.
async function bootedClient(orgId, { plantLastGood = false } = {}) {
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-afc-"));
  const c = new WhatsAppClient({ orgId, dataBase });
  if (plantLastGood) {
    const bak = c._backupDir("__lastgood");
    fs.mkdirSync(bak, { recursive: true });
    fs.writeFileSync(path.join(bak, "Default"), "dead-credentials"); // no .host-bind, no env => restore allowed
  }
  await c.initialize();
  if (c._healthTimer) { clearInterval(c._healthTimer); c._healthTimer = null; }
  if (c._readyTimeout) { clearTimeout(c._readyTimeout); c._readyTimeout = null; }
  c._monitorGen = (c._monitorGen || 0) + 1;
  return c;
}

test("_restoreFromBackupOnBoot flags _restoredFromLastGood when it actually restores", () => {
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-afc2-"));
  const c = new WhatsAppClient({ orgId: 4, dataBase });
  const bak = c._backupDir("__lastgood");
  fs.mkdirSync(bak, { recursive: true });
  fs.writeFileSync(path.join(bak, "Default"), "creds");
  assert.strictEqual(c._restoreFromBackupOnBoot(), true);
  assert.strictEqual(c._restoredFromLastGood, true, "a real restore must set the flag");
});

test("a healthy 'ready' clears _restoredFromLastGood (a fresh/healthy session is not 'dead-restored')", async () => {
  const c = await bootedClient(4, { plantLastGood: true });
  assert.strictEqual(c._restoredFromLastGood, true, "boot restored the backup");
  c.client.emit("ready");
  assert.strictEqual(c._restoredFromLastGood, false, "ready must clear the dead-restore flag");
});

test("auth_failure on a restored-then-failed __lastgood DISCARDS it (converges to QR next boot)", async () => {
  const c = await bootedClient(4, { plantLastGood: true });
  assert.strictEqual(c._restoredFromLastGood, true);
  const discarded = [];
  c._discardLastGoodBackup = (r) => discarded.push(r);
  c._snapshotSession = () => true;                              // skip fs snapshot work
  c.initialize = async () => { c.qrCode = "x"; c.status = "awaiting_scan"; }; // resolve the QR-wait fast
  c.client.emit("auth_failure", new Error("Session logged out"));
  await waitFor(() => c._reconnecting === false);
  assert.strictEqual(discarded.length, 1, "a proven-dead restored __lastgood must be discarded");
});

test("auth_failure on a NON-restored session PRESERVES __lastgood (transient self-cure)", async () => {
  const c = await bootedClient(4, { plantLastGood: false });
  assert.ok(!c._restoredFromLastGood, "nothing was restored this boot");
  const discarded = [];
  c._discardLastGoodBackup = (r) => discarded.push(r);
  c._snapshotSession = () => true;
  c.initialize = async () => { c.qrCode = "x"; c.status = "awaiting_scan"; };
  c.client.emit("auth_failure", new Error("transient auth blip"));
  await waitFor(() => c._reconnecting === false);
  assert.strictEqual(discarded.length, 0, "a non-restored session keeps __lastgood for transient self-cure");
});

test("Target closed after authenticated preserves LocalAuth and soft-reconnects instead of wiping", async () => {
  const c = await bootedClient(4, { plantLastGood: false });
  fs.mkdirSync(c._sessionDir(), { recursive: true });
  fs.writeFileSync(path.join(c._sessionDir(), "Default"), "saved-auth");
  c.status = "authenticated";
  c._markEvent("authenticated");

  const clears = [];
  const reconnects = [];
  c.clearAndReinitialize = async () => { clears.push("wipe"); };
  c.softReconnect = async (reason) => { reconnects.push(reason); };

  c.client.emit(
    "auth_failure",
    new Error("Protocol error (Page.addScriptToEvaluateOnNewDocument): Target closed")
  );

  await waitFor(() => reconnects.length === 1);
  assert.deepStrictEqual(clears, [], "browser target closure must not wipe session-org-4");
  assert.strictEqual(reconnects[0], "auth_failure:browser-target-closed");
  assert.strictEqual(c._authFailureCount, 0, "browser target closure is not counted as rejected auth");
});
