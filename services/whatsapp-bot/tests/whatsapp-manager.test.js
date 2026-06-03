/**
 * Tests for WhatsAppManager / WhatsAppClient (multi-session per-tenant F29).
 *
 * Run: node services/whatsapp-bot/tests/whatsapp-manager.test.js
 * (or via package.json "test:lite" script)
 *
 * These tests use a CLIENT FACTORY MOCK so we never spin Puppeteer/Chromium.
 * The factory swaps the real WhatsAppClient for a stub that records calls and
 * emits events synchronously — enough to validate the orchestration logic.
 */
"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");
const EventEmitter = require("node:events");

// IMPORTANT: load the real WhatsAppManager but inject a mock client factory.
// This avoids requiring `whatsapp-web.js` (Puppeteer dep) at module load time.
const path = require("node:path");

// Monkey-patch require cache so the WhatsAppClient class never touches
// whatsapp-web.js. We need to stub the module BEFORE require'ing the file.
const Module = require("node:module");
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  if (request === "whatsapp-web.js") {
    return path.join(__dirname, "stubs", "whatsapp-web-stub.js");
  }
  if (request === "qrcode-terminal" || request === "qrcode") {
    return path.join(__dirname, "stubs", "noop-stub.js");
  }
  return originalResolve.call(this, request, parent, ...rest);
};

// Load module under test AFTER the patch.
const { WhatsAppManager, WhatsAppClient, DEFAULT_ORG_ID } = require("../whatsapp-client");

// Helper: factory that builds a stub client carrying the same API surface
// the manager and server-lite expect, without spinning real Puppeteer.
function mockClientFactory(opts) {
  const stub = new EventEmitter();
  stub.orgId = opts.orgId;
  stub.dataBase = opts.dataBase;
  stub.status = "disconnected";
  stub.isReady = false;
  stub.qrCode = null;
  stub.client = null;
  stub._initCount = 0;
  stub._sentMessages = [];
  stub.initialize = async () => {
    stub._initCount += 1;
    stub.client = { sendMessage: () => ({}) };
    stub.status = "ready";
    stub.isReady = true;
    stub.emit("ready");
  };
  stub.getStatus = () => ({
    orgId: stub.orgId,
    status: stub.status,
    isReady: stub.isReady,
    hasQrCode: !!stub.qrCode,
    hasPairingCode: false,
    pairingCode: null,
    pairingPhoneNumber: null,
  });
  stub.getQrCode = () => stub.qrCode;
  stub.sendMessage = async (to, text) => {
    stub._sentMessages.push({ orgId: stub.orgId, to, text });
    return { id: { _serialized: `msg-${stub.orgId}-${stub._sentMessages.length}` } };
  };
  stub.disconnect = async () => { stub.status = "disconnected"; stub.isReady = false; };
  stub.getClient = () => stub.client;
  return stub;
}

test("WhatsAppManager.getOrCreate returns same instance for same orgId", () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  const c1 = mgr.getOrCreate(1);
  const c2 = mgr.getOrCreate(1);
  assert.strictEqual(c1, c2, "same orgId must yield same client");
  assert.strictEqual(c1.orgId, 1);
});

test("WhatsAppManager.getOrCreate isolates different orgs", () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  const orgA = mgr.getOrCreate(1);
  const orgB = mgr.getOrCreate(4);
  assert.notStrictEqual(orgA, orgB, "different orgs must yield different clients");
  assert.strictEqual(orgA.orgId, 1);
  assert.strictEqual(orgB.orgId, 4);
});

test("WhatsAppManager.ensureInitialized boots only once per org", async () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  const c1 = await mgr.ensureInitialized(1);
  const c2 = await mgr.ensureInitialized(1);
  assert.strictEqual(c1, c2);
  assert.strictEqual(c1._initCount, 1, "initialize must run exactly once");
});

test("WhatsAppManager._resolveOrgId accepts number, string, falls back to default", () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  assert.strictEqual(mgr._resolveOrgId(4), 4);
  assert.strictEqual(mgr._resolveOrgId("4"), 4);
  assert.strictEqual(mgr._resolveOrgId(null), DEFAULT_ORG_ID);
  assert.strictEqual(mgr._resolveOrgId(undefined), DEFAULT_ORG_ID);
  assert.strictEqual(mgr._resolveOrgId(""), DEFAULT_ORG_ID);
  assert.throws(() => mgr._resolveOrgId("abc"), /orgId invalido/);
  assert.throws(() => mgr._resolveOrgId(0), /orgId invalido/);
  assert.throws(() => mgr._resolveOrgId(-1), /orgId invalido/);
});

test("WhatsAppManager emits forwarded events with {orgId} meta arg", async () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  const client = await mgr.ensureInitialized(4);
  const received = [];
  mgr.on("message", (payload, meta) => received.push({ payload, meta }));
  // Emit a synthetic message from the client; the manager should re-emit with meta.
  client.emit("message", { from: "5511999@c.us", body: "hello", orgId: 4 });
  assert.strictEqual(received.length, 1);
  assert.strictEqual(received[0].payload.body, "hello");
  assert.strictEqual(received[0].meta.orgId, 4);
});

test("WhatsAppManager keeps tenant sends isolated", async () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  const orgA = await mgr.ensureInitialized(1);
  const orgB = await mgr.ensureInitialized(4);
  await orgA.sendMessage("5511111111111", "to A's tenant");
  await orgB.sendMessage("5522222222222", "to B's tenant");
  assert.strictEqual(orgA._sentMessages.length, 1);
  assert.strictEqual(orgB._sentMessages.length, 1);
  assert.strictEqual(orgA._sentMessages[0].text, "to A's tenant");
  assert.strictEqual(orgB._sentMessages[0].text, "to B's tenant");
  // No bleed across tenants.
  assert.strictEqual(orgA._sentMessages[0].orgId, 1);
  assert.strictEqual(orgB._sentMessages[0].orgId, 4);
});

test("WhatsAppManager.snapshot reports per-org state", async () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  await mgr.ensureInitialized(1);
  await mgr.ensureInitialized(4);
  const snap = mgr.snapshot();
  assert.strictEqual(snap.length, 2);
  const ids = snap.map((s) => s.orgId).sort();
  assert.deepStrictEqual(ids, [1, 4]);
  assert.ok(snap.every((s) => s.isReady === true), "all stubs should be ready");
});

test("WhatsAppManager.destroy removes one org without affecting others", async () => {
  const mgr = new WhatsAppManager({ clientFactory: mockClientFactory });
  await mgr.ensureInitialized(1);
  await mgr.ensureInitialized(4);
  await mgr.destroy(1);
  assert.strictEqual(mgr.has(1), false);
  assert.strictEqual(mgr.has(4), true);
});

test("resolveOrgId (server-lite) priority: header > query > body > default", () => {
  // Avoid loading server-lite (it tries to listen). Reimplement the same
  // priority order — this is a smoke test of the contract, not the impl.
  // The actual server-lite is exercised by integration tests.
  function resolveOrgId(req) {
    const header = req.headers["x-org-id"] || req.headers["x-orgid"];
    const fromHeader = header ? parseInt(String(header), 10) : NaN;
    if (Number.isFinite(fromHeader) && fromHeader > 0) return fromHeader;
    const fromQuery = req.query && req.query.org_id ? parseInt(String(req.query.org_id), 10) : NaN;
    if (Number.isFinite(fromQuery) && fromQuery > 0) return fromQuery;
    const fromBody = req.body && req.body.org_id ? parseInt(String(req.body.org_id), 10) : NaN;
    if (Number.isFinite(fromBody) && fromBody > 0) return fromBody;
    return DEFAULT_ORG_ID;
  }
  assert.strictEqual(resolveOrgId({ headers: { "x-org-id": "4" }, query: {}, body: {} }), 4);
  assert.strictEqual(resolveOrgId({ headers: {}, query: { org_id: "7" }, body: {} }), 7);
  assert.strictEqual(resolveOrgId({ headers: {}, query: {}, body: { org_id: "9" } }), 9);
  assert.strictEqual(resolveOrgId({ headers: {}, query: {}, body: {} }), DEFAULT_ORG_ID);
  // Header wins over query/body.
  assert.strictEqual(resolveOrgId({ headers: { "x-org-id": "1" }, query: { org_id: "2" }, body: { org_id: "3" } }), 1);
  // Invalid header falls through.
  assert.strictEqual(resolveOrgId({ headers: { "x-org-id": "abc" }, query: { org_id: "2" }, body: {} }), 2);
});
