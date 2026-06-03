/**
 * CaseHub bridge - forwards inbound WhatsApp events to the Python FastAPI backend.
 *
 * Two forwarders, same HMAC scheme:
 *   forwardInbound(data) -> POST <app-prefix>/whatsapp/inbound
 *       mensagens recebidas (com metadados de mídia).
 *   forwardAck(data)     -> POST <app-prefix>/whatsapp/ack
 *       message_ack — evolução dos ticks (enviado/entregue/lido) de mensagens
 *       que NÓS enviamos. O backend casa pelo messageId e atualiza wa_messages.status.
 *
 * Failure of the bridge does NOT block the bot: it logs and returns.
 *
 * Auth: HMAC-SHA256. Headers:
 *   X-Casehub-Timestamp: <unix seconds>
 *   X-Casehub-Signature: hex(hmac_sha256(secret, "<ts>." + rawBody))
 *
 * Configure via env (see config.js): CASEHUB_API_URL, CASEHUB_APP_PREFIX,
 * CASEHUB_PREFIX/PREFIX, CASEHUB_INBOUND_HMAC_SECRET.
 */
"use strict";

const crypto = require("crypto");
const https = require("https");
const http = require("http");
const { URL } = require("url");

const CASEHUB_API_URL = process.env.CASEHUB_API_URL || "http://localhost:8001";
const HMAC_SECRET = process.env.CASEHUB_INBOUND_HMAC_SECRET || "";
const BRIDGE_ENABLED = process.env.CASEHUB_BRIDGE_ENABLED !== "false"; // default ON when secret is set
const BRIDGE_TIMEOUT_MS = parseInt(process.env.CASEHUB_BRIDGE_TIMEOUT_MS || "5000", 10);
const CASEHUB_APP_PREFIX = normalizePrefix(
  firstDefined(
    process.env.CASEHUB_APP_PREFIX,
    process.env.CASEHUB_PREFIX,
    process.env.PREFIX,
    defaultAppPrefix(CASEHUB_API_URL)
  )
);

function firstDefined(...values) {
  for (const value of values) {
    if (typeof value !== "undefined") return value;
  }
  return "";
}

function normalizePrefix(value) {
  const raw = String(value || "").trim();
  if (!raw || raw === "/") return "";
  return `/${raw.replace(/^\/+|\/+$/g, "")}`;
}

function defaultAppPrefix(apiUrl) {
  try {
    const target = new URL(apiUrl);
    const basePath = target.pathname.replace(/\/+$/g, "");
    return basePath && basePath !== "/" ? "" : "/casehub";
  } catch (err) {
    return "/casehub";
  }
}

function bridgePath(suffix) {
  const cleanSuffix = `/${String(suffix || "").replace(/^\/+/g, "")}`;
  return `${CASEHUB_APP_PREFIX}${cleanSuffix}`;
}

/**
 * Build the inbound-message payload from a whatsapp-web.js message object.
 *
 * Media metadata (hasMedia/media_type/mime/filename) is forwarded so the
 * FastAPI backend can persist it in wa_messages and the frontend can render
 * the right bubble. The binary itself is NOT forwarded — payload stays tight;
 * the backend resolves the download from the bot if it needs the bytes.
 */
function buildPayload(data) {
  const fromRaw = (data && (data.from || data.author || "")).toString();
  const fromPhone = fromRaw.replace(/@.*$/, "");
  const hasMedia = !!(data && data.hasMedia);

  return {
    from_phone: fromPhone,
    message: (data && data.body) || "",
    media_type: (data && (data.mediaType || data.type)) || "text",
    // Identidade estável da mensagem no WhatsApp — dedup (wa_messages.wa_message_id).
    wa_message_id: (data && data.messageId) || null,
    has_media: hasMedia,
    media: hasMedia
      ? {
          type: (data && data.mediaType) || (data && data.type) || null,
          mimetype: (data && data.mimetype) || null,
          filename: (data && data.filename) || null,
          caption: (data && data.caption) || null,
        }
      : null,
    raw_payload: {
      from: fromRaw,
      type: data && data.type,
      timestamp: data && data.timestamp,
      hasMedia,
      from_me: !!(data && data.fromMe),
      // Keep payload tight - do not forward binary media or large objects.
      isGroup: !!(fromRaw && fromRaw.includes("@g.us")),
      // Identidade do contato — process_inbound le display_name/profile_pic_url
      // daqui e grava em wa_contacts.
      display_name: (data && data.name) || null,
      profile_pic_url: (data && data.profilePicUrl) || null,
      // Mídia — o binário foi baixado pelo server-lite e salvo em media/.
      // media_file é o nome do arquivo no bot; o backend monta a media_url
      // (rota proxy auth-gated) a partir dele. O binário NÃO trafega aqui.
      media_file: (data && data.media_file) || null,
      media_mime: (data && data.mimetype) || null,
      media_filename: (data && data.filename) || null,
      media_size: (data && data.media_size) || null,
      // OCR de PDF recebido (extraído pelo server-lite via pdf-parse).
      ocr_text: (data && data.ocr_text) || null,
    },
  };
}

/**
 * Build the message_ack payload from a whatsapp-client message_ack event.
 *
 * Shape (see whatsapp-client.js emit):
 *   { messageId, ack, status, to, fromMe, timestamp }
 */
function buildAckPayload(data) {
  return {
    type: "message_ack",
    wa_message_id: (data && data.messageId) || null,
    // ack numérico do whatsapp-web.js: -1 error, 0 pending, 1 sent,
    // 2 delivered, 3 read, 4 played.
    ack: data && typeof data.ack === "number" ? data.ack : null,
    // status textual já mapeado — alimenta direto wa_messages.status (ticks).
    status: (data && data.status) || "unknown",
    to_phone: (data && data.to) || "",
    from_me: !!(data && data.fromMe),
    timestamp: data && data.timestamp,
  };
}

function signPayload(bodyString, secret) {
  const ts = Math.floor(Date.now() / 1000);
  const signature = crypto
    .createHmac("sha256", secret)
    .update(`${ts}.${bodyString}`, "utf8")
    .digest("hex");
  return { ts, signature };
}

function postJson(url, bodyString, headers) {
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL(url);
    } catch (err) {
      return reject(err);
    }

    const lib = target.protocol === "https:" ? https : http;
    const req = lib.request(
      {
        hostname: target.hostname,
        port: target.port || (target.protocol === "https:" ? 443 : 80),
        path: target.pathname + (target.search || ""),
        method: "POST",
        headers,
        timeout: BRIDGE_TIMEOUT_MS,
      },
      (res) => {
        let chunks = "";
        res.on("data", (chunk) => (chunks += chunk.toString()));
        res.on("end", () => resolve({ status: res.statusCode, body: chunks }));
      }
    );
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("casehub-bridge timeout")));
    req.write(bodyString);
    req.end();
  });
}

/**
 * Sign + POST a payload object to a CaseHub endpoint path. Shared by both
 * forwarders so the HMAC scheme is identical (ts + hmac_sha256(secret, "ts.body")).
 *
 * Multi-tenant (F29): orgId flows through `X-Org-Id` so the FastAPI side
 * routes the inbound/ack to the right tenant without phone heuristics. The
 * header is OUTSIDE the signed body — replaying it across orgs would still
 * need a valid HMAC of the body, so no auth weakening.
 */
async function postSigned(pathName, payload, options) {
  const bodyString = JSON.stringify(payload);
  const { ts, signature } = signPayload(bodyString, HMAC_SECRET);
  const headers = {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(bodyString),
    "X-Casehub-Timestamp": ts.toString(),
    "X-Casehub-Signature": signature,
  };
  if (options && Number.isFinite(options.orgId) && options.orgId > 0) {
    headers["X-Org-Id"] = String(options.orgId);
  }

  const url = `${CASEHUB_API_URL.replace(/\/$/, "")}${pathName}`;
  try {
    const response = await postJson(url, bodyString, headers);
    if (response.status >= 200 && response.status < 300) {
      return { ok: true, status: response.status, body: response.body };
    }
    console.error(
      "[casehub-bridge] non-2xx response",
      response.status,
      (response.body || "").substring(0, 200)
    );
    return { ok: false, status: response.status, body: response.body };
  } catch (err) {
    console.error("[casehub-bridge] forward failed:", err.message);
    return { ok: false, error: err.message };
  }
}

/**
 * Forward an inbound message to CaseHub. Safe to fire-and-forget.
 *
 * Multi-tenant (F29): pass `{ orgId }` (or include `data.orgId`) so the
 * X-Org-Id header is set on the outbound POST. The FastAPI side uses it to
 * attribute the message to the right tenant deterministically (no phone
 * heuristics). When orgId is missing the FastAPI falls back to the legacy
 * heuristic — safe but ambiguous for 2+ orgs.
 *
 * Skips silently if:
 *   - bridge disabled by env
 *   - HMAC secret missing (treat as misconfiguration, not crash)
 *   - message is from a group chat (alpha is 1:1 only)
 *   - message body is empty AND no media (heartbeat / typing indicator)
 */
async function forwardInbound(data, options) {
  if (!BRIDGE_ENABLED) return { skipped: "bridge disabled" };

  if (!HMAC_SECRET) {
    console.warn("[casehub-bridge] CASEHUB_INBOUND_HMAC_SECRET not set; skipping forward");
    return { skipped: "no secret" };
  }

  const payload = buildPayload(data);
  if (payload.raw_payload && payload.raw_payload.isGroup) {
    return { skipped: "group" };
  }
  // Mensagem de mídia sem corpo de texto é válida — só pula se for vazia E sem mídia.
  if (!payload.message && !payload.has_media) {
    return { skipped: "empty text" };
  }

  // orgId pode vir em options.orgId (preferido) ou em data.orgId (emitido
  // pelo WhatsAppManager). Aceita ambos pra compat.
  const orgId = (options && Number.isFinite(options.orgId) && options.orgId)
    || (data && Number.isFinite(data.orgId) && data.orgId)
    || null;

  return postSigned(bridgePath("/whatsapp/inbound"), payload, orgId ? { orgId } : null);
}

/**
 * Forward a message_ack (delivery/read tick update) to CaseHub.
 * Safe to fire-and-forget. Same HMAC scheme as forwardInbound.
 *
 * Skips silently if:
 *   - bridge disabled by env
 *   - HMAC secret missing
 *   - no message id to correlate against (nothing the backend can update)
 */
async function forwardAck(data, options) {
  if (!BRIDGE_ENABLED) return { skipped: "bridge disabled" };

  if (!HMAC_SECRET) {
    console.warn("[casehub-bridge] CASEHUB_INBOUND_HMAC_SECRET not set; skipping ack forward");
    return { skipped: "no secret" };
  }

  const payload = buildAckPayload(data);
  if (!payload.wa_message_id) {
    return { skipped: "no message id" };
  }

  const orgId = (options && Number.isFinite(options.orgId) && options.orgId)
    || (data && Number.isFinite(data.orgId) && data.orgId)
    || null;

  return postSigned(bridgePath("/whatsapp/ack"), payload, orgId ? { orgId } : null);
}

/**
 * Bulk-upsert contact identity (display_name + profile photo) into CaseHub.
 * Fired on `ready` with the full 1:1 roster so avatars/names populate even for
 * contacts who never messaged since the wa_* tables existed. Same HMAC scheme.
 */
async function forwardContactsSync(contacts, options) {
  if (!BRIDGE_ENABLED) return { skipped: "bridge disabled" };
  if (!HMAC_SECRET) {
    console.warn("[casehub-bridge] CASEHUB_INBOUND_HMAC_SECRET not set; skipping contacts-sync");
    return { skipped: "no secret" };
  }
  const list = Array.isArray(contacts) ? contacts : [];
  if (!list.length) return { skipped: "no contacts" };
  const orgId = (options && Number.isFinite(options.orgId) && options.orgId) || null;
  return postSigned(bridgePath("/whatsapp/contacts-sync"), { contacts: list }, orgId ? { orgId } : null);
}

/**
 * Forward a session lifecycle event (currently: `disconnected`) to CaseHub so
 * the backend can raise an in-app alert. Fire-and-forget; same HMAC scheme.
 */
async function forwardEvent(event, options) {
  if (!BRIDGE_ENABLED) return { skipped: "bridge disabled" };
  if (!HMAC_SECRET) {
    console.warn("[casehub-bridge] CASEHUB_INBOUND_HMAC_SECRET not set; skipping event forward");
    return { skipped: "no secret" };
  }
  const payload = (event && typeof event === "object") ? event : { event: String(event || "") };
  const orgId = (options && Number.isFinite(options.orgId) && options.orgId) || null;
  return postSigned(bridgePath("/whatsapp/event"), payload, orgId ? { orgId } : null);
}

module.exports = {
  forwardInbound,
  forwardAck,
  forwardContactsSync,
  forwardEvent,
  // exported for tests
  _internal: {
    buildPayload,
    buildAckPayload,
    signPayload,
    normalizePrefix,
    defaultAppPrefix,
    bridgePath,
  },
};
