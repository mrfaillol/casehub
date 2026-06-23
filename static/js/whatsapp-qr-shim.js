/**
 * whatsapp-qr-shim.js — fix de UX da tela "Conectar WhatsApp" sem editar
 * static/js/chat.js (208KB, evitando reescrita risk de transcrição).
 *
 * Bug-fix companion ao patch backend em services/whatsapp-bot/server-lite.js
 * (PR casehub#645). O chat.js original tem:
 *
 *     if (data.qr) { render QR }
 *     else if (data.connected) { spinner "Conectando..." }
 *     else { render "QR indisponível" }   // ← caia em TODOS qr=null cases
 *
 * Backend agora retorna {qr, connected, isReady, status, pairingCode}, mas:
 *   1. O branch "QR indisponível" ainda é dead-end quando status='awaiting_scan'
 *      durante cold-start de Puppeteer (~5-10s no primeiro hit por org).
 *   2. Não distingue "já conectado" de "ainda iniciando" pra logging.
 *
 * Este shim sobrescreve window.loadQRCode com lógica state-aware:
 *   - qr presente → render QR
 *   - isReady/connected → "Conectado, carregando conversas..." (intermediate)
 *   - status='awaiting_scan'|'initializing'|'reconnecting'|'disconnected'
 *     → spinner + auto-retry em 2s (cold-start gracioso)
 *   - qualquer outro caso → "QR temporariamente indisponível [Tentar de novo]"
 *
 * Carregado após chat.js no template app/whatsapp/chat.html (mesmo block
 * extra_js, mesmo defer attribute — ordem de execução garantida).
 *
 * Refs:
 *   - PR casehub#645 backend
 *   - WhatsApp do UsuarioDemo 2026-05-28 08:27 "O QR não tá aparecendo"
 *   - services/whatsapp-bot/whatsapp-client.js v4.0 multi-session F29
 */
(function () {
  "use strict";

  // Defensive guard: chat.js define loadQRCode no escopo global; este script
  // tem `defer` e ordem garantida atrás do chat.js, mas vale checar.
  if (typeof window.loadQRCode !== "function") {
    console.warn(
      "[wa-qr-shim] loadQRCode nao definido — chat.js falhou ao carregar? skip shim."
    );
    return;
  }
  if (typeof window.fetchAPI !== "function") {
    console.warn("[wa-qr-shim] fetchAPI nao definido — skip shim.");
    return;
  }

  const _escape =
    typeof window.escapeHtml === "function"
      ? window.escapeHtml
      : function (s) {
          return String(s || "").replace(/[&<>"']/g, function (c) {
            return {
              "&": "&amp;",
              "<": "&lt;",
              ">": "&gt;",
              '"': "&quot;",
              "'": "&#39;",
            }[c];
          });
        };

  // Any non-ready state where a QR is plausibly still on its way. We treat the
  // set as "everything that is not an explicit ready/connected" — the previous
  // allow-list silently dead-ended on statuses it didn't enumerate
  // ("authenticated", "auth_failed", "unknown", "connecting", ...), which is
  // exactly what made the apex (default org) show "QR indisponível" forever
  // while a subdomain tenant worked. Now ANY unknown/transient state retries.
  const READY_STATUSES = new Set(["ready", "connected"]);

  // After this many polls with no QR and no progress, ask the backend for a
  // soft reconnect (POST /api/reconnect). The bot preserves LocalAuth and only
  // emits a fresh QR if the saved session cannot reconnect.
  const FORCE_REINIT_AFTER = 4;

  let _retryHandle = null;
  let _emptyPolls = 0;
  let _reinitInFlight = false;
  // Last QR data: URI actually painted. The bot rotates the QR every ~20s and the
  // front polls faster; only swap the <img> when the QR truly changes so a rotated
  // code appears immediately without rebuilding the same image every poll.
  let _lastRenderedQr = null;

  function _clearRetry() {
    if (_retryHandle) {
      clearTimeout(_retryHandle);
      _retryHandle = null;
    }
  }

  function _scheduleRetry(ms) {
    _clearRetry();
    _retryHandle = setTimeout(function () {
      _retryHandle = null;
      window.loadQRCode();
    }, ms);
  }

  function _setConnectState(text) {
    if (typeof window.setConnectStateText === "function") {
      window.setConnectStateText(text);
    }
  }

  // Ask the backend to reconnect when the session is wedged. Uses the existing
  // /api/reconnect route (tenant-scoped via X-Org-Id on the backend). Guarded
  // so we only fire once per stuck streak.
  async function _forceReinit() {
    if (_reinitInFlight) return;
    _reinitInFlight = true;
    try {
      const base =
        window.WA_API_BASE ||
        (typeof CASEHUB_PREFIX !== "undefined" ? CASEHUB_PREFIX : "/casehub") +
          "/whatsapp-chat";
      await fetch(base + "/api/reconnect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
    } catch (e) {
      console.warn("[wa-qr-shim] forceReinit falhou:", e && e.message);
    } finally {
      _reinitInFlight = false;
    }
  }

  window.loadQRCode = async function loadQRCode() {
    const container = document.getElementById("qrCode");
    if (!container) return;

    try {
      const data = await window.fetchAPI("/api/qr");

      const status = String((data && data.status) || "").toLowerCase();
      const ready = !!(data && (data.isReady || data.connected)) || READY_STATUSES.has(status);

      // Branch 1: QR presente → render (caso ideal, sessão aguardando scan).
      if (data && data.qr) {
        _clearRetry();
        _emptyPolls = 0;
        _setConnectState("Aguardando leitura do QR");
        if (data.qr !== _lastRenderedQr) {
          container.innerHTML =
            '<img src="' +
            _escape(data.qr) +
            '" alt="QR code para conectar o WhatsApp">';
          _lastRenderedQr = data.qr;
        }
      }
      // Branch 2: sessão já autenticada/conectada → updateStatusUI cuida do
      // resto no próximo poll de checkStatus(); placeholder amigável.
      else if (ready) {
        _clearRetry();
        _emptyPolls = 0;
        _lastRenderedQr = null;
        _setConnectState("Conectado");
        container.innerHTML =
          '<div class="wa-loading"><div class="wa-spinner" aria-hidden="true"></div>Conectado, carregando conversas…</div>';
      }
      // Branch 3: sem QR e não conectado. Qualquer estado (conhecido,
      // transitório OU desconhecido) entra aqui: mostramos spinner e
      // auto-retry — nunca mais o dead-end "QR indisponível". Depois de
      // FORCE_REINIT_AFTER polls sem progresso, pedimos ao backend uma nova
      // sessão (cura o caso da org default que subiu stale no boot).
      else {
        _emptyPolls += 1;
        _lastRenderedQr = null;
        if (_emptyPolls >= FORCE_REINIT_AFTER) {
          _emptyPolls = 0;
          _setConnectState("Reconectando WhatsApp");
          container.innerHTML =
            '<div class="wa-loading"><div class="wa-spinner" aria-hidden="true"></div>Reconectando WhatsApp…</div>';
          _forceReinit();
          _scheduleRetry(3500);
        } else {
          _setConnectState("Aguardando conexão");
          container.innerHTML =
            '<div class="wa-loading"><div class="wa-spinner" aria-hidden="true"></div>Iniciando conexão (até 15s)…</div>';
          _scheduleRetry(2000);
        }
      }

      // Pairing-code fallback (bot pode emitir junto com QR).
      if (typeof window.updatePairingCode === "function") {
        window.updatePairingCode(
          data ? data.pairingCode || data.code || data.pairing_code : null
        );
      }
    } catch (error) {
      // Erro de rede / proxy / 502 do bot. Mostra spinner + auto-retry em 3s.
      console.warn(
        "[wa-qr-shim] erro fetch /api/qr, retry em 3s:",
        error && error.message
      );
      container.innerHTML =
        '<div class="wa-loading"><div class="wa-spinner" aria-hidden="true"></div>Aguardando bot do WhatsApp…</div>';
      _setConnectState("Aguardando bot do WhatsApp");
      _scheduleRetry(3000);
    }
  };

  // Limpa retry pendente quando o usuário sai da tela (changes module etc).
  window.addEventListener("beforeunload", _clearRetry);

  console.log(
    "[wa-qr-shim] loadQRCode override active (multi-tenant aware, retry on cold-start)"
  );
})();
