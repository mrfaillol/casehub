/**
 * Noop stub for qrcode-terminal and qrcode in unit tests.
 * Both modules render strings; in unit tests we never render, we just need
 * the require() not to fail.
 */
"use strict";

module.exports = {
  generate: () => undefined,
  toDataURL: async (qr) => `data:image/png;base64,${Buffer.from(qr || "").toString("base64")}`,
};
