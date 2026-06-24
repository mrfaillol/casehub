"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const serverLitePath = path.join(__dirname, "..", "server-lite.js");
const source = fs.readFileSync(serverLitePath, "utf8");

function routeCall(method, route) {
  const needle = `app.${method}(${JSON.stringify(route)}`;
  const start = source.indexOf(needle);
  assert.notStrictEqual(start, -1, `missing ${method.toUpperCase()} ${route}`);

  const openParen = source.indexOf("(", start);
  assert.notStrictEqual(openParen, -1, `malformed ${method.toUpperCase()} ${route}`);

  let depth = 0;
  let state = "code";
  let escaped = false;

  for (let i = openParen; i < source.length; i += 1) {
    const ch = source[i];
    const next = source[i + 1];

    if (state === "line-comment") {
      if (ch === "\n") state = "code";
      continue;
    }

    if (state === "block-comment") {
      if (ch === "*" && next === "/") {
        state = "code";
        i += 1;
      }
      continue;
    }

    if (state === "single" || state === "double" || state === "template") {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (
        (state === "single" && ch === "'") ||
        (state === "double" && ch === '"') ||
        (state === "template" && ch === "`")
      ) {
        state = "code";
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      state = "line-comment";
      i += 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      state = "block-comment";
      i += 1;
      continue;
    }
    if (ch === "'") {
      state = "single";
      continue;
    }
    if (ch === '"') {
      state = "double";
      continue;
    }
    if (ch === "`") {
      state = "template";
      continue;
    }
    if (ch === "(") {
      depth += 1;
      continue;
    }
    if (ch === ")") {
      depth -= 1;
      if (depth === 0) {
        const semicolon = source.indexOf(";", i);
        assert.notStrictEqual(semicolon, -1, `unterminated ${method.toUpperCase()} ${route}`);
        return source.slice(start, semicolon + 1);
      }
    }
  }

  assert.fail(`could not parse ${method.toUpperCase()} ${route}`);
}

function occurrences(haystack, needle) {
  return haystack.split(needle).length - 1;
}

test("server-lite exposes POST /api/reconnect and preserves the saved session", () => {
  const reconnect = routeCall("post", "/api/reconnect");

  assert.match(reconnect, /await\s+client\.softReconnect\(\);/);
  assert.match(reconnect, /preserved:\s*true/);
  assert.doesNotMatch(reconnect, /clearAndReinitialize\s*\(/);
});

test("server-lite /api/status uses verified WhatsApp state when available", () => {
  const statusRoute = routeCall("get", "/api/status");
  const payloadHelper = source.slice(
    source.indexOf("async function statusPayload"),
    source.indexOf("function normalizeLimit")
  );

  assert.match(payloadHelper, /client\.getStatusVerified/);
  assert.match(statusRoute, /await\s+statusPayload\(client\)/);
});

test("server-lite exposes profile picture endpoints for chat avatars", () => {
  const one = routeCall("get", "/api/profile-pic/:phone");
  const batch = routeCall("post", "/api/profile-pics");
  const conversations = routeCall("get", "/api/conversations");

  assert.match(one, /await\s+client\.getProfilePicUrl\(req\.params\.phone\)/);
  assert.match(batch, /await\s+client\.getProfilePics\(phones/);
  assert.match(batch, /profiles:\s*\[\]/);
  assert.match(conversations, /includeProfilePics:\s*req\.query\.profilePics\s*===\s*"1"/);
});

test("server-lite ready handler accepts manager metadata as the only event arg", () => {
  const readyStart = source.indexOf('manager.on("ready"');
  const readyEnd = source.indexOf('manager.on("disconnected"', readyStart);
  const readyHandler = source.slice(readyStart, readyEnd);

  assert.match(readyHandler, /async\s*\(\.\.\.args\)/);
  assert.match(readyHandler, /args\.find\(\(arg\)\s*=>\s*arg\s*&&\s*Number\.isFinite\(arg\.orgId\)\)/);
  assert.match(readyHandler, /forwardContactsSync\(contacts,\s*\{\s*orgId\s*\}\)/);
});

test("server-lite suppresses noisy health-monitor disconnect alerts", () => {
  const helperStart = source.indexOf("function isNoisyHealthMonitorReason");
  const helperEnd = source.indexOf("// --- Inbound media serving", helperStart);
  const handlerStart = source.indexOf('manager.on("disconnected"');
  const handlerEnd = source.indexOf('manager.on("auth_failure"', handlerStart);
  assert.notStrictEqual(helperStart, -1, "missing health-monitor noise helper");
  assert.ok(helperEnd > helperStart, "helper boundary not found");
  assert.ok(handlerEnd > handlerStart, "disconnect handler boundary not found");

  const helper = source.slice(helperStart, helperEnd);
  const handler = source.slice(handlerStart, handlerEnd);
  assert.match(helper, /health-monitor:\(UNKNOWN\|UNREACHABLE\|TIMEOUT\|OPENING\|CONNECTING\)/);
  assert.match(handler, /isNoisyHealthMonitorReason\(reason\)/);
  assert.match(handler, /alerta de disconnect suprimido/);
  assert.match(handler, /forwardEvent\(\{\s*event:\s*"disconnected",\s*reason\s*\}/);
});

test("server-lite /health reports process and WhatsApp readiness without failing on pairing", () => {
  const health = routeCall("get", "/health");

  assert.match(health, /res\.status\(200\)\.json\(\{/);
  assert.match(health, /processOk:\s*true/);
  assert.match(health, /whatsappReady:\s*anyReady/);
  assert.match(health, /requiresPairing/);
});

test("server-lite /api/disconnect wipes only behind an explicit confirmation branch", () => {
  const disconnect = routeCall("post", "/api/disconnect");

  assert.match(disconnect, /const\s+confirmWipe\s*=/);
  assert.match(disconnect, /b\.confirm\s*===\s*"wipe"/);
  assert.strictEqual(occurrences(disconnect, "clearAndReinitialize"), 1);

  const confirmIndex = disconnect.indexOf("if (confirmWipe)");
  const wipeIndex = disconnect.indexOf("await client.clearAndReinitialize();");
  const preserveIndex = disconnect.indexOf("await client.disconnect();");

  assert.ok(confirmIndex > -1, "missing confirmWipe guard");
  assert.ok(wipeIndex > confirmIndex, "wipe must be inside the confirmation path");
  assert.ok(preserveIndex > wipeIndex, "default disconnect path must come after the wipe branch returns");

  assert.match(disconnect, /wiped:\s*true/);
  assert.match(disconnect, /wiped:\s*false/);
  assert.match(disconnect, /preserved:\s*true/);
});
