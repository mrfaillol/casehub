"use strict";

// Frente 7 (RC5): the disconnected and change_state handlers each had their own
// fatal-vs-transient vocabulary, and they disagreed on NAVIGATION/LOGOUT — the
// inconsistency behind the earlier LOGOUT incident. A single _classifyReason()
// gives both handlers ONE vocabulary (fatal = UNPAIRED|CONFLICT|LOGOUT|NAVIGATION)
// and a single place that zeros liveness on a truly-dead session.

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

function tmpClient(orgId = 1) {
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-cr-"));
  return new WhatsAppClient({ orgId, dataBase });
}

test("_classifyReason marks the logout family fatal (case-insensitive)", () => {
  const c = tmpClient();
  for (const r of ["LOGOUT", "UNPAIRED", "CONFLICT", "NAVIGATION", "logout", "Navigation"]) {
    assert.strictEqual(c._classifyReason(r), "fatal", `${r} must be fatal`);
  }
});

test("_classifyReason marks everything else transient (incl. empty/unknown)", () => {
  const c = tmpClient();
  for (const r of ["TIMEOUT", "OPENING", "PAIRING", "CONNECTING", "SOMETHING_ELSE", "", null, undefined]) {
    assert.strictEqual(c._classifyReason(r), "transient", `${String(r)} must be transient`);
  }
});

test("_isAmbiguousHealthState marks watchdog flakiness as non-user-facing", () => {
  const c = tmpClient();
  for (const state of ["UNKNOWN", "UNREACHABLE", "TIMEOUT", "OPENING", "CONNECTING", "unknown"]) {
    assert.strictEqual(c._isAmbiguousHealthState(state), true, `${state} must be ambiguous`);
  }
  for (const state of ["UNPAIRED", "CONFLICT", "LOGOUT", "NAVIGATION", "CONNECTED"]) {
    assert.strictEqual(c._isAmbiguousHealthState(state), false, `${state} must not be ambiguous`);
  }
});

test("both disconnected and change_state delegate to _classifyReason", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "whatsapp-client.js"), "utf8");
  const discStart = source.indexOf('this.client.on("disconnected"');
  const csStart = source.indexOf('this.client.on("change_state"');
  const authStart = source.indexOf('this.client.on("auth_failure"');
  assert.ok(discStart !== -1 && csStart > discStart && authStart > csStart, "handler boundaries not found");
  const disconnectedBody = source.slice(discStart, csStart);
  const changeStateBody = source.slice(csStart, authStart);
  assert.match(disconnectedBody, /_classifyReason\(/, "disconnected must use the shared classifier");
  assert.match(changeStateBody, /_classifyReason\(/, "change_state must use the shared classifier");
});
