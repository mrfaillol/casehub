/**
 * Message Handler Service - Main incoming message processing
 * Extracted from server.js (Fase 2.4 decomposition)
 *
 * Contains:
 *   handleIncomingMessage() - Main handler for all incoming WhatsApp messages
 *   shouldProcessMessage()  - Deduplication + phone lock check
 *   releaseLock()           - Release phone processing lock
 *   getWhatsAppName()       - Extract WhatsApp display name from message
 *
 * Flow: receive → dedup → guard checks → route to handler → respond
 *   1. Deduplication (message ID + phone lock)
 *   2. Maestro v4 admin handler (bypasses all other logic)
 *   3. Known client protection
 *   4. Bot control (hard off, business hours, never-contact)
 *   5. Human takeover check
 *   6. Quick Intake flow
 *   7. Intake Form flow
 *   8. Urgency detection
 *   9. Bot flow processing + LLM response
 *   10. Action processing (notify_team, start_quick_intake, etc.)
 *   11. Send response + Moskit transfer
 */

const { detectLanguage, getMessages, getLanguageName } = require("../languages");

// Dependencies injected via init()
let db = null;
let whatsappClient = null;
let notificationService = null;
let botConfig = null;
let knownClients = null;
let botFlow = null;
let quickIntake = null;
let intakeIntegration = null;
let llmChatbot = null;
let conversionTracking = null;
let moskitService = null;
let smsService = null;
let email = null;
let crmSync = null;
let mediaHandler = null;
let maestroV4 = null;
let schedulingService = null;

// ===== DEDUPLICATION STATE =====
const processedMessages = new Map();
const MESSAGE_CACHE_TTL = 120000; // 2 minutes

const processingLock = new Map();
const LOCK_TTL = 5000; // 5 seconds

/**
 * Initialize the message handler with all dependencies
 */
function init(deps) {
  db = deps.db;
  whatsappClient = deps.whatsappClient;
  notificationService = deps.notificationService;
  botConfig = deps.botConfig;
  knownClients = deps.knownClients;
  botFlow = deps.botFlow;
  quickIntake = deps.quickIntake;
  intakeIntegration = deps.intakeIntegration;
  llmChatbot = deps.llmChatbot;
  conversionTracking = deps.conversionTracking;
  moskitService = deps.moskitService;
  smsService = deps.smsService;
  email = deps.email;
  crmSync = deps.crmSync;
  mediaHandler = deps.mediaHandler;
  maestroV4 = deps.maestroV4;
  schedulingService = deps.schedulingService;

  // Proactive cache cleanup every 1 minute
  setInterval(() => {
    const now = Date.now();
    let cleaned = 0;

    for (const [id, timestamp] of processedMessages) {
      if (now - timestamp > MESSAGE_CACHE_TTL) {
        processedMessages.delete(id);
        cleaned++;
      }
    }

    for (const [phone, timestamp] of processingLock) {
      if (now - timestamp > LOCK_TTL) {
        processingLock.delete(phone);
      }
    }

    if (cleaned > 0) {
      console.log(`[DEDUP-CLEANUP] ${cleaned} mensagens antigas removidas do cache`);
    }
  }, 60000);

  console.log("[MSG-HANDLER] Service initialized");
}

/**
 * Check if a message should be processed (dedup + lock)
 */
function shouldProcessMessage(messageId, phoneNumber) {
  const now = Date.now();

  // Passive cleanup
  for (const [id, timestamp] of processedMessages) {
    if (now - timestamp > MESSAGE_CACHE_TTL) {
      processedMessages.delete(id);
    }
  }

  // ATOMIC check-and-set for message dedup
  if (processedMessages.has(messageId)) {
    console.log("[DEDUP] Mensagem duplicada ignorada:", messageId.substring(0, 20));
    return false;
  }
  processedMessages.set(messageId, now);

  // Phone lock check
  const lockTime = processingLock.get(phoneNumber);
  if (lockTime && (now - lockTime) < LOCK_TTL) {
    console.log("[LOCK] Telefone em processamento, ignorando:", phoneNumber);
    processedMessages.delete(messageId);
    return false;
  }
  processingLock.set(phoneNumber, now);

  return true;
}

/**
 * Release phone processing lock
 */
function releaseLock(phoneNumber) {
  processingLock.delete(phoneNumber);
}

/**
 * Extract WhatsApp display name from message object
 */
async function getWhatsAppName(message) {
  // Method 1: From _data (most reliable)
  try {
    if (message._data) {
      const pushName = message._data.notifyName || message._data.pushName;
      if (pushName && pushName.trim()) {
        console.log("[WA-NAME] Nome via _data:", pushName);
        return pushName.trim();
      }
    }
  } catch (e) {
    console.log("[WA-NAME] Erro _data:", e.message);
  }

  // Method 2: Via getContact()
  try {
    const contact = await message.getContact();
    if (contact) {
      const name = contact.pushname || contact.name || contact.shortName || contact.verifiedName;
      if (name && name.trim()) {
        console.log("[WA-NAME] Nome via contact:", name);
        return name.trim();
      }
    }
  } catch (e) {
    console.log("[WA-NAME] Erro contact:", e.message);
  }

  // Method 3: Via chat
  try {
    const chat = await message.getChat();
    if (chat && chat.name && chat.name.trim()) {
      console.log("[WA-NAME] Nome via chat:", chat.name);
      return chat.name.trim();
    }
  } catch (e) {
    console.log("[WA-NAME] Erro chat:", e.message);
  }

  return null;
}

/**
 * Main incoming message handler
 */
async function handleIncomingMessage(data) {
  const { from, body, message } = data;
  const { createMoskitContact, addMoskitActivity, calculateLeadScore, generateRecommendation } = moskitService;

  const phoneNumber = from.replace(/@c\.us|@lid/g, "");

  // Generate unique message ID
  const messageId = message.id
    ? (message.id._serialized || message.id.toString())
    : (phoneNumber + "_" + Date.now() + "_" + (body || "").substring(0, 10));

  // Dedup + lock check
  if (!shouldProcessMessage(messageId, phoneNumber)) {
    return;
  }

  let lead;
  try {
    // Skip empty messages
    const messageBody = body ? body.trim() : "";
    if (messageBody.length === 0) {
      console.log("[SKIP] Mensagem vazia ignorada de:", phoneNumber);
      releaseLock(phoneNumber);
      return;
    }

    console.log("\n[MSG] " + phoneNumber + ": " + messageBody.substring(0, 50) + "...");

    // v12.4: Maestro v4 Handler - Admin code modification via WhatsApp
    if (process.env.MAESTRO_ACTIVATION_ENABLED === "true" && maestroV4) {
      try {
        const maestroResponse = await maestroV4.handleMessage(phoneNumber, messageBody);
        if (maestroResponse) {
          console.log("[MAESTRO-V4] Resposta do Maestro para " + phoneNumber);
          await db.saveMessage(phoneNumber, "user", messageBody);
          await notificationService.send(phoneNumber, maestroResponse, {
            source: 'maestro-v4',
            skipGuard: true,
            saveToDB: true
          });
          releaseLock(phoneNumber);
          return;
        }
      } catch (maestroError) {
        console.error("[MAESTRO-V4] Erro:", maestroError.message);
      }
    }

    lead = await db.getLead(phoneNumber) || {};
    const currentState = lead.conversation_state || null;

    // v12.5: Known clients protection
    const clientCheck = knownClients.shouldBlockAutoResponse(phoneNumber, messageBody, lead);
    if (clientCheck.shouldBlock) {
      console.log(`[KNOWN-CLIENT] BLOQUEADO: ${phoneNumber} - ${clientCheck.reason}`);

      if (clientCheck.clientInfo && lead.contact_type !== "active_client") {
        console.log(`[KNOWN-CLIENT] Atualizando ${phoneNumber} para active_client`);
        await db.updateLead(phoneNumber, {
          contact_type: "active_client",
          bot_enabled: 0,
          human_takeover: 1,
          name: clientCheck.clientInfo.name,
          language: clientCheck.clientInfo.language || lead.language
        });
      }

      await db.saveMessage(phoneNumber, "user", messageBody);

      // v14.1: Notify caseworkers via CaseHub when known client sends message
      const clientName = (clientCheck.clientInfo && clientCheck.clientInfo.name) || lead.name || 'Unknown Client';
      crmSync.notifyClientMessage(phoneNumber, clientName, messageBody)
        .catch(err => console.log("[CRM-NOTIFY] Erro known-client:", err.message));

      releaseLock(phoneNumber);
      return;
    }

    // v12.0: Global bot control check
    const botStatus = botConfig.shouldBotRespond(phoneNumber);
    if (!botStatus.shouldRespond) {
      console.log(`[BOT-CONTROL] Bot inativo: ${botStatus.reason} - salvando mensagem sem responder`);
      await db.saveMessage(phoneNumber, "user", messageBody);

      // v14.1: Notify caseworkers when message received during business hours (bot off)
      const senderName = (lead && lead.name) || phoneNumber;
      crmSync.notifyClientMessage(phoneNumber, senderName, messageBody)
        .catch(err => console.log("[CRM-NOTIFY] Erro bot-off:", err.message));

      releaseLock(phoneNumber);
      return;
    }

    // v12.2: Never contact check
    if (lead && lead.never_contact === 1) {
      console.log(`[NEVER-CONTACT] Lead ${phoneNumber} marcada como NUNCA CONTATAR - ignorando completamente`);
      releaseLock(phoneNumber);
      return;
    }

    // v12.3: Active clients - no auto-reply
    if (lead && lead.contact_type === "active_client") {
      console.log(`[ACTIVE-CLIENT] Cliente ativo ${phoneNumber} - salvando mensagem sem resposta automatica`);
      await db.saveMessage(phoneNumber, "user", messageBody);
      releaseLock(phoneNumber);
      return;
    }

    // v11.0: Human takeover check
    if (lead && (lead.bot_enabled === 0 || lead.human_takeover)) {
      console.log(`[HUMAN-TAKEOVER] Bot pausado para ${phoneNumber} - salvando mensagem sem responder`);
      await db.saveMessage(phoneNumber, "user", messageBody);
      releaseLock(phoneNumber);
      return;
    }

    const isNewLead = !currentState;

    // Capture WhatsApp name on first message
    let whatsappName = lead.whatsapp_name;
    if (isNewLead) {
      whatsappName = await getWhatsAppName(message);
      console.log("[NEW] Novo lead! Nome WA:", whatsappName || "N/A");

      conversionTracking.trackNewLead({
        phone: phoneNumber,
        whatsapp_name: whatsappName,
        source: 'WhatsApp'
      }).catch(e => console.log("[CONVERSION] Erro nova lead:", e.message));
    }

    const source = lead.source || "Meta Ads";
    const langForUrgent = lead.language || detectLanguage(phoneNumber);

    // ===== Quick Intake in progress =====
    if (quickIntake.isQuickIntakeState(lead.conversation_state)) {
      console.log("[QUICK-INTAKE] Processando resposta Quick Intake...");
      const intakeResult = quickIntake.processQuickIntakeResponse(
        messageBody, lead.conversation_state, lead, langForUrgent
      );

      if (intakeResult) {
        if (intakeResult.isCompleted) {
          const scoring = intakeResult.scoring;
          const recommendation = generateRecommendation(scoring, langForUrgent);

          await db.updateLead(phoneNumber, {
            conversation_state: 'awaiting_human',
            lead_score: scoring.normalizedScore,
            lead_status: scoring.status ? scoring.status.toLowerCase() : 'qualified',
            quick_intake_answers: JSON.stringify(intakeResult.answers),
            quick_intake_scoring: JSON.stringify(scoring),
            quick_intake_completed: 1
          });

          await notificationService.send(phoneNumber, recommendation, {
            source: 'quick-intake-complete',
            replyTo: message,
            skipGuard: true,
            saveToDB: true
          });

          try {
            await conversionTracking.trackQualifiedLead({
              phone: phoneNumber,
              client_name: lead.client_name || lead.whatsapp_name,
              lead_score: scoring.normalizedScore,
              visa_interest: (intakeResult.answers && intakeResult.answers.goal) || ''
            });
          } catch(e) { console.log('[CONVERSION] Error:', e.message); }
        } else {
          await db.updateLead(phoneNumber, {
            conversation_state: intakeResult.newState,
            quick_intake_answers: JSON.stringify(intakeResult.answers || {})
          });
          await notificationService.send(phoneNumber, intakeResult.response, {
            source: 'quick-intake-question',
            replyTo: message,
            skipGuard: true,
            saveToDB: true
          });
        }
        releaseLock(phoneNumber);
        return;
      }
    }

    // ===== Intake Form flow =====
    if (intakeIntegration.isInIntakeFlow(lead)) {
      console.log("[INTAKE] Lead em fluxo de intake, processando...");

      let mediaInfo = null;
      if (message.hasMedia) {
        console.log("[INTAKE] Mensagem contem midia, baixando...");
        mediaInfo = await mediaHandler.processCVFile(message, phoneNumber);
        if (mediaInfo.success) {
          console.log("[INTAKE] Arquivo salvo:", mediaInfo.filename);
        } else {
          console.log("[INTAKE] Erro ao processar midia:", mediaInfo.error);
        }
      }

      const intakeResult = await intakeIntegration.processIntakeMessage(
        phoneNumber, messageBody, lead, whatsappClient, mediaInfo
      );
      if (intakeResult) {
        console.log("[INTAKE] Processado. Estado:", intakeResult.newState);
        releaseLock(phoneNumber);
        return;
      }
    }

    // ===== Urgency detection =====
    if (botFlow.isUrgent(messageBody, langForUrgent)) {
      console.log("[URGENT] Detectado!");
      const msgs = getMessages(langForUrgent);
      const resp = msgs.urgent;
      await db.saveMessage(phoneNumber, "user", messageBody);
      await notificationService.send(phoneNumber, resp, {
        source: 'urgent-handler',
        replyTo: message,
        skipGuard: true,
        saveToDB: true
      });

      const urgentLead = { ...lead, is_urgent: true };
      const { score, status } = calculateLeadScore(urgentLead);

      await db.updateLead(phoneNumber, {
        conversation_state: "transferred",
        is_urgent: true,
        whatsapp_name: whatsappName,
        source: source,
        moskit_sent: true,
        language: langForUrgent,
        lead_score: score,
        lead_status: status
      });

      conversionTracking.trackQualifiedLead({
        phone: phoneNumber,
        client_name: lead.client_name || whatsappName,
        is_urgent: true,
        lead_score: score
      }).catch(e => console.log("[CONVERSION] Erro urgente:", e.message));

      email.sendUrgentLeadEmail({
        phone: phoneNumber,
        client_name: lead.client_name || whatsappName,
        visa_interest: lead.visa_interest,
        whatsapp_name: whatsappName
      }).catch(err => console.log("[EMAIL] Erro urgente:", err.message));

      await createMoskitContact({
        ...lead,
        phone: phoneNumber,
        urgent: true,
        whatsapp_name: whatsappName,
        source: source,
        lead_score: score,
        lead_status: status
      });
      crmSync.sendToCRM({ ...lead, phone: phoneNumber, urgent: true, whatsapp_name: whatsappName, source, lead_score: score, lead_status: status })
        .catch(err => console.log("[CRM-SYNC] Erro urgent:", err.message));
      releaseLock(phoneNumber);
      return;
    }

    // ===== Main bot flow processing =====
    const detectedLang = lead.language || detectLanguage(phoneNumber);
    if (isNewLead) {
      console.log("[LANG] Idioma detectado:", getLanguageName(detectedLang), "(" + detectedLang + ")");
    }

    const cachedSlots = schedulingService.getAvailableSlotsCache().get(phoneNumber);
    const context = {
      availableSlots: cachedSlots ? cachedSlots.slots : null,
      phoneNumber: phoneNumber
    };

    const leadWithUpdatedCount = { ...lead, message_count: (lead.message_count || 0) + 1 };
    const result = botFlow.processMessage(messageBody, currentState, leadWithUpdatedCount, context);

    await db.saveMessage(phoneNumber, "user", messageBody);

    addMoskitActivity(phoneNumber, messageBody, 'received')
      .catch(err => console.log("[MOSKIT-ACTIVITY] Erro registrar recebida:", err.message));

    // Handle shouldIgnore (awaiting human)
    if (result.shouldIgnore) {
      console.log("[HANDOFF] Aguardando atendimento humano - mensagem salva");

      await db.updateLead(phoneNumber, {
        conversation_state: result.newState,
        whatsapp_name: whatsappName || lead.whatsapp_name,
        source: source
      });

      releaseLock(phoneNumber);
      return;
    }

    let responseMessage = result.response;

    // ===== LLM response generation =====
    if (result.useLLM && !responseMessage) {
      try {
        console.log("[LLM] Gerando resposta automática para:", phoneNumber);

        const isActiveClient = !!(
          lead.has_paid === 1 ||
          ['VISA_IN_PROGRESS', 'CONSULTATION', 'CLOSING'].includes(lead.deal_stage) ||
          lead.moskit_deal_id
        );

        if (isActiveClient) {
          console.log("[ACTIVE-CLIENT-DETECTOR] Cliente ativo detectado - LLM oferecerá SOMENTE /meeting");
        }

        const llmResponse = await llmChatbot.processMessage(messageBody, lead, db, isActiveClient);

        if (llmResponse && llmResponse.shouldRespond && llmResponse.response) {
          responseMessage = llmResponse.response;
          console.log("[LLM] Resposta gerada com sucesso");

          if (llmResponse.blocked === 'legal_advice') {
            console.error("╔═══════════════════════════════════════════════════════════════╗");
            console.error("║  ⚠️  LEGAL ADVICE BLOQUEADO - REVISÃO HUMANA NECESSÁRIA  ⚠️   ║");
            console.error("╠═══════════════════════════════════════════════════════════════╣");
            console.error("║ Telefone:", phoneNumber.padEnd(48), "║");
            console.error("║ Nome:", (lead.client_name || lead.whatsapp_name || 'N/A').substring(0, 48).padEnd(48), "║");
            console.error("║ Pattern:", (llmResponse.blockedPattern || 'N/A').substring(0, 48).padEnd(48), "║");
            console.error("║ Ação: Resposta substituída por redirecionamento seguro       ║");
            console.error("║ Próximos passos: Revisar conversa manualmente no CaseHub    ║");
            console.error("╚═══════════════════════════════════════════════════════════════╝");

            try {
              await db.query(
                `UPDATE leads SET
                  needs_human_review = 1,
                  legal_advice_blocked_count = COALESCE(legal_advice_blocked_count, 0) + 1,
                  last_legal_advice_block = NOW()
                WHERE phone = ?`,
                [phoneNumber]
              );
            } catch (dbErr) {
              console.error("[DB] Erro ao marcar lead para revisão:", dbErr.message);
            }
          }

          if (llmResponse.needsHuman) {
            console.log("[LLM] Sinalizou necessidade de humano");
          }
        } else {
          console.log("[LLM] Não gerou resposta (shouldRespond=false ou resposta vazia)");
        }
      } catch (llmError) {
        console.error("[LLM] Erro ao gerar resposta:", llmError.message);

        const fallbackLang = langForUrgent || "en";
        const fallbackMsgs = {
          pt: "Obrigado pela mensagem! Nossa equipe vai te atender em breve.\n\nEnquanto isso, se preferir, agende uma reuniao com nossa equipe:\n\n📅 Clientes ativos (reuniao com paralegal):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n📅 Clientes novos (ligacao introdutoria gratuita):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall\n\nAtenciosamente,\n${process.env.ORG_NAME || "CaseHub"}",
          en: "Thank you for your message! We will answer it as soon as possible.\n\nMeanwhile, if you would like, you can schedule a meeting with our team:\n\n📅 Active clients (meeting with paralegal):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n📅 New clients (free introductory call - no legal advice or lawyer):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall\n\nThank you!\n${process.env.ORG_NAME || "CaseHub"}",
          es: "Gracias por tu mensaje! Nuestro equipo te atendera pronto.\n\nMientras tanto, si lo desea, puede programar una reunion con nuestro equipo:\n\n📅 Clientes activos (reunion con paralegal):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n📅 Clientes nuevos (llamada introductoria gratuita):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall\n\nSaludos cordiales,\n${process.env.ORG_NAME || "CaseHub"}"
        };
        responseMessage = fallbackMsgs[fallbackLang] || fallbackMsgs.en;
        console.log("[LLM] Usando resposta fallback");
      }
    }

    // ===== Action processing =====
    if (result.action) {
      switch (result.action) {
        case "notify_team":
          console.log("[ACTION] Nova lead - notificando equipe...");
          smsService.queueSMS(`Nova Lead CaseHub!\n${whatsappName || 'Lead'}\nTel: ${phoneNumber}\nMsg: ${messageBody.substring(0, 50)}`);

          createMoskitContact({
            phone: phoneNumber,
            client_name: whatsappName || "Lead WhatsApp",
            whatsapp_name: whatsappName,
            source: source,
            lead_score: 10,
            lead_status: 'new'
          }).catch(err => console.log("[MOSKIT] Erro criar lead:", err.message));
          crmSync.sendToCRM({ phone: phoneNumber, client_name: whatsappName || "Lead WhatsApp", whatsapp_name: whatsappName, source, lead_score: 10 })
            .catch(err => console.log("[CRM-SYNC] Erro new lead:", err.message));
          break;

        case "notify_team_message":
          console.log("[ACTION] Mensagem adicional...");
          break;

        case "start_quick_intake":
          console.log("[QUICK-INTAKE] Iniciando Quick Intake automatico para", phoneNumber);
          {
            const intakeStart = quickIntake.startQuickIntake(detectedLang);
            if (intakeStart) {
              await db.updateLead(phoneNumber, {
                conversation_state: intakeStart.newState || 'quick_intake_q1',
                quick_intake_answers: '{}'
              });

              const transitionMsg = detectedLang === 'pt'
                ? "Para te atender melhor, gostaria de fazer algumas perguntas rapidas sobre seu caso. Sao apenas 12 perguntas e vai nos ajudar a entender como podemos te ajudar!\n\n"
                : "To better assist you, I'd like to ask a few quick questions about your case. It's just 12 questions and will help us understand how we can help!\n\n";

              const fullMessage = transitionMsg + intakeStart.response;
              await notificationService.send(phoneNumber, fullMessage, {
                source: 'quick-intake-start',
                replyTo: message,
                skipGuard: true,
                saveToDB: true
              });

              responseMessage = null;
            }
          }
          break;

        case "use_llm":
          console.log("[ACTION] Resposta LLM processada");
          break;

        case "send_free_consultation_email":
          console.log("[ACTION] Enviando email de consulta gratuita...");
          const leadDataForEmail = {
            phone: phoneNumber,
            client_name: lead.client_name || whatsappName,
            email: lead.email,
            visa_interest: lead.visa_interest,
            whatsapp_name: whatsappName,
            language: lead.language || detectedLang
          };
          email.sendFreeConsultationRequest(leadDataForEmail).catch(err =>
            console.log("[EMAIL] Erro:", err.message)
          );
          break;
      }
    }

    // ===== Send response =====
    if (responseMessage) {
      const sendResult = await notificationService.send(phoneNumber, responseMessage, {
        source: 'main-handler',
        replyTo: message,
        skipGuard: true,
        saveToDB: true
      });

      if (sendResult.sent) {
        addMoskitActivity(phoneNumber, responseMessage, 'sent')
          .catch(err => console.log("[MOSKIT-ACTIVITY] Erro registrar enviada:", err.message));

        await db.updateLead(phoneNumber, {
          ...result.data,
          conversation_state: result.newState,
          whatsapp_name: whatsappName || lead.whatsapp_name,
          source: source
        });

        console.log("[STATE] " + result.newState);
      } else {
        console.log("[MAIN-HANDLER] Envio bloqueado: " + sendResult.reason);
      }
    }

    // ===== Transfer to Moskit (complete flow) =====
    if (result.shouldTransfer) {
      const updatedLead = await db.getLead(phoneNumber);

      const { score, status } = calculateLeadScore(updatedLead);
      await db.updateLead(phoneNumber, { lead_score: score, lead_status: status });

      const leadForNotification = {
        ...updatedLead,
        phone: phoneNumber,
        lead_score: score,
        lead_status: status
      };

      console.log("[NOTIFY] Fluxo completo - enviando notificacoes...");

      email.sendNewLeadEmail(leadForNotification).catch(err =>
        console.log("[EMAIL] Erro ao enviar lead completa:", err.message)
      );

      await createMoskitContact({
        ...leadForNotification,
        source: source,
        auto_registered: false
      });
      await db.updateLead(phoneNumber, { moskit_sent: true });
      console.log("[MOSKIT] Lead enviado! Score:", score, "Status:", status);

      crmSync.sendToCRM({ ...leadForNotification, source })
        .catch(err => console.log("[CRM-SYNC] Erro lead complete:", err.message));
    }

  } catch (error) {
    console.error("[ERROR]", error.message);
    try {
      const errorLang = (lead && lead.language) || detectLanguage(phoneNumber);
      const errorMsgs = {
        pt: "Desculpe, problema técnico. Nossa equipe vai te atender em breve! / Sorry, technical issue. Our team will assist you shortly!",
        en: "Sorry, technical issue. Our team will assist you shortly! / Desculpe, problema técnico. Nossa equipe vai te atender em breve!",
        es: "Disculpe, problema técnico. Nuestro equipo le atenderá pronto! / Sorry, technical issue. Our team will assist you shortly!"
      };
      if (message && typeof message.reply === "function") {
        await notificationService.send(phoneNumber, errorMsgs[errorLang] || errorMsgs.en, {
          source: 'error-handler',
          replyTo: message,
          skipGuard: true,
          skipDedup: true,
          saveToDB: false
        });
      }
    } catch(e){}
  } finally {
    releaseLock(phoneNumber);
  }
}

module.exports = {
  init,
  handleIncomingMessage,
  shouldProcessMessage,
  releaseLock,
  getWhatsAppName
};
