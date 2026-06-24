"use strict";

// Frente 1/E: pin the load-bearing LocalAuth clientId -> on-disk dir convention.
// whatsapp-web.js's LocalAuth stores a session at <dataPath>/session-<clientId>.
// We use clientId = "org-<id>", so the live dir is "session-org-<id>". _sessionDir()
// MIRRORS that path by hand (there is no API to read it back), and host-binding,
// wipe, lock-clear and backup all target _sessionDir(). If a lib upgrade or a
// refactor drifts EITHER side, those operations would silently target the wrong
// directory. This test fails loudly the moment the mirror diverges.

const assert = require("node:assert/strict");
const fs = require("node:fs");
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

test("_sessionDir() is <dataBase>/session-org-<id>", () => {
  const c4 = new WhatsAppClient({ orgId: 4, dataBase: "./.wwebjs_auth" });
  assert.strictEqual(c4._sessionDir(), path.join("./.wwebjs_auth", "session-org-4"));
  const c7 = new WhatsAppClient({ orgId: 7, dataBase: "/tmp/wa" });
  assert.strictEqual(c7._sessionDir(), path.join("/tmp/wa", "session-org-7"));
});

test("_sessionDir() basename equals session-<clientId> with clientId=org-<id>", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "whatsapp-client.js"), "utf8");
  // LocalAuth is constructed with clientId = `org-${this.orgId}` ...
  assert.match(source, /clientId:\s*`org-\$\{this\.orgId\}`/, "LocalAuth clientId convention drifted");
  // ... and whatsapp-web.js derives the dir as session-<clientId>, which _sessionDir mirrors.
  const c = new WhatsAppClient({ orgId: 4, dataBase: "/tmp/wa" });
  assert.strictEqual(path.basename(c._sessionDir()), "session-" + "org-4");
});
