/**
 * Webhook Routes - External integrations (SMS, CallHippo, Forms, Messenger, Stripe)
 * Extracted from server.js (Fase 2.2 decomposition)
 *
 * Returns { apiRouter, webhookRouter }:
 *   apiRouter    → mounted at /api (sms-webhook, callhippo-webhook, sms-queue)
 *   webhookRouter → mounted at /webhook (form, messenger, elementor, stripe)
 */

const express = require('express');

module.exports = function(deps) {
  const {
    db,
    notificationService,
    moskitService,
    smsService,
    conversionTracking,
    crmSync,
    email,
    callhippo,
    messenger,
    messengerHandler,
    stripe,
    botFlow,
    detectLanguage,
    getAndCacheAvailableTimes,
    processedForms
  } = deps;

  // =============================================
  // API ROUTER (/api prefix)
  // =============================================
  const apiRouter = express.Router();

  // ===== SMS WEBHOOK - Receber SMS do Android/Tasker =====
  apiRouter.post("/sms-webhook", async (req, res) => {
    try {
      const { from, body, timestamp } = req.body;

      console.log('[SMS-WEBHOOK] SMS recebido:', { from, body });

      let timeStr = 'N/A';
      if (timestamp) {
        const ts = parseInt(timestamp);
        timeStr = new Date(ts * 1000).toLocaleString('pt-BR', { timeZone: 'America/New_York' });
      }

      res.json({ success: true, message: 'SMS processado' });
    } catch (error) {
      console.error('[SMS-WEBHOOK] Erro:', error);
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // ===== CALLHIPPO WEBHOOK - Receber SMS/Calls =====
  const callhippoRateLimit = {};
  const CALLHIPPO_RATE_LIMIT = 100;
  const CALLHIPPO_RATE_WINDOW = 60000;

  function checkCallhippoRateLimit(ip) {
    const now = Date.now();
    if (!callhippoRateLimit[ip]) {
      callhippoRateLimit[ip] = { count: 1, resetAt: now + CALLHIPPO_RATE_WINDOW };
      return true;
    }
    if (now > callhippoRateLimit[ip].resetAt) {
      callhippoRateLimit[ip] = { count: 1, resetAt: now + CALLHIPPO_RATE_WINDOW };
      return true;
    }
    callhippoRateLimit[ip].count++;
    return callhippoRateLimit[ip].count <= CALLHIPPO_RATE_LIMIT;
  }

  apiRouter.post("/callhippo-webhook", async (req, res) => {
    try {
      const clientIp = req.ip || req.connection.remoteAddress;
      if (!checkCallhippoRateLimit(clientIp)) {
        console.warn('[CALLHIPPO-WEBHOOK] Rate limit excedido para IP:', clientIp);
        return res.status(429).json({ success: false, error: 'Too many requests' });
      }

      const signature = req.headers['x-callhippo-signature'];
      if (!callhippo.validateWebhookSignature(req.body, signature)) {
        console.warn('[CALLHIPPO-WEBHOOK] Signature inválida');
      }

      const { activityType, content, from, to, smsType, status, time, callType, callDuration } = req.body;

      console.log('[CALLHIPPO-WEBHOOK] Atividade recebida:', req.body);

      if (activityType === 'sms') {
        const direction = smsType === 'Incoming' ? 'Recebido' : 'Enviado';
        console.log(`[CALLHIPPO-WEBHOOK] SMS ${direction}: ${from} -> ${to}`);

        if (smsType === 'Incoming' && from) {
          console.log('[CALLHIPPO-WEBHOOK] SMS recebido - criando lead no Moskit...');

          const leadData = {
            phone: from,
            message: content || 'SMS from Google Ads',
            source: 'Google Ads Miami',
            visa_interest: content || 'Immigration services inquiry',
            lead_score: 30,
            lead_status: 'new',
            auto_registered: true
          };

          try {
            const moskitResult = await moskitService.createMoskitContact(leadData);
            if (moskitResult.success) {
              console.log('[CALLHIPPO-WEBHOOK] Lead criado no Moskit:', moskitResult.id);

              crmSync.sendToCRM({ ...leadData, moskit_id: moskitResult.id })
                .catch(err => console.log("[CRM-SYNC] Erro callhippo:", err.message));

              const autoResponse = `Thank you for your message! We will answer it soon.

Schedule a meeting:
- Active clients: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting
- New clients: ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

${process.env.ORG_NAME || "CaseHub"}`;
              await callhippo.sendSMS(autoResponse, from);
              console.log('[CALLHIPPO-WEBHOOK] Resposta automatica enviada para:', from);
            }
          } catch (moskitError) {
            console.error('[CALLHIPPO-WEBHOOK] Erro ao criar lead:', moskitError.message);
          }
        }
      } else if (activityType === 'call') {
        const direction = callType === 'Incoming' ? 'Recebida' : 'Realizada';
        console.log(`[CALLHIPPO-WEBHOOK] Chamada ${direction}: ${from} -> ${to}`);

        if (direction === "Incoming" || callType === "Incoming") {
          smsService.queueSMS(`Chamada CaseHub!\nDe: ${from || "N/A"}\nPara: ${to || "N/A"}\nStatus: ${status || "N/A"}\nDuracao: ${callDuration || "0"}s`);
        }
      }

      res.json({ success: true, received: true });
    } catch (error) {
      console.error('[CALLHIPPO-WEBHOOK] Erro:', error);
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // ===== SMS QUEUE ENDPOINTS =====

  apiRouter.get("/sms-queue", (req, res) => {
    const queue = smsService.getQueue();
    if (!queue.pending) {
      return res.json({ pending: false, count: 0, messages: [] });
    }
    console.log('[SMS-QUEUE] Enviando', queue.count, 'SMS para Android');
    res.json(queue);
  });

  apiRouter.post("/sms-queue/confirm", (req, res) => {
    const { ids } = req.body;
    if (!ids || !Array.isArray(ids)) {
      return res.status(400).json({ error: "ids array obrigatorio" });
    }
    const result = smsService.confirmSMS(ids);
    res.json(result);
  });

  apiRouter.post("/sms-queue/test", (req, res) => {
    const { message } = req.body;
    smsService.queueSMS(message || "Teste de SMS via Android - " + new Date().toLocaleTimeString());
    res.json({ success: true, queue_size: smsService.getQueueSize() });
  });

  apiRouter.get("/sms-queue/simple", (req, res) => {
    const message = smsService.getNextSimple();
    if (!message) {
      return res.type('text/plain').send('NONE');
    }
    res.type('text/plain').send(message);
  });

  // =============================================
  // WEBHOOK ROUTER (/webhook prefix)
  // =============================================
  const webhookRouter = express.Router();

  // ===== WEBHOOK PARA FORMULARIOS DO SITE =====
  webhookRouter.post("/form", async (req, res) => {
    try {
      console.log("\n[FORM] Webhook recebido:", JSON.stringify(req.body).substring(0, 500));

      const data = req.body;
      const fields = data.form_fields || data.fields || {};

      // Suporte ao formato Facebook Lead Ads
      let fbData = {};
      if (data.field_data) {
        if (Array.isArray(data.field_data)) {
          data.field_data.forEach(item => {
            if (item.name && item.values) {
              const key = item.name.toLowerCase().replace(/ /g, "_");
              fbData[key] = item.values[0] || "";
            }
          });
        } else if (typeof data.field_data === "object") {
          Object.keys(data.field_data).forEach(key => {
            const normalizedKey = key.toLowerCase().replace(/ /g, "_");
            fbData[normalizedKey] = data.field_data[key];
          });
        }
      }
      console.log("[FORM] Facebook Lead Ads parsed:", JSON.stringify(fbData));

      const gfv = moskitService.getFieldValue;
      const formData = {
        name: data.Nome || data["Nome Completo"] || data.name || data.nome || gfv(fields.nome) || gfv(fields.name) || gfv(fields["Nome"]) || fbData.full_name || fbData.nome_completo || fbData.nome || "",
        email: data.Email || data["E-mail"] || data.email || gfv(fields.email) || gfv(fields.Email) || fbData.email || fbData.e_mail || "",
        phone: data["Telefone ou Celular"] || data.Telefone || data.telefone || data.phone || gfv(fields.telefone) || gfv(fields.phone) || gfv(fields["Telefone ou Celular"]) || gfv(fields.field_8dbd00d) || fbData.phone_number || fbData.telefone || fbData.phone || "",
        message: data.Mensagem || data["Como podemos te ajudar?"] || data.message || data.mensagem || gfv(fields.mensagem) || gfv(fields.message) || gfv(fields.interesse) || gfv(fields["Como podemos te ajudar?"]) || "",
        page: data.referer_title || data.page || data.form_name || (data.form && data.form.name) || data.form_id || "Site",
        language: data.language || data.lang || "en",
        utm_source: data.utm_source || gfv(fields.utm_source) || "",
        utm_campaign: data.utm_campaign || gfv(fields.utm_campaign) || "",
        utm_medium: data.utm_medium || gfv(fields.utm_medium) || "",
        utm_term: data.utm_term || gfv(fields.utm_term) || "",
        utm_content: data.utm_content || gfv(fields.utm_content) || "",
        gclid: data.gclid || gfv(fields.gclid) || "",
        fbclid: data.fbclid || gfv(fields.fbclid) || "",
        fbp: data.fbp || gfv(fields.fbp) || ""
      };

      if (!formData.name && !formData.email && !formData.phone) {
        console.log("[FORM] Dados insuficientes, ignorando");
        return res.status(400).json({ error: "Dados insuficientes. Necessario nome, email ou telefone." });
      }

      // Deduplicacao
      const formId = `${formData.email || ''}_${formData.phone || ''}_${formData.name || ''}_${Date.now().toString().substring(0, 10)}`;
      if (processedForms.has(formId)) {
        console.log("[FORM] Formulario duplicado ignorado:", formId.substring(0, 30));
        return res.json({ success: true, message: "Ja processado", duplicate: true });
      }
      processedForms.set(formId, Date.now());

      const { score, status } = moskitService.calculateFormScore(formData);

      console.log("[FORM] Lead do site:", formData.name, "| Email:", formData.email, "| Tel:", formData.phone);
      console.log("[FORM] Score:", score, "| Status:", status);

      const leadForMoskit = {
        client_name: formData.name,
        name: formData.name,
        email: formData.email,
        phone: formData.phone ? formData.phone.replace(/\D/g, '') : '',
        visa_interest: formData.message,
        message: formData.message,
        source: 'Site',
        page: formData.page,
        form_name: formData.page,
        language: formData.language,
        lead_score: score,
        lead_status: status
      };

      conversionTracking.trackNewLead({
        ...leadForMoskit,
        source: 'Site',
        gclid: formData.gclid || '',
        fbclid: formData.fbclid || '',
        fbp: formData.fbp || '',
        utm_source: formData.utm_source || '',
        utm_medium: formData.utm_medium || '',
        utm_campaign: formData.utm_campaign || ''
      }).catch(e => console.log("[CONVERSION] Erro site lead:", e.message));

      const moskitResult = await moskitService.createMoskitContact(leadForMoskit);

      if (moskitResult.success) {
        console.log("[FORM] Lead criada no Moskit:", moskitResult.id);

        crmSync.sendToCRM({
          ...leadForMoskit,
          moskit_id: moskitResult.id,
          source: 'Site',
          gclid: formData.gclid || '',
          fbclid: formData.fbclid || '',
          utm_source: formData.utm_source || '',
          utm_medium: formData.utm_medium || '',
          utm_campaign: formData.utm_campaign || ''
        }).catch(err => console.log("[CRM-SYNC] Erro form:", err.message));

        email.sendNewLeadEmail({
          ...leadForMoskit,
          source: 'Formulario Site'
        }).catch(err => console.log("[EMAIL] Erro form:", err.message));

        smsService.queueSMS(`Nova Lead SITE CaseHub!\n${formData.name || "Lead Site"}\nTel: ${formData.phone || "N/A"}\nEmail: ${formData.email || "N/A"}\nMsg: ${(formData.message || "").substring(0, 50)}`);

        res.json({
          success: true,
          moskit_id: moskitResult.id,
          score: score,
          status: status,
          message: "Lead registrada com sucesso"
        });
      } else {
        console.error("[FORM] Erro ao criar lead no Moskit:", moskitResult.error);
        res.status(500).json({
          success: false,
          error: moskitResult.error,
          message: "Erro ao registrar lead"
        });
      }

    } catch (error) {
      console.error("[FORM] Erro no webhook:", error.message);
      res.status(500).json({ error: error.message });
    }
  });

  // ===== WEBHOOK DO MESSENGER =====
  webhookRouter.get("/messenger", (req, res) => {
    const mode = req.query["hub.mode"];
    const token = req.query["hub.verify_token"];
    const challenge = req.query["hub.challenge"];

    if (mode === "subscribe" && token === messenger.MESSENGER_CONFIG.verifyToken) {
      console.log("[MESSENGER] Webhook verificado!");
      res.status(200).send(challenge);
    } else {
      console.log("[MESSENGER] Verificacao falhou");
      res.sendStatus(403);
    }
  });

  webhookRouter.post("/messenger", async (req, res) => {
    try {
      res.status(200).send("EVENT_RECEIVED");

      const body = req.body;

      if (body.object !== "page") {
        return;
      }

      for (const entry of body.entry || []) {
        for (const event of entry.messaging || []) {
          if (event.sender.id === messenger.MESSENGER_CONFIG.pageId) {
            continue;
          }

          if (event.message && event.message.text) {
            const senderId = event.sender.id;
            const messageText = event.message.text;

            console.log("[MESSENGER] Mensagem recebida de " + senderId + ": " + messageText.substring(0, 50));

            const result = await messengerHandler.processMessengerMessage(senderId, messageText);

            if (result.phone) {
              console.log("[MESSENGER] Lead convertida para WhatsApp: " + result.phone);
            }

            if (result.success && !result.duplicate && result.state === "msg_greeted") {
              smsService.queueSMS(`Nova Lead MESSENGER CaseHub!\nID: ${senderId}\nMsg: ${messageText.substring(0, 80)}`);
            }
          }
        }
      }
    } catch (error) {
      console.error("[MESSENGER] Erro no webhook:", error.message);
    }
  });

  // Alias Elementor → form handler
  webhookRouter.post("/elementor", async (req, res) => {
    req.url = "/form";
    webhookRouter.handle(req, res);
  });

  // ===== WEBHOOK STRIPE =====
  webhookRouter.post("/stripe", express.raw({ type: "application/json" }), async (req, res) => {
    try {
      const event = JSON.parse(req.body);
      const result = await stripe.processWebhook(event);

      if (result && result.type === "payment_success") {
        console.log("[STRIPE-WEBHOOK] Pagamento confirmado:", result.phone);

        await db.updatePaymentStatus(result.phone, "paid");

        const lead = await db.getLead(result.phone);
        if (lead) {
          const timesData = await getAndCacheAvailableTimes(result.phone, "paid");
          const leadLang = lead.language || detectLanguage(result.phone);
          const message = botFlow.generateSchedulingMessage(timesData.slots, "paid", leadLang);

          try {
            await notificationService.send(result.phone, message, {
              source: 'stripe-webhook',
              skipGuard: true,
              skipDedup: true,
              saveToDB: true
            });
            await db.updateLead(result.phone, { conversation_state: "asked_scheduling" });
            console.log("[STRIPE-WEBHOOK] Horarios enviados para:", result.phone);

            conversionTracking.trackPaymentCompleted({
              ...lead,
              phone: result.phone
            }).catch(e => console.log("[CONVERSION] Erro pagamento:", e.message));

          } catch (e) {
            console.error("[STRIPE-WEBHOOK] Erro ao enviar mensagem:", e.message);
          }
        }
      }

      res.json({ received: true });
    } catch (error) {
      console.error("[STRIPE-WEBHOOK] Erro:", error.message);
      res.status(400).json({ error: error.message });
    }
  });

  return { apiRouter, webhookRouter };
};
