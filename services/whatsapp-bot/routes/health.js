/**
 * Health, Status, QR, Metrics & UI Routes
 * Extracted from server.js - Fase 2.1 Decomposition
 *
 * Routes:
 *   GET  /              - Root status info
 *   GET  /qr            - QR code page (HTML)
 *   POST /pairing-code  - Request pairing code
 *   POST /api/pairing-code     - Request pairing code (alias /api prefix)
 *   POST /api/send-message     - Send a text message
 *   GET  /health        - Health check
 *   GET  /stats         - Stats page (HTML)
 *   GET  /ui            - Chat UI (token-protected)
 *   GET  /ui/health     - UI health check
 *   GET  /monitor       - Monitor dashboard (token-protected)
 *   POST /api/disconnect       - Force WhatsApp disconnect
 *   GET  /api/status           - WhatsApp connection status
 *   GET  /api/qr               - QR code (JSON)
 *   GET  /api/metrics          - Metrics (JSON)
 *   GET  /api/metrics/html     - Metrics dashboard (HTML)
 *
 * Deps:
 *   whatsappClient  - required.
 *   db              - OPTIONAL. The lite/alpha server (server-lite.js) é
 *                     stateless e NÃO passa db. Quando db é null, as rotas
 *                     que dependem dele (/health DB check, /stats, /api/metrics)
 *                     degradam graciosamente em vez de quebrar.
 */

const express = require('express');
const path = require('path');

module.exports = function(deps) {
  const { whatsappClient, db } = deps || {};
  const router = express.Router();

  if (!whatsappClient) {
    throw new Error('routes/health.js requires { whatsappClient }');
  }

  const UI_ACCESS_TOKEN = process.env.UI_ACCESS_TOKEN || 'CaseHub_WhatsApp_Secret';

  // ===== ROOT STATUS =====
  router.get("/", (req, res) => {
    res.json({
      bot: "CaseHub Bot v8.2 (Moskit + Calendly + Stripe + Email + Telegram + Score + Forms + Conversion Tracking)",
      ...whatsappClient.getStatus()
    });
  });

  // ===== QR CODE PAGE (HTML) =====
  router.get("/qr", (req, res) => {
    const status = whatsappClient.getStatus();
    const qrCode = whatsappClient.getQrCode();
    if (status.isReady) {
      res.send("<html><body style='text-align:center;padding:50px;font-family:Arial'><h1>Conectado</h1><p>Bot v8.2</p></body></html>");
    } else if (qrCode) {
      res.send("<html><body style='text-align:center;padding:50px;font-family:Arial'><h1>QR</h1><img src='" + qrCode + "' style='max-width:300px'></body></html>");
    } else {
      res.send("<html><head><meta http-equiv='refresh' content='3'></head><body style='text-align:center;padding:50px'><h2>Aguarde...</h2></body></html>");
    }
  });

  // ===== PAIRING CODE =====
  // Fallback de conexão quando o QR não pode ser escaneado: o operador
  // informa o número e recebe um código de 8 dígitos para digitar em
  // WhatsApp > Aparelhos conectados > Conectar com número de telefone.
  async function handlePairingCode(req, res) {
    try {
      const { phone } = req.body || {};

      if (!phone) {
        return res.status(400).json({
          success: false,
          error: "Phone number is required. Use format: +1 (940) 618-3140 or 19406183140"
        });
      }

      const status = whatsappClient.getStatus();

      if (status.isReady) {
        return res.status(400).json({
          success: false,
          error: "WhatsApp already connected. Call /api/disconnect first to get a new pairing code.",
          currentStatus: status
        });
      }

      console.log("[PAIRING-CODE] Request for:", phone);
      console.log("[PAIRING-CODE] This will clear the current session and reinitialize...");

      const code = await whatsappClient.requestPairingCode(phone);

      res.json({
        success: true,
        code: code,
        phone: phone,
        instructions: [
          "1. Open WhatsApp on your phone",
          "2. Go to Settings > Linked Devices",
          "3. Tap 'Link a Device'",
          "4. Tap 'Link with phone number instead'",
          "5. Enter this code: " + code
        ],
        message: "Enter this code in WhatsApp > Linked Devices > Link a Device > Link with phone number"
      });

    } catch (error) {
      console.error("[PAIRING-CODE] Error:", error.message);
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  }

  // Montado em dois paths: o legado /pairing-code e o /api/pairing-code que
  // o proxy /whatsapp-api do FastAPI espera (contrato uniforme sob /api).
  router.post("/pairing-code", handlePairingCode);
  router.post("/api/pairing-code", handlePairingCode);

  // ===== API: SEND MESSAGE =====
  // Disparo de mensagem de texto a partir do CaseHub (proxy /whatsapp-api).
  // Aceita { phone, message } (contrato do clone) e o alias { to, text }.
  async function handleSendMessage(req, res) {
    const body = req.body || {};
    const phone = body.phone || body.to;
    const message = body.message || body.text;
    const replyTo = body.reply_to_wa_message_id || body.replyToWaMessageId || body.quotedMessageId;
    if (!phone || !message) {
      return res.status(400).json({ ok: false, error: "phone and message required" });
    }
    try {
      const options = replyTo ? { quotedMessageId: String(replyTo) } : undefined;
      const result = await whatsappClient.sendMessage(String(phone), String(message), options);
      res.json({
        ok: true,
        // ID da mensagem enviada — o backend o usa para casar os ticks
        // que chegam depois via message_ack.
        messageId:
          result && result.id && result.id._serialized
            ? result.id._serialized
            : null
      });
    } catch (err) {
      console.error("[send-message]", err.message);
      res.status(502).json({ ok: false, error: err.message });
    }
  }

  router.post("/api/send-message", handleSendMessage);
  router.post("/api/send", handleSendMessage);

  // ===== FORCE DISCONNECT =====
  router.post("/api/disconnect", async (req, res) => {
    try {
      console.log("[DISCONNECT] Forcing disconnection and clearing session...");
      await whatsappClient.clearAndReinitialize();

      res.json({
        success: true,
        message: "Session cleared and reinitialized. QR code should be available now at /qr",
        status: whatsappClient.getStatus()
      });
    } catch (error) {
      console.error("[DISCONNECT] Error:", error.message);
      res.status(500).json({
        success: false,
        error: error.message
      });
    }
  });

  // ===== HEALTH CHECK =====
  router.get("/health", async (req, res) => {
    const checks = {};
    let healthy = true;

    // WhatsApp connection
    try {
      const waStatus = whatsappClient.getStatus();
      checks.whatsapp = { ok: waStatus.isReady, status: waStatus.status || (waStatus.isReady ? 'ready' : 'disconnected') };
      if (!waStatus.isReady) healthy = false;
    } catch (e) {
      checks.whatsapp = { ok: false, error: e.message };
      healthy = false;
    }

    // Database connection (opcional — server-lite.js roda sem db)
    if (db && typeof db.testConnection === 'function') {
      try {
        const dbOk = await db.testConnection();
        checks.database = { ok: dbOk };
        if (!dbOk) healthy = false;
      } catch (e) {
        checks.database = { ok: false, error: e.message };
        healthy = false;
      }
    } else {
      // Modo lite: bot é stateless, persistência fica no FastAPI/Postgres.
      checks.database = { ok: true, mode: 'stateless' };
    }

    // Memory usage
    const mem = process.memoryUsage();
    checks.memory = {
      rss_mb: Math.round(mem.rss / 1024 / 1024),
      heap_used_mb: Math.round(mem.heapUsed / 1024 / 1024),
      heap_total_mb: Math.round(mem.heapTotal / 1024 / 1024)
    };

    // Uptime
    checks.uptime_seconds = Math.round(process.uptime());

    res.status(healthy ? 200 : 503).json({
      ok: healthy,
      version: "2.0.0",
      architecture: "decomposed-v13.4",
      checks,
      timestamp: new Date().toISOString()
    });
  });

  // ===== STATS PAGE (HTML) =====
  router.get("/stats", async (req, res) => {
    if (!db || typeof db.getStats !== 'function') {
      return res.send("<html><body style='text-align:center;padding:50px;font-family:Arial'>" +
        "<h1>Bot (lite)</h1><p>Stats indisponíveis — bot stateless. " +
        "Métricas ficam no CaseHub.</p></body></html>");
    }
    try {
      const stats = await db.getStats();
      const ws = whatsappClient.getStatus();
      res.send(`<html><head><meta http-equiv='refresh' content='30'></head>
        <body style='font-family:Arial;padding:30px;text-align:center'>
          <h1>Bot v8.2</h1>
          <p>${ws.isReady ? "Online" : "Offline"}</p>
          <p>Total: ${stats.total} | Hoje: ${stats.today}</p>
          <p>Consultas Pagas: ${stats.paidConsultations} | Gratuitas: ${stats.freeConsultations}</p>
          <p>Agendados: ${stats.scheduledTotal}</p>
        </body></html>`);
    } catch (e) { res.status(500).json({ error: e.message }); }
  });

  // ===== UI SERVING =====
  router.get('/ui', (req, res) => {
    const token = req.query.token;
    if (token !== UI_ACCESS_TOKEN) {
      return res.status(401).send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Acesso Restrito - CaseHub WhatsApp</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #0b141a;
                    color: #e9edef;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    text-align: center;
                }
                .container { padding: 40px; }
                h1 { font-size: 48px; margin-bottom: 16px; }
                p { color: #8696a0; font-size: 16px; }
                .hint { margin-top: 30px; font-size: 13px; color: #5a6a74; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>&#128274;</h1>
                <h2>Acesso Restrito</h2>
                <p>Token invalido ou ausente.</p>
                <p class="hint">Contate o administrador para obter acesso.</p>
            </div>
        </body>
        </html>
      `);
    }
    res.sendFile(path.join(__dirname, '..', 'views', 'chat.html'));
  });

  router.get('/ui/health', (req, res) => {
    res.json({ ok: true, ui: 'standalone', version: '1.0' });
  });

  // ===== MONITOR DASHBOARD =====
  router.get('/monitor', (req, res) => {
    const token = req.query.token;
    if (token !== UI_ACCESS_TOKEN) {
      return res.status(401).send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Acesso Restrito - Monitor</title>
            <style>
                body { font-family: sans-serif; background: #0b141a; color: #e9edef;
                       display: flex; align-items: center; justify-content: center;
                       min-height: 100vh; margin: 0; text-align: center; }
                h1 { font-size: 48px; }
                p { color: #8696a0; }
            </style>
        </head>
        <body>
            <div>
                <h1>403</h1>
                <p>Token invalido ou ausente.</p>
            </div>
        </body>
        </html>
      `);
    }
    res.sendFile(path.join(__dirname, '..', 'views', 'monitor.html'));
  });

  // ===== API: WhatsApp Status =====
  router.get("/api/status", async (req, res) => {
    try {
      // Status VERIFICADO — checa o estado real da sessao (getState), nao a
      // flag cacheada. Evita o front mostrar "conectado" com a sessao morta.
      const status = await whatsappClient.getStatusVerified();
      res.json({
        ...status,
        connected: status.connected,
        ok: status.connected,
        version: "9.1"
      });
    } catch (e) {
      res.json({ connected: false, ok: false, status: "error", error: e.message });
    }
  });

  // ===== API: QR Code (JSON) =====
  router.get("/api/qr", async (req, res) => {
    try {
      const qr = whatsappClient.getQrCode();
      res.json({ qr });
    } catch (e) {
      res.json({ qr: null, error: e.message });
    }
  });

  // ===== API: Metrics (JSON) =====
  router.get("/api/metrics", async (req, res) => {
    if (!db || typeof db.getMetricsReport !== 'function') {
      return res.json({ period: "0 dias", metrics: {}, mode: "stateless" });
    }
    try {
      const days = parseInt(req.query.days) || 7;
      const metrics = await db.getMetricsReport(days);
      res.json({ period: days + " dias", metrics });
    } catch (e) {
      console.error("[API] Erro ao buscar metricas:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== API: Metrics Dashboard (HTML) =====
  router.get("/api/metrics/html", async (req, res) => {
    if (!db || typeof db.getMetricsReport !== 'function') {
      return res.send("<!DOCTYPE html><html><body style='font-family:Arial;padding:30px'>" +
        "<h1>Métricas indisponíveis</h1><p>Bot stateless — métricas ficam no CaseHub.</p>" +
        "</body></html>");
    }
    try {
      const days = parseInt(req.query.days) || 7;
      const metrics = await db.getMetricsReport(days);

      res.send(`<!DOCTYPE html>
      <html>
      <head>
        <title>Metricas do Bot - Ultimos ${days} dias</title>
        <meta charset="utf-8">
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
          h1 { color: #333; }
          .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
          .metric { display: inline-block; margin: 10px 20px; text-align: center; }
          .metric-value { font-size: 32px; font-weight: bold; color: #2196F3; }
          .metric-label { color: #666; }
          table { width: 100%; border-collapse: collapse; }
          th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
          th { background: #f0f0f0; }
          .hot { color: #f44336; font-weight: bold; }
          .qualified { color: #ff9800; }
          .warm { color: #4caf50; }
          .cold { color: #9e9e9e; }
        </style>
      </head>
      <body>
        <h1>Metricas do Bot - Ultimos ${days} dias</h1>

        <div class="card">
          <h2>Resumo Geral</h2>
          <div class="metric">
            <div class="metric-value">${metrics.totalLeads}</div>
            <div class="metric-label">Total de Leads</div>
          </div>
          <div class="metric">
            <div class="metric-value">${metrics.avgScore}</div>
            <div class="metric-label">Score Medio</div>
          </div>
          <div class="metric">
            <div class="metric-value">${metrics.consultations?.paid || 0}</div>
            <div class="metric-label">Consultas Pagas</div>
          </div>
          <div class="metric">
            <div class="metric-value">${metrics.consultations?.free || 0}</div>
            <div class="metric-label">Consultas Gratuitas</div>
          </div>
          <div class="metric">
            <div class="metric-value">${metrics.urgentLeads || 0}</div>
            <div class="metric-label">Casos Urgentes</div>
          </div>
        </div>

        <div class="card">
          <h2>Por Status</h2>
          <table>
            <tr><th>Status</th><th>Quantidade</th></tr>
            ${Object.entries(metrics.byStatus || {}).map(([status, count]) =>
              `<tr><td class="${status}">${status.toUpperCase()}</td><td>${count}</td></tr>`
            ).join('')}
          </table>
        </div>

        <div class="card">
          <h2>Por Interesse</h2>
          <table>
            <tr><th>Interesse</th><th>Quantidade</th></tr>
            ${Object.entries(metrics.byInterest || {}).map(([interest, count]) =>
              `<tr><td>${interest}</td><td>${count}</td></tr>`
            ).join('')}
          </table>
        </div>

        <div class="card">
          <h2>Leads por Dia</h2>
          <table>
            <tr><th>Data</th><th>Quantidade</th></tr>
            ${Object.entries(metrics.leadsPerDay || {}).map(([date, count]) =>
              `<tr><td>${date}</td><td>${count}</td></tr>`
            ).join('')}
          </table>
        </div>

        <p style="color:#999;text-align:center;margin-top:30px;">
          Atualizado em: ${new Date().toLocaleString('pt-BR')}
        </p>
      </body>
      </html>`);
    } catch (e) {
      console.error("[API] Erro ao gerar metricas HTML:", e.message);
      res.status(500).send("Erro ao gerar metricas: " + e.message);
    }
  });

  return router;
};
