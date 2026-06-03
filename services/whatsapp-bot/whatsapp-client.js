/**
 * WhatsApp Client + Manager - whatsapp-web.js
 * CaseHub
 * v4.0 - Multi-session per-tenant (F29)
 *
 * Mudanca v4.0 (2026-05-27): a classe deixou de ser singleton no module.exports.
 * Agora cada tenant tem seu proprio Client (LocalAuth com clientId = "org-<N>"),
 * orquestrado pelo WhatsAppManager. Compat default: getOrCreate(1) reproduz o
 * comportamento single-org anterior, e module.exports continua expondo um
 * proxy "manager" + um shim "default" que mapeia chamadas legadas para
 * manager.getOrCreate(DEFAULT_ORG_ID).
 *
 * Por que multi-session: tenant alpha (cliente.example.com) compartilhava
 * a sessao WhatsApp da org "default" — qualquer um logado em qualquer tenant
 * via as mesmas conversas. Cada org agora tem QR/numero proprio, isolado.
 *
 * v3.2 (legado) - Fix QR Authentication Loop + webpack-exodus compatibility
 */
const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const QRCode = require("qrcode");
const EventEmitter = require("events");
const fs = require("fs");
const path = require("path");

// ID da org que assume o comportamento legado single-tenant quando nada
// (header X-Org-Id, dispatch) for passado. ENV opcional: CASEHUB_DEFAULT_ORG_ID.
const DEFAULT_ORG_ID = parseInt(process.env.CASEHUB_DEFAULT_ORG_ID || "1", 10);

// QR Cooldown por sessao (Map orgId -> last timestamp). Evita loop de
// regeneracao quando um QR e re-emitido em rapida sucessao por uma instancia.
const QR_COOLDOWN = 5000; // 5 segundos entre QR codes
const _lastQrTimes = new Map();

// Mapa do ack numerico do whatsapp-web.js -> status textual usado no clone.
// Espelha os ticks do WhatsApp Web: enviado (1 tick), entregue (2 ticks),
// lido/played (2 ticks azuis).
const ACK_STATUS_MAP = {
  "-1": "failed",
  0: "pending",
  1: "sent",
  2: "delivered",
  3: "read",
  4: "played"
};

class WhatsAppClient extends EventEmitter {
  /**
   * @param {Object} [options]
   * @param {number} [options.orgId] - tenant id; usado como clientId do LocalAuth.
   *     Quando omitido, cai pra DEFAULT_ORG_ID (compat single-org).
   * @param {string} [options.dataBase] - diretorio raiz do auth (default ./.wwebjs_auth).
   *     Cada org ganha um subdiretorio "session-org-<id>" via LocalAuth.clientId.
   */
  constructor(options = {}) {
    super();
    this.orgId = Number.isFinite(options.orgId) ? options.orgId : DEFAULT_ORG_ID;
    this.dataBase = options.dataBase || "./.wwebjs_auth";
    this.logPrefix = `[org-${this.orgId}]`;
    this.client = null;
    this.isReady = false;
    this.qrCode = null;
    this.qrTimestamp = null;
    this.status = "disconnected";
    this.lidCache = new Map();
    this.pairingCode = null;
    this.pairingPhoneNumber = null;
    this.connectionState = null;   // ultimo estado real (change_state / getState)
    this._healthTimer = null;      // monitor de saude da sessao
    this._reconnecting = false;    // guarda contra reconnect concorrente
  }

  _log(...args) {
    console.log(this.logPrefix, ...args);
  }

  _warn(...args) {
    console.warn(this.logPrefix, ...args);
  }

  _error(...args) {
    console.error(this.logPrefix, ...args);
  }

  async initialize(phoneNumber = null) {
    this._log("[INIT] WhatsApp Client v4.0 (multi-session)");

    // Auto-cura: se a sessao sumiu mas ha backup __lastgood, restaura o
    // pareamento ANTES do LocalAuth carregar (so no boot, so sem re-pair).
    if (!phoneNumber) this._restoreFromBackupOnBoot();

    // Limpa locks Singleton orfaos do Chromium antes de subir o browser.
    // LocalAuth persiste o profile num volume Docker; ao recriar o container
    // o profile herda um SingletonLock apontando pro hostname do container
    // morto => o novo Chromium recusa ("profile in use", Code 21) e o QR
    // nunca aparece. Remover os locks (preservando a sessao) cura o launch.
    this._clearChromiumLocks();

    // Build client options with fixes for QR authentication loop
    const clientOptions = {
      // clientId isola a sessao por org dentro do MESMO dataPath. O LocalAuth
      // cria <dataBase>/session-<clientId> automaticamente — perfeito pra
      // manter um unico volume Docker (whatsapp_session) com subpastas por org.
      authStrategy: new LocalAuth({
        clientId: `org-${this.orgId}`,
        dataPath: this.dataBase,
      }),

      // webVersionCache REMOVIDO 2026-05-21 (audit do QR): o pin remoto apontava
      // para uma versao ANTIGA do WhatsApp Web (2.3000.1032473763-alpha, era do
      // legado ILC). Versao velha => WhatsApp forca atualizacao / whatsapp-web.js
      // nao carrega a pagina => o evento 'qr' nunca dispara => QR "indisponivel"
      // pra sempre. Sem pin, whatsapp-web.js usa a versao corrente do WA Web.

      puppeteer: {
        headless: true,
        // NOVO: usa o Chromium do sistema dentro do container Docker.
        // Sem isto o Puppeteer tenta achar/baixar o próprio binário e
        // falha no container (PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true).
        // Fora do container (dev local) a env fica vazia → Puppeteer usa o bundled.
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
        // userDataDir explicito por org pra duas instancias Chromium nao
        // brigarem pelo mesmo profile. LocalAuth ja faz isso via clientId,
        // mas formalizar evita surpresa quando o profile e re-aproveitado.
        args: [
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-dev-shm-usage",
          "--disable-accelerated-2d-canvas",
          "--no-first-run",
          "--no-zygote",
          "--disable-gpu",
          // --single-process REMOVIDO 2026-05-21 (audit de conexao): com o
          // Puppeteer, renderer e browser no mesmo processo -> um hang do
          // renderer congela a pagina do WhatsApp Web inteira; a sessao morre
          // sem emitir 'disconnected' (o "conectado fantasma"). Sem a flag,
          // o renderer roda isolado e um travamento nao derruba tudo.
          "--disable-background-timer-throttling",
          "--disable-backgrounding-occluded-windows",
          "--disable-renderer-backgrounding"
        ],
        // NOVO: timeout estendido para conexões lentas
        protocolTimeout: 300000
      }
    };

    // If phone number is provided, use pairing code instead of QR
    if (phoneNumber) {
      const cleanPhone = phoneNumber.replace(/\D/g, "");
      this._log("[INIT] Using pairing code for:", cleanPhone);
      clientOptions.pairWithPhoneNumber = {
        phoneNumber: cleanPhone
      };
      this.pairingPhoneNumber = cleanPhone;
    }

    this.client = new Client(clientOptions);

    // QR code event com cooldown para evitar loop de regeneração (por org).
    this.client.on("qr", async (qr) => {
      const now = Date.now();
      const last = _lastQrTimes.get(this.orgId) || 0;
      if (now - last < QR_COOLDOWN) {
        this._log("[QR] Cooldown ativo, ignorando regeneracao rapida");
        return;
      }
      _lastQrTimes.set(this.orgId, now);

      this._log("[QR] Escaneie com o WhatsApp:");
      qrcode.generate(qr, { small: true });
      this.qrCode = await QRCode.toDataURL(qr);
      this.qrTimestamp = Date.now();
      this.status = "awaiting_scan";
      this.emit("qr", this.qrCode);
    });

    // Pairing code event - triggered when using pairWithPhoneNumber
    this.client.on("code", (code) => {
      this._log("[PAIRING] Code received:", code);
      this.pairingCode = code;
      this.status = "awaiting_pairing";
      this.emit("code", code);
    });

    this.client.on("authenticated", () => {
      this._log("[AUTH] Autenticado!");
      this.status = "authenticated";
      this.emit("authenticated");

      // Timeout para verificar se READY dispara em 60s
      this._readyTimeout = setTimeout(() => {
        if (!this.isReady) {
          // PROFILAXIA: um READY lento (Mumbai/WhatsApp Web/rede transiente) NAO
          // pode mais apagar a sessao pareada. softReconnect PRESERVA a sessao e
          // tenta de novo; se persistir, vira loop de reconnect (preservando) +
          // o alerta de disconnect ja dispara — nunca um wipe silencioso.
          this._warn("[WARN] READY timeout apos 60s - soft reconnect (preserva a sessao)...");
          this.softReconnect();
        }
      }, 60000);
    });

    this.client.on("ready", () => {
      this._log("[READY] WhatsApp conectado!");
      if (this._readyTimeout) clearTimeout(this._readyTimeout);
      this.isReady = true;
      this.qrCode = null;
      this.qrTimestamp = null;
      this.status = "ready";
      this.emit("ready");
    });

    this.client.on("message", async (message) => {
      if (message.from.includes("@g.us") || message.fromMe || message.from === "status@broadcast") return;

      let phoneNumber = message.from;
      let realPhone = null;

      if (message.from.includes("@lid")) {
        const lidId = message.from.replace("@lid", "");
        this._log("[LID] Mensagem de LID:", lidId);

        if (this.lidCache.has(lidId)) {
          realPhone = (this.lidCache.get(lidId) || "").replace(/@c\.us/g, "");
          phoneNumber = realPhone + "@c.us";
          this._log("[CACHE] Numero:", realPhone);
        } else {
          // Metodo 1: getContactLidAndPhone
          try {
            const result = await this.client.getContactLidAndPhone([message.from]);
            this._log("[LID-RESOLVE] Result:", JSON.stringify(result));
            if (result && result.length > 0 && result[0].pn) {
              realPhone = (result[0].pn || "").replace(/@c\.us/g, "");
              phoneNumber = realPhone + "@c.us";
              this.lidCache.set(lidId, realPhone);
              this._log("[LID-RESOLVE] Numero:", realPhone);
            }
          } catch (e) { this._log("[LID-RESOLVE] Erro:", e.message); }

          // Metodo 2: getContact
          if (!realPhone) {
            try {
              const contact = await message.getContact();
              if (contact && contact.number) {
                realPhone = (contact.number || "").replace(/@c\.us/g, "");
                phoneNumber = realPhone + "@c.us";
                this.lidCache.set(lidId, realPhone);
                this._log("[CONTACT] Numero:", realPhone);
              } else if (contact && contact.id && contact.id.user && !contact.id.user.includes("lid")) {
                realPhone = (contact.id.user || "").replace(/@c\.us|@lid/g, "");
                phoneNumber = realPhone + "@c.us";
                this.lidCache.set(lidId, realPhone);
                this._log("[CONTACT-ID] Numero:", realPhone);
              }
            } catch (e2) { this._log("[CONTACT] Erro:", e2.message); }
          }

          // Metodo 3: getChat
          if (!realPhone) {
            try {
              const chat = await message.getChat();
              if (chat && chat.id && chat.id.user && !chat.id.user.includes("lid")) {
                realPhone = (chat.id.user || "").replace(/@c\.us|@lid/g, "");
                phoneNumber = realPhone + "@c.us";
                this.lidCache.set(lidId, realPhone);
                this._log("[CHAT] Numero:", realPhone);
              }
            } catch (e3) { this._log("[CHAT] Erro:", e3.message); }
          }
        }

        if (!realPhone) this._warn("[WARN] LID nao resolvido:", message.from);
      }

      this._log("[MSG] De " + phoneNumber + ": " + (message.body || "").substring(0, 50));

      // Metadados de mídia — o frontend (clone WhatsApp Web) precisa disto
      // para renderizar imagem/vídeo/áudio/documento. Não baixamos o binário
      // aqui (payload enxuto); o backend FastAPI resolve o download se quiser.
      const hasMedia = !!message.hasMedia;

      // Nome + foto do contato — alimentam wa_contacts.display_name /
      // profile_pic_url no backend. notifyName vem de graca no objeto;
      // getContact e a foto sao best-effort (chamada extra, pode falhar
      // em contato LID — segue sem quebrar o inbound).
      let contactName = (message._data && message._data.notifyName) || null;
      let profilePicUrl = null;
      try {
        const contact = await message.getContact();
        if (contact) {
          contactName = contact.pushname || contact.name || contactName;
          try {
            profilePicUrl = (await contact.getProfilePicUrl()) || null;
          } catch (_) { /* contato sem foto ou inacessivel */ }
        }
      } catch (_) { /* segue so com notifyName */ }

      // #17 — foto de contato LID: getProfilePicUrl falha no JID @lid. Quando
      // o telefone real foi resolvido (bloco LID acima), tenta de novo com o
      // JID @c.us, que o whatsapp-web.js aceita.
      if (!profilePicUrl && realPhone) {
        try {
          profilePicUrl =
            (await this.client.getProfilePicUrl(realPhone + "@c.us")) || null;
          if (profilePicUrl) this._log("[LID-FOTO] resolvida via", realPhone);
        } catch (_) { /* contato sem foto ou inacessivel */ }
      }

      this.emit("message", {
        // orgId emitido junto pra bridge encaminhar com X-Org-Id correto.
        orgId: this.orgId,
        from: phoneNumber,
        body: message.body || "",
        timestamp: message.timestamp,
        type: message.type,
        message: message,
        realPhone: realPhone,
        originalId: message.from,
        // ID estável da mensagem no WhatsApp — usado para dedup (wa_message_id)
        // e como alvo dos eventos message_ack subsequentes.
        messageId: message.id && message.id._serialized ? message.id._serialized : null,
        fromMe: !!message.fromMe,
        // --- metadados de mídia ---
        hasMedia,
        mediaType: hasMedia ? (message.type || null) : null,
        mimetype: (hasMedia && message._data && message._data.mimetype) || null,
        filename:
          (hasMedia &&
            (message._data && (message._data.filename || message._data.caption))) ||
          null,
        caption: hasMedia ? (message.body || null) : null,
        // Identidade do contato (alimenta wa_contacts no backend).
        name: contactName,
        profilePicUrl: profilePicUrl
      });
    });

    // message_ack — evolução do status de entrega/leitura de mensagens
    // enviadas. whatsapp-web.js emite ack: -1 ERROR, 0 PENDING, 1 SERVER (enviado),
    // 2 DEVICE (entregue), 3 READ (lido), 4 PLAYED (áudio ouvido).
    // O frontend usa isto para renderizar os ticks (cinza/duplo/azul).
    this.client.on("message_ack", (message, ack) => {
      try {
        const messageId =
          message && message.id && message.id._serialized
            ? message.id._serialized
            : null;
        const toRaw = (message && (message.to || message.from) || "").toString();
        const status = ACK_STATUS_MAP[ack] || "unknown";
        this._log(`[ACK] ${messageId || "?"} -> ${status} (${ack})`);
        this.emit("message_ack", {
          orgId: this.orgId,
          messageId,
          ack,
          status,
          to: toRaw.replace(/@.*$/, ""),
          fromMe: !!(message && message.fromMe),
          timestamp: message && message.timestamp
        });
      } catch (e) {
        this._log("[ACK] erro ao processar ack:", e.message);
      }
    });

    this.client.on("disconnected", (reason) => {
      this._log("[DISCONNECT]", reason);
      this.isReady = false;
      this.status = "disconnected";
      this.connectionState = "DISCONNECTED";
      this.emit("disconnected", reason);
    });

    // change_state — estado real da conexao reportado pelo whatsapp-web.js.
    // CONNECTED = sessao viva; qualquer outro (TIMEOUT/CONFLICT/UNPAIRED/...)
    // = caiu. Mantem isReady sincronizado com a verdade, em tempo real.
    this.client.on("change_state", (state) => {
      this._log("[STATE]", state);
      this.connectionState = state;
      if (state === "CONNECTED") {
        this.isReady = true;
        this.status = "ready";
      } else {
        this.isReady = false;
        if (this.status === "ready") this.status = "disconnected";
      }
    });

    this.client.on("auth_failure", (error) => {
      this._error("[AUTH-FAIL]", error);
      this.status = "auth_failed";
      this.emit("auth_failure", error);
    });

    await this.client.initialize();
    this._startHealthMonitor();
  }

  // Remove locks Singleton* orfaos do Chromium sob ./.wwebjs_auth. O Chromium
  // os cria e, num volume Docker persistido, eles sobrevivem ao container ->
  // bloqueiam o proximo launch ("profile in use"). Seguro remover: nao apaga
  // a sessao do WhatsApp, so os arquivos de lock.
  //
  // Multi-session: removemos apenas os locks DA NOSSA org (session-org-<id>/),
  // nao do volume inteiro. Senao um Client subindo zera locks de outras orgs
  // que estao online e quebra elas sem motivo.
  _clearChromiumLocks() {
    const sessionDir = path.join(
      process.cwd(),
      this.dataBase.replace(/^\.\//, ""),
      `session-org-${this.orgId}`
    );
    if (!fs.existsSync(sessionDir)) return;
    const LOCKS = new Set(["SingletonLock", "SingletonSocket", "SingletonCookie"]);
    const walk = (dir) => {
      let entries;
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
      catch (e) { return; }
      for (const ent of entries) {
        const full = path.join(dir, ent.name);
        if (LOCKS.has(ent.name)) {
          try { fs.rmSync(full, { force: true }); this._log("[INIT] lock Chromium removido:", ent.name); }
          catch (e) { this._log("[INIT] erro removendo lock:", e.message); }
        } else if (ent.isDirectory()) {
          walk(full);
        }
      }
    };
    walk(sessionDir);
  }

  getClient() { return this.client; }

  // Enumera os contatos 1:1 da sessao e resolve nome + foto de perfil de cada
  // um. Chamado no evento `ready` (server-lite) para popular avatares/nomes de
  // TODOS os contatos — inclusive os que nao mandaram mensagem desde que as
  // tabelas wa_* passaram a existir. Sequencial de proposito: o getProfilePicUrl
  // bate no servidor do WhatsApp e disparar em paralelo arrisca rate-limit.
  async syncProfilePhotos(options = {}) {
    this.assertReady();
    const limit = Math.max(1, Math.min(Number(options.limit || 500), 1000));
    const chats = (await this.client.getChats())
      .filter((chat) => !chat.isGroup)
      .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0))
      .slice(0, limit);
    const out = [];
    for (const chat of chats) {
      const phone = this.phoneFromChatId(this.normalizeChatId(chat.id));
      if (!phone || phone.endsWith("@lid")) continue; // sem telefone real => pula
      let displayName = chat.name || null;
      let profilePicUrl = null;
      let isBusiness = false;
      try {
        const contact = await chat.getContact();
        if (contact) {
          displayName = contact.pushname || contact.name || displayName;
          isBusiness = Boolean(contact.isBusiness);
          try { profilePicUrl = (await contact.getProfilePicUrl()) || null; }
          catch (_) { /* contato sem foto ou privado */ }
        }
      } catch (_) { /* segue so com chat.name */ }
      out.push({
        phone,
        display_name: displayName,
        profile_pic_url: profilePicUrl,
        is_business: isBusiness,
      });
    }
    return out;
  }

  // Snapshot atomico-ish da sessao recem-pareada num diretorio irmao que o
  // LocalAuth NUNCA enxerga (prefixo "_bak-", nao "session-"). Permite recuperar
  // de um reset acidental sem reescanear o QR. Best-effort: nunca lanca. O
  // tmp+rename evita corromper o ultimo backup bom se o copy morrer no meio.
  // Caminho do dir de sessao da org corrente.
  _sessionDir() {
    return path.join(this.dataBase, `session-org-${this.orgId}`);
  }

  // true se o dir de sessao existe E tem conteudo (pareamento plausivel).
  _sessionLooksPresent() {
    try {
      const d = this._sessionDir();
      return fs.existsSync(d) && fs.readdirSync(d).length > 0;
    } catch (_) { return false; }
  }

  // Snapshot atomico-ish da sessao corrente num dir irmao que o LocalAuth IGNORA
  // (prefixo "_bak-", nao "session-"). `suffix` escolhe o slot: "__lastgood"
  // (on-ready) ou "__prewipe" (antes de um wipe intencional). O tmp+rename evita
  // corromper o ultimo backup bom se o copy morrer no meio. Best-effort: nunca lanca.
  _snapshotSession(suffix) {
    try {
      const src = this._sessionDir();
      if (!fs.existsSync(src)) return false;
      const dst = path.join(this.dataBase, `_bak-session-org-${this.orgId}${suffix}`);
      const tmp = `${dst}.tmp`;
      fs.rmSync(tmp, { recursive: true, force: true });
      fs.cpSync(src, tmp, { recursive: true, force: true });
      fs.rmSync(dst, { recursive: true, force: true });
      fs.renameSync(tmp, dst);
      this._log(`[BACKUP] snapshot da sessao em ${dst}`);
      return true;
    } catch (e) {
      this._warn("[BACKUP] snapshot falhou (best-effort):", e && e.message ? e.message : e);
      return false;
    }
  }

  // Backup da sessao recem-pareada (chamado no evento `ready`).
  backupSession() { return this._snapshotSession("__lastgood"); }

  // AUTO-CURA no boot: se a sessao sumiu/esvaziou (volume perdido, ou wipe
  // acidental enquanto o bot estava fora) MAS existe um backup __lastgood,
  // restaura o pareamento ANTES do LocalAuth carregar — evita exigir um QR novo.
  // So roda no PRIMEIRO initialize do processo (flag _bootRestoreTried) e so
  // quando NAO e um pareamento explicito: nunca desfaz um clearAndReinitialize
  // ou re-pair, que acontecem depois do boot. Idempotente e sem loop.
  _restoreFromBackupOnBoot() {
    if (this._bootRestoreTried) return false;
    this._bootRestoreTried = true;
    try {
      if (this._sessionLooksPresent()) return false;              // sessao ja esta la
      const bak = path.join(this.dataBase, `_bak-session-org-${this.orgId}__lastgood`);
      if (!fs.existsSync(bak) || fs.readdirSync(bak).length === 0) return false;
      const dst = this._sessionDir();
      fs.rmSync(dst, { recursive: true, force: true });
      fs.cpSync(bak, dst, { recursive: true, force: true });
      this._warn("[RESTORE] sessao ausente no boot — restaurada do backup __lastgood (auto-cura, sem QR)");
      return true;
    } catch (e) {
      this._warn("[RESTORE] auto-cura falhou (segue p/ QR):", e && e.message ? e.message : e);
      return false;
    }
  }

  assertReady() {
    if (!this.client || !this.isReady) {
      throw new Error(`WhatsApp nao conectado (org=${this.orgId})`);
    }
  }

  normalizeChatId(value) {
    if (!value) return "";
    if (typeof value === "string") return value;
    return value._serialized || value.user || "";
  }

  phoneFromChatId(value) {
    const id = this.normalizeChatId(value);
    if (!id) return "";
    if (id.endsWith("@c.us")) return id.replace("@c.us", "");
    if (id.endsWith("@lid")) return id.replace("@lid", "@lid");
    return id;
  }

  // Resolve um JID "<lid>@lid" para o telefone real, reusando o lidCache + os
  // metodos que o handler de inbound (message) ja usa. Sem isto, ler mensagens
  // de uma conversa keyed por LID falha (getChatById nao acha o JID errado).
  async _resolvePhoneFromLid(lidJid) {
    const lidId = String(lidJid).replace("@lid", "");
    if (this.lidCache.has(lidId)) return this.lidCache.get(lidId);
    try {
      const result = await this.client.getContactLidAndPhone([lidJid]);
      if (result && result.length > 0 && result[0].pn) {
        const realPhone = (result[0].pn || "").replace(/@c\.us/g, "").replace(/\D/g, "");
        if (realPhone) { this.lidCache.set(lidId, realPhone); return realPhone; }
      }
    } catch (e) { this._log("[LID-READ] resolve falhou:", e.message); }
    return null;
  }

  isoFromTimestamp(value) {
    const ts = Number(value || 0);
    if (!ts) return new Date().toISOString();
    return new Date(ts * 1000).toISOString();
  }

  messagePayload(message, fallbackPhone = "") {
    const fromMe = Boolean(message.fromMe);
    const peer = fromMe ? (message.to || fallbackPhone) : (message.from || fallbackPhone);
    const phone = this.phoneFromChatId(peer) || this.phoneFromChatId(fallbackPhone);
    return {
      id: this.normalizeChatId(message.id) || `${phone}-${message.timestamp || Date.now()}`,
      wid: this.normalizeChatId(message.id),
      phone,
      role: fromMe ? "assistant" : "user",
      content: message.body || message.caption || "",
      created_at: this.isoFromTimestamp(message.timestamp),
      ack: typeof message.ack === "number" ? message.ack : null,
      from_bot: fromMe ? 1 : 0,
      hasMedia: Boolean(message.hasMedia),
      media_type: message.type || null,
      source: "whatsapp-web",
    };
  }

  async listConversations(options = {}) {
    this.assertReady();
    const limit = Math.max(1, Math.min(Number(options.limit || 80), 200));
    const includeGroups = Boolean(options.includeGroups);
    const chats = await this.client.getChats();
    return chats
      .filter((chat) => includeGroups || !chat.isGroup)
      .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0))
      .slice(0, limit)
      .map((chat) => {
        const chatId = this.normalizeChatId(chat.id);
        const phone = this.phoneFromChatId(chatId);
        const last = chat.lastMessage || null;
        return {
          phone,
          jid: chatId,
          name: chat.name || phone,
          whatsapp_name: chat.name || phone,
          lastMessage: last ? (last.body || last.caption || "") : "",
          lastMessageTime: this.isoFromTimestamp((last && last.timestamp) || chat.timestamp),
          updated_at: this.isoFromTimestamp((last && last.timestamp) || chat.timestamp),
          unread: Number(chat.unreadCount || 0),
          from_bot: last && last.fromMe ? 1 : 0,
          bot_enabled: true,
          human_takeover: false,
          never_contact: false,
          messageCount: Number(chat.unreadCount || 0),
          source: "whatsapp-web",
        };
      });
  }

  async getMessages(phone, options = {}) {
    this.assertReady();
    const limit = Math.max(1, Math.min(Number(options.limit || 100), 200));
    const raw = String(phone || "").trim();
    const candidates = [];
    // Conversa keyed por LID ("123@lid"): os digitos sao o LID, NAO o telefone —
    // reconstruir "<digits>@c.us" gera um JID errado. Tenta o @lid cru (getChatById
    // aceita), depois resolve LID->telefone reusando o lidCache do inbound.
    if (raw.includes("@lid")) {
      candidates.push(raw);
      const resolved = await this._resolvePhoneFromLid(raw);
      if (resolved) candidates.push(`${resolved}@c.us`);
    } else if (raw.includes("@")) {
      candidates.push(raw);
      const digits = raw.replace(/\D/g, "");
      if (digits) candidates.push(`${digits}@c.us`);
    } else {
      const digits = raw.replace(/\D/g, "");
      if (digits) candidates.push(`${digits}@c.us`);
    }
    candidates.push(raw);

    let chat = null;
    let lastError = null;
    for (const candidate of [...new Set(candidates.filter(Boolean))]) {
      try {
        chat = await this.client.getChatById(candidate);
        if (chat) break;
      } catch (e) {
        lastError = e;
      }
    }
    if (!chat) {
      throw lastError || new Error("Conversa nao encontrada");
    }
    const chatId = this.normalizeChatId(chat.id);
    const messages = await chat.fetchMessages({ limit });
    return messages
      .sort((a, b) => Number(a.timestamp || 0) - Number(b.timestamp || 0))
      .map((message) => this.messagePayload(message, chatId));
  }

  async sendMessage(to, text, options) {
    this.assertReady();
    const chatId = to.includes("@") ? to : to + "@c.us";
    const result = options
      ? await this.client.sendMessage(chatId, text, options)
      : await this.client.sendMessage(chatId, text);
    this._log("[SEND] Para " + to);
    return result;
  }

  getStatus() {
    return {
      orgId: this.orgId,
      status: this.status,
      isReady: this.isReady,
      hasQrCode: !!this.qrCode,
      hasPairingCode: !!this.pairingCode,
      pairingCode: this.pairingCode,
      pairingPhoneNumber: this.pairingPhoneNumber
    };
  }

  // Estado REAL da conexao — consulta client.getState() (que pergunta a
  // pagina viva do WhatsApp Web), com timeout. Se a pagina travou, getState()
  // tambem trava; o timeout entao devolve 'UNREACHABLE'.
  async getRealState() {
    if (!this.client) return "NO_CLIENT";
    try {
      const state = await Promise.race([
        this.client.getState(),
        new Promise((_, rej) => setTimeout(() => rej(new Error("getState timeout")), 7000))
      ]);
      return state || "UNKNOWN";
    } catch (e) {
      return "UNREACHABLE";
    }
  }

  // Status VERIFICADO — nao confia na flag isReady cacheada; checa o estado
  // real. O /api/status usa isto para o front nunca mostrar "conectado"
  // quando a sessao na verdade caiu.
  async getStatusVerified() {
    const base = this.getStatus();
    if (base.status === "awaiting_scan" || base.status === "awaiting_pairing" || !this.client) {
      return { ...base, connected: false };
    }
    const realState = await this.getRealState();
    const connected = realState === "CONNECTED";
    if (!connected && this.isReady) {
      this._log("[STATE] divergencia: isReady=true mas getState=" + realState + " -> desconectado");
      this.isReady = false;
      this.status = "disconnected";
    }
    return {
      ...base,
      isReady: connected,
      status: connected ? "ready" : (this.qrCode ? "awaiting_scan" : "disconnected"),
      connected,
      realState
    };
  }

  // Reconecta PRESERVANDO a sessao salva (.wwebjs_auth NAO e apagado). Se a
  // sessao ainda for valida, reconecta sem QR; se morreu de vez, o initialize
  // emite 'qr' e o front mostra o QR de novo.
  async softReconnect() {
    if (this._reconnecting) return;
    this._reconnecting = true;
    this._log("[RECONNECT] soft reconnect (preserva a sessao)...");
    try {
      if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
      try { if (this.client) await this.client.destroy(); } catch (e) {}
      this.client = null;
      this.isReady = false;
      this.status = "reconnecting";
      await this.initialize();
    } catch (e) {
      this._log("[RECONNECT] erro:", e.message);
    } finally {
      this._reconnecting = false;
    }
  }

  // Monitor de saude: a cada 45s confere o estado real. 2 falhas seguidas =>
  // sessao morta (ex.: Chromium travou) => soft reconnect automatico. Cura o
  // "conectado fantasma" sem intervencao manual.
  _startHealthMonitor() {
    if (this._healthTimer) clearInterval(this._healthTimer);
    let bad = 0;
    this._healthTimer = setInterval(async () => {
      if (this._reconnecting) return;
      if (this.status === "awaiting_scan" || this.status === "awaiting_pairing") return;
      const state = await this.getRealState();
      if (state === "CONNECTED") {
        bad = 0;
        if (!this.isReady) { this.isReady = true; this.status = "ready"; }
        return;
      }
      bad += 1;
      this._log(`[HEALTH] estado=${state} (falha ${bad}/2)`);
      if (bad >= 2) {
        bad = 0;
        this.isReady = false;
        this.status = "disconnected";
        this.emit("disconnected", "health-monitor:" + state);
        this.softReconnect();
      }
    }, 45000);
    if (this._healthTimer.unref) this._healthTimer.unref();
  }

  getQrCode() { return this.qrCode; }
  getQrTimestamp() { return this.qrTimestamp; }
  getPairingCode() { return this.pairingCode; }
  async disconnect() {
    if (this.client) { await this.client.destroy(); this.isReady = false; this.status = "disconnected"; }
  }

  async requestPairingCode(phoneNumber) {
    const cleanPhone = phoneNumber.replace(/\D/g, "");
    if (!cleanPhone || cleanPhone.length < 10) {
      throw new Error("Invalid phone number. Use format: +1 (940) 618-3140 or 19406183140");
    }
    this._log("[PAIRING] Requesting pairing code for:", cleanPhone);
    await this.clearAndReinitialize(cleanPhone);
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error("Timeout waiting for pairing code (30 seconds). Make sure the phone number is correct."));
      }, 30000);
      if (this.pairingCode) {
        clearTimeout(timeout);
        resolve(this.pairingCode);
        return;
      }
      const codeHandler = (code) => {
        clearTimeout(timeout);
        this.removeListener("code", codeHandler);
        resolve(code);
      };
      this.on("code", codeHandler);
    });
  }

  async clearAndReinitialize(phoneNumber = null) {
    this._log("[PAIRING] Clearing auth and reinitializing...");
    try {
      if (this.client) { await this.client.destroy(); }
    } catch (e) { this._log("[PAIRING] Error destroying client:", e.message); }

    this.client = null;
    this.isReady = false;
    this.qrCode = null;
    this.pairingCode = null;
    this.pairingPhoneNumber = null;
    this.status = "disconnected";

    // Apenas a sessao DA org corrente — outras orgs continuam vivas.
    const sessionPath = path.join(
      process.cwd(),
      this.dataBase.replace(/^\.\//, ""),
      `session-org-${this.orgId}`
    );
    // PROFILAXIA: snapshot de seguranca ANTES de apagar — qualquer wipe (timeout,
    // /api/disconnect ou re-pair) fica recuperavel via _bak-...__prewipe.
    this._snapshotSession("__prewipe");
    try {
      if (fs.existsSync(sessionPath)) {
        fs.rmSync(sessionPath, { recursive: true, force: true });
        this._log("[PAIRING] Auth folder cleared");
      }
    } catch (e) { this._log("[PAIRING] Error clearing auth:", e.message); }

    await this.initialize(phoneNumber);

    if (phoneNumber) {
      this._log("[PAIRING] Reinitialized with pairing mode for:", phoneNumber);
    } else {
      this._log("[PAIRING] Reinitialized - waiting for QR code...");
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error("Timeout waiting for QR code after reinitialization"));
        }, 30000);
        const checkQR = setInterval(() => {
          if (this.qrCode && this.status === "awaiting_scan") {
            clearInterval(checkQR);
            clearTimeout(timeout);
            resolve(true);
          }
        }, 500);
      });
    }
  }
}

/**
 * WhatsAppManager — orchestra Clients por tenant.
 *
 * Cada org tem (no maximo) UMA instancia de WhatsAppClient. A primeira chamada
 * pra `getOrCreate(orgId)` inicializa a sessao (lazy). Chamadas subsequentes
 * devolvem a mesma instancia. `forEach` itera todas as sessoes vivas (util
 * para shutdown).
 *
 * O Manager nao auto-inicia nada: quem decide quando inicializar e o server
 * (server-lite.js). Isto permite testes sem precisar de Puppeteer rodando.
 */
class WhatsAppManager extends EventEmitter {
  constructor(options = {}) {
    super();
    this.dataBase = options.dataBase || "./.wwebjs_auth";
    this.defaultOrgId = Number.isFinite(options.defaultOrgId) ? options.defaultOrgId : DEFAULT_ORG_ID;
    // Permite injetar um factory pra testes (cria mocks no lugar de Client real).
    this._clientFactory = options.clientFactory || ((opts) => new WhatsAppClient(opts));
    /** @type {Map<number, WhatsAppClient>} */
    this._clients = new Map();
  }

  /**
   * Resolve um orgId valido. Aceita number, string numerica e null
   * (fallback default). Throw se vier invalido (string nao-numerica).
   */
  _resolveOrgId(orgId) {
    if (orgId === undefined || orgId === null || orgId === "") {
      return this.defaultOrgId;
    }
    const n = typeof orgId === "number" ? orgId : parseInt(String(orgId), 10);
    if (!Number.isFinite(n) || n <= 0) {
      throw new Error(`orgId invalido: ${orgId}`);
    }
    return n;
  }

  /**
   * Cria (ou devolve) o Client da org. Nao inicializa o Puppeteer; chame
   * `.initialize()` no Client retornado (ou use `ensureInitialized`).
   */
  getOrCreate(orgId) {
    const id = this._resolveOrgId(orgId);
    let client = this._clients.get(id);
    if (client) return client;
    client = this._clientFactory({ orgId: id, dataBase: this.dataBase });
    this._clients.set(id, client);
    // Re-emite eventos com orgId — server-lite.js escuta no manager pra
    // dispatcher ack/inbound pra bridge sem precisar binder N clientes.
    const forward = (evt) => {
      client.on(evt, (...args) => this.emit(evt, ...args, { orgId: id }));
    };
    ["qr", "ready", "authenticated", "disconnected", "auth_failure", "message", "message_ack"]
      .forEach(forward);
    this.emit("client_created", { orgId: id });
    return client;
  }

  /**
   * Cria + inicializa em uma chamada. Idempotente: se ja inicializou, devolve
   * a instancia existente sem re-iniciar.
   */
  async ensureInitialized(orgId, phoneNumber = null) {
    const client = this.getOrCreate(orgId);
    if (!client.client) {
      await client.initialize(phoneNumber);
    }
    return client;
  }

  has(orgId) {
    const id = this._resolveOrgId(orgId);
    return this._clients.has(id);
  }

  list() {
    return Array.from(this._clients.keys());
  }

  async destroy(orgId) {
    const id = this._resolveOrgId(orgId);
    const client = this._clients.get(id);
    if (client) {
      try { await client.disconnect(); } catch (e) {}
      this._clients.delete(id);
      this.emit("client_destroyed", { orgId: id });
    }
  }

  async destroyAll() {
    const ids = Array.from(this._clients.keys());
    for (const id of ids) {
      try { await this.destroy(id); } catch (e) {}
    }
  }

  /**
   * Snapshot do estado de todas as sessoes — usado pelo endpoint /api/sessions
   * (admin) e por testes pra inspecionar o manager.
   */
  snapshot() {
    return this.list().map((orgId) => {
      const c = this._clients.get(orgId);
      const status = c ? c.getStatus() : null;
      return {
        orgId,
        status: status ? status.status : "unknown",
        isReady: status ? status.isReady : false,
        hasQrCode: status ? status.hasQrCode : false,
      };
    });
  }
}

// Singleton manager — ponto de entrada padrao.
const manager = new WhatsAppManager();

/**
 * Shim de compat single-org: chamadas legadas tipo `whatsappClient.getStatus()`
 * continuam funcionando, redirecionando pra org default. Isto evita uma
 * cascata de mudancas em todos os modulos legado (database.js, bot-flow.js etc).
 *
 * Importante: este shim NAO inicializa nada — quem inicializa e o server.
 * Se o codigo legado chamar `whatsappClient.sendMessage(...)` antes do server
 * inicializar a org default, vai falhar com "WhatsApp nao conectado".
 *
 * Tecnica: usamos um objeto-alvo que ja carrega as named exports
 * (WhatsAppClient, WhatsAppManager, manager, DEFAULT_ORG_ID, ACK_STATUS_MAP).
 * O Proxy redireciona QUALQUER outra property pro client da org default.
 * Assim `whatsappClient.WhatsAppClient`, `whatsappClient.manager` continuam
 * acessiveis (named imports nao quebram), e `whatsappClient.getStatus()` cai
 * no client default.
 */
const _target = {
  WhatsAppClient,
  WhatsAppManager,
  manager,
  DEFAULT_ORG_ID,
  ACK_STATUS_MAP,
};

const _legacyProxy = new Proxy(_target, {
  get(target, prop) {
    if (prop in target) return target[prop];
    const client = manager.getOrCreate(DEFAULT_ORG_ID);
    const value = client[prop];
    if (typeof value === "function") {
      return value.bind(client);
    }
    return value;
  },
  set(target, prop, val) {
    if (prop in target) {
      target[prop] = val;
      return true;
    }
    const client = manager.getOrCreate(DEFAULT_ORG_ID);
    client[prop] = val;
    return true;
  },
  has(target, prop) {
    if (prop in target) return true;
    const client = manager.getOrCreate(DEFAULT_ORG_ID);
    return prop in client;
  },
});

module.exports = _legacyProxy;
