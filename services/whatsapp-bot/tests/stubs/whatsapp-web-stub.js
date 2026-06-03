/**
 * Stub of whatsapp-web.js for unit tests. Avoids spinning Puppeteer in CI.
 * Only mocks the surface our code touches:
 *   - new Client(options) — captures options, no-op initialize
 *   - new LocalAuth({ clientId, dataPath }) — captures both
 *
 * The Manager unit tests inject their own client factory anyway, so this
 * stub is just to let the WhatsAppClient class be required without crashing.
 */
"use strict";

const EventEmitter = require("node:events");

class StubClient extends EventEmitter {
  constructor(options) {
    super();
    this.options = options || {};
  }
  async initialize() {
    // No-op; tests inject their own behaviour via clientFactory.
    return;
  }
  async destroy() { /* no-op */ }
  async getState() { return "CONNECTED"; }
  async sendMessage() { return { id: { _serialized: "stub-msg" } }; }
  async getChats() { return []; }
  async getChatById() { throw new Error("stub: not implemented"); }
  async getProfilePicUrl() { return null; }
  async getContactLidAndPhone() { return []; }
}

class StubLocalAuth {
  constructor(opts) { this.opts = opts || {}; }
}

module.exports = {
  Client: StubClient,
  LocalAuth: StubLocalAuth,
};
