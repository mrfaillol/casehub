/**
 * Lead Management Routes
 * Extracted from server.js - Fase 2.1 Decomposition
 *
 * Routes:
 *   GET  /leads                       - Get qualified leads
 *   GET  /scheduled                   - Get scheduled leads
 *   POST /check-incomplete            - (disabled) Check incomplete leads
 *   GET  /test-telegram               - (disabled) Telegram test
 *   POST /quick-intake                - Start quick intake for a lead
 *   GET  /quick-intake/:phone         - Get quick intake status
 *   GET  /lead/:phone                 - Get lead details + summary
 *   POST /conversation-context        - Get conversation stage/interest
 *   GET  /lead-summary/:phone         - Get lead summary from monitor
 *   GET  /monitor/status              - Lead monitor status
 *   POST /monitor/check               - Force monitor check
 *   GET  /monitor/leads-needing-attention - Leads needing attention
 *   POST /lead/:phone/flag-for-review    - Flag lead for review
 *   POST /lead/:phone/clear-review-flag  - Clear review flag
 */

const express = require('express');

module.exports = function(deps) {
  const { db, notificationService, quickIntake, leadMonitor, detectLanguage } = deps;
  const router = express.Router();

  // ===== LEADS LISTING =====
  router.get("/leads", async (req, res) => {
    try {
      const leads = await db.getQualifiedLeads(0);
      res.json({ leads, count: leads.length });
    } catch (e) { res.status(500).json({ error: e.message }); }
  });

  router.get("/scheduled", async (req, res) => {
    try {
      const leads = await db.getScheduledLeads();
      res.json({ leads, count: leads.length });
    } catch (e) { res.status(500).json({ error: e.message }); }
  });

  // DESATIVADO v9.1 - Usar intake form follow-ups
  router.post("/check-incomplete", async (req, res) => {
    res.json({ ok: false, message: "DESATIVADO - Use /api/intake/check-followups para follow-ups do intake form" });
  });

  // DESATIVADO v10.3
  router.get("/test-telegram", async (req, res) => {
    res.json({ ok: false, message: "Telegram desativado na v10.3" });
  });

  // ===== QUICK INTAKE =====
  router.post("/quick-intake", async (req, res) => {
    try {
      const { phone, lang } = req.body;

      if (!phone) {
        return res.status(400).json({ error: "Telefone obrigatorio" });
      }

      const cleanPhone = phone.replace(/\D/g, "");
      const language = lang || detectLanguage(cleanPhone);

      // Verificar se lead existe
      let lead = await db.getLead(cleanPhone);
      if (!lead) {
        await db.createLead(cleanPhone, { phone: cleanPhone, source: 'Quick Intake API' });
        lead = await db.getLead(cleanPhone);
      }

      // Iniciar Quick Intake
      const intakeStart = quickIntake.startQuickIntake(language);

      // Atualizar estado do lead
      await db.updateLead(cleanPhone, {
        conversation_state: intakeStart.newState,
        quick_intake_answers: intakeStart.answers,
        language: language
      });

      // Enviar mensagem via WhatsApp
      try {
        await notificationService.send(cleanPhone, intakeStart.response, {
          source: 'quick-intake-api',
          skipGuard: true,
          saveToDB: true
        });

        console.log("[QUICK-INTAKE] Iniciado para:", cleanPhone);
        res.json({
          success: true,
          phone: cleanPhone,
          state: intakeStart.newState,
          message: "Quick Intake iniciado"
        });
      } catch (sendErr) {
        console.error("[QUICK-INTAKE] Erro ao enviar:", sendErr.message);
        res.status(500).json({ error: "Erro ao enviar mensagem: " + sendErr.message });
      }

    } catch (e) {
      console.error("[QUICK-INTAKE] Erro:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  router.get("/quick-intake/:phone", async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, "");
      const lead = await db.getLead(phone);

      if (!lead) {
        return res.status(404).json({ error: "Lead nao encontrado" });
      }

      const isInQuickIntake = quickIntake.isQuickIntakeState(lead.conversation_state);

      res.json({
        phone,
        inQuickIntake: isInQuickIntake,
        state: lead.conversation_state,
        answers: lead.quick_intake_answers || {},
        scoring: lead.quick_intake_scoring || null
      });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // ===== LEAD DETAIL =====
  router.get("/lead/:phone", async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, "");
      if (!phone) {
        return res.status(400).json({ error: "Telefone invalido" });
      }

      const leadData = await db.query(
        `SELECT phone, name as client_name, whatsapp_name, email, lead_status, lead_score,
                visa_interest, conversation_state, language, is_urgent, created_at, updated_at
         FROM leads WHERE phone = ? LIMIT 1`,
        [phone]
      );

      const lead = leadData && leadData[0] ? leadData[0] : null;

      if (!lead) {
        return res.status(404).json({ error: "Lead nao encontrado" });
      }

      const summary = await db.getLeadSummary(phone);

      res.json({ phone, lead, summary });
    } catch (e) {
      console.error("[API] Erro ao buscar lead:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== CONVERSATION CONTEXT =====
  router.post("/conversation-context", async (req, res) => {
    try {
      const { phone } = req.body;
      if (!phone) {
        return res.json({ stage: "-", interest: "-" });
      }

      const lead = await db.getLead(phone);
      if (!lead) {
        return res.json({ stage: "Novo Lead", interest: "-" });
      }

      const stageMap = {
        "new": "Novo Lead",
        "greeted": "Saudacao Enviada",
        "asked_name": "Aguardando Nome",
        "asked_email": "Aguardando Email",
        "asked_interest": "Aguardando Interesse",
        "qualified": "Qualificado",
        "scheduling": "Agendando",
        "scheduled": "Agendado",
        "awaiting_human": "Aguardando Atendimento",
        "human_takeover": "Atendimento Humano",
        "completed": "Concluido",
        "inactive": "Inativo"
      };

      const stage = stageMap[lead.conversation_state] || lead.conversation_state || "-";

      let interest = "-";
      if (lead.lead_score >= 70) interest = "Alto";
      else if (lead.lead_score >= 40) interest = "Medio";
      else if (lead.lead_score > 0) interest = "Baixo";
      else if (lead.lead_status === "hot") interest = "Alto";
      else if (lead.lead_status === "warm") interest = "Medio";
      else if (lead.lead_status === "cold") interest = "Baixo";

      res.json({ stage, interest });
    } catch (e) {
      console.error("[CONTEXT] Erro:", e.message);
      res.json({ stage: "-", interest: "-" });
    }
  });

  // ===== LEAD SUMMARY =====
  router.get("/lead-summary/:phone", async (req, res) => {
    try {
      const phone = req.params.phone;
      if (!phone) {
        return res.status(400).json({ error: "Telefone obrigatorio" });
      }

      const summary = await leadMonitor.getLeadSummary(phone);
      res.json(summary);
    } catch (e) {
      console.error("[API] Erro ao buscar resumo da lead:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== LEAD MONITOR =====
  router.get("/monitor/status", async (req, res) => {
    try {
      const status = leadMonitor.getMonitorStatus();
      const dbStats = await db.getMonitorStats();
      res.json({ ...status, dbStats });
    } catch (e) {
      console.error("[API] Erro ao buscar status do monitor:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  router.post("/monitor/check", async (req, res) => {
    try {
      const result = await leadMonitor.forceCheck();
      res.json(result);
    } catch (e) {
      console.error("[API] Erro ao forcar verificacao:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  router.get("/monitor/leads-needing-attention", async (req, res) => {
    try {
      const leads = await db.getLeadsNeedingAttention();
      res.json({ leads, count: leads.length });
    } catch (e) {
      console.error("[API] Erro ao buscar leads:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== LEAD FLAGS =====
  router.post("/lead/:phone/flag-for-review", async (req, res) => {
    try {
      const phone = req.params.phone;
      const { reason } = req.body;

      await leadMonitor.flagForHumanReview(phone, reason || "Marcada manualmente");
      res.json({ success: true });
    } catch (e) {
      console.error("[API] Erro ao marcar lead:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  router.post("/lead/:phone/clear-review-flag", async (req, res) => {
    try {
      const phone = req.params.phone;
      await leadMonitor.clearHumanReviewFlag(phone);
      res.json({ success: true });
    } catch (e) {
      console.error("[API] Erro ao limpar flag:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  return router;
};
