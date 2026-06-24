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
 * Por que multi-session: tenant alpha (tenanta.casehub.legal) compartilhava
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
const crypto = require("crypto");

// ID da org que assume o comportamento legado single-tenant quando nada
// (header X-Org-Id, dispatch) for passado. ENV opcional: CASEHUB_DEFAULT_ORG_ID.
const DEFAULT_ORG_ID = parseInt(process.env.CASEHUB_DEFAULT_ORG_ID || "1", 10);

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
    this.profilePicCache = new Map();
    this.profilePicTimeoutMs = Math.max(
      500,
      Math.min(Number(options.profilePicTimeoutMs || process.env.CASEHUB_WA_PROFILE_PIC_TIMEOUT_MS || 1200), 5000)
    );
    // Cache REVERSO telefone(digitos) -> JID original "<lid>@lid". Preenchido no
    // inbound (client.on "message") sempre que uma conversa chega keyed por LID e
    // resolvemos o telefone real. O ENVIO consulta este mapa: na era de
    // LID-addressing o WhatsApp Web indexa a "chat table" pelo LID, NAO pelo
    // telefone — mandar para "<numero>@c.us" dispara a resolucao usync
    // phone->LID interna (constructUsyncDeltaQuery) que, quando o interlocutor so
    // existe no store como LID, falha com "Lid is missing in chat table". Mandar
    // de volta para o "<lid>@lid" original acerta o Store.Chat.get direto (Tier 1
    // do WWebJS.getChat) e contorna esse caminho quebrado.
    this.reverseLidCache = new Map();
    this.pairingCode = null;
    this.pairingPhoneNumber = null;
    this.connectionState = null;   // ultimo estado real (change_state / getState)
    this._healthTimer = null;      // monitor de saude da sessao
    this._reconnecting = false;    // guarda contra reconnect concorrente
    this._authFailureCount = 0;    // recuperacoes automaticas de auth_failure
    this._AUTH_FAILURE_MAX = 2;    // teto antes de exigir intervencao manual
    this._lastEvent = "created";
    this._lastEventAt = new Date().toISOString();
    this._lastError = null;
    this._lastWatchdogAt = null;
    this._lastHealthState = null;
    this._watchdogFailures = 0;
    this._lastReconnectAt = null;
    this._lastReconnectMs = 0;     // timestamp numerico p/ cooldown do reconnect
    this._reconnectAttempts = 0;   // backoff exponencial; zera num 'ready'
    // Fonte de verdade da conexao: ATIVIDADE viva. message/message_ack carimbam
    // _lastInboundMs; _isLive()/isConnected() leem dali. Uma sessao que recebe
    // trafego esta conectada — nenhuma flag cacheada nem getState() lento pode
    // dizer o contrario (cura do "fantasma desconectado").
    this._lastInboundMs = 0;
    this._LIVENESS_WINDOW_MS = 120000;  // 2min de inbound => definitivamente vivo
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

  _safeDiagnosticText(value) {
    if (value === undefined || value === null) return null;
    return String(value)
      .replace(/data:image\/png;base64,[A-Za-z0-9+/=]+/g, "[qr-redacted]")
      .replace(/\b\d{6,}\b/g, "[digits-redacted]")
      .replace(this.dataBase, "[auth-dir]")
      .slice(0, 220);
  }

  _markEvent(event, detail = null) {
    this._lastEvent = String(event || "event");
    this._lastEventAt = new Date().toISOString();
    const err = detail && (detail.error || detail.reason || detail.message);
    if (err) this._lastError = this._safeDiagnosticText(err);
  }

  _dirLooksPresent(dirPath) {
    try {
      return fs.existsSync(dirPath) && fs.readdirSync(dirPath).length > 0;
    } catch (_) { return false; }
  }

  _backupDir(suffix) {
    return path.join(this.dataBase, `_bak-session-org-${this.orgId}${suffix}`);
  }

  _intentionalDownMarkerPath() {
    return path.join(this.dataBase, `.intentional-down-org-${this.orgId}`);
  }

  _isIntentionalDown() {
    try {
      return Boolean(this._intentionalDown || fs.existsSync(this._intentionalDownMarkerPath()));
    } catch (_) { return Boolean(this._intentionalDown); }
  }

  _markIntentionalDown() {
    this._intentionalDown = true;
    try {
      fs.mkdirSync(this.dataBase, { recursive: true });
      fs.writeFileSync(this._intentionalDownMarkerPath(), new Date().toISOString(), { mode: 0o600 });
    } catch (e) {
      this._warn("[INTENTIONAL-DOWN] falha ao persistir marcador:", e && e.message ? e.message : e);
    }
  }

  _clearIntentionalDown() {
    this._intentionalDown = false;
    try { fs.rmSync(this._intentionalDownMarkerPath(), { force: true }); } catch (_) {}
  }

  _hostBindingHash() {
    const secret = process.env.CASEHUB_WA_SESSION_BINDING || "";
    return secret ? crypto.createHash("sha256").update(secret).digest("hex") : "";
  }

  _readHostBindMarker(dirPath) {
    try {
      const markerPath = path.join(dirPath, ".host-bind");
      if (fs.existsSync(markerPath)) return fs.readFileSync(markerPath, "utf8").trim();
    } catch (_) {}
    return "";
  }

  _backupAllowedForHost(backupDir) {
    const expected = this._hostBindingHash();
    const marker = this._readHostBindMarker(backupDir);
    if (!expected) {
      if (marker) {
        this._error("[HOST-BIND] backup __lastgood tem marcador mas este host nao tem CASEHUB_WA_SESSION_BINDING — restore recusado");
        this.status = "blocked_host";
        this._markEvent("backup_restore_blocked_host");
        return false;
      }
      return true;
    }
    if (!marker) {
      this._error("[HOST-BIND] backup __lastgood sem .host-bind em host bound — restore recusado");
      this.status = "blocked_host";
      this._markEvent("backup_restore_missing_host_bind");
      return false;
    }
    if (marker !== expected) {
      this._error("[HOST-BIND] backup __lastgood pertence a outro host — restore recusado");
      this.status = "blocked_host";
      this._markEvent("backup_restore_wrong_host");
      return false;
    }
    return true;
  }

  _discardLastGoodBackup(reason) {
    try {
      const dir = this._backupDir("__lastgood");
      if (fs.existsSync(dir)) {
        fs.rmSync(dir, { recursive: true, force: true });
        this._warn(`[BACKUP] __lastgood descartado (${reason})`);
      }
    } catch (e) {
      this._warn("[BACKUP] falha ao descartar __lastgood:", e && e.message ? e.message : e);
    }
  }

  _maskedPairingPhone() {
    const digits = String(this.pairingPhoneNumber || "").replace(/\D/g, "");
    if (!digits) return null;
    return digits.length <= 4 ? "****" : `${"*".repeat(Math.max(4, digits.length - 4))}${digits.slice(-4)}`;
  }

  _recommendedAction(status = this.status) {
    const s = String(status || "").toLowerCase();
    if (this.isReady || s === "ready" || s === "connected") return "none";
    if (this.qrCode || s === "awaiting_scan" || s === "qr") return "scan_qr";
    if (this.pairingCode || s === "awaiting_pairing") return "enter_pairing_code";
    if (this._reconnecting || ["authenticated", "initializing", "reconnecting", "connecting", "loading", "starting"].includes(s)) {
      return "wait";
    }
    if (s === "auth_failed") {
      return this._authFailureCount > this._AUTH_FAILURE_MAX ? "manual_review" : "soft_reconnect";
    }
    // Host-binding lockout: a soft reconnect just re-blocks. The operator must
    // re-bind this host (CASEHUB_WA_REBIND=1) or restore the env secret.
    if (s === "blocked_host") return "rebind_host";
    // Deliberate teardown survives restart and suppresses autostart; coming back
    // needs an EXPLICIT reconnect/init, not the implicit soft path.
    if (s === "intentional_down" || (typeof this._isIntentionalDown === "function" && this._isIntentionalDown())) {
      return "reconnect_explicit";
    }
    if (this._sessionLooksPresent()) return "soft_reconnect";
    return "scan_qr";
  }

  _nextStep(action) {
    switch (action) {
      case "none":
        return "Conectado. O watchdog continua monitorando a sessao.";
      case "scan_qr":
        return "Escaneie o QR pelo WhatsApp do celular.";
      case "enter_pairing_code":
        return "Digite o codigo exibido no WhatsApp do celular.";
      case "wait":
        return "Aguarde a sessao terminar de inicializar.";
      case "soft_reconnect":
        return "Use Reconectar; a sessao salva sera preservada.";
      case "manual_review":
        return "Auth recusada repetidamente. Repareamento manual pode ser necessario.";
      case "rebind_host":
        return "Sessao bloqueada por host-binding. Restaure CASEHUB_WA_SESSION_BINDING neste host, ou rode o rebind explicito (CASEHUB_WA_REBIND=1).";
      case "reconnect_explicit":
        return "Sessao desconectada deliberadamente. Use Reconectar (init explicito) para religar.";
      default:
        return "Atualize o status da conexao.";
    }
  }

  // Vocabulario UNICO fatal-vs-transiente, partilhado por disconnected/change_state.
  // FATAL = sessao morta (precisa re-pareamento/QR): logout pelo celular, conflito
  // de sessao, ou a navegacao que varios forks do whatsapp-web.js emitem no logout.
  // Qualquer outro reason (TIMEOUT/OPENING/...) e' transiente — blip que o watchdog
  // cura. Centralizar mata a divergencia historica de LOGOUT/NAVIGATION entre os dois.
  _classifyReason(reason) {
    return /UNPAIRED|CONFLICT|LOGOUT|NAVIGATION/i.test(String(reason || "")) ? "fatal" : "transient";
  }

  _isAmbiguousHealthState(state) {
    return /^(UNKNOWN|UNREACHABLE|TIMEOUT|OPENING|CONNECTING)$/i.test(String(state || "").trim());
  }

  _isTransientBrowserAuthFailure(error) {
    const text = String(
      (error && (error.stack || error.message || error.toString && error.toString())) ||
      error ||
      ""
    );
    return /Target closed|Session closed|Connection closed|browser has disconnected|Protocol error .*Target/i.test(text);
  }

  async initialize(phoneNumber = null, options = {}) {
    this._log("[INIT] WhatsApp Client v4.0 (multi-session)");
    const explicit = Boolean(options && options.explicit) || Boolean(phoneNumber);
    if (this._isIntentionalDown() && !explicit) {
      this._intentionalDown = true;
      this.status = "disconnected";
      this._markEvent("initialize_blocked_intentional_down");
      this._log("[INIT] bloqueado — sessao derrubada deliberadamente; use reconnect/init explicito");
      return;
    }
    if (explicit) this._clearIntentionalDown();
    this.status = phoneNumber ? "awaiting_pairing" : (this.status === "reconnecting" ? "reconnecting" : "initializing");
    this._markEvent(phoneNumber ? "pairing_initialize" : "initialize");
    if (this._readyTimeout) { clearTimeout(this._readyTimeout); this._readyTimeout = null; }

    // Auto-cura: se a sessao sumiu mas ha backup __lastgood, restaura o
    // pareamento ANTES do LocalAuth carregar (so no boot, so sem re-pair).
    if (!phoneNumber) this._restoreFromBackupOnBoot();

    // Limpa locks Singleton orfaos do Chromium antes de subir o browser.
    // LocalAuth persiste o profile num volume Docker; ao recriar o container
    // o profile herda um SingletonLock apontando pro hostname do container
    // morto => o novo Chromium recusa ("profile in use", Code 21) e o QR
    // nunca aparece. Remover os locks (preservando a sessao) cura o launch.
    this._clearChromiumLocks();

    // Gate anti-hijack (Equipe CaseHub 10/06): recusa subir a sessao se os arquivos de
    // auth nao pertencem a este host. Fail-safe e aditivo (sem env => sem trava).
    if (!this._enforceHostBinding()) {
      this._error("[HOST-BIND] inicializacao abortada — sessao nao pertence a este host");
      this._markEvent("blocked_host");
      this.emit("blocked_host", this.orgId);
      return;
    }

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

    // QR code event. SEMPRE atualiza o QR servido — o QR do WhatsApp expira em
    // ~20-60s e, com a latencia de remote runtime, o front precisa SEMPRE da versao mais
    // nova ou da "nao foi possivel conectar o dispositivo". O cooldown cosmetico
    // (RC3) foi removido: cada `qr` reemitido atualiza this.qrCode/qrTimestamp,
    // emite o evento e renderiza no terminal, sem throttle.
    this.client.on("qr", async (qr) => {
      this.qrCode = await QRCode.toDataURL(qr);
      this.qrTimestamp = Date.now();
      this.status = "awaiting_scan";
      this._markEvent("qr");
      this.emit("qr", this.qrCode);
      this._log("[QR] Escaneie com o WhatsApp:");
      qrcode.generate(qr, { small: true });
    });

    // Pairing code event - triggered when using pairWithPhoneNumber
    this.client.on("code", (code) => {
      this._log("[PAIRING] Code received");
      this.pairingCode = code;
      this.status = "awaiting_pairing";
      this._markEvent("pairing_code");
      this.emit("code", code);
    });

    this.client.on("authenticated", () => {
      this._log("[AUTH] Autenticado!");
      this.status = "authenticated";
      this._markEvent("authenticated");
      this.emit("authenticated");

      // Timeout p/ READY lento. Limpa o anterior antes de re-armar: um ciclo
      // authenticated->ready-lento->novo-authenticated orfanava o timer #1
      // (referencia sobrescrita), que aos 60s disparava softReconnect espurio.
      if (this._readyTimeout) clearTimeout(this._readyTimeout);
      this._readyTimeout = setTimeout(() => {
        // So reconecta se nao esta ready E nao ha atividade (socket morto mesmo).
        if (!this.isReady && !this._isLive()) {
          this._warn("[WARN] READY timeout apos 60s - soft reconnect (preserva a sessao)...");
          this.softReconnect("ready-timeout");
        }
      }, 60000);
      if (this._readyTimeout.unref) this._readyTimeout.unref();
    });

    this.client.on("ready", () => {
      this._log("[READY] WhatsApp conectado!");
      if (this._readyTimeout) { clearTimeout(this._readyTimeout); this._readyTimeout = null; }
      this._intentionalDown = false;
      this.isReady = true;
      this.qrCode = null;
      this.qrTimestamp = null;
      this.status = "ready";
      this._authFailureCount = 0; // sessao saudavel — zera o circuito de auth_failure
      this._restoredFromLastGood = false; // sessao saudavel: o __lastgood (novo ou restaurado) e' bom
      this._reconnectAttempts = 0; // sessao saudavel — zera o backoff de reconnect
      this._lastReconnectMs = 0;
      this._markEvent("ready");
      this.emit("ready");
    });

    this.client.on("message", async (message) => {
      this._touchActivity();  // qualquer inbound = socket vivo (fonte de verdade)
      if (message.from.includes("@g.us") || message.fromMe || message.from === "status@broadcast") return;

      let phoneNumber = message.from;
      let realPhone = null;

      if (message.from.includes("@lid")) {
        const lidId = message.from.replace("@lid", "");
        this._log("[LID] Mensagem de LID:", lidId);

        if (this.lidCache.has(lidId)) {
          realPhone = (this.lidCache.get(lidId) || "").replace(/@c\.us/g, "");
          phoneNumber = realPhone + "@c.us";
          this._rememberLidForPhone(realPhone, message.from); // reforca reverso (TTL do envio)
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

        // Qualquer metodo (1/2/3) que resolveu o telefone -> grava o reverso
        // telefone->"<lid>@lid" para o ENVIO reusar o JID que o store ja conhece.
        if (realPhone) this._rememberLidForPhone(realPhone, message.from);
        else this._warn("[WARN] LID nao resolvido:", message.from);
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

    // message_create — N2: mensagens ENVIADAS pelo proprio celular (outbound
    // manual). whatsapp-web.js emite message_create para toda mensagem criada,
    // inclusive as que o operador manda pelo aparelho. O handler 'message' acima
    // ignora fromMe (so inbound), entao sem isto o outbound manual nunca chega ao
    // CaseHub. Re-emitimos com a MESMA forma do 'message' (from = destinatario,
    // fromMe: true) pra reaproveitar buildPayload/forwardInbound (mesmo HMAC).
    this.client.on("message_create", (message) => {
      try {
        if (!message || !message.fromMe) return;
        const toRaw = (message.to || "").toString();
        if (!toRaw || toRaw.includes("@g.us") || toRaw === "status@broadcast") return;
        // N2/LID: destinos endereçados por LID (@lid) ainda NAO tem o telefone
        // real resolvido no caminho outbound (so o handler inbound 'message'
        // acima resolve, via lidCache/getContact/getChat). Re-emitir com
        // from = "<lid>@lid" criaria um wa_contact chaveado nos DIGITOS do LID =
        // thread DIFERENTE da thread real-phone usada pelo inbound (fragmentacao,
        // o mesmo bug de 'meia thread' que o N2 tenta consertar). Ate a resolucao
        // LID no outbound existir (follow-up Codex: espelhar lidCache/getContact/
        // getChat), PULAR-E-LOGAR — mesmo padrao dos guards de @g.us /
        // status@broadcast acima.
        if (toRaw.includes("@lid")) {
          this._warn("[wa-bot] message_create skip @lid (N2 LID resolution deferida):", toRaw);
          return;
        }
        const hasMedia = !!message.hasMedia;
        this.emit("message_create", {
          orgId: this.orgId,
          // from = a OUTRA ponta da conversa (destinatario) pra cair no mesmo
          // thread do contato no CaseHub. buildPayload usa data.from como telefone.
          from: toRaw,
          body: message.body || "",
          timestamp: message.timestamp,
          type: message.type,
          message: message,
          originalId: toRaw,
          messageId: message.id && message.id._serialized ? message.id._serialized : null,
          fromMe: true,
          hasMedia,
          mediaType: hasMedia ? (message.type || null) : null,
          mimetype: (hasMedia && message._data && message._data.mimetype) || null,
          filename:
            (hasMedia &&
              (message._data && (message._data.filename || message._data.caption))) ||
            null,
          caption: hasMedia ? (message.body || null) : null
        });
      } catch (e) {
        this._log("[OUTBOUND] erro ao processar message_create:", e.message);
      }
    });

    // message_ack — evolução do status de entrega/leitura de mensagens
    // enviadas. whatsapp-web.js emite ack: -1 ERROR, 0 PENDING, 1 SERVER (enviado),
    // 2 DEVICE (entregue), 3 READ (lido), 4 PLAYED (áudio ouvido).
    // O frontend usa isto para renderizar os ticks (cinza/duplo/azul).
    this.client.on("message_ack", (message, ack) => {
      this._touchActivity();  // ack recebido = socket vivo
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
      this.connectionState = "DISCONNECTED";
      this._markEvent("disconnected", { reason });
      // Deny-list: SO um conjunto FECHADO de reasons sabidamente transitorios
      // pode ser ignorado como blip (quando ha atividade recente). Qualquer outro
      // — inclui NAVIGATION/LOGOUT que varios forks emitem no logout pelo celular
      // — rebaixa e oferece QR. O watchdog re-promove em <=60s se for so um blip.
      const r = String(reason || "");
      const fatal = this._classifyReason(r) === "fatal";
      // Blip: ignora SO um conjunto fechado de reasons sabidamente transitorios com
      // socket vivo. Um reason FATAL nunca e' ignorado; um reason desconhecido
      // rebaixa (fail-loud), preservando a deny-list conservadora original.
      const knownBlip = /TIMEOUT|OPENING|PAIRING|CONNECTING/i.test(r);
      if (!fatal && knownBlip && this._isLive()) {
        this._warn("[DISCONNECT] ignorado (blip transitorio, socket vivo):", r);
        return;
      }
      this._lastInboundMs = 0;
      this.isReady = false;
      this.status = "disconnected";
      this.emit("disconnected", reason);
    });

    // change_state — estado real da conexao reportado pelo whatsapp-web.js.
    // CONNECTED = sessao viva; qualquer outro (TIMEOUT/CONFLICT/UNPAIRED/...)
    // = caiu. Mantem isReady sincronizado com a verdade, em tempo real.
    this.client.on("change_state", (state) => {
      this._log("[STATE]", state);
      this.connectionState = state;
      this._lastHealthState = state;
      if (state === "CONNECTED") {
        this.isReady = true;
        this.status = "ready";
        this._reconnectAttempts = 0;
        this._lastReconnectMs = 0;
        this._markEvent("state_connected");
      } else if (this._classifyReason(state) === "fatal" || !this._isLive()) {
        // Rebaixa SEMPRE num estado fatal (UNPAIRED/CONFLICT/LOGOUT/NAVIGATION);
        // nos demais, so quando NAO ha atividade recente (um TIMEOUT/OPENING com
        // socket vivo e' blip e nao rebaixa). O watchdog decide reconectar de fato.
        if (this._classifyReason(state) === "fatal") this._lastInboundMs = 0;
        this.isReady = false;
        this.status = "disconnected";
      }
    });

    // auth_failure: o WhatsApp REJEITOU as credenciais salvas (deslogado pelo
    // celular, conflito de sessao, ou pareamento corrompido apos um wipe). A
    // sessao em disco esta morta — preserva-la so produz um loop infinito de
    // "authenticated -> ready-timeout -> softReconnect -> auth_failure". A cura
    // e' apagar a auth rejeitada e re-inicializar limpo, oferecendo um QR novo
    // valido. clearAndReinitialize ja faz snapshot __prewipe ANTES de apagar
    // (recuperavel) — entao isto nao e' destrutivo de verdade.
    //
    // Guarda contra loop: no maximo _AUTH_FAILURE_MAX recuperacoes automaticas;
    // depois disso para e deixa a sessao em "auth_failed" para intervencao
    // manual (evita apagar/recriar em tempestade). O contador zera num `ready`.
    this.client.on("auth_failure", async (error) => {
      this._error("[AUTH-FAIL]", error);
      const transientBrowserFailure = this._isTransientBrowserAuthFailure(error);
      const hadAuthenticatedSession = this.status === "authenticated" || this._lastEvent === "authenticated";
      if (transientBrowserFailure && hadAuthenticatedSession && this._sessionLooksPresent()) {
        this.status = this._reconnecting ? "reconnecting" : "disconnected";
        this._markEvent("auth_failure_browser_transient", { error });
        this.emit("auth_failure", error);
        this._warn("[AUTH-FAIL] falha transitoria do Chromium/CDP apos authenticated — preservando LocalAuth e tentando soft reconnect");
        if (this._reconnecting) return;
        this._authFailureCount = 0;
        await this.softReconnect("auth_failure:browser-target-closed");
        return;
      }
      this.status = "auth_failed";
      this._markEvent("auth_failure", { error });
      this.emit("auth_failure", error);
      if (this._reconnecting) return;
      this._authFailureCount = (this._authFailureCount || 0) + 1;
      if (this._authFailureCount > this._AUTH_FAILURE_MAX) {
        this._warn(`[AUTH-FAIL] limite de ${this._AUTH_FAILURE_MAX} recuperacoes atingido — parando (intervencao manual via /api/disconnect { confirm: 'wipe' })`);
        return;
      }
      this._reconnecting = true;
      try {
        this._warn(`[AUTH-FAIL] auth rejeitada — limpando sessao morta e re-inicializando (${this._authFailureCount}/${this._AUTH_FAILURE_MAX}); QR novo sera emitido`);
        if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
        // clearAndReinitialize faz destroy + snapshot __prewipe + rm + initialize.
        // Sem phoneNumber => volta pro fluxo de QR. MANTEM _reconnecting=true por
        // TODA a recuperacao (resetado no finally): zera-lo antes do await abria a
        // janela do self-heal de 45s disparar um 2o initialize => duplo Chromium.
        // preserveLastGood: uma rejeicao de auth TRANSIENTE (sessao nao-restaurada)
        // preserva o __lastgood para auto-cura no proximo boot. MAS se a sessao que
        // falhou veio do restore do __lastgood neste boot, o backup esta morto
        // (logout real) — descarta, para o proximo boot ir direto ao QR em vez de
        // re-restaurar credenciais mortas a cada restart de container.
        await this.clearAndReinitialize(null, { preserveLastGood: !this._restoredFromLastGood });
      } catch (e) {
        this._error("[AUTH-FAIL] recuperacao falhou:", e && e.message ? e.message : e);
      } finally {
        this._reconnecting = false;
      }
    });

    // Watchdog armado ANTES do await: no remote runtime CPU-only o client.initialize()
    // pode levar minutos (protocolTimeout=5min) ou travar num hang puro de
    // qr/ready — re-armar so no finally deixava o watchdog MORTO toda a janela
    // (o "active:false" que dizemos curar). Armado aqui, ele monitora ja no boot.
    // Guarda de reentrancia: impede um 2o initialize() concorrente (self-heal,
    // ensureInitialized na janela client=null) que subiria um 2o Chromium no MESMO
    // profile session-org-N => SingletonLock/"profile in use" (Code 21) => QR
    // nunca aparece. Setado ANTES do 1o await (sincrono); resetado no finally.
    this._initInFlight = true;
    this._ensureHealthMonitor();
    let initTimer = null;
    let initTimedOut = false;
    try {
      // Timeout DURO: um hang puro de eventos (qr/ready que nunca disparam) NAO e'
      // coberto por protocolTimeout. Sem isto a sessao ficava presa em
      // "initializing" pra sempre. Timeout e' recuperado pelo watchdog; rejeicao
      // imediata de initialize() deve propagar para os callers/HTTP 502.
      const initP = this.client.initialize();
      initP.catch(() => {});   // perna perdedora do race nao vira unhandledRejection
      const timeoutP = new Promise((_, rej) => {
        initTimer = setTimeout(() => {
          initTimedOut = true;
          rej(new Error("initialize timeout 120s"));
        }, 120000);
        if (initTimer.unref) initTimer.unref();
      });
      await Promise.race([
        initP,
        timeoutP,
      ]);
    } catch (e) {
      this._warn("[INIT] initialize falhou/timeout:", e && e.message ? e.message : e);
      this._markEvent("initialize_failed", { error: e && e.message ? e.message : e });
      if (!initTimedOut) {
        try { if (this.client) await this.client.destroy(); } catch (_) {}
        this.client = null;
        this.isReady = false;
        this._lastInboundMs = 0;
        this.connectionState = "DISCONNECTED";
        this.status = "disconnected";
        throw e;
      }
    } finally {
      if (initTimer) clearTimeout(initTimer);
      this._initInFlight = false;
      this._ensureHealthMonitor();
    }
  }

  // GATE ANTI-HIJACK: amarra os arquivos de sessao (.wwebjs_auth/session-org-N)
  // ao host autorizado. O segredo CASEHUB_WA_SESSION_BINDING vive SO no host
  // (env, fora do volume Docker); no diretorio da sessao gravamos apenas o
  // sha256 dele em .host-bind. Se o volume for copiado para outro host:
  //   - host sem o segredo (env ausente) + sessao ja-amarrada  => RECUSA
  //   - host com segredo DIFERENTE (hash nao bate)             => RECUSA
  // So um host com o MESMO segredo carrega a sessao. O segredo nunca vai pro
  // volume (so o hash, irreversivel). Sem env => sem restricao (dev nao quebra).
  _enforceHostBinding() {
    const sessionDir = this._sessionDir();
    const markerPath = path.join(sessionDir, ".host-bind");
    const expected = this._hostBindingHash();
    const marker = this._readHostBindMarker(sessionDir);

    if (!expected) {
      // Sem segredo neste host. Se a sessao ja foi amarrada noutro lugar, recusa
      // (impede carregar sessao roubada num host sem credencial). Senao, libera.
      if (marker) {
        this._error("[HOST-BIND] sessao amarrada a outro host mas CASEHUB_WA_SESSION_BINDING ausente — recusando (possivel hijack)");
        this.status = "blocked_host";
        return false;
      }
      return true;
    }

    if (!marker) {
      // Primeira amarracao neste host (sessao nova OU pre-existente do remote runtime).
      try {
        if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });
        fs.writeFileSync(markerPath, expected, { mode: 0o600 });
        this._log("[HOST-BIND] sessao amarrada a este host");
      } catch (e) {
        this._warn("[HOST-BIND] falha ao gravar marcador:", e && e.message ? e.message : e);
        this._markEvent("host_bind_marker_write_failed", { error: e && e.message ? e.message : e });
      }
      return true;
    }
    if (marker !== expected) {
      this._error("[HOST-BIND] marcador da sessao nao confere com este host — recusando (possivel hijack de sessao)");
      this.status = "blocked_host";
      return false;
    }
    return true; // marcador confere — host autorizado
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
    const sessionDir = this._sessionDir();
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
    // #5 — getChats() pode falhar transitoriamente logo apos o `ready` (o
    // WhatsApp Web ainda esta hidratando os chats). Pequeno retry com backoff
    // antes de desistir; sem isso o sync inteiro aborta e fica sem fotos/nomes.
    const chatRetries = Math.max(0, Number(options.chatRetries == null ? 2 : options.chatRetries));
    let rawChats = null;
    for (let attempt = 0; attempt <= chatRetries; attempt++) {
      try {
        rawChats = await this.client.getChats();
        break;
      } catch (e) {
        if (attempt >= chatRetries) throw e;
        const wait = 1500 * (attempt + 1);
        this._warn(`[SYNC] getChats falhou (tentativa ${attempt + 1}/${chatRetries + 1}), retry em ${wait}ms:`, e && e.message ? e.message : e);
        await new Promise((r) => setTimeout(r, wait));
      }
    }
    const chats = (rawChats || [])
      .filter((chat) => !chat.isGroup)
      .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0))
      .slice(0, limit);
    const out = [];
    for (const chat of chats) {
      const chatId = this.normalizeChatId(chat.id);
      let phone = this.phoneFromChatId(chatId);
      let displayName = chat.name || null;
      let profilePicUrl = null;
      let isBusiness = false;
      let contact = null;
      try {
        contact = await chat.getContact();
        if (contact) {
          displayName = contact.pushname || contact.name || displayName;
          isBusiness = Boolean(contact.isBusiness);
          const contactNumber = String(contact.number || "").replace(/\D/g, "");
          if (contactNumber) phone = contactNumber;
          // #5 — a foto e o dado mais flaky (chamada extra ao servidor WA).
          // 1 retry rapido por contato cobre falha transitoria sem virar
          // varredura cara: contato realmente sem foto cai no catch e segue.
          for (let picTry = 0; picTry < 2; picTry++) {
            try {
              profilePicUrl = (await this._profilePicUrlFromContact(contact, [chatId, phone])) || null;
              break;
            } catch (_) {
              if (picTry === 0) { await new Promise((r) => setTimeout(r, 400)); continue; }
              /* contato sem foto ou privado */
            }
          }
        }
      } catch (_) { /* segue so com chat.name */ }
      if (phone && phone.endsWith("@lid")) {
        const resolved = await this._resolvePhoneFromLid(chatId);
        if (resolved) phone = resolved;
      }
      if (!phone || phone.endsWith("@lid")) continue; // sem telefone real => nao grava no backend
      out.push({
        phone,
        display_name: displayName,
        profile_pic_url: profilePicUrl,
        is_business: isBusiness,
      });
    }
    return out;
  }

  _profilePicCacheKey(phone) {
    const raw = String(phone || "").trim();
    return raw.replace(/@.*$/, "").replace(/\D/g, "") || raw;
  }

  _cacheProfilePicUrl(keys, url) {
    if (!url) return url;
    for (const key of keys || []) {
      const cacheKey = this._profilePicCacheKey(key);
      if (cacheKey) this.profilePicCache.set(cacheKey, url);
    }
    return url;
  }

  async _profilePicWithTimeout(promise, label) {
    let timer = null;
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => {
          timer = setTimeout(
            () => reject(new Error(`${label || "profile picture"} timeout`)),
            this.profilePicTimeoutMs
          );
        }),
      ]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  async _profilePicThumbDataUrlFromJid(jid) {
    const rawJid = String(jid || "").trim();
    if (!rawJid || !this.client || !this.client.pupPage) return null;
    try {
      return await this._profilePicWithTimeout(
        this.client.pupPage.evaluate(async (contactId) => {
          const store = window.Store || {};
          const widFactory = store.WidFactory;
          if (!widFactory || typeof widFactory.createWid !== "function") return null;
          const chatWid = widFactory.createWid(contactId);
          if (window.WWebJS && typeof window.WWebJS.getProfilePicThumbToBase64 === "function") {
            const base64 = await window.WWebJS.getProfilePicThumbToBase64(chatWid);
            return base64 ? `data:image/jpeg;base64,${base64}` : null;
          }
          return null;
        }, rawJid),
        "profile thumbnail"
      );
    } catch (_) {
      return null;
    }
  }

  async _profilePicUrlFromContact(contact, fallbackJids = []) {
    const candidates = [];
    if (contact) {
      const contactId = this.normalizeChatId(contact.id);
      if (contactId) candidates.push(contactId);
      const number = String(contact.number || "").replace(/\D/g, "");
      if (number) candidates.push(`${number}@c.us`, number);
    }
    candidates.push(...(fallbackJids || []));

    for (const candidate of [...new Set(candidates.filter(Boolean))]) {
      const jid = String(candidate).includes("@")
        ? String(candidate)
        : `${String(candidate).replace(/\D/g, "")}@c.us`;
      const thumb = await this._profilePicThumbDataUrlFromJid(jid);
      if (thumb) return this._cacheProfilePicUrl([candidate, ...fallbackJids], thumb);
    }

    if (contact && typeof contact.getProfilePicUrl === "function") {
      try {
        const url = (await this._profilePicWithTimeout(
          contact.getProfilePicUrl(),
          "contact profile picture"
        )) || null;
        if (url) return this._cacheProfilePicUrl(fallbackJids, url);
      } catch (_) { /* contato sem foto, privado ou ainda nao hidratado */ }
    }

    for (const candidate of [...new Set(candidates.filter(Boolean))]) {
      try {
        const jid = String(candidate).includes("@")
          ? String(candidate)
          : `${String(candidate).replace(/\D/g, "")}@c.us`;
        const url = (await this._profilePicWithTimeout(
          this.client.getProfilePicUrl(jid),
          "profile picture URL"
        )) || null;
        if (url) return this._cacheProfilePicUrl([candidate, ...fallbackJids], url);
      } catch (_) { /* best-effort */ }
    }
    return null;
  }

  async _profilePicUrlForChat(chat) {
    if (!chat) return null;
    const chatId = this.normalizeChatId(chat.id);
    let contact = null;
    try {
      contact = await chat.getContact();
    } catch (_) { /* segue com o JID do chat */ }

    const url = await this._profilePicUrlFromContact(contact, [chatId]);
    if (url) return url;
    return this.getProfilePicUrl(chatId);
  }

  _phoneDigitsMatch(a, b) {
    const left = String(a || "").replace(/\D/g, "");
    const right = String(b || "").replace(/\D/g, "");
    if (!left || !right) return false;
    if (left === right) return true;
    if (left.length >= 10 && right.length >= 10) {
      return left.slice(-10) === right.slice(-10);
    }
    return false;
  }

  async _profilePicUrlFromChatsByPhone(phone) {
    const digits = String(phone || "").replace(/\D/g, "");
    if (!digits) return null;
    let chats = [];
    try {
      chats = await this.client.getChats();
    } catch (_) {
      return null;
    }
    for (const chat of chats || []) {
      if (!chat || chat.isGroup) continue;
      let contact = null;
      try {
        contact = await chat.getContact();
      } catch (_) { /* next source */ }
      const contactNumber = contact && contact.number;
      const chatPhone = this.phoneFromChatId(this.normalizeChatId(chat.id));
      if (!this._phoneDigitsMatch(contactNumber, digits) && !this._phoneDigitsMatch(chatPhone, digits)) {
        continue;
      }
      const url = await this._profilePicUrlFromContact(contact, [
        this.normalizeChatId(chat.id),
        `${digits}@c.us`,
        digits,
      ]);
      if (url) return url;
    }
    return null;
  }

  async getProfilePicUrl(phone) {
    this.assertReady();
    const raw = String(phone || "").trim();
    if (!raw) return null;

    const cacheKey = this._profilePicCacheKey(raw);
    if (cacheKey && this.profilePicCache.has(cacheKey)) {
      return this.profilePicCache.get(cacheKey);
    }

    const candidates = [];
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

    for (const candidate of [...new Set(candidates.filter(Boolean))]) {
      const thumb = await this._profilePicThumbDataUrlFromJid(candidate);
      if (thumb) return this._cacheProfilePicUrl([raw, candidate], thumb);
    }

    for (const candidate of [...new Set(candidates.filter(Boolean))]) {
      try {
        const url = (await this._profilePicWithTimeout(
          this.client.getProfilePicUrl(candidate),
          "profile picture URL"
        )) || null;
        if (url) {
          if (cacheKey) this.profilePicCache.set(cacheKey, url);
          const digitsKey = this._profilePicCacheKey(candidate);
          if (digitsKey) this.profilePicCache.set(digitsKey, url);
          return url;
        }
      } catch (_) { /* contato sem foto, privado ou ainda nao hidratado */ }
    }

    const digits = raw.replace(/\D/g, "");
    const fromChat = await this._profilePicUrlFromChatsByPhone(digits);
    if (fromChat) return this._cacheProfilePicUrl([raw, digits, `${digits}@c.us`], fromChat);

    return null;
  }

  async getProfilePics(phones, options = {}) {
    this.assertReady();
    const limit = Math.max(1, Math.min(Number(options.limit || 40), 80));
    const unique = [...new Set((Array.isArray(phones) ? phones : [])
      .map((phone) => String(phone || "").trim())
      .filter(Boolean))]
      .slice(0, limit);
    const profiles = [];
    const byPhone = {};

    for (const phone of unique) {
      const url = await this.getProfilePicUrl(phone);
      profiles.push({ phone, url, profilePic: url });
      byPhone[phone] = url;
    }

    return { profiles, byPhone };
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
      const dst = this._backupDir(suffix);
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
      const bak = this._backupDir("__lastgood");
      if (!fs.existsSync(bak) || fs.readdirSync(bak).length === 0) return false;
      if (!this._backupAllowedForHost(bak)) return false;
      const dst = this._sessionDir();
      fs.rmSync(dst, { recursive: true, force: true });
      fs.cpSync(bak, dst, { recursive: true, force: true });
      this._warn("[RESTORE] sessao ausente no boot — restaurada do backup __lastgood (auto-cura, sem QR)");
      this._markEvent("session_restored_from_backup");
      this._restoredFromLastGood = true;   // se ESTA sessao auth-falhar, o __lastgood esta morto
      return true;
    } catch (e) {
      this._warn("[RESTORE] auto-cura falhou (segue p/ QR):", e && e.message ? e.message : e);
      this._markEvent("session_restore_failed", { error: e && e.message ? e.message : e });
      return false;
    }
  }

  assertReady() {
    // Aceita a sessao quando ha conexao viva comprovada (isConnected: ready OU
    // atividade recente OU estado real CONNECTED). Antes exigia a flag isReady
    // crua, presa em false no reconnect morno, bloqueando getMessages/
    // listConversations com o socket vivo => "mensagens nao carregam".
    if (!this.client || !this.isConnected()) {
      throw new Error(`WhatsApp nao conectado (org=${this.orgId})`);
    }
  }

  normalizeChatId(value) {
    if (!value) return "";
    if (typeof value === "string") return value;
    return value._serialized || value.user || "";
  }

  _isLidJid(value) {
    return /^[A-Za-z0-9._-]+@lid$/.test(String(value || ""));
  }

  _isPhoneJid(value) {
    return /^\d+@c\.us$/.test(String(value || ""));
  }

  _isGroupJid(value) {
    return /^[\d-]+@g\.us$/.test(String(value || ""));
  }

  _isSupportedSendJid(value) {
    return this._isPhoneJid(value) || this._isLidJid(value) || this._isGroupJid(value);
  }

  _sendableJidFromId(value) {
    const jid = this.normalizeChatId(value);
    return this._isSupportedSendJid(jid) ? jid : "";
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
    const normalized = String(lidJid || "");
    if (!this._isLidJid(normalized)) return null;
    const lidId = normalized.replace("@lid", "");
    if (this.lidCache.has(lidId)) return this.lidCache.get(lidId);
    try {
      const result = await this.client.getContactLidAndPhone([normalized]);
      if (result && result.length > 0 && result[0].pn) {
        const realPhone = (result[0].pn || "").replace(/@c\.us/g, "").replace(/\D/g, "");
        if (realPhone) { this.lidCache.set(lidId, realPhone); return realPhone; }
      }
    } catch (e) { this._log("[LID-READ] resolve falhou:", e.message); }
    return null;
  }

  // Grava o reverso telefone(digitos) -> "<lid>@lid". Chamado no inbound toda
  // vez que uma conversa LID resolve para um telefone. O ENVIO consulta isto:
  // se o destino conversa via LID, mandamos de volta para o JID @lid original
  // (chave que o store ja indexa), em vez de "<numero>@c.us" (que dispara a
  // resolucao phone->LID interna e falha com "Lid is missing in chat table").
  _rememberLidForPhone(phone, lidJid) {
    const digits = String(phone || "").replace(/\D/g, "");
    const jid = String(lidJid || "");
    if (!digits || !this._isLidJid(jid)) return;
    this.reverseLidCache.set(digits, jid);
  }

  // Resolve o JID de ENVIO para um destino arbitrario (numero, @c.us ou @lid).
  // Ordem de robustez:
  //   0. Ja e @lid           -> usa cru (store indexa por LID; Tier 1 do getChat).
  //   1. reverseLidCache      -> destino fala por LID e ja vimos no inbound: usa o
  //                              "<lid>@lid" memorizado (caminho que NUNCA falha,
  //                              pois e a mesma chave que recebeu a msg).
  //   2. getChatById("<num>@c.us") -> chat @c.us existe no store: usa o JID real
  //      dele (.id._serialized), que pode inclusive ser @lid. Confirma roteamento.
  //   3. getNumberId("<num>")      -> QueryExist no servidor; devolve o wid
  //      canonico registrado (lida com numero existente mas chat ainda nao no store).
  //   4. fallback "<num>@c.us"     -> ultimo recurso (numero sem historico de LID;
  //      WWebJS.getChat tenta a resolucao usync por conta propria).
  async _resolveSendJid(to) {
    const raw = String(to || "").trim();
    if (this._isLidJid(raw)) return raw;

    const digits = raw.replace(/\D/g, "");
    // Destinos com servidor explicito ficam limitados aos namespaces que este
    // worker envia de forma intencional. Nao encaminhe JID arbitrario cru para
    // o WhatsApp Web: entrada HTTP/CRM deve virar telefone, @c.us, @lid ou grupo.
    if (raw.includes("@")) {
      if (this._isPhoneJid(raw)) {
        // segue pelo fluxo normal: cache LID -> chat store -> number id -> @c.us
      } else if (this._isGroupJid(raw)) {
        return raw;
      } else {
        throw new Error("JID WhatsApp nao suportado para envio");
      }
    }
    if (!digits) throw new Error("Destino WhatsApp invalido");

    if (digits && this.reverseLidCache.has(digits)) {
      const lidJid = this.reverseLidCache.get(digits);
      this._log("[SEND-LID] usando JID @lid memorizado para", digits);
      return lidJid;
    }

    const cusJid = digits ? `${digits}@c.us` : raw;

    // getChatById: se o chat ja existe no store, seu .id._serialized e a chave
    // canonica de roteamento (pode ser @lid). Best-effort — nao quebra o envio.
    if (digits) {
      try {
        const chat = await this.client.getChatById(cusJid);
        const sid = chat && this._sendableJidFromId(chat.id);
        if (sid) {
          if (this._isLidJid(sid)) this._rememberLidForPhone(digits, sid);
          this._log("[SEND-LID] JID via getChatById:", sid);
          return sid;
        }
      } catch (_) { /* chat ainda nao no store — tenta getNumberId */ }

      // getNumberId: QueryExist no servidor devolve o wid registrado canonico.
      try {
        if (typeof this.client.getNumberId === "function") {
          const wid = await this.client.getNumberId(cusJid);
          const sid = wid && (wid._serialized || (wid.user && wid.server ? `${wid.user}@${wid.server}` : null));
          if (this._isSupportedSendJid(sid)) {
            this._log("[SEND-LID] JID via getNumberId:", sid);
            return sid;
          }
        }
      } catch (_) { /* numero nao registrado / metodo ausente — cai no fallback */ }
    }

    return cusJid;
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
    const includeProfilePics = Boolean(options.includeProfilePics);
    const chatRows = (await this.client.getChats())
      .filter((chat) => includeGroups || !chat.isGroup)
      .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0))
      .slice(0, limit);
    const conversations = chatRows
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
          profilePic: null,
          source: "whatsapp-web",
        };
      });

    if (includeProfilePics) {
      for (let i = 0; i < conversations.length; i += 1) {
        const conversation = conversations[i];
        if (!conversation.phone || String(conversation.jid || "").includes("@g.us")) continue;
        conversation.profilePic =
          await this._profilePicUrlForChat(chatRows[i]) ||
          await this.getProfilePicUrl(conversation.jid || conversation.phone);
      }
    }

    return conversations;
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
    // Resolve o JID de ENVIO de forma robusta. Na era de LID-addressing o
    // WhatsApp Web indexa a "chat table" pelo LID: mandar para "<numero>@c.us"
    // forca a resolucao usync phone->LID interna que, quando o interlocutor so
    // existe no store como LID, lanca "Lid is missing in chat table" (erro vindo
    // do proprio JS do WA Web). _resolveSendJid prefere o "<lid>@lid" que o store
    // ja conhece (reverseLidCache preenchido no inbound, getChatById, getNumberId).
    const chatId = await this._resolveSendJid(to);
    const _send = (jid) =>
      options
        ? this.client.sendMessage(jid, text, options)
        : this.client.sendMessage(jid, text);

    try {
      const result = await _send(chatId);
      this._log(`[SEND] Para ${to} (jid=${chatId})`);
      return result;
    } catch (err) {
      // Retry dirigido: o envio @c.us bateu no "Lid is missing in chat table" e
      // o resolver ainda nao tinha um @lid (cache frio + getChatById/getNumberId
      // sem sucesso). Tenta uma ultima resolucao LID e reenvia para o @lid antes
      // de desistir. So entra aqui quando NAO mandamos ja para um @lid.
      const msg = String(err && err.message ? err.message : err);
      const lidMissing = /lid is missing|missing in chat table/i.test(msg);
      if (lidMissing && !this._isLidJid(chatId)) {
        const digits = String(to).replace(/\D/g, "");
        let lidJid = digits && this.reverseLidCache.get(digits);
        if (lidJid && !this._isLidJid(lidJid)) lidJid = null;
        if (!lidJid) {
          // Ultimo recurso: pede o LID ao store via getChatById (.id pode ser @lid).
          try {
            const chat = await this.client.getChatById(`${digits}@c.us`);
            const sid = chat && this._sendableJidFromId(chat.id);
            if (this._isLidJid(sid)) { lidJid = sid; this._rememberLidForPhone(digits, sid); }
          } catch (_) { /* sem chat — propaga o erro original abaixo */ }
        }
        if (lidJid && lidJid !== chatId) {
          this._warn(`[SEND] "${msg}" para ${chatId} — retry via LID ${lidJid}`);
          const result = await _send(lidJid);
          this._log(`[SEND] Para ${to} (jid=${lidJid}, via retry-lid)`);
          return result;
        }
      }
      throw err;
    }
  }

  // --- Fonte unica de verdade da conexao --------------------------------
  // Carimba atividade inbound (message/message_ack). Trafego recebido = prova
  // de que o socket WhatsApp esta vivo — o sinal mais forte e mais barato.
  _touchActivity() { this._lastInboundMs = Date.now(); }

  // Houve inbound dentro da janela de liveness? Mais confiavel que getState()
  // (lento/instavel no remote runtime CPU-only, 15s de timeout).
  _isLive() {
    return this._lastInboundMs > 0 &&
      (Date.now() - this._lastInboundMs) < this._LIVENESS_WINDOW_MS;
  }

  // CONECTADO = derivacao UNICA, usada por getStatus/getSessionHealth/
  // getStatusVerified/assertReady. Acaba com o drift dos 7 escritores das flags:
  // (evento ready disparou) OU (atividade recente) OU (estado real CONNECTED).
  // Atividade recente SOBREPOE qualquer flag cacheada de "disconnected" — cura o
  // "fantasma desconectado" (socket recebe mensagens mas isReady ficou preso).
  isConnected() {
    return Boolean(this.isReady) || this._isLive() || this.connectionState === "CONNECTED";
  }

  getStatus() {
    const connected = this.isConnected();
    return {
      orgId: this.orgId,
      status: connected ? "ready" : this.status,
      isReady: connected,
      hasQrCode: !!this.qrCode,
      hasPairingCode: !!this.pairingCode,
      pairingCode: this.pairingCode,
      pairingPhoneNumber: this.pairingPhoneNumber
    };
  }

  getSessionHealth() {
    const connected = this.isConnected();
    const status = connected ? "ready" : (this.status || "unknown");
    const action = this._recommendedAction(status);
    const qrAgeSeconds = this.qrTimestamp ? Math.max(0, Math.round((Date.now() - this.qrTimestamp) / 1000)) : null;
    return {
      orgId: this.orgId,
      status,
      connected,
      isReady: connected,
      live: this._isLive(),
      realState: this.connectionState || null,
      sessionPresent: this._sessionLooksPresent(),
      backups: {
        lastGood: this._dirLooksPresent(this._backupDir("__lastgood")),
        prewipe: this._dirLooksPresent(this._backupDir("__prewipe")),
      },
      qr: {
        available: Boolean(this.qrCode),
        ageSeconds: qrAgeSeconds,
      },
      pairing: {
        available: Boolean(this.pairingCode),
        phone: this._maskedPairingPhone(),
      },
      watchdog: {
        active: Boolean(this._healthTimer),
        intervalSeconds: 60,
        lastCheckAt: this._lastWatchdogAt,
        lastState: this._lastHealthState,
        failures: Number(this._watchdogFailures || 0),
        reconnecting: Boolean(this._reconnecting),
        lastReconnectAt: this._lastReconnectAt,
      },
      authFailures: {
        count: Number(this._authFailureCount || 0),
        max: Number(this._AUTH_FAILURE_MAX || 0),
        limitReached: Number(this._authFailureCount || 0) > Number(this._AUTH_FAILURE_MAX || 0),
      },
      lastEvent: this._lastEvent,
      lastEventAt: this._lastEventAt,
      lastError: this._lastError,
      requiresPairing: !connected && (Boolean(this.qrCode || this.pairingCode) || action === "scan_qr" || action === "enter_pairing_code"),
      safeToReconnect: true,
      recommendedAction: action,
      nextStep: this._nextStep(action),
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
        new Promise((_, rej) => setTimeout(() => rej(new Error("getState timeout")), 25000))
      ]);
      return state || "UNKNOWN";
    } catch (e) {
      return "UNREACHABLE";
    }
  }

  // Status VERIFICADO — nao confia na flag isReady cacheada; checa o estado
  // real. O /api/status usa isto para o front nunca mostrar "conectado"
  // quando a sessao na verdade caiu.
  // Status VERIFICADO — SEM efeitos colaterais. O watchdog e' o UNICO dono da
  // reconexao; um read endpoint jamais dispara reconnect (era a fonte do churn).
  // Atividade inbound recente comprova o socket e dispensa o getState() lento.
  async getStatusVerified() {
    const rawStatus = this.status;   // ANTES de getStatus() derivar 'ready'
    const base = this.getStatus();
    if (rawStatus === "awaiting_scan" || rawStatus === "awaiting_pairing" || !this.client) {
      return { ...base, isReady: false, status: rawStatus, connected: false, realState: this.connectionState || null };
    }
    if (this._isLive()) {
      return { ...base, isReady: true, status: "ready", connected: true, realState: "CONNECTED" };
    }
    // isReady (evento 'ready' disparou e o watchdog o mantem) e' verdade: NAO
    // deixar um unico getState() lento/UNREACHABLE do remote runtime derrubar uma sessao
    // saudavel porem quieta (>120s sem inbound). So o watchdog (3 strikes)
    // rebaixa isReady; aqui apenas reportamos. Mata o fantasma no caminho quieto.
    if (this.isReady) {
      return { ...base, isReady: true, status: "ready", connected: true, realState: this.connectionState || "CONNECTED" };
    }
    const realState = await this.getRealState();
    const connected = realState === "CONNECTED" || this._isLive();
    return {
      ...base,
      isReady: connected,
      status: connected ? "ready" : (this.qrCode ? "awaiting_scan" : (base.status || "disconnected")),
      connected,
      realState,
    };
  }

  // Reconecta PRESERVANDO a sessao salva (.wwebjs_auth NAO e apagado). Se a
  // sessao ainda for valida, reconecta sem QR; se morreu de vez, o initialize
  // emite 'qr' e o front mostra o QR de novo.
  async softReconnect() {
    const reason = arguments.length > 0 ? arguments[0] : "";
    const options = arguments.length > 1 ? (arguments[1] || {}) : {};
    if (this._reconnecting) return;
    // Teardown DELIBERADO (disconnect()/LGPD): nao ressuscita. O self-heal do
    // server-lite e qualquer outro gatilho param aqui — a sessao so volta por
    // acao explicita (initialize/reconnect), que zera _intentionalDown.
    const explicit = Boolean(options && options.explicit);
    if (this._isIntentionalDown() && !explicit) { this._log("[RECONNECT] abortado — teardown deliberado"); return; }
    if (explicit) this._clearIntentionalDown();
    // Socket vivo (atividade recente) => NAO reconecta. Era a causa do churn:
    // uma divergencia transitoria do getState derrubava uma sessao saudavel.
    if (this._isLive()) {
      this._log(`[RECONNECT] abortado — atividade recente, socket vivo${reason ? " [" + reason + "]" : ""}`);
      this.isReady = true;
      this.status = "ready";
      return;
    }
    // Cooldown + backoff exponencial limitado; um 'ready'/atividade zera o contador.
    const now = Date.now();
    const minGap = Math.min(60000 * Math.pow(2, this._reconnectAttempts || 0), 15 * 60000); // 1,2,4,8min -> teto 15min
    if (this._lastReconnectMs && now - this._lastReconnectMs < minGap) {
      const left = Math.round((minGap - (now - this._lastReconnectMs)) / 1000);
      this._log(`[RECONNECT] cooldown ativo (${left}s, tentativa ${this._reconnectAttempts}) — pulando${reason ? " [" + reason + "]" : ""}`);
      return;
    }
    this._reconnecting = true;
    this._lastReconnectMs = now;
    this._reconnectAttempts = (this._reconnectAttempts || 0) + 1;
    this._lastReconnectAt = new Date().toISOString();
    this._markEvent("soft_reconnect", reason ? { reason } : null);
    this._log(`[RECONNECT] soft reconnect #${this._reconnectAttempts} (preserva a sessao)${reason ? " — " + reason : ""}...`);
    try {
      if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
      try { if (this.client) await this.client.destroy(); } catch (e) {}
      this.client = null;
      this.isReady = false;
      this.connectionState = "RECONNECTING";   // limpa CONNECTED stale (isConnected nao mente no reconnect)
      this.status = "reconnecting";
      if (explicit) {
        await this.initialize(null, { explicit });
      } else {
        await this.initialize();
      }
    } catch (e) {
      this._log("[RECONNECT] erro:", e.message);
      this._markEvent("soft_reconnect_failed", { error: e && e.message ? e.message : e });
    } finally {
      this._reconnecting = false;
      // O watchdog DEVE sobreviver a qualquer reconnect (ver _ensureHealthMonitor).
      this._ensureHealthMonitor();
    }
  }

  // Monitor de saude: a cada 60s confere o estado real. 3 falhas seguidas (sem
  // atividade inbound) => sessao morta (ex.: Chromium travou) => soft reconnect
  // automatico. Cura o "conectado fantasma" sem intervencao manual.
  _ensureHealthMonitor() {
    // Idempotente: garante o watchdog vivo. Chamado nos finally de initialize()
    // e softReconnect() pra que o monitor NUNCA morra permanentemente (era a
    // causa do active:false eterno quando client.initialize() travava no remote runtime).
    if (!this._healthTimer) this._startHealthMonitor();
  }

  _startHealthMonitor() {
    if (this._healthTimer) clearInterval(this._healthTimer);
    let bad = 0;
    this._watchdogFailures = 0;
    this._lastHealthState = this.connectionState || this.status || null;
    // Geracao: invalida ticks em-voo de um interval anterior. clearInterval NAO
    // cancela um callback ja suspenso num await (getState, 15s) — sem isto um tick
    // antigo ressuscitaria uma sessao derrubada de proposito (disconnect()).
    const myGen = (this._monitorGen = (this._monitorGen || 0) + 1);
    this._healthTimer = setInterval(async () => {
      if (myGen !== this._monitorGen || this._intentionalDown) return;
      if (this._reconnecting) return;
      this._lastWatchdogAt = new Date().toISOString();
      if (this.status === "awaiting_scan" || this.status === "awaiting_pairing") {
        bad = 0;
        this._watchdogFailures = 0;
        this._lastHealthState = this.status;
        return;
      }
      // Atividade inbound recente = sessao viva. Promove e zera strikes SEM pagar
      // o getState() (15s no pior caso). Cura o "fantasma desconectado".
      if (this._isLive()) {
        bad = 0;
        this._watchdogFailures = 0;
        this._lastHealthState = "ACTIVE";
        if (!this.isReady) {
          this.isReady = true;
          this.status = "ready";
          this._reconnectAttempts = 0;
          this._lastReconnectMs = 0;
          this._log("[HEALTH] promovido a ready (atividade recente comprova o socket)");
        }
        return;
      }
      const state = await this.getRealState();
      // Tick obsoleto / sessao intencionalmente derrubada durante o await: aborta
      // sem agir (nao ressuscita o que o usuario desconectou de proposito).
      if (myGen !== this._monitorGen || this._intentionalDown || this._reconnecting) return;
      this.connectionState = state;   // mantem isConnected() coerente com a verdade
      if (state === "CONNECTED") {
        bad = 0;
        this._watchdogFailures = 0;
        this._lastHealthState = state;
        if (!this.isReady) {
          this.isReady = true;
          this.status = "ready";
          this._reconnectAttempts = 0;
          this._lastReconnectMs = 0;
          this._log("[HEALTH] promovido a ready (getState=CONNECTED)");
        }
        return;
      }
      // Latencia remote runtime (India): um getState() lento/UNREACHABLE NAO prova sessao
      // morta. Estados DEFINITIVAMENTE mortos derrubam rapido (e os eventos
      // change_state/disconnected ja pegam esses na hora); estados AMBIGUOS
      // (UNREACHABLE/UNKNOWN/timeout do getState num link de alta latencia)
      // toleram MUITO mais antes do teardown — senao o watchdog destruia uma
      // sessao saudavel-porem-quieta a cada ~3min ("cai sozinho a cada 4min").
      // Um unico CONNECTED ou inbound zera os strikes. (fix 11/06: ping-da-India)
      const _dead = /UNPAIRED|CONFLICT|DEPRECATED|UNLAUNCHED|DESTROYED|NO_CLIENT/i.test(String(state));
      const _limit = _dead ? 3 : 10;
      bad += 1;
      this._watchdogFailures = bad;
      this._lastHealthState = state;
      this._log(`[HEALTH] estado=${state} sem atividade (falha ${bad}/${_limit})`);
      if (bad >= _limit) {
        bad = 0;
        this._watchdogFailures = 0;
        if (this._isAmbiguousHealthState(state)) {
          this._markEvent("watchdog_reconnect_ambiguous", { reason: state });
          this._warn(`[HEALTH] estado ambíguo persistente (${state}) — soft reconnect silencioso, sem alerta de QR`);
          this.softReconnect("health-monitor:" + state);
          return;
        }
        this.isReady = false;
        this.status = "disconnected";
        this._markEvent("watchdog_reconnect", { reason: state });
        this.emit("disconnected", "health-monitor:" + state);
        this.softReconnect("health-monitor:" + state);
      }
    }, 60000);
    if (this._healthTimer.unref) this._healthTimer.unref();
  }

  getQrCode() { return this.qrCode; }
  getQrTimestamp() { return this.qrTimestamp; }
  getPairingCode() { return this.pairingCode; }
  async disconnect() {
    // Teardown DELIBERADO: zera TODA a fonte de verdade. Sem isto, _lastInboundMs
    // recente + this.client truthy + connectionState='CONNECTED' faziam
    // isConnected() mentir "ready" por ate 120s apos o usuario clicar Desconectar,
    // e assertReady() passava => operacoes batiam num browser ja destruido.
    this._markIntentionalDown();
    this._monitorGen = (this._monitorGen || 0) + 1;   // invalida tick do watchdog em voo
    if (this._readyTimeout) { clearTimeout(this._readyTimeout); this._readyTimeout = null; }
    if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
    if (this.client) { try { await this.client.destroy(); } catch (e) {} }
    this.client = null;
    this.isReady = false;
    this._lastInboundMs = 0;
    this.connectionState = "DISCONNECTED";
    this.status = "disconnected";
    this._markEvent("disconnect_preserve_session");
  }

  async requestPairingCode(phoneNumber) {
    const cleanPhone = phoneNumber.replace(/\D/g, "");
    if (!cleanPhone || cleanPhone.length < 10) {
      throw new Error("Invalid phone number. Use format: +1 (940) 618-3140 or 19406183140");
    }
    this._log("[PAIRING] Requesting pairing code for:", cleanPhone);
    this._markEvent("pairing_requested");
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

  async clearAndReinitialize(phoneNumber = null, options = {}) {
    this._log("[PAIRING] Clearing auth and reinitializing...");
    this._markEvent(phoneNumber ? "pairing_reinitialize" : "session_wipe_reinitialize");
    try {
      if (this.client) { await this.client.destroy(); }
    } catch (e) { this._log("[PAIRING] Error destroying client:", e.message); }

    if (this._readyTimeout) { clearTimeout(this._readyTimeout); this._readyTimeout = null; }
    if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
    this._monitorGen = (this._monitorGen || 0) + 1;   // invalida tick do watchdog em voo
    this.client = null;
    this.isReady = false;
    this._lastInboundMs = 0;            // invalida prova-de-vida stale (mascarava awaiting_*)
    this.connectionState = "DISCONNECTED"; // limpa CONNECTED cacheado
    this.qrCode = null;
    this.pairingCode = null;
    this.pairingPhoneNumber = null;
    this.status = "disconnected";

    // Apenas a sessao DA org corrente — outras orgs continuam vivas.
    const sessionPath = this._sessionDir();
    // PROFILAXIA: snapshot de seguranca ANTES de apagar — qualquer wipe (timeout,
    // /api/disconnect ou re-pair) fica recuperavel via _bak-...__prewipe.
    this._snapshotSession("__prewipe");
    // Wipe/re-pair explicito nao pode ser desfeito pelo restore automatico do
    // ultimo backup saudavel; manter so o __prewipe para recuperacao manual.
    // EXCECAO (Frente 3): a recuperacao automatica de auth_failure pede
    // preserveLastGood — se a rejeicao for transiente, o auto-cura do proximo
    // boot restaura __lastgood em vez de forcar QR. __prewipe (acima) e' sempre tirado.
    const preserveLastGood = Boolean(options && options.preserveLastGood);
    if (!preserveLastGood) {
      this._discardLastGoodBackup(phoneNumber ? "pairing reinitialize" : "wipe reinitialize");
    } else {
      this._log("[AUTO-CURA] __lastgood preservado (recuperacao de auth_failure)");
    }
    try {
      if (fs.existsSync(sessionPath)) {
        fs.rmSync(sessionPath, { recursive: true, force: true });
        this._log("[PAIRING] Auth folder cleared");
      }
    } catch (e) { this._log("[PAIRING] Error clearing auth:", e.message); }

    await this.initialize(phoneNumber, { explicit: true });

    if (phoneNumber) {
      this._log("[PAIRING] Reinitialized with pairing mode for:", phoneNumber);
    } else {
      this._log("[PAIRING] Reinitialized - waiting for QR code...");
      return new Promise((resolve, reject) => {
        let checkQR;
        const timeout = setTimeout(() => {
          if (checkQR) clearInterval(checkQR);   // vazava: interval seguia pollando p/ sempre
          reject(new Error("Timeout waiting for QR code after reinitialization"));
        }, 30000);
        checkQR = setInterval(() => {
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
  async ensureInitialized(orgId, phoneNumber = null, options = {}) {
    const client = this.getOrCreate(orgId);
    const explicit = Boolean(options && options.explicit) || Boolean(phoneNumber);
    if (!explicit && typeof client._isIntentionalDown === "function" && client._isIntentionalDown()) {
      client._intentionalDown = true;
      return client;
    }
    // Nao dispara um 2o initialize se ja ha um em voo (janela client=null durante
    // softReconnect/clearAndReinitialize) — evita duplo Chromium no mesmo profile.
    if (!client.client && !client._initInFlight && !client._reconnecting) {
      await client.initialize(phoneNumber, { explicit });
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
      const health = c && typeof c.getSessionHealth === "function" ? c.getSessionHealth() : null;
      return {
        orgId,
        status: status ? status.status : "unknown",
        isReady: status ? status.isReady : false,
        hasQrCode: status ? status.hasQrCode : false,
        requiresPairing: health ? health.requiresPairing : Boolean(status && (status.hasQrCode || status.hasPairingCode)),
        recommendedAction: health ? health.recommendedAction : null,
        watchdog: health ? health.watchdog : null,
        sessionPresent: health ? health.sessionPresent : false,
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
