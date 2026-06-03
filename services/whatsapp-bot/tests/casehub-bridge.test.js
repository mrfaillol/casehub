/**
 * Tests for casehub-bridge multi-tenant X-Org-Id forwarding (F29).
 *
 * Verifies forwardInbound / forwardAck attach X-Org-Id when orgId is given,
 * and omit it otherwise. Uses a mock HTTP server that captures requests
 * (no real network call).
 *
 * Run: node services/whatsapp-bot/tests/casehub-bridge.test.js
 */
"use strict";

const assert = require("node:assert/strict");
const { test, before, after } = require("node:test");
const http = require("node:http");

// Force HMAC secret + bridge enabled for the test process.
process.env.CASEHUB_INBOUND_HMAC_SECRET = "test-secret-deadbeef-deadbeef";
process.env.CASEHUB_BRIDGE_ENABLED = "true";

let server;
let serverUrl;
// Captures request bodies + headers so tests can assert on them.
let captured = [];

before(async () => {
  await new Promise((resolve) => {
    server = http.createServer((req, res) => {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        captured.push({
          method: req.method,
          url: req.url,
          headers: { ...req.headers },
          body,
        });
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
      });
    });
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      serverUrl = `http://127.0.0.1:${addr.port}`;
      process.env.CASEHUB_API_URL = serverUrl;
      // Bridge module reads env at require time — defer require until after env is set.
      resolve();
    });
  });
});

after(async () => {
  await new Promise((r) => server.close(() => r()));
});

function loadBridge() {
  // Fresh require each time to pick up env changes.
  delete require.cache[require.resolve("../casehub-bridge")];
  return require("../casehub-bridge");
}

test("forwardInbound includes X-Org-Id when orgId is given", async () => {
  captured = [];
  const { forwardInbound } = loadBridge();
  const result = await forwardInbound(
    {
      from: "5511999999999@c.us",
      body: "hello",
      messageId: "m1",
      hasMedia: false,
    },
    { orgId: 4 }
  );
  assert.strictEqual(result.ok, true);
  assert.strictEqual(captured.length, 1);
  assert.strictEqual(captured[0].headers["x-org-id"], "4");
  // HMAC headers also present
  assert.ok(captured[0].headers["x-casehub-signature"]);
  assert.ok(captured[0].headers["x-casehub-timestamp"]);
});

test("forwardInbound omits X-Org-Id when orgId is missing", async () => {
  captured = [];
  const { forwardInbound } = loadBridge();
  await forwardInbound({
    from: "5511999999999@c.us",
    body: "hello",
    messageId: "m1",
    hasMedia: false,
  });
  assert.strictEqual(captured.length, 1);
  assert.strictEqual(captured[0].headers["x-org-id"], undefined);
});

test("forwardInbound picks up orgId from data.orgId when options missing", async () => {
  captured = [];
  const { forwardInbound } = loadBridge();
  await forwardInbound({
    orgId: 7,
    from: "5511999999999@c.us",
    body: "hello",
    messageId: "m1",
    hasMedia: false,
  });
  assert.strictEqual(captured.length, 1);
  assert.strictEqual(captured[0].headers["x-org-id"], "7");
});

test("forwardInbound skips on group chat (does not call upstream)", async () => {
  captured = [];
  const { forwardInbound } = loadBridge();
  const result = await forwardInbound(
    {
      from: "5511999999999-1234567890@g.us",
      body: "hello",
      messageId: "m1",
      hasMedia: false,
    },
    { orgId: 4 }
  );
  assert.strictEqual(result.skipped, "group");
  assert.strictEqual(captured.length, 0);
});

test("forwardInbound skips empty text + no media", async () => {
  captured = [];
  const { forwardInbound } = loadBridge();
  const result = await forwardInbound(
    {
      from: "5511999999999@c.us",
      body: "",
      messageId: "m1",
      hasMedia: false,
    },
    { orgId: 4 }
  );
  assert.strictEqual(result.skipped, "empty text");
  assert.strictEqual(captured.length, 0);
});

test("forwardAck includes X-Org-Id when orgId is given", async () => {
  captured = [];
  const { forwardAck } = loadBridge();
  const result = await forwardAck(
    { messageId: "wa-msg-1", ack: 2, status: "delivered", to: "5511999999999" },
    { orgId: 4 }
  );
  assert.strictEqual(result.ok, true);
  assert.strictEqual(captured.length, 1);
  assert.strictEqual(captured[0].headers["x-org-id"], "4");
});

test("forwardAck skips when wa_message_id is missing", async () => {
  captured = [];
  const { forwardAck } = loadBridge();
  const result = await forwardAck(
    { messageId: null, ack: 2, status: "delivered" },
    { orgId: 4 }
  );
  assert.strictEqual(result.skipped, "no message id");
  assert.strictEqual(captured.length, 0);
});

test("X-Org-Id is OUTSIDE the signed body (replay-safe)", async () => {
  captured = [];
  const { forwardInbound } = loadBridge();
  await forwardInbound(
    {
      from: "5511999999999@c.us",
      body: "hello",
      messageId: "m1",
      hasMedia: false,
    },
    { orgId: 4 }
  );
  assert.strictEqual(captured.length, 1);
  // The body must NOT contain orgId / org_id at the top level — it lives
  // in the header so the HMAC contract stays unchanged.
  const parsed = JSON.parse(captured[0].body);
  assert.strictEqual(parsed.org_id, undefined);
  assert.strictEqual(parsed.orgId, undefined);
  // Header carries it.
  assert.strictEqual(captured[0].headers["x-org-id"], "4");
});
