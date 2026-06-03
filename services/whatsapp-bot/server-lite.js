/**
 * server-lite.js — WhatsApp bridge minimo para o CaseHub alpha.
 *
 * Multi-session per-tenant (F29, v4.0 — 2026-05-27): em vez de uma unica
 * sessao whatsapp-web.js singleton, este server escuta o header `X-Org-Id`
 * em cada request e despacha para o Client correspondente via WhatsAppManager.
 * Quando o header esta ausente, cai pra org default (CASEHUB_DEFAULT_ORG_ID,
 * default 1) — comportamento legado preservado.
 *
 * Cada org recebe sua propria sessao isolada: QR proprio, numero proprio,
 * conversas isoladas. O LocalAuth do whatsapp-web.js armazena cada sessao
 * em ./.wwebjs_auth/session-org-<N>/ dentro do mesmo volume Docker.
 *
 * Diferente de server.js (legado ILC: Moskit/Stripe/Calendly/callhippo/intake US),
 * este server roda APENAS o subconjunto necessario para o alpha 25/05:
 *   - conexao whatsapp-web.js por tenant (QR pairing, sessao persistida)
 *   - forward de mensagens inbound para o FastAPI via casehub-bridge (HMAC + X-Org-Id)
 *   - forward de message_ack via casehub-bridge (HMAC + X-Org-Id)
 *
 * Alinhado com a estrategia hibrida C+B+B (decisoes 18/05): portar subconjunto
 * demonstravel, nao o subsistema legado completo. O bot e STATELESS — nao abre
 * conexao de banco; a persistencia (wa_contacts/wa_conversations/wa_messages)
 * fica no FastAPI/Postgres (WS-A), com tenant isolado pelo org_id.
 *
 * Endpoint contract (sem prefixo):
 *   GET  /api/status         — status da conexao (header X-Org-Id ou ?org_id)
 *   GET  /api/qr             — QR + status da sessao (rich payload, ver bug-fix 2026-05-28)
 *   GET  /qr                 — pagina HTML com o QR
 *   POST /api/pairing-code   — fallback de conexao por codigo
 *   POST /api/disconnect     — limpa sessao e reinicia (novo QR)
 *   POST /api/send-message   — dispara texto { phone, message }
 *   POST /api/send-media     — dispara midia (multipart)
 *   GET  /api/conversations  — lista conversas vivas da sessao
 *   GET  /api/messages/:phone — mensagens da conversa
 *   GET  /api/sessions       — admin: snapshot multi-tenant
 *   POST /api/sessions/:orgId/init — admin: forca init de uma sessao
 *   GET  /health             — health check (db em modo stateless)
 *
 * O FastAPI proxeia /casehub/whatsapp-api/* -> este server, sempre com
 * o header X-Org-Id setado a partir do tenant resolvido (TenantMiddleware).
 *
 * Env (config via .env ou docker-compose):
 *   PORT                          — porta HTTP (default 3001)
 *   CASEHUB_API_URL               — base do FastAPI (ex: http://casehub:8001)
 *   CASEHUB_INBOUND_HMAC_SECRET   — segredo HMAC compartilhado com o backend
 *   PUPPETEER_EXECUTABLE_PATH     — Chromium do sistema (setado no Dockerfile)
 *   CASEHUB_DEFAULT_ORG_ID        — org-id quando X-Org-Id estiver ausente (default 1)
 *   CASEHUB_AUTOSTART_ORGS        — CSV de orgs pra iniciar no boot (ex: "1,4"). default: "1"
 */
"use strict";

require("dotenv").config();

const express = require("express");
const fs = require("fs");
const path = require("path");
const multer = require("multer");
const { manager, DEFAULT_ORG_ID } = require("./whatsapp-client");
const { forwardInbound, forwardAck, forwardContactsSync, forwardEvent } = require("./casehub-bridge");

// media-handler e opcional — sem ele as rotas de midia degradam graciosamente.
let mediaHandler = null;
try {
  mediaHandler = require("./media-handler");
} catch (e) {
  console.warn("[server-lite] media-handler indisponivel:", e.message);
}

// Upload multipart pra /api/send-media. Tmp local; o binario sai pelo client.sendMedia.
const _mediaUploadDir = path.join(process.cwd(), "media", "tmp");
try { fs.mkdirSync(_mediaUploadDir, { recursive: true }); } catch (e) {}
const _mediaUpload = multer({
  dest: _mediaUploadDir,
  limits: { fileSize: 32 * 1024 * 1024 }, // 32 MB
});

const PORT = parseInt(process.env.PORT || "3001", 10);
const app = express();
app.use(express.json({ limit: "1mb" }));

// Per-tenant in-memory state. botControl/followup ficam por orgId pra
// nao vazar config entre tenants (mesmo sendo state efemero do bot).
const botControlState = new Map();   // Map<orgId, Map<phone, enabled>>
const followupState = new Map();     // Map<orgId, Map<phone, { marked, requestedAt }>>

function _tenantBucket(map, orgId) {
  let bucket = map.get(orgId);
  if (!bucket) {
    bucket = new Map();
    map.set(orgId, bucket);
  }
  return bucket;
}

function normalizePhone(value) {
  return String(value || "").replace(/\D/g, "");
}

// --- Tenant dispatch ------------------------------------------------------
/**
 * Resolve a org da request. Aceita:
 *   1. header X-Org-Id (primario; setado pelo FastAPI proxy)
 *   2. query string ?org_id=N (fallback debug/admin)
 *   3. body.org_id (fallback POST)
 *   4. CASEHUB_DEFAULT_ORG_ID (default 1)
 */
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

/**
 * Devolve (e cria, se necessario) o Client da org. Inicializa lazy: a primeira
 * chamada pra essa org dispara o boot do Puppeteer. Chamadas subsequentes
 * reusam o mesmo Client. Falha de init e propagada com 502 pelo handler.
 */
async function getClientFor(req) {
  const orgId = resolveOrgId(req);
  return manager.ensureInitialized(orgId);
}

// --- Payload helpers ------------------------------------------------------
function statusPayload(client) {
  const status = client.getStatus();
  const ready = Boolean(status.isReady);
  return {
    ...status,
    service: "whatsapp-bot-lite",
    ok: ready,
    connected: ready,
    isReady: ready,
    ready,
    status: status.status || (ready ? "ready" : "offline"),
    version: process.env.npm_package_version || "-",
    qr: client.getQrCode() || null,
    pairingCode: status.pairingCode || null,
  };
}

function normalizeLimit(value, fallback = 80, max = 200) {
  const parsed = Number(value || fallback);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.min(parsed, max));
}

// --- Health (multi-tenant snapshot) --------------------------------------
app.get("/health", async (_req, res) => {
  // /health responde pelo snapshot agregado — util pro probe do Docker.
  // Saudavel se ao menos uma sessao esta `ready` ou se nenhuma foi
  // iniciada (boot timing).
  const sessions = manager.snapshot();
  const anyReady = sessions.some((s) => s.isReady);
  res.status(sessions.length === 0 || anyReady ? 200 : 503).json({
    ok: anyReady || sessions.length === 0,
    service: "whatsapp-bot-lite",
    sessions,
    version: process.env.npm_package_version || "-",
  });
});

// /api/status — status da sessao da org corrente.
app.get("/api/status", async (req, res) => {
  try {
    const client = await getClientFor(req);
    res.json(statusPayload(client));
  } catch (err) {
    res.status(502).json({ ok: false, error: err.message });
  }
});

// /api/qr — QR + status da sessao da org corrente.
//
// Bug-fix 2026-05-28 (multitenant F29): o frontend
// (static/js/chat.js#loadQRCode) precisa de `connected`/`isReady`/`status`
// para distinguir tres cenarios que antes eram indistinguiveis (todos com
// qr=null):
//   (a) sessao da org JA esta autenticada -> nao precisa de QR
//   (b) sessao ainda bootando Puppeteer (cold start ~5-10s no primeiro
//       request de uma org que nao esta em CASEHUB_AUTOSTART_ORGS)
//   (c) erro real (Chromium nao subiu, WA Web inacessivel, etc.)
//
// Antes desta mudanca a response era apenas { qr, orgId } -> o else final
// do loadQRCode renderizava "QR indisponivel" em TODOS os tres casos,
// inclusive (a) e (b) — UX que aparecia para o cliente alpha (Vieira
// Salles) como "WhatsApp travado" mesmo quando estava so iniciando ou
// ja conectado em background.
//
// Reusa statusPayload(client) — mesma forma que /api/status. Frontend ja
// tem branches para data.connected; este patch faz esses branches realmente
// ativarem.
app.get("/api/qr", async (req, res) => {
  try {
    const client = await getClientFor(req);
    res.json({ ...statusPayload(client), orgId: client.orgId });
  } catch (err) {
    res.status(502).json({
      qr: null,
      orgId: null,
      connected: false,
      isReady: false,
      ready: false,
      status: "offline",
      ok: false,
      error: err.message,
    });
  }
});

// /qr — pagina HTML pra escanear (debug); usa a org default.
app.get("/qr", async (req, res) => {
  try {
    const client = await getClientFor(req);
    const status = client.getStatus();
    const qrCode = client.getQrCode();
    if (status.isReady) {
      res.send(`<html><body style='text-align:center;padding:50px;font-family:Arial'><h1>Conectado</h1><p>org-${client.orgId}</p></body></html>`);
    } else if (qrCode) {
      res.send(`<html><body style='text-align:center;padding:50px;font-family:Arial'><h1>QR (org-${client.orgId})</h1><img src='${qrCode}' style='max-width:300px'></body></html>`);
    } else {
      res.send("<html><head><meta http-equiv='refresh' content='3'></head><body style='text-align:center;padding:50px'><h2>Aguarde...</h2></body></html>");
    }
  } catch (err) {
    res.status(502).send(`<html><body><h1>Erro</h1><pre>${err.message}</pre></body></html>`);
  }
});

app.get("/api/conversations", async (req, res) => {
  try {
    const client = await getClientFor(req);
    const conversations = await client.listConversations({
      limit: normalizeLimit(req.query.limit, 80, 200),
      includeGroups: req.query.includeGroups === "1",
    });
    res.json(conversations);
  } catch (err) {
    try {
      const client = await getClientFor(req);
      const status = client.getStatus();
      const httpStatus = status.isReady ? 502 : 503;
      res.status(httpStatus).json({ ok: false, error: err.message, status: status.status });
    } catch (_) {
      res.status(502).json({ ok: false, error: err.message });
    }
  }
});

app.get("/api/messages/:phone", async (req, res) => {
  try {
    const client = await getClientFor(req);
    const messages = await client.getMessages(req.params.phone, {
      limit: normalizeLimit(req.query.limit, 100, 200),
    });
    res.json(messages);
  } catch (err) {
    try {
      const client = await getClientFor(req);
      const status = client.getStatus();
      const httpStatus = status.isReady ? 404 : 503;
      res.status(httpStatus).json({ ok: false, error: err.message, status: status.status });
    } catch (_) {
      res.status(502).json({ ok: false, error: err.message });
    }
  }
});

app.post("/api/send-media", _mediaUpload.single("file"), async (req, res) => {
  const phone = (req.body && req.body.phone ? String(req.body.phone) : "").trim();
  const caption = req.body && req.body.caption ? String(req.body.caption) : "";
  const file = req.file;
  if (!phone || !file) {
    if (file) {
      try { fs.unlinkSync(file.path); } catch (e) {}
    }
    return res.status(400).json({ ok: false, error: "phone and file required" });
  }
  if (!mediaHandler) {
    try { fs.unlinkSync(file.path); } catch (e) {}
    return res.status(503).json({ ok: false, error: "media-handler not available" });
  }
  try {
    const client = await getClientFor(req);
    // sendMedia legado: media-handler monta o MessageMedia + chama
    // client.sendMessage. Aqui passamos o raw whatsapp-web.js Client.
    const result = await mediaHandler.sendFile(
      client.getClient(),
      phone,
      file.path,
      caption,
      file.mimetype || null,
      file.originalname || file.filename || null,
    );
    res.json({
      ok: true,
      orgId: client.orgId,
      messageId:
        result && result.id && result.id._serialized
          ? result.id._serialized
          : null,
      media_file: result && result.media_file ? result.media_file : file.filename,
      mimetype: file.mimetype || null,
    });
  } catch (err) {
    console.error("[send-media]", err.message);
    try { fs.unlinkSync(file.path); } catch (e) {}
    res.status(502).json({ ok: false, error: err.message });
  }
});

app.post("/api/bot-control", (req, res) => {
  const phone = normalizePhone(req.body && req.body.phone);
  if (!phone) return res.status(400).json({ success: false, error: "phone required" });
  const orgId = resolveOrgId(req);
  const rawEnabled =
    req.body.botEnabled !== undefined ? req.body.botEnabled : req.body.enabled;
  const botEnabled =
    rawEnabled === true || rawEnabled === "true" || rawEnabled === 1 || rawEnabled === "1";
  _tenantBucket(botControlState, orgId).set(phone, botEnabled);
  res.json({ success: true, botEnabled, orgId });
});

app.post("/api/followup/mark", (req, res) => {
  const phone = normalizePhone(req.body && req.body.phone);
  if (!phone) return res.status(400).json({ success: false, error: "phone required" });
  const orgId = resolveOrgId(req);
  _tenantBucket(followupState, orgId).set(phone, { marked: true, requestedAt: new Date().toISOString() });
  res.json({ success: true, marked: true, orgId });
});

app.post("/api/followup/unmark", (req, res) => {
  const phone = normalizePhone(req.body && req.body.phone);
  if (!phone) return res.status(400).json({ success: false, error: "phone required" });
  const orgId = resolveOrgId(req);
  _tenantBucket(followupState, orgId).delete(phone);
  res.json({ success: true, marked: false, orgId });
});

app.get("/api/followup/check/:phone", (req, res) => {
  const orgId = resolveOrgId(req);
  const state = _tenantBucket(followupState, orgId).get(normalizePhone(req.params.phone));
  res.json({
    success: true,
    marked: !!state,
    requestedAt: state ? state.requestedAt : null,
    orgId,
  });
});

app.post("/pairing-code", async (req, res) => {
  const { phone } = req.body || {};
  if (!phone) {
    return res.status(400).json({ ok: false, success: false, error: "phone required" });
  }
  try {
    const client = await getClientFor(req);
    const code = await client.requestPairingCode(String(phone));
    res.json({
      ok: true,
      success: true,
      pairingCode: code,
      phone: String(phone).replace(/\D/g, ""),
      orgId: client.orgId,
      status: client.getStatus().status,
    });
  } catch (err) {
    res.status(502).json({
      ok: false,
      success: false,
      error: err && err.message ? err.message : "pairing code failed",
    });
  }
});

app.post("/api/pairing-code", async (req, res) => {
  const { phone } = req.body || {};
  if (!phone) {
    return res.status(400).json({ ok: false, success: false, error: "phone required" });
  }
  try {
    const client = await getClientFor(req);
    const code = await client.requestPairingCode(String(phone));
    res.json({
      ok: true,
      success: true,
      pairingCode: code,
      phone: String(phone).replace(/\D/g, ""),
      orgId: client.orgId,
      status: client.getStatus().status,
    });
  } catch (err) {
    res.status(502).json({
      ok: false,
      success: false,
      error: err && err.message ? err.message : "pairing code failed",
    });
  }
});

app.post("/api/disconnect", async (req, res) => {
  try {
    const client = await getClientFor(req);
    const b = req.body || {};
    const confirmWipe = b.confirm === "wipe" || b.confirm === true || b.wipe === true;
    if (confirmWipe) {
      // Re-pareamento EXPLICITO: apaga a sessao (backup-first dentro do clear) e
      // pede QR novo. So acontece com confirmacao deliberada.
      await client.clearAndReinitialize();
      return res.json({ ok: true, success: true, wiped: true, orgId: client.orgId, status: client.getStatus().status });
    }
    // PROFILAXIA (incidente 29/05): por padrao DESCONECTA sem apagar o pareamento.
    // Um clique acidental em "desconectar" nao destroi mais a sessao nem forca QR.
    await client.disconnect();
    return res.json({
      ok: true, success: true, wiped: false, preserved: true,
      orgId: client.orgId, status: client.getStatus().status,
      hint: "Sessao preservada. Para REPAREAR do zero (apaga e pede QR), repita com { confirm: 'wipe' }.",
    });
  } catch (err) {
    res.status(502).json({
      ok: false,
      success: false,
      error: err && err.message ? err.message : "disconnect failed",
    });
  }
});

// --- Send message (CaseHub Python -> bot) --------------------------------
async function sendMessageHandler(req, res) {
  const { phone, message } = req.body || {};
  if (!phone || !message) {
    return res.status(400).json({ error: "phone and message required" });
  }
  try {
    const client = await getClientFor(req);
    const replyTo = req.body.reply_to_wa_message_id || req.body.replyToWaMessageId || req.body.quotedMessageId;
    const options = replyTo ? { quotedMessageId: String(replyTo) } : undefined;
    const result = await client.sendMessage(String(phone), String(message), options);
    res.json({
      ok: true,
      orgId: client.orgId,
      messageId:
        result && result.id && result.id._serialized
          ? result.id._serialized
          : null,
    });
  } catch (err) {
    console.error("[send-message]", err.message);
    res.status(502).json({ ok: false, error: err.message });
  }
}

app.post("/api/send-message", sendMessageHandler);
app.post("/api/send", sendMessageHandler);

// --- Multi-session admin endpoints ---------------------------------------
// /api/sessions — snapshot agregado, util pra dashboards e debug.
app.get("/api/sessions", (_req, res) => {
  res.json({ sessions: manager.snapshot(), defaultOrgId: DEFAULT_ORG_ID });
});

// POST /api/sessions/:orgId/init — forca o boot de uma sessao especifica.
// Util quando o FastAPI tem 2 orgs e quer pre-aquecer a segunda antes do
// primeiro request do front (cold start de Puppeteer e lento).
app.post("/api/sessions/:orgId/init", async (req, res) => {
  const orgId = parseInt(req.params.orgId, 10);
  if (!Number.isFinite(orgId) || orgId <= 0) {
    return res.status(400).json({ ok: false, error: "invalid orgId" });
  }
  try {
    const client = await manager.ensureInitialized(orgId);
    res.json({ ok: true, orgId, status: client.getStatus().status });
  } catch (err) {
    res.status(502).json({ ok: false, error: err.message });
  }
});

// --- Inbound -> forward para CaseHub via HMAC bridge (com X-Org-Id) -------
// Manager re-emite eventos com {orgId} no ultimo arg. forwardInbound recebe
// orgId pra enviar o header X-Org-Id, que o FastAPI usa pra atribuir a msg
// a tenant correto (sem heuristica por telefone).
manager.on("message", async (data, meta) => {
  const orgId = meta && meta.orgId ? meta.orgId : (data && data.orgId);
  try {
    // Midia inbound: baixa o binario ANTES de encaminhar, para a bridge
    // mandar a media_url. Falha de download nao bloqueia o forward — degrada
    // para metadados so (balao sem preview), nunca derruba a ingestao.
    if (mediaHandler && data && data.hasMedia && data.message) {
      try {
        const saved = await mediaHandler.downloadAndSaveMedia(
          data.message,
          data.from || ""
        );
        if (saved && saved.success) {
          data.media_file = saved.filename;
          data.media_size = saved.size;
          if (!data.mimetype) data.mimetype = saved.mimetype;
          // OCR: PDF recebido -> extrai o texto para o clone exibir/buscar.
          const baseMime = (saved.mimetype || "").split(";")[0].trim();
          if (baseMime === "application/pdf") {
            const ocr = await mediaHandler.extractPdfText(saved.filePath);
            if (ocr) data.ocr_text = ocr;
          }
        } else {
          console.warn("[media] download inbound falhou:", saved && saved.error);
        }
      } catch (mErr) {
        console.error("[media] erro no download inbound:", mErr.message);
      }
    }
    const result = await forwardInbound(data, { orgId });
    if (result && result.skipped) {
      console.log(`[bridge][org-${orgId}] skipped:`, result.skipped);
    } else if (result && result.ok) {
      console.log(`[bridge][org-${orgId}] forwarded ->`, result.status);
    } else {
      console.warn(`[bridge][org-${orgId}] forward not ok:`, JSON.stringify(result).slice(0, 200));
    }
  } catch (err) {
    console.error(`[bridge][org-${orgId}] error:`, err.message);
  }
});

// --- message_ack -> forward dos ticks para CaseHub via HMAC bridge --------
manager.on("message_ack", async (data, meta) => {
  const orgId = meta && meta.orgId ? meta.orgId : (data && data.orgId);
  try {
    const result = await forwardAck(data, { orgId });
    if (result && result.skipped) {
      console.log(`[bridge][org-${orgId}] ack skipped:`, result.skipped);
    } else if (result && result.ok) {
      console.log(`[bridge][org-${orgId}] ack forwarded ->`, data.status);
    } else {
      console.warn(`[bridge][org-${orgId}] ack forward not ok:`, JSON.stringify(result).slice(0, 200));
    }
  } catch (err) {
    console.error(`[bridge][org-${orgId}] ack error:`, err.message);
  }
});

// Eventos informativos por sessao — facilitam triage de logs multi-tenant.
manager.on("qr", (_qr, meta) => console.log(`[QR][org-${meta && meta.orgId}] novo QR — escaneie via /api/qr ou /qr`));
// READY: sessao viva. (1) snapshot recuperavel da sessao recem-pareada;
// (2) sync de fotos/nomes de TODOS os contatos 1:1 para o backend. Best-effort
// e fora do hot-path — uma falha aqui jamais derruba a sessao.
manager.on("ready", async (_v, meta) => {
  const orgId = meta && meta.orgId;
  console.log(`[WA][org-${orgId}] cliente pronto`);
  if (!orgId) return;
  try {
    const client = manager.getOrCreate(orgId);
    if (client && typeof client.backupSession === "function") client.backupSession();
    if (client && typeof client.syncProfilePhotos === "function") {
      const contacts = await client.syncProfilePhotos();
      if (contacts.length) {
        const res = await forwardContactsSync(contacts, { orgId });
        console.log(`[WA][org-${orgId}] profile-sync: ${contacts.length} contatos`, res && (res.skipped || res.status || "ok"));
      }
    }
  } catch (e) {
    console.warn(`[WA][org-${orgId}] profile-sync/backup falhou:`, e && e.message ? e.message : e);
  }
});
manager.on("authenticated", (_v, meta) => console.log(`[WA][org-${meta && meta.orgId}] autenticado`));
// DISCONNECTED: alerta o backend para gerar notificacao in-app urgente, assim
// uma queda de sessao nunca mais passa despercebida. Fire-and-forget.
manager.on("disconnected", async (r, meta) => {
  const orgId = meta && meta.orgId;
  console.warn(`[WA][org-${orgId}] desconectado:`, r);
  if (!orgId) return;
  try {
    await forwardEvent({ event: "disconnected", reason: String(r == null ? "" : r) }, { orgId });
  } catch (e) {
    console.warn(`[WA][org-${orgId}] alerta de disconnect falhou:`, e && e.message ? e.message : e);
  }
});
manager.on("auth_failure", (e, meta) => console.error(`[WA][org-${meta && meta.orgId}] auth_failure:`, e));

// --- Boot -----------------------------------------------------------------
process.on("unhandledRejection", (err) => {
  console.error("[unhandledRejection]", err && err.message ? err.message : err);
});

// Autostart: inicia sessoes ao subir. Default = so a org default (1).
// CASEHUB_AUTOSTART_ORGS="1,4" pra alpha onde queremos ambos quentes.
const autostart = (process.env.CASEHUB_AUTOSTART_ORGS || String(DEFAULT_ORG_ID))
  .split(",")
  .map((s) => parseInt(s.trim(), 10))
  .filter((n) => Number.isFinite(n) && n > 0);

// Boot loop e o listen sao gated por NODE_ENV=test pra que tests podem
// importar o app sem subir Puppeteer (cold start) nem ocupar a porta.
if (process.env.NODE_ENV !== "test") {
  (async () => {
    for (const orgId of autostart) {
      try {
        console.log(`[boot] inicializando org-${orgId}...`);
        await manager.ensureInitialized(orgId);
      } catch (err) {
        console.error(`[boot] falha ao inicializar org-${orgId}:`, err.message);
      }
    }
  })();

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[server-lite] WhatsApp bridge ouvindo na porta ${PORT} (multi-session)`);
    console.log(`[server-lite] autostart orgs: ${autostart.join(", ") || "(none)"}`);
  });
}

// Export pra testes — server-lite nao e tipicamente importado, mas o
// resolveOrgId/normalizePhone sao tested em isolation.
module.exports = {
  app,
  resolveOrgId,
  normalizePhone,
  _tenantBucket,
  manager,
};
