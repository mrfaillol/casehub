"use strict";

// Frente 3 (Solucao C): auth_failure auto-recovery must PRESERVE __lastgood (the
// healthy snapshot from the last `ready`) so a TRANSIENT auth_failure can auto-
// cure on the next boot instead of forcing a manual QR. __prewipe (the dead auth)
// is still ALWAYS captured (invariant #4), and an explicit human wipe / re-pair
// still discards __lastgood (it must not be undone by the auto-restore).

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
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-lg-"));
  const c = new WhatsAppClient({ orgId, dataBase });
  // No Puppeteer re-init. For the no-phone (QR) path, satisfy the QR-wait promise
  // inside clearAndReinitialize() so it resolves quickly instead of timing out.
  c.initialize = async () => { c.qrCode = "data:image/png;base64,stub"; c.status = "awaiting_scan"; };
  return c;
}

test("clearAndReinitialize preserves __lastgood when options.preserveLastGood is set", async () => {
  const c = tmpClient(4);
  const discarded = [];
  c._discardLastGoodBackup = (reason) => discarded.push(reason);
  await c.clearAndReinitialize(null, { preserveLastGood: true });
  assert.strictEqual(discarded.length, 0, "auth_failure auto-recovery must keep __lastgood");
});

test("clearAndReinitialize discards __lastgood on an explicit wipe (no phone, no options)", async () => {
  const c = tmpClient(4);
  const discarded = [];
  c._discardLastGoodBackup = (reason) => discarded.push(reason);
  await c.clearAndReinitialize();
  assert.strictEqual(discarded.length, 1, "an explicit wipe must still discard __lastgood");
});

test("clearAndReinitialize discards __lastgood on an explicit re-pair (phoneNumber)", async () => {
  const c = tmpClient(4);
  const discarded = [];
  c._discardLastGoodBackup = (reason) => discarded.push(reason);
  await c.clearAndReinitialize("5511999998888");
  assert.strictEqual(discarded.length, 1, "a re-pair must still discard __lastgood");
});

test("__prewipe is ALWAYS snapshotted before the wipe, even when preserving __lastgood", async () => {
  const c = tmpClient(4);
  const snaps = [];
  c._snapshotSession = (suffix) => { snaps.push(suffix); return true; };
  c._discardLastGoodBackup = () => {};
  await c.clearAndReinitialize(null, { preserveLastGood: true });
  assert.ok(snaps.includes("__prewipe"), "__prewipe snapshot must always run (invariant #4)");
});

test("the auth_failure handler recovers with preserveLastGood:true", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "whatsapp-client.js"), "utf8");
  const start = source.indexOf('this.client.on("auth_failure"');
  assert.ok(start !== -1, "could not locate the auth_failure handler");
  const handler = source.slice(start, start + 2500);   // window covers the whole handler
  // preserveLastGood is conditional: preserved for a transient (non-restored)
  // auth_failure, discarded when the failed session was itself restored from a
  // now-proven-dead __lastgood. The end-to-end discard/preserve decision is
  // covered behaviorally in auth-failure-convergence.test.js.
  assert.match(
    handler,
    /clearAndReinitialize\(\s*null\s*,\s*\{\s*preserveLastGood:\s*!this\._restoredFromLastGood/,
    "auth_failure recovery must call clearAndReinitialize(null, { preserveLastGood: !this._restoredFromLastGood })"
  );
});
