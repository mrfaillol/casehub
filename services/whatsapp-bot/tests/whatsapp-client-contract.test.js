"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const clientPath = path.join(__dirname, "..", "whatsapp-client.js");
const source = fs.readFileSync(clientPath, "utf8");

test("WhatsAppClient keeps LocalAuth isolated per org without wiping saved sessions", () => {
  assert.match(source, /authStrategy:\s*new\s+LocalAuth\(\{/);
  assert.match(source, /clientId:\s*`org-\$\{this\.orgId\}`/);
  assert.match(source, /dataPath:\s*this\.dataBase/);
  assert.match(source, /async\s+softReconnect\(\)/);
  assert.match(source, /await\s+this\.initialize\(\);/);

  const reconnectStart = source.indexOf("async softReconnect()");
  const reconnectEnd = source.indexOf("// Monitor de saude", reconnectStart);
  const reconnectBody = source.slice(reconnectStart, reconnectEnd);
  assert.doesNotMatch(reconnectBody, /clearAndReinitialize\s*\(/);
  assert.doesNotMatch(reconnectBody, /rmSync\s*\(/);
});

test("incoming messages forward stable contact names and profile photos", () => {
  const start = source.indexOf('this.client.on("message"');
  const end = source.indexOf("// message_ack", start);
  const handler = source.slice(start, end);

  assert.match(handler, /message\.getContact\(\)/);
  assert.match(handler, /contact\.pushname\s*\|\|\s*contact\.name/);
  assert.match(handler, /contact\.getProfilePicUrl\(\)/);
  assert.match(handler, /this\.client\.getProfilePicUrl\(realPhone\s*\+\s*"@c\.us"\)/);
  assert.match(handler, /name:\s*contactName/);
  assert.match(handler, /profilePicUrl:\s*profilePicUrl/);
});

test("ready sync enumerates chats and returns names plus profile_pic_url", () => {
  const start = source.indexOf("async syncProfilePhotos");
  const end = source.indexOf("// Snapshot atomico", start);
  const sync = source.slice(start, end);

  assert.match(sync, /this\.client\.getChats\(\)/);
  assert.match(sync, /chat\.getContact\(\)/);
  assert.match(sync, /contact\.pushname\s*\|\|\s*contact\.name/);
  assert.match(sync, /contact\.getProfilePicUrl\(\)/);
  assert.match(sync, /display_name:\s*displayName/);
  assert.match(sync, /profile_pic_url:\s*profilePicUrl/);
});

test("chat history fetched from WhatsApp Web is normalized oldest-first", () => {
  const start = source.indexOf("async getMessages");
  const end = source.indexOf("async sendMessage", start);
  const getMessages = source.slice(start, end);

  assert.match(getMessages, /chat\.fetchMessages\(\{\s*limit\s*\}\)/);
  assert.match(getMessages, /\.sort\(\(a,\s*b\)\s*=>\s*Number\(a\.timestamp/);
  assert.match(getMessages, /\.map\(\(message\)\s*=>\s*this\.messagePayload\(message,\s*chatId\)\)/);
});
