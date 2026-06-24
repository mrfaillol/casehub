"use strict";

// RC3 (Frente 1): the cosmetic QR cooldown is removed so a fresh QR is never
// throttled. The served QR (`this.qrCode`) must update on EVERY 'qr' event —
// the legacy cooldown that suppressed the served QR caused stale/expired QRs and
// "nao foi possivel conectar o dispositivo". This pins that the served QR is
// unconditional and that no time-gate remains around the QR render.
//
// Source-introspection contract (same idiom as whatsapp-client-contract.test.js):
// reading the file as text avoids spinning Puppeteer just to assert structure.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const clientPath = path.join(__dirname, "..", "whatsapp-client.js");
const source = fs.readFileSync(clientPath, "utf8");

function qrHandler() {
  const start = source.indexOf('this.client.on("qr"');
  const end = source.indexOf('this.client.on("code"', start);
  assert.ok(start !== -1 && end > start, "could not locate the 'qr' event handler");
  return source.slice(start, end);
}

test("the cosmetic QR cooldown is fully removed (no QR_COOLDOWN / _lastQrTimes)", () => {
  assert.doesNotMatch(source, /QR_COOLDOWN/, "QR_COOLDOWN must be deleted");
  assert.doesNotMatch(source, /_lastQrTimes/, "_lastQrTimes throttle map must be deleted");
});

test("the served QR is stored unconditionally on every 'qr' event", () => {
  const handler = qrHandler();
  assert.match(
    handler,
    /this\.qrCode = await QRCode\.toDataURL\(qr\)/,
    "every 'qr' event must refresh this.qrCode"
  );
  // No time-based gate may wrap the QR render (the old `if (now - last >= ...)`).
  assert.doesNotMatch(handler, /now - last/, "no cooldown time-gate may remain in the QR handler");
});
