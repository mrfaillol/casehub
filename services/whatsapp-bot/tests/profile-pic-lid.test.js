"use strict";

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

function readyClient() {
  const dataBase = fs.mkdtempSync(path.join(os.tmpdir(), "casehub-wa-pic-lid-"));
  const c = new WhatsAppClient({ orgId: 4, dataBase });
  c.isReady = true;
  c.connectionState = "CONNECTED";
  return c;
}

function lidChatWithPhoto() {
  return {
    id: { _serialized: "123456789@lid" },
    isGroup: false,
    name: "Contato LID",
    timestamp: 100,
    unreadCount: 0,
    lastMessage: { body: "oi", timestamp: 100, fromMe: false },
    async getContact() {
      return {
        id: { _serialized: "123456789@lid" },
        number: "5511999990000",
        pushname: "Contato LID",
        isBusiness: false,
        async getProfilePicUrl() {
          return "https://pps.whatsapp.net/lid-avatar.jpg";
        },
      };
    },
  };
}

test("getProfilePicUrl falls back to Chat Contact for LID-backed phone contacts", async () => {
  const c = readyClient();
  const calls = [];
  c.client = {
    async getProfilePicUrl(jid) {
      calls.push(jid);
      return null;
    },
    async getChats() {
      return [lidChatWithPhoto()];
    },
  };

  const url = await c.getProfilePicUrl("+5511999990000");

  assert.strictEqual(url, "https://pps.whatsapp.net/lid-avatar.jpg");
  assert.ok(calls.includes("5511999990000@c.us"), "direct @c.us lookup should be attempted first");
});

test("syncProfilePhotos does not skip LID chats when Contact exposes the real phone", async () => {
  const c = readyClient();
  c.client = {
    async getChats() {
      return [lidChatWithPhoto()];
    },
    async getProfilePicUrl() {
      return null;
    },
  };

  const contacts = await c.syncProfilePhotos({ limit: 1 });

  assert.strictEqual(contacts.length, 1);
  assert.strictEqual(contacts[0].phone, "5511999990000");
  assert.strictEqual(contacts[0].display_name, "Contato LID");
  assert.strictEqual(contacts[0].profile_pic_url, "https://pps.whatsapp.net/lid-avatar.jpg");
});
