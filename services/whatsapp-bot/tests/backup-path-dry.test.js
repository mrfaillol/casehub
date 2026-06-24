"use strict";

// RC4 (Frente 1): single-source the backup directory name through _backupDir(),
// and delete the misleading userDataDir comment — there is no userDataDir key;
// LocalAuth isolates the profile via clientId. The DRY refactor produces a
// byte-identical path, so the relationship is pinned by introspection (does
// _snapshotSession resolve via _backupDir?) plus a behavioral pin of _backupDir.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

// Behavioral pin needs a WhatsAppClient instance without Puppeteer: redirect the
// native deps to the test stubs before requiring the module (same idiom as
// whatsapp-manager.test.js).
const Module = require("node:module");
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  if (request === "whatsapp-web.js") return path.join(__dirname, "stubs", "whatsapp-web-stub.js");
  if (request === "qrcode-terminal" || request === "qrcode") return path.join(__dirname, "stubs", "noop-stub.js");
  return originalResolve.call(this, request, parent, ...rest);
};
const { WhatsAppClient } = require("../whatsapp-client");

const source = fs.readFileSync(path.join(__dirname, "..", "whatsapp-client.js"), "utf8");

function snapshotBody() {
  const start = source.indexOf("_snapshotSession(suffix) {");
  const end = source.indexOf("backupSession()", start);
  assert.ok(start !== -1 && end > start, "could not locate _snapshotSession body");
  return source.slice(start, end);
}

test("_backupDir builds the canonical per-org backup name for a suffix", () => {
  const c = new WhatsAppClient({ orgId: 7, dataBase: "./.wwebjs_auth" });
  const dir = c._backupDir("__lastgood");
  assert.ok(dir.includes("_bak-session-org-7"), "backup must be scoped to the org");
  assert.ok(dir.endsWith("__lastgood"), "backup must carry the slot suffix");
});

test("_snapshotSession resolves its destination via this._backupDir(suffix)", () => {
  const body = snapshotBody();
  assert.match(body, /this\._backupDir\(suffix\)/, "_snapshotSession must reuse _backupDir(suffix)");
  // The literal backup path must live ONLY in _backupDir(), not be re-spelled here.
  assert.doesNotMatch(
    body,
    /_bak-session-org-\$\{this\.orgId\}\$\{suffix\}/,
    "backup literal must not be duplicated inside _snapshotSession"
  );
});

test("the false userDataDir comment is removed (no userDataDir key ever existed)", () => {
  assert.doesNotMatch(source, /userDataDir/, "misleading userDataDir comment must be deleted");
});
