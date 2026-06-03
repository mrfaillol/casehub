/**
 * Servidor Principal - WhatsApp Bot
 * CaseHub
 *
 * After Fase 2 decomposition (v13.0-v13.4), this file is the thin orchestration layer:
 *   - Express app setup + middleware
 *   - Route mounting (admin, health, leads, conversations, webhooks)
 *   - Service initialization
 *   - WhatsApp client event handlers
 *   - Periodic tasks (messenger, catch-up)
 *   - Process handlers (uncaught exceptions, graceful shutdown)
 *
 * Business logic lives in:
 *   services/message-handler.js     - Main incoming message processing
 *   services/notification-service.js - Centralized message sending gateway
 *   services/moskit-service.js      - Moskit CRM operations + lead scoring
 *   services/sms-service.js         - SMS queue for Android/Tasker
 *   services/scheduling-service.js  - Follow-ups, catch-up, Calendly caching
 *   routes/admin.js                 - Bot control endpoints
 *   routes/health.js                - Health, QR, metrics, UI
 *   routes/leads.js                 - Lead management, quick intake, monitor
 *   routes/conversations.js         - Chat interface, AI suggestions, internal chat
 *   routes/webhooks.js              - Form, Messenger, Stripe, SMS webhooks
 */
require("dotenv").config();

const express = require("express");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const cors = require("cors");
const path = require("path");

// ===== CORE MODULES =====
const whatsappClient = require("./whatsapp-client");
const botFlow = require("./bot-flow");
const db = require("./database");
const calendly = require("./calendly");
const stripe = require("./stripe");
const email = require("./email");
const callhippo = require("./callhippo");
const messengerHandler = require("./messenger-handler");
const conversionTracking = require("./conversion-tracking");
const messenger = require("./messenger");
const { detectLanguage } = require("./languages");
const intakeIntegration = require("./intake-integration");
const mediaHandler = require("./media-handler");
const clientFollowup = require("./client-followup");
const quickIntake = require("./quick-intake");
const llmChatbot = require("./llm-chatbot-v3");
const leadMonitor = require("./lead-monitor");
const maestroHandler = require("./maestro-handler");
const { maestroHandler: maestroV4 } = require("./maestro-handler-v4");
const crmSync = require("./crm-sync");
const botConfig = require("./bot-config");
const knownClients = require("./known-clients");
const autoFollowup = require("./auto-followup");

// ===== SERVICES (extracted in Fase 2) =====
const notificationService = require("./services/notification-service");
const moskitService = require("./services/moskit-service");
const smsService = require("./services/sms-service");
const schedulingService = require("./services/scheduling-service");
const messageHandler = require("./services/message-handler");
const casehubBridge = require("./casehub-bridge");

// ===== EXPRESS APP SETUP =====
const app = express();
app.set("trust proxy", 1);
const PORT = process.env.PORT || 3001;

app.use(cors({
  origin: [
    (process.env.ORG_WEBSITE || "https://casehub.app"),
    (process.env.ORG_WEBSITE || "https://casehub.app"),
    "http://localhost:3000"
  ],
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization"],
  credentials: true
}));

app.use(helmet({ contentSecurityPolicy: false }));
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 1000 }));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Static files
app.use('/ui/static', express.static(path.join(__dirname, 'public')));
app.use('/media', express.static(mediaHandler.MEDIA_DIR, {
  index: false,
  dotfiles: 'deny',
  maxAge: '1d'
}));

// ===== FORM DEDUP CACHE (shared with webhooks) =====
const processedForms = new Map();
const FORM_CACHE_TTL = 300000; // 5 minutes
setInterval(() => {
  const now = Date.now();
  for (const [id, timestamp] of processedForms) {
    if (now - timestamp > FORM_CACHE_TTL) {
      processedForms.delete(id);
    }
  }
}, 5 * 60 * 1000);

// ===== SERVICE INITIALIZATION (pre-routes) =====
moskitService.init({ conversionTracking });

// ===== ROUTE MOUNTING =====
app.use('/api', require('./routes/admin')({
  db, botConfig, notificationService, conversionTracking, autoFollowup
}));

app.use(require('./routes/health')({ whatsappClient, db }));

app.use('/api', require('./routes/leads')({
  db, notificationService, quickIntake, leadMonitor, detectLanguage
}));

app.use('/api', require('./routes/conversations')({
  db, whatsappClient, notificationService, botConfig, mediaHandler
}));

const { apiRouter: webhookApiRoutes, webhookRouter: webhookRoutes } = require('./routes/webhooks')({
  db, notificationService, moskitService, smsService,
  conversionTracking, crmSync, email, callhippo, messenger,
  messengerHandler, stripe, botFlow, detectLanguage,
  getAndCacheAvailableTimes: schedulingService.getAndCacheAvailableTimes,
  processedForms
});
app.use('/api', webhookApiRoutes);
app.use('/webhook', webhookRoutes);

// Start auto-followup scheduler
autoFollowup.startScheduler();

// ===== SERVER STARTUP =====
async function startServer() {
  console.log("[BOT] WhatsApp Bot - CaseHub (decomposed architecture v13.4)");

  if (!await db.testConnection()) { console.error("[ERROR] DB"); process.exit(1); }
  console.log("[OK] DB conectado");

  // Initialize services
  email.init();

  notificationService.init(whatsappClient, db, botConfig);
  console.log("[OK] Notification Service ativo");

  schedulingService.init({
    db, notificationService, moskitService, email, crmSync,
    calendly, llmChatbot, botConfig
  });
  console.log("[OK] Scheduling Service ativo");

  messageHandler.init({
    db, whatsappClient, notificationService, botConfig, knownClients,
    botFlow, quickIntake, intakeIntegration, llmChatbot, conversionTracking,
    moskitService, smsService, email, crmSync, mediaHandler,
    maestroV4, schedulingService
  });
  console.log("[OK] Message Handler ativo");

  leadMonitor.initialize({
    db, whatsappClient, llmChatbot,
    emailService: email,
    notificationService
  });
  leadMonitor.startMonitorScheduler();
  console.log("[OK] Lead Monitor ativo");

  // WhatsApp event handlers
  whatsappClient.on("message", async (data) => {
    try {
      await messageHandler.handleIncomingMessage(data);
    } catch (error) {
      console.error("[FATAL] Erro no handler de mensagens:", error.message);
      console.error("[FATAL] Stack:", error.stack);
    }
    // Mirror inbound to CaseHub. Isolated try/catch so legacy auto-response keeps working
    // even if Python backend is down.
    try {
      if (data && data.hasMedia && data.message) {
        try {
          const saved = await mediaHandler.downloadAndSaveMedia(
            data.message,
            data.from || ""
          );
          if (saved && saved.success) {
            data.media_file = saved.filename;
            data.media_size = saved.size;
            if (!data.mimetype) data.mimetype = saved.mimetype;
            const baseMime = (saved.mimetype || "").split(";")[0].trim();
            if (baseMime === "application/pdf") {
              const ocr = await mediaHandler.extractPdfText(saved.filePath);
              if (ocr) data.ocr_text = ocr;
            }
          }
        } catch (mediaErr) {
          console.error("[casehub-bridge] media metadata error:", mediaErr.message);
        }
      }
      await casehubBridge.forwardInbound(data);
    } catch (bridgeErr) {
      console.error("[casehub-bridge] unexpected error:", bridgeErr.message);
    }
  });

  whatsappClient.on("message_ack", async (data) => {
    try {
      await casehubBridge.forwardAck(data);
    } catch (bridgeErr) {
      console.error("[casehub-bridge] ack error:", bridgeErr.message);
    }
  });

  whatsappClient.on("ready", () => console.log("\n[OK] WhatsApp pronto!\n"));
  whatsappClient.on("qr", () => console.log("[QR] http://localhost:" + PORT + "/qr"));

  // Capture outgoing messages (sent via WhatsApp Web)
  whatsappClient.on("message_create", async (msg) => {
    try {
      if (!msg.fromMe) return;
      if (msg.to.includes("@g.us")) return;

      const phone = msg.to.replace("@c.us", "");
      const content = msg.body;
      if (!content || content.trim() === "") return;

      const existingCheck = await db.query(
        "SELECT id FROM conversations WHERE phone = ? AND role = ? AND content = ? AND created_at > DATE_SUB(NOW(), INTERVAL 5 MINUTE) LIMIT 1",
        [phone, "assistant", content]
      );

      if (existingCheck && existingCheck.length > 0) return;

      await db.saveMessage(phone, "assistant", content);
      console.log("[SYNC] Mensagem enviada capturada:", phone, content.substring(0, 50) + "...");
    } catch (e) {
      console.error("[SYNC] Erro ao capturar mensagem:", e.message);
    }
  });

  await whatsappClient.initialize();

  // Periodic tasks
  setInterval(async () => {
    try { await messengerHandler.processFollowups(); }
    catch (e) { console.error("[MESSENGER] Erro follow-ups:", e.message); }
  }, 30 * 60 * 1000);

  setInterval(async () => {
    try { await messengerHandler.processInactiveLeads(moskitService.createMoskitContact); }
    catch (e) { console.error("[MESSENGER] Erro registro inativas:", e.message); }
  }, 60 * 60 * 1000);

  // Catch-up: process pending messages after auto-reactivation
  setInterval(async () => {
    try {
      const catchUpEvent = botConfig.consumeCatchUpEvent();
      if (catchUpEvent.pending) {
        console.log("[CATCH-UP] Evento de auto-reativacao detectado!");
        await schedulingService.processPendingMessages(catchUpEvent.disabledAt);
      }
    } catch (e) { console.error("[CATCH-UP] Erro:", e.message); }
  }, 2 * 60 * 1000);

  setTimeout(async () => {
    try {
      const catchUpEvent = botConfig.consumeCatchUpEvent();
      if (catchUpEvent.pending) {
        console.log("[CATCH-UP] Catch-up pendente no startup!");
        await schedulingService.processPendingMessages(catchUpEvent.disabledAt);
      }
    } catch (e) { console.error("[CATCH-UP] Erro startup:", e.message); }
  }, 30 * 1000);

  // Legacy module routes
  maestroHandler.setupMaestroRoutes(app);
  intakeIntegration.setupRoutes(app, whatsappClient);
  intakeIntegration.startFollowupIntervals(whatsappClient);
  clientFollowup.init();
  clientFollowup.setupRoutes(app);
  clientFollowup.startScheduler();

  app.listen(PORT, "0.0.0.0", () => console.log("[OK] Porta " + PORT));

  console.log("[OK] Auto Follow-up System ativo");
  console.log("[OK] Intake Form System ativo");
  console.log("[OK] Client Follow-up System ativo");
  console.log("[OK] Catch-up System ativo");
}

// ===== PROCESS HANDLERS =====
process.on("uncaughtException", (error) => {
  console.error("[FATAL] Uncaught Exception:", error.message);
  console.error("[FATAL] Stack:", error.stack);
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("[FATAL] Unhandled Rejection at:", promise);
  console.error("[FATAL] Reason:", reason);
});

process.on("SIGINT", async () => {
  console.log("[SHUTDOWN] Recebido SIGINT, desconectando...");
  try {
    await whatsappClient.disconnect();
    console.log("[SHUTDOWN] WhatsApp desconectado");
  } catch(e) {
    console.error("[SHUTDOWN] Erro ao desconectar:", e.message);
  }
  process.exit(0);
});

startServer();
