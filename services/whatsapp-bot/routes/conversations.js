/**
 * Chat Interface & Conversation Routes
 * Extracted from server.js - Fase 2.1 Decomposition
 *
 * Routes:
 *   GET  /conversations         - List recent conversations
 *   GET  /messages/:phone       - Messages for a conversation
 *   POST /send                  - Send message (human use)
 *   POST /send-media            - Send media file
 *   POST /bot-control           - Enable/disable bot per conversation
 *   POST /human-takeover        - Toggle human takeover
 *   POST /suggest-response      - AI response suggestion
 *   POST /case-summary          - AI case summary
 *   GET  /sync-history          - Sync history from WhatsApp
 *   POST /mark-read/:phone      - Mark conversation as read
 *   GET  /config                - Get bot config (for UI)
 *   POST /config                - Update bot config
 *   POST /chat/internal         - Internal team chat (CaseHub)
 */

const express = require('express');
const path = require('path');
const fs = require('fs');
const multer = require('multer');

module.exports = function(deps) {
  const { db, whatsappClient, notificationService, botConfig, mediaHandler } = deps;
  const router = express.Router();

  const aiSuggestions = require('../ai-suggestions');

  // ===== MULTER SETUP =====
  const uploadsDir = path.join(__dirname, '..', 'uploads');
  const mediaDir = mediaHandler && mediaHandler.MEDIA_DIR
    ? mediaHandler.MEDIA_DIR
    : uploadsDir;
  if (!fs.existsSync(mediaDir)) {
    fs.mkdirSync(mediaDir, { recursive: true });
  }

  const storage = multer.diskStorage({
    destination: mediaDir,
    filename: (req, file, cb) => {
      const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
      const ext = path.extname(file.originalname)
        || (mediaHandler && mediaHandler.extFromMime
          ? mediaHandler.extFromMime(file.mimetype)
          : '');
      cb(null, uniqueSuffix + ext);
    }
  });

  const upload = multer({
    storage,
    limits: { fileSize: 16 * 1024 * 1024 }, // 16MB max
    fileFilter: (req, file, cb) => {
      const allowedTypes = /jpeg|jpg|png|gif|pdf|doc|docx|webp/;
      const ext = allowedTypes.test(path.extname(file.originalname).toLowerCase());
      const mime = allowedTypes.test(file.mimetype) || file.mimetype.startsWith('image/');
      if (ext || mime) {
        cb(null, true);
      } else {
        cb(new Error('Tipo de arquivo nao permitido'));
      }
    }
  });

  // ===== CONVERSATION LIST =====
  router.get("/conversations", async (req, res) => {
    try {
      const limit = parseInt(req.query.limit) || 50;
      const conversations = await db.query(
        `SELECT DISTINCT l.phone, l.name, l.whatsapp_name, l.email, l.lead_status, l.lead_score,
                l.conversation_state, l.language, l.bot_enabled, l.human_takeover, l.updated_at, l.contact_type, l.contact_tags, l.never_contact,
                (SELECT content FROM conversations c WHERE c.phone = l.phone ORDER BY c.created_at DESC LIMIT 1) as lastMessage,
                (SELECT created_at FROM conversations c WHERE c.phone = l.phone ORDER BY c.created_at DESC LIMIT 1) as lastMessageTime,
                (SELECT from_bot FROM conversations c WHERE c.phone = l.phone ORDER BY c.created_at DESC LIMIT 1) as from_bot,
                (SELECT COUNT(*) FROM conversations c2 WHERE c2.phone = l.phone AND c2.role = 'user' AND c2.created_at > COALESCE(l.last_read_at, '1970-01-01')) as unread
         FROM leads l
         WHERE l.phone IS NOT NULL
         ORDER BY COALESCE((SELECT MAX(created_at) FROM conversations c WHERE c.phone = l.phone), l.created_at) DESC
         LIMIT ?`,
        [limit]
      );
      res.json(conversations || []);
    } catch (e) {
      console.error("[API] Erro ao buscar conversas:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== MESSAGES =====
  router.get("/messages/:phone", async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, "");
      const limit = parseInt(req.query.limit) || 100;

      const messages = await db.query(
        `SELECT * FROM (
           SELECT id, phone, role, content, created_at, from_bot
           FROM conversations
           WHERE phone = ?
           ORDER BY created_at DESC
           LIMIT ?
         ) sub ORDER BY created_at ASC`,
        [phone, limit]
      );
      res.json(messages || []);
    } catch (e) {
      console.error("[API] Erro ao buscar mensagens:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== SEND MESSAGE (human use) =====
  router.post("/send", async (req, res) => {
    let reqPhone = "unknown";
    try {
      const { phone, message, fromHuman } = req.body || {};
      reqPhone = phone || "unknown";
      if (!phone || !message) {
        return res.status(400).json({ error: "phone e message sao obrigatorios" });
      }

      const cleanPhone = phone.replace(/\D/g, "");

      // Manual send from CaseHub - skip guard, record for dedup
      await whatsappClient.sendMessage(cleanPhone, message);
      notificationService.recordSend(cleanPhone, 'casehub-manual');

      await db.saveMessage(cleanPhone, "assistant", message);

      if (fromHuman) {
        await db.query(
          "UPDATE conversations SET from_bot = 0 WHERE phone = ? AND content = ? ORDER BY created_at ASC LIMIT 1",
          [cleanPhone, message]
        );
      }

      res.json({ success: true });
    } catch (e) {
      console.error("[API] Erro ao enviar para " + reqPhone + ":", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // ===== SEND MEDIA =====
  router.post("/send-media", upload.single('file'), async (req, res) => {
    const { phone, caption } = req.body;
    const file = req.file;

    if (!phone || !file) {
      return res.status(400).json({ error: 'Phone and file required' });
    }

    try {
      const cleanPhone = phone.replace(/\D/g, '');
      const chatId = phone.includes('@c.us') ? phone : cleanPhone + '@c.us';
      const result = whatsappClient.sendMedia
        ? await whatsappClient.sendMedia(chatId, file.path, caption || '')
        : await whatsappClient.getClient().sendMessage(
          chatId,
          require('whatsapp-web.js').MessageMedia.fromFilePath(file.path),
          { caption: caption || '' }
        );

      // Media sends are human-initiated from CaseHub (like manual text sends)
      notificationService.recordSend(cleanPhone, 'casehub-media');
      await db.query(
        `INSERT INTO conversations (phone, role, content, from_bot, created_at)
         VALUES (?, 'assistant', ?, 0, NOW())`,
        [cleanPhone, caption || '[Midia enviada]']
      );

      console.log('[MEDIA] Enviado para:', cleanPhone);
      res.json({
        ok: true,
        success: true,
        message: 'Midia enviada',
        messageId:
          result && result.id && result.id._serialized
            ? result.id._serialized
            : null,
        media_file: file.filename,
        mediaFile: file.filename,
        filename: file.filename,
        mimetype: file.mimetype || null
      });
    } catch (error) {
      console.error('[MEDIA] Error:', error);
      try { fs.unlinkSync(file.path); } catch (e) {}
      res.status(500).json({ error: error.message });
    }
  });

  // ===== BOT CONTROL (per conversation) =====
  router.post("/bot-control", async (req, res) => {
    try {
      const phone = req.body.phone;
      const enabled = req.body.botEnabled !== undefined ? req.body.botEnabled : req.body.enabled;
      if (!phone) {
        return res.status(400).json({ error: "phone e obrigatorio" });
      }

      const cleanPhone = phone.replace(/\D/g, "");
      const botEnabled = enabled === true || enabled === 'true' || enabled === 1 || enabled === '1';

      await db.query(
        "UPDATE leads SET bot_enabled = ?, human_takeover = ? WHERE phone = ?",
        [botEnabled ? 1 : 0, botEnabled ? 0 : 1, cleanPhone]
      );

      console.log(`[BOT-CONTROL] ${cleanPhone}: bot ${botEnabled ? 'ATIVADO' : 'DESATIVADO (human takeover)'}`);

      res.json({ success: true, botEnabled });
    } catch (e) {
      console.error("[API] Erro ao controlar bot:", e.message);
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // ===== HUMAN TAKEOVER =====
  router.post("/human-takeover", async (req, res) => {
    try {
      const { phone, takeover } = req.body;

      if (!phone) {
        return res.status(400).json({ error: 'Phone required' });
      }

      const cleanPhone = phone.replace(/\D/g, '');
      const humanTakeover = takeover ? 1 : 0;

      await db.query(
        `UPDATE leads SET human_takeover = ?, bot_enabled = ?, updated_at = NOW()
         WHERE phone = ?`,
        [humanTakeover, takeover ? 0 : 1, cleanPhone]
      );

      console.log('[TAKEOVER] Phone:', cleanPhone, 'Human:', takeover);
      res.json({ success: true, humanTakeover: takeover });
    } catch (error) {
      console.error('[TAKEOVER] Error:', error);
      res.status(500).json({ error: error.message });
    }
  });

  // ===== AI SUGGESTIONS =====
  router.post("/suggest-response", async (req, res) => {
    try {
      const { phone } = req.body;

      if (!phone) {
        return res.status(400).json({ error: 'Phone required', suggestion: null });
      }

      const messages = await db.query(
        `SELECT role, content FROM conversations
         WHERE phone = ?
         ORDER BY created_at ASC
         LIMIT 10`,
        [phone.replace(/\D/g, '')]
      );

      if (!messages || messages.length === 0) {
        return res.json({ suggestion: null });
      }

      const history = messages.reverse();
      const lastUserMessage = history.filter(m => m.role === 'user').pop();

      if (!lastUserMessage) {
        return res.json({ suggestion: null });
      }

      const historyText = aiSuggestions.formatHistory(history);
      const suggestion = await aiSuggestions.generateSuggestion(
        historyText,
        lastUserMessage.content
      );

      res.json({ suggestion });
    } catch (error) {
      console.error('[AI] Suggestion error:', error);
      res.json({ suggestion: null, error: error.message });
    }
  });

  // ===== CASE SUMMARY =====
  router.post("/case-summary", async (req, res) => {
    try {
      const { phone } = req.body;

      if (!phone) {
        return res.status(400).json({ error: 'Phone required', summary: null });
      }

      const cleanPhone = phone.replace(/\D/g, '');

      const [leads] = await db.query(
        `SELECT * FROM leads WHERE phone = ?`,
        [cleanPhone]
      );

      if (!leads || leads.length === 0) {
        return res.json({ summary: null, error: 'Lead not found' });
      }

      const lead = leads[0];

      const messages = await db.query(
        `SELECT role, content, created_at FROM conversations
         WHERE phone = ?
         ORDER BY created_at ASC
         LIMIT 30`,
        [cleanPhone]
      );

      const history = messages ? messages.reverse() : [];

      const result = await aiSuggestions.generateCaseSummary(lead, history);

      if (result) {
        res.json({
          summary: result.summary,
          recommendedTemplate: result.recommendedTemplate,
          generatedAt: result.generatedAt,
          lead: {
            name: lead.client_name || lead.whatsapp_name,
            score: lead.lead_score,
            status: lead.lead_status,
            interest: lead.visa_interest,
            urgent: lead.is_urgent
          }
        });
      } else {
        res.json({ summary: null, error: 'Could not generate summary' });
      }
    } catch (error) {
      console.error('[AI] Case summary error:', error);
      res.json({ summary: null, error: error.message });
    }
  });

  // ===== SYNC HISTORY =====
  router.get("/sync-history", async (req, res) => {
    try {
      const client = whatsappClient.getClient();
      if (!client || !whatsappClient.isReady) {
        return res.status(503).json({ error: "WhatsApp not connected" });
      }

      const limit = parseInt(req.query.limit) || 50;
      const daysBack = parseInt(req.query.days) || 7;
      const specificPhone = req.query.phone;
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - daysBack);

      console.log("[SYNC] Starting history sync, days:", daysBack, "limit:", limit);

      let totalSynced = 0;
      let totalSkipped = 0;
      let totalErrors = 0;
      const syncedChats = [];

      let phonesToSync = [];
      if (specificPhone) {
        phonesToSync = [specificPhone.replace(/\D/g, "")];
      } else {
        const leads = await db.query(
          `SELECT DISTINCT phone FROM leads WHERE phone IS NOT NULL ORDER BY updated_at DESC LIMIT 50`
        );
        phonesToSync = leads.map(l => l.phone);
      }

      console.log("[SYNC] Phones to sync:", phonesToSync.length);

      for (const phone of phonesToSync) {
        try {
          const chatId = phone + "@c.us";
          const chat = await client.getChatById(chatId);

          if (!chat) {
            console.log("[SYNC] Chat not found for:", phone);
            continue;
          }

          const messages = await chat.fetchMessages({ limit });
          let chatSynced = 0;
          let chatSkipped = 0;

          for (const msg of messages) {
            const msgDate = new Date(msg.timestamp * 1000);
            if (msgDate < cutoffDate) {
              continue;
            }

            const role = msg.fromMe ? "assistant" : "user";
            const content = msg.body;

            if (!content || content.trim() === "") {
              continue;
            }

            const existingCheck = await db.query(
              `SELECT id FROM conversations
               WHERE phone = ? AND role = ? AND content = ?
               AND ABS(TIMESTAMPDIFF(MINUTE, created_at, ?)) < 5
               LIMIT 1`,
              [phone, role, content, msgDate]
            );

            if (existingCheck && existingCheck.length > 0) {
              chatSkipped++;
              continue;
            }

            await db.query(
              `INSERT INTO conversations (phone, role, content, created_at) VALUES (?, ?, ?, ?)`,
              [phone, role, content, msgDate]
            );

            chatSynced++;
          }

          if (chatSynced > 0) {
            syncedChats.push({
              phone,
              name: chat.name || phone,
              synced: chatSynced,
              skipped: chatSkipped
            });
            totalSynced += chatSynced;
          }
          totalSkipped += chatSkipped;
          console.log("[SYNC] Processed", phone, "- synced:", chatSynced, "skipped:", chatSkipped);

        } catch (chatError) {
          console.error("[SYNC] Error processing", phone, ":", chatError.message);
          totalErrors++;
        }
      }

      console.log("[SYNC] Completed. Synced:", totalSynced, "Skipped:", totalSkipped, "Errors:", totalErrors);

      res.json({
        success: true,
        totalSynced,
        totalSkipped,
        totalErrors,
        phonesProcessed: phonesToSync.length,
        chatsProcessed: syncedChats.length,
        chats: syncedChats
      });

    } catch (e) {
      console.error("[SYNC] Error:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== MARK AS READ =====
  router.post("/mark-read/:phone", async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, "");
      await db.query('UPDATE leads SET last_read_at = NOW() WHERE phone = ?', [phone]);
      res.json({ success: true });
    } catch (e) {
      console.error("[API] Erro ao marcar como lido:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== CONFIG API =====
  router.get("/config", async (req, res) => {
    try {
      const config = botConfig.loadConfig();
      res.json({
        businessHoursEnabled: config.businessHoursEnabled,
        businessHoursStart: config.businessHoursStart,
        businessHoursEnd: config.businessHoursEnd,
        timezone: config.timezone,
        lastUpdated: config.lastUpdated
      });
    } catch (e) {
      console.error("[API] Erro ao buscar config:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  router.post("/config", async (req, res) => {
    try {
      const { businessHoursStart, businessHoursEnd, businessHoursEnabled, timezone } = req.body;

      const updates = {};
      if (businessHoursStart !== undefined) updates.businessHoursStart = parseInt(businessHoursStart);
      if (businessHoursEnd !== undefined) updates.businessHoursEnd = parseInt(businessHoursEnd);
      if (businessHoursEnabled !== undefined) updates.businessHoursEnabled = businessHoursEnabled;
      if (timezone !== undefined) updates.timezone = timezone;

      botConfig.updateConfig(updates);
      const newConfig = botConfig.loadConfig();

      console.log("[API] Config atualizada:", updates);
      res.json({ success: true, config: newConfig });
    } catch (e) {
      console.error("[API] Erro ao atualizar config:", e.message);
      res.status(500).json({ error: e.message });
    }
  });

  // ===== INTERNAL CHAT (CaseHub Team Chat) =====
  router.post("/chat/internal", async (req, res) => {
    try {
      const { message, from, source } = req.body;

      if (!message) {
        return res.status(400).json({ error: "Message required" });
      }

      if (source !== "casehub_chat") {
        return res.status(403).json({ error: "Unauthorized source" });
      }

      const llmChatbot = require("../llm-chatbot-v3");

      const context = {
        leadHistory: [],
        isInternalChat: true,
        userName: from || "Equipe"
      };

      const systemPrompt = `Voce e o Assistente WhatsApp CaseHub, um sistema de processamento baseado em LLM (Large Language Model).

REGRAS IMPORTANTES:
- NUNCA diga que e uma "inteligencia artificial" ou "IA"
- Se perguntado, diga que e um "assistente baseado em LLM"
- Voce auxilia a equipe interna do ${process.env.ORG_NAME || "CaseHub"}
- Responda de forma profissional e concisa
- Foco em ajudar com duvidas sobre o sistema, processos e clientes`;

      const response = await llmChatbot.generateResponse(message, context, "pt", systemPrompt);

      res.json({
        success: true,
        response: response || "Desculpe, nao consegui processar sua mensagem."
      });
    } catch (error) {
      console.error("Internal chat error:", error);
      res.json({
        success: false,
        response: "Ocorreu um erro ao processar sua mensagem. Tente novamente."
      });
    }
  });

  return router;
};
