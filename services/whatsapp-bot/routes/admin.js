/**
 * Admin Routes - Bot Control, Follow-up, Conversion Tracking
 * CaseHub WhatsApp Bot
 * v1.0 - Extracted from server.js (Fase 2.1)
 */
const express = require('express');

module.exports = function(deps) {
  const { db, botConfig, notificationService, conversionTracking, autoFollowup } = deps;
  const router = express.Router();

  // ===== BOT STATUS =====
  // Mounted at /api, so paths include admin/ prefix where needed
  router.get('/admin/bot-status', async (req, res) => {
    try {
      const status = botConfig.getStatus();
      res.json({ success: true, ...status, notificationService: notificationService.getStats() });
    } catch (e) {
      console.error("[API] Erro ao obter status bot:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // ===== BOT GLOBAL TOGGLE =====
  router.post('/admin/bot-global-toggle', async (req, res) => {
    try {
      const { enabled, updatedBy } = req.body;

      if (enabled === undefined) {
        return res.status(400).json({ error: "enabled é obrigatório (true/false)" });
      }

      const isEnabled = enabled === true || enabled === 'true' || enabled === 1 || enabled === '1';
      const result = botConfig.setGlobalEnabled(isEnabled, updatedBy || 'CaseHub');

      console.log(`[BOT-GLOBAL] Toggle: ${isEnabled ? 'ON' : 'OFF'} por ${updatedBy || 'CaseHub'}`);

      res.json({ success: result.success, ...result.status });
    } catch (e) {
      console.error("[API] Erro ao toggle bot global:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // ===== BUSINESS HOURS TOGGLE =====
  router.post('/admin/bot-business-hours', async (req, res) => {
    try {
      const { enabled, updatedBy } = req.body;

      if (enabled === undefined) {
        return res.status(400).json({ error: "enabled é obrigatório (true/false)" });
      }

      const isEnabled = enabled === true || enabled === 'true' || enabled === 1 || enabled === '1';
      const result = botConfig.setBusinessHoursEnabled(isEnabled, updatedBy || 'CaseHub');

      console.log(`[BOT-HOURS] Business hours check: ${isEnabled ? 'ON' : 'OFF'}`);

      res.json({ success: result.success, ...result.status });
    } catch (e) {
      console.error("[API] Erro ao toggle business hours:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // ===== CONVERSION FEEDBACK =====
  router.post('/conversion-feedback', async (req, res) => {
    try {
      const { event, lead_id, phone, email, client_name, gclid, fbclid, source, lead_score } = req.body;

      if (!event) {
        return res.status(400).json({ success: false, error: "event is required" });
      }

      const leadData = {
        phone: phone || '',
        email: email || '',
        client_name: client_name || '',
        gclid: gclid || '',
        fbclid: fbclid || '',
        source: source || '',
        lead_score: lead_score || 0
      };

      console.log(`[CONVERSION-FEEDBACK] Event: ${event} | Lead: ${client_name || phone || lead_id}`);

      let results;
      switch (event) {
        case 'qualified':
          results = await conversionTracking.trackQualifiedLead(leadData);
          break;
        case 'consultation_scheduled':
          results = await conversionTracking.trackConsultationScheduled(leadData);
          break;
        case 'payment_completed':
          results = await conversionTracking.trackPaymentCompleted(leadData);
          break;
        case 'new_lead':
          results = await conversionTracking.trackNewLead(leadData);
          break;
        default:
          return res.status(400).json({ success: false, error: `Unknown event: ${event}` });
      }

      const anySuccess = results.some(r => r.success);
      console.log(`[CONVERSION-FEEDBACK] Results: ${JSON.stringify(results.map(r => ({ platform: r.platform, success: r.success })))}`);

      res.json({ success: anySuccess, results });
    } catch (e) {
      console.error("[CONVERSION-FEEDBACK] Error:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // ===== AUTO FOLLOW-UP ENDPOINTS =====
  router.post('/followup/mark', async (req, res) => {
    try {
      const { phone } = req.body;
      if (!phone) {
        return res.status(400).json({ error: "phone é obrigatório" });
      }
      const result = await autoFollowup.markForFollowup(phone.replace(/\D/g, ""));
      res.json(result);
    } catch (e) {
      console.error("[API] Erro ao marcar follow-up:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  router.post('/followup/unmark', async (req, res) => {
    try {
      const { phone } = req.body;
      if (!phone) {
        return res.status(400).json({ error: "phone é obrigatório" });
      }
      const result = await autoFollowup.unmarkForFollowup(phone.replace(/\D/g, ""));
      res.json(result);
    } catch (e) {
      console.error("[API] Erro ao desmarcar follow-up:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  router.get('/followup/stats', async (req, res) => {
    try {
      const stats = await autoFollowup.getFollowupStats();
      res.json({ success: true, ...stats });
    } catch (e) {
      console.error("[API] Erro ao buscar stats:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  router.get('/followup/marked', async (req, res) => {
    try {
      const leads = await autoFollowup.getMarkedLeads();
      res.json({ success: true, leads });
    } catch (e) {
      console.error("[API] Erro ao buscar leads marcadas:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  router.post('/followup/process', async (req, res) => {
    try {
      const result = await autoFollowup.processAllFollowups();
      res.json({ success: true, ...result });
    } catch (e) {
      console.error("[API] Erro ao processar follow-ups:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  router.get('/followup/check/:phone', async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, "");
      const result = await db.query(
        "SELECT needs_auto_followup, auto_followup_requested_at FROM leads WHERE phone = ?",
        [phone]
      );
      if (result && result.length > 0) {
        res.json({
          success: true,
          marked: result[0].needs_auto_followup === 1,
          requestedAt: result[0].auto_followup_requested_at
        });
      } else {
        res.json({ success: true, marked: false });
      }
    } catch (e) {
      console.error("[API] Erro ao verificar follow-up:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  return router;
};
