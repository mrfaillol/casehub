/**
 * Scheduling Service - Follow-ups, consultation checks, catch-up, time caching
 * Extracted from server.js (Fase 2.2 decomposition)
 *
 * Functions:
 *   checkLeadsAwaitingConsultation() - Follow-up leads that finished flow but didn't schedule
 *   checkIncompleteLeads()           - Follow-up incomplete leads (2h timeout)
 *   getAndCacheAvailableTimes()      - Fetch and cache Calendly slots
 *   processPendingMessages()         - Catch-up: respond to messages received while bot was off
 *   getAvailableSlotsCache()         - Access the slots cache (for message handler context)
 *   cleanupSlotsCache()              - Cleanup expired cache entries
 *
 * NOTE: checkLeadsAwaitingConsultation and checkIncompleteLeads are currently DISABLED
 *       in production (setIntervals commented out in server.js since v9.1).
 *       Code is preserved for potential future re-enablement.
 */

const { detectLanguage } = require("../languages");

// Dependencies injected via init()
let db = null;
let notificationService = null;
let moskitService = null;
let email = null;
let crmSync = null;
let calendly = null;
let llmChatbot = null;
let botConfig = null;

const INCOMPLETE_LEAD_TIMEOUT_HOURS = 2;

// Cache for Calendly available slots
const availableSlotsCache = new Map();
const SLOTS_CACHE_TTL = 30 * 60 * 1000; // 30 minutes

/**
 * Initialize the scheduling service with dependencies
 */
function init(deps) {
  db = deps.db;
  notificationService = deps.notificationService;
  moskitService = deps.moskitService;
  email = deps.email;
  crmSync = deps.crmSync;
  calendly = deps.calendly;
  llmChatbot = deps.llmChatbot;
  botConfig = deps.botConfig;
  // Cleanup expired slots cache every 5 minutes
  setInterval(cleanupSlotsCache, 5 * 60 * 1000);
  console.log("[SCHEDULING] Service initialized");
}

/**
 * Cleanup expired cache entries (slots + forms)
 */
function cleanupSlotsCache() {
  const now = Date.now();
  for (const [phone, data] of availableSlotsCache) {
    if (now - data.timestamp > SLOTS_CACHE_TTL) {
      availableSlotsCache.delete(phone);
    }
  }
}

/**
 * Get the available slots cache Map (for message handler context)
 */
function getAvailableSlotsCache() {
  return availableSlotsCache;
}

/**
 * Fetch and cache available Calendly consultation times
 */
async function getAndCacheAvailableTimes(phone, consultationType = "free") {
  try {
    let times;
    if (consultationType === "paid") {
      times = await calendly.getPaidConsultationTimes(7);
    } else {
      times = await calendly.getFreeConsultationTimes(7);
    }

    const formatted = calendly.formatTimesForWhatsApp(times, 6);

    availableSlotsCache.set(phone, {
      slots: formatted.slots,
      consultationType: consultationType,
      timestamp: Date.now()
    });

    return formatted;
  } catch (error) {
    console.error("[CALENDLY] Erro ao buscar horarios:", error.message);
    return {
      message: "Desculpe, nao consegui buscar os horarios. Por favor, acesse: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting",
      slots: []
    };
  }
}

/**
 * Follow-up leads that completed the flow but didn't schedule a consultation
 * DISABLED since v9.1 - replaced by intake form follow-ups
 */
async function checkLeadsAwaitingConsultation() {
  try {
    const leads = await db.getLeadsAwaitingConsultation();

    console.log("[CONSULT-FOLLOWUP] Verificando " + leads.length + " leads aguardando consulta...");

    for (const lead of leads) {
      const followupStage = lead.awaiting_consultation_followup || 0;
      const lang = lead.language || detectLanguage(lead.phone);
      const firstName = (lead.client_name || lead.whatsapp_name || "").split(" ")[0];

      // Já agendou? Pular
      if (lead.consultation_scheduled) continue;

      // ===== VERIFICACAO DE CONVERSA ATIVA (v8.3) =====
      const activity = await db.getConversationActivity(lead.phone);
      if (activity) {
        if (activity.hasHumanResponse) {
          console.log("[CONSULT-FOLLOWUP] Resposta humana detectada, marcando agendado:", lead.phone);
          await db.updateLead(lead.phone, { consultation_scheduled: true });
          continue;
        }

        if (activity.lastClientMessage) {
          const hoursSinceClientMsg = (Date.now() - new Date(activity.lastClientMessage.created_at).getTime()) / (1000 * 60 * 60);
          if (hoursSinceClientMsg < 24) {
            console.log("[CONSULT-FOLLOWUP] Conversa ativa (" + Math.round(hoursSinceClientMsg) + "h), pulando:", lead.phone);
            continue;
          }
        }

        if (activity.recentMessageCount >= 3) {
          console.log("[CONSULT-FOLLOWUP] Conversa em andamento (" + activity.recentMessageCount + " msgs), pulando:", lead.phone);
          continue;
        }
      }

      // Calcular tempo desde última mensagem do CLIENTE
      let hoursSinceUpdate;
      if (activity && activity.lastClientMessage) {
        hoursSinceUpdate = (Date.now() - new Date(activity.lastClientMessage.created_at).getTime()) / (1000 * 60 * 60);
      } else {
        hoursSinceUpdate = (Date.now() - new Date(lead.updated_at || lead.created_at).getTime()) / (1000 * 60 * 60);
      }

      let shouldSend = false;
      let message = "";
      let newStage = followupStage;

      // Stage 0 -> 1: Após 4h - Tranquilizar
      if (followupStage === 0 && hoursSinceUpdate >= 4) {
        shouldSend = true;
        newStage = 1;
        if (lang === "pt") {
          message = "Olá" + (firstName ? " " + firstName : "") + "! \n\nRecebemos seu contato e nossa equipe está analisando seu caso.\n\nEm breve entraremos em contato para agendar sua consulta. Obrigado pela paciência!";
        } else if (lang === "es") {
          message = "¡Hola" + (firstName ? " " + firstName : "") + "! \n\nRecibimos tu contacto y nuestro equipo está analizando tu caso.\n\nPronto te contactaremos para agendar tu consulta. ¡Gracias por tu paciencia!";
        } else {
          message = "Hi" + (firstName ? " " + firstName : "") + "! \n\nWe received your message and our team is reviewing your case.\n\nWe will contact you soon to schedule your consultation. Thank you for your patience!";
        }
      }
      // Stage 1 -> 2: Após 24h - Oferecer Calendly
      else if (followupStage === 1 && hoursSinceUpdate >= 24) {
        shouldSend = true;
        newStage = 2;
        if (lang === "pt") {
          message = (firstName ? firstName + ", " : "") + "pedimos desculpas pela demora! \n\nSe preferir não esperar, você pode agendar diretamente sua consulta gratuita:\n\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\nÉ rápido e você escolhe o melhor horário para você!";
        } else if (lang === "es") {
          message = (firstName ? firstName + ", " : "") + "¡pedimos disculpas por la demora! \n\nSi prefieres no esperar, puedes agendar directamente tu consulta gratuita:\n\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n¡Es rápido y eliges el mejor horario para ti!";
        } else {
          message = (firstName ? firstName + ", " : "") + "we apologize for the delay! \n\nIf you prefer not to wait, you can schedule your free consultation directly:\n\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\nIt's quick and you choose the best time for you!";
        }
      }
      // Stage 2 -> 3: Após 48h - Última tentativa
      else if (followupStage === 2 && hoursSinceUpdate >= 48) {
        shouldSend = true;
        newStage = 3;
        if (lang === "pt") {
          message = (firstName ? firstName + ", " : "") + "esta é nossa última tentativa de contato! \n\nNão queremos que você perca a oportunidade de uma consulta gratuita sobre seu caso de imigração.\n\nAgende agora (leva 30 segundos):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\nEstamos ansiosos para ajudar!";
        } else if (lang === "es") {
          message = (firstName ? firstName + ", " : "") + "¡este es nuestro último intento de contacto! \n\nNo queremos que pierdas la oportunidad de una consulta gratuita sobre tu caso de inmigración.\n\nAgenda ahora (toma 30 segundos):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n¡Estamos ansiosos por ayudarte!";
        } else {
          message = (firstName ? firstName + ", " : "") + "this is our last attempt to reach you! \n\nWe don't want you to miss the opportunity for a free consultation about your immigration case.\n\nSchedule now (takes 30 seconds):\n${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\nWe're eager to help!";
        }
      }

      if (shouldSend && message) {
        try {
          const sendResult = await notificationService.send(lead.phone, message, {
            source: 'consult-followup',
            saveToDB: true
          });
          if (sendResult.sent) {
            await db.updateLead(lead.phone, {
              awaiting_consultation_followup: newStage,
              last_consultation_followup_at: new Date()
            });
            console.log("[CONSULT-FOLLOWUP] Stage " + newStage + " enviado para:", lead.phone);
          }
        } catch (e) {
          console.error("[CONSULT-FOLLOWUP] Erro ao enviar:", e.message);
        }
      }
    }
  } catch (error) {
    console.error("[CONSULT-FOLLOWUP] Erro:", error.message);
  }
}

/**
 * Follow-up incomplete leads after timeout (2h)
 * DISABLED since v9.1 - replaced by intake form follow-ups
 */
async function checkIncompleteLeads() {
  const { calculateLeadScore, createMoskitContact } = moskitService;

  try {
    const timeoutMs = INCOMPLETE_LEAD_TIMEOUT_HOURS * 60 * 60 * 1000;
    const cutoffTime = new Date(Date.now() - timeoutMs);

    const incompleteLeads = await db.getIncompleteLeads(cutoffTime);

    console.log("[FOLLOWUP] Verificando " + incompleteLeads.length + " leads incompletas...");

    for (const lead of incompleteLeads) {
      const followupCount = lead.followup_count || 0;
      const lang = lead.language || detectLanguage(lead.phone);

      if (followupCount < 2) {
        console.log("[FOLLOWUP] Enviando follow-up " + (followupCount + 1) + " para:", lead.phone);

        let followupMessage = "";
        const firstName = (lead.client_name || lead.whatsapp_name || "").split(" ")[0];

        if (followupCount === 0) {
          if (lang === "pt") {
            followupMessage = "Oi" + (firstName ? " " + firstName : "") + "! Vi que voce nos procurou mas nao conseguimos terminar sua consulta.\n\nAinda precisa de ajuda com imigracao? Estou aqui para te ajudar! Qual seu interesse?\n\n1. Green Card\n2. Visto de Trabalho\n3. Cidadania\n4. Outro";
          } else if (lang === "es") {
            followupMessage = "Hola" + (firstName ? " " + firstName : "") + "! Vi que nos contactaste pero no pudimos terminar tu consulta.\n\nTodavia necesitas ayuda con inmigracion? Estoy aqui para ayudarte! Cual es tu interes?\n\n1. Green Card\n2. Visa de Trabajo\n3. Ciudadania\n4. Otro";
          } else {
            followupMessage = "Hi" + (firstName ? " " + firstName : "") + "! I noticed you reached out but we couldn't finish your consultation.\n\nDo you still need help with immigration? I'm here to help! What's your interest?\n\n1. Green Card\n2. Work Visa\n3. Citizenship\n4. Other";
          }
        } else {
          if (lang === "pt") {
            followupMessage = (firstName ? firstName + ", " : "") + "ultima tentativa de contato!\n\nSe ainda tiver interesse em nossos servicos de imigracao, responda esta mensagem.\n\nCaso contrario, quando precisar, estamos a disposicao.\n\nAbracos,\n${process.env.ORG_NAME || "CaseHub"}";
          } else if (lang === "es") {
            followupMessage = (firstName ? firstName + ", " : "") + "ultimo intento de contacto!\n\nSi aun tienes interes en nuestros servicios de inmigracion, responde a este mensaje.\n\nDe lo contrario, cuando necesites, estamos a tu disposicion.\n\nSaludos,\n${process.env.ORG_NAME || "CaseHub"}";
          } else {
            followupMessage = (firstName ? firstName + ", " : "") + "last attempt to reach you!\n\nIf you're still interested in our immigration services, please reply to this message.\n\nOtherwise, we're here whenever you need us.\n\nBest regards,\n${process.env.ORG_NAME || "CaseHub"}";
          }
        }

        try {
          const sendResult = await notificationService.send(lead.phone, followupMessage, {
            source: 'legacy-followup',
            saveToDB: true
          });
          if (sendResult.sent) {
            await db.updateLead(lead.phone, {
              followup_count: followupCount + 1,
              last_followup_at: new Date()
            });
            console.log("[FOLLOWUP] Follow-up " + (followupCount + 1) + " enviado para:", lead.phone);
          }
        } catch (e) {
          console.error("[FOLLOWUP] Erro ao enviar:", e.message);
        }

        continue;
      }

      // Se ja enviou 2 follow-ups e nao respondeu, registra no Moskit
      console.log("[FOLLOWUP] Auto-registrando (apos 2 follow-ups):", lead.phone, "-", lead.whatsapp_name || "Sem nome");

      const { score, status } = calculateLeadScore(lead);

      const leadDataForMoskit = {
        ...lead,
        client_name: lead.client_name || lead.whatsapp_name || "Lead WhatsApp (sem resposta)",
        source: lead.source || "Meta Ads",
        auto_registered: true,
        lead_score: score,
        lead_status: status
      };

      email.sendNewLeadEmail({
        ...leadDataForMoskit,
        phone: lead.phone,
        timeout_registered: true
      }).catch(err => console.log("[EMAIL] Erro timeout:", err.message));

      const moskitResult = await createMoskitContact(leadDataForMoskit);

      if (moskitResult.success) {
        await db.updateLead(lead.phone, {
          moskit_sent: true,
          moskit_id: moskitResult.id,
          auto_registered: true,
          lead_score: score,
          lead_status: status
        });
        console.log("[FOLLOWUP] Lead auto-registrada no Moskit:", moskitResult.id);

        crmSync.sendToCRM({ ...leadDataForMoskit, moskit_id: moskitResult.id })
          .catch(err => console.log("[CRM-SYNC] Erro followup:", err.message));
      }
    }
  } catch (error) {
    console.error("[FOLLOWUP] Erro:", error.message);
  }
}

/**
 * Catch-up: Respond to messages received while bot was off (auto-reactivation)
 * v4.1 - Feb 2026
 */
let _catchUpRunning = false;

async function processPendingMessages(disabledSince) {
  if (_catchUpRunning) {
    console.log("[CATCH-UP] Já em execução, pulando...");
    return;
  }
  _catchUpRunning = true;

  try {
    console.log("[CATCH-UP] Iniciando catch-up de mensagens pendentes desde", disabledSince);

    const [pendingLeads] = await db.query(`
      SELECT DISTINCT c1.phone,
             c1.content as last_message,
             c1.created_at as msg_time,
             l.bot_enabled, l.human_takeover, l.contact_type,
             l.never_contact, l.language, l.client_name, l.whatsapp_name
      FROM conversations c1
      INNER JOIN leads l ON c1.phone = l.phone
      LEFT JOIN conversations c2 ON
        c1.phone = c2.phone
        AND c2.role = 'assistant'
        AND c2.created_at > c1.created_at
      WHERE c1.role = 'user'
        AND c1.created_at >= ?
        AND c2.id IS NULL
        AND l.bot_enabled = 1
        AND (l.human_takeover = 0 OR l.human_takeover IS NULL)
        AND (l.contact_type != 'active_client' OR l.contact_type IS NULL)
        AND (l.never_contact = 0 OR l.never_contact IS NULL)
      ORDER BY c1.created_at ASC
    `, [disabledSince]);

    if (!pendingLeads || pendingLeads.length === 0) {
      console.log("[CATCH-UP] Nenhuma mensagem pendente encontrada.");
      return;
    }

    console.log("[CATCH-UP] Encontradas " + pendingLeads.length + " conversas pendentes.");

    let processed = 0;
    let failed = 0;

    for (const pending of pendingLeads) {
      try {
        console.log("[CATCH-UP] Processando: " + pending.phone + " (" + (pending.client_name || pending.whatsapp_name || "desconhecido") + ")");
        console.log("[CATCH-UP] Mensagem pendente: " + pending.last_message.substring(0, 80) + "...");

        const lead = await db.getLead(pending.phone);
        if (!lead) {
          console.log("[CATCH-UP] Lead não encontrado, pulando:", pending.phone);
          continue;
        }

        if (!lead.bot_enabled || lead.human_takeover || lead.contact_type === "active_client" || lead.never_contact) {
          console.log("[CATCH-UP] Lead não elegível mais, pulando:", pending.phone);
          continue;
        }

        const llmResponse = await llmChatbot.processMessage(pending.last_message, lead, db);

        if (llmResponse && llmResponse.shouldRespond && llmResponse.response) {
          if (processed > 0) {
            await new Promise(resolve => setTimeout(resolve, 3000 + Math.random() * 2000));
          }

          const sendResult = await notificationService.send(pending.phone, llmResponse.response, {
            source: 'catch-up',
            saveToDB: true
          });

          if (sendResult.sent) {
            processed++;
            console.log("[CATCH-UP] Resposta enviada para " + pending.phone);
          } else {
            console.log("[CATCH-UP] Envio bloqueado para " + pending.phone + ": " + sendResult.reason);
          }
        } else {
          console.log("[CATCH-UP] LLM não gerou resposta para " + pending.phone);
        }

      } catch (err) {
        failed++;
        console.error("[CATCH-UP] Erro ao processar " + pending.phone + ":", err.message);
      }
    }

    console.log("[CATCH-UP] Finalizado. Processadas: " + processed + " | Falhas: " + failed + " | Total: " + pendingLeads.length);

  } catch (error) {
    console.error("[CATCH-UP] Erro geral:", error.message);
  } finally {
    _catchUpRunning = false;
  }
}

module.exports = {
  init,
  checkLeadsAwaitingConsultation,
  checkIncompleteLeads,
  getAndCacheAvailableTimes,
  processPendingMessages,
  getAvailableSlotsCache,
  cleanupSlotsCache,
  INCOMPLETE_LEAD_TIMEOUT_HOURS
};
