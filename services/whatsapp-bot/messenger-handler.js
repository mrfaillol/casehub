/**
 * Messenger Handler Inteligente
 * CaseHub
 * v1.0 - Gerenciamento com migracao para WhatsApp
 *
 * Regras:
 * 1. Score baixo por padrao (Messenger = canal menos qualificado)
 * 2. Objetivo principal: migrar lead para WhatsApp
 * 3. So registra no Moskit se:
 *    - Tiver contato real (telefone/email) E
 *    - NAO migrou para WhatsApp E
 *    - Ficou inativo por X horas
 * 4. Follow-up automatico 2x antes de desistir
 */

const messenger = require('./messenger');
const db = require('./database');
const { detectLanguage } = require('./languages');

// ===== CONFIGURACAO =====
const MESSENGER_SETTINGS = {
  // Tempo de inercia para considerar lead "abandonada" (em horas)
  INACTIVITY_TIMEOUT_HOURS: 4,

  // Intervalo entre follow-ups (em horas)
  FOLLOWUP_INTERVAL_HOURS: 2,

  // Maximo de follow-ups automaticos
  MAX_FOLLOWUPS: 2,

  // Score base para leads do Messenger (baixo)
  BASE_SCORE: 15,

  // Score maximo para Messenger (mesmo com todos os dados)
  MAX_SCORE: 45,

  // Numero do WhatsApp para redirecionar
  WHATSAPP_NUMBER: '19406195856'
};

// Estados do fluxo Messenger
const MESSENGER_STATES = {
  NEW: 'msg_new',
  GREETED: 'msg_greeted',
  ASKED_INTEREST: 'msg_asked_interest',
  ASKED_WHATSAPP: 'msg_asked_whatsapp',
  FOLLOWUP_1: 'msg_followup_1',
  FOLLOWUP_2: 'msg_followup_2',
  CONVERTED: 'msg_converted',
  ABANDONED: 'msg_abandoned',
  REGISTERED: 'msg_registered'
};

// Cache de leads em processamento
const processingMessenger = new Map();
const PROCESSING_TTL = 10000; // 10 segundos

/**
 * Calcular score especifico para Messenger
 * Score maximo: 45 (muito abaixo do WhatsApp que pode chegar a 100)
 */
function calculateMessengerScore(lead) {
  let score = MESSENGER_SETTINGS.BASE_SCORE;

  // Tem nome (+5)
  if (lead.lead_name && lead.lead_name !== 'Usuario') score += 5;

  // Tem telefone (+10) - dado mais valioso
  if (lead.lead_phone) score += 10;

  // Tem email (+5)
  if (lead.lead_email) score += 5;

  // Respondeu mais de 3 mensagens (+5) - engajamento
  if (lead.message_count && lead.message_count > 3) score += 5;

  // Mencionou interesse em visto (+5)
  if (lead.interest && lead.interest.length > 10) score += 5;

  return Math.min(score, MESSENGER_SETTINGS.MAX_SCORE);
}

/**
 * Verificar se deve registrar no Moskit
 */
function shouldRegisterInMoskit(lead) {
  // Nao registrar se ja converteu para WhatsApp
  if (lead.converted_to_whatsapp) {
    console.log('[MSG-HANDLER] Nao registrar: ja converteu para WhatsApp');
    return false;
  }

  // Nao registrar se so tem ID e nome (dados insuficientes)
  const hasRealContact = lead.lead_phone || lead.lead_email;
  if (!hasRealContact) {
    console.log('[MSG-HANDLER] Nao registrar: sem contato real (telefone/email)');
    return false;
  }

  // Nao registrar se ja foi registrado
  if (lead.registered_in_moskit) {
    console.log('[MSG-HANDLER] Nao registrar: ja esta no Moskit');
    return false;
  }

  return true;
}

/**
 * Verificar se lead esta inativa (para registro)
 */
function isInactive(lead) {
  if (!lead.last_activity) return false;

  const lastActivity = new Date(lead.last_activity);
  const now = new Date();
  const hoursDiff = (now - lastActivity) / (1000 * 60 * 60);

  return hoursDiff >= MESSENGER_SETTINGS.INACTIVITY_TIMEOUT_HOURS;
}

/**
 * Detectar se a mensagem contem um numero de telefone
 */
function extractPhoneNumber(text) {
  if (!text) return null;

  // Padroes de telefone
  const patterns = [
    /\+?\d{1,3}[\s.-]?\(?\d{2,3}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}/g,
    /\(?\d{2,3}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}/g,
    /\d{10,13}/g
  ];

  for (const pattern of patterns) {
    const matches = text.match(pattern);
    if (matches && matches.length > 0) {
      // Limpar e normalizar
      let phone = matches[0].replace(/[\s.\-()]/g, '');

      // Adicionar codigo do pais se nao tiver
      if (!phone.startsWith('+')) {
        if (phone.length === 10 || phone.length === 11) {
          phone = '55' + phone; // Brasil
        } else if (phone.length === 10) {
          phone = '1' + phone; // EUA
        }
      }

      return phone.replace('+', '');
    }
  }

  return null;
}

/**
 * Detectar se a mensagem contem um email
 */
function extractEmail(text) {
  if (!text) return null;

  const emailPattern = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
  const matches = text.match(emailPattern);

  return matches ? matches[0].toLowerCase() : null;
}

/**
 * Gerar mensagem baseada no estado e idioma
 */
function getMessageForState(state, lang, leadName) {
  const name = leadName || '';
  const firstName = name.split(' ')[0] || '';
  const WPP = MESSENGER_SETTINGS.WHATSAPP_NUMBER;

  const messages = {
    pt: {
      greeting: "Ola" + (firstName ? " " + firstName : "") + "! Obrigado por entrar em contato com o ${process.env.ORG_NAME || "CaseHub"}.\n\nPara melhor atende-lo, podemos continuar pelo WhatsApp? E mais rapido e seguro.\n\nQual seu numero de WhatsApp? (com codigo do pais)",

      ask_whatsapp: "Para darmos continuidade ao seu atendimento, preciso do seu WhatsApp.\n\nPor favor, envie seu numero com codigo do pais.\nEx: +55 11 99999-9999 ou +1 555 123-4567",

      followup_1: "Oi" + (firstName ? " " + firstName : "") + "! Vi que voce nos procurou.\n\nAinda precisa de ajuda com imigracao? Posso te ajudar pelo WhatsApp - e mais rapido!\n\nMe passa seu numero?",

      followup_2: (firstName ? firstName + ", " : "") + "ultima tentativa de contato.\n\nSe ainda tiver interesse, me envie seu WhatsApp ou clique aqui para falar conosco:\nhttps://wa.me/" + WPP,

      got_phone: "Perfeito!\n\nVou te chamar no WhatsApp agora. Aguarde!\n\nOu clique aqui para iniciar: https://wa.me/" + WPP,

      no_phone_final: "Sem problemas!\n\nQuando quiser falar conosco, e so clicar:\nhttps://wa.me/" + WPP + "\n\nAtendemos em Portugues, English e Espanol."
    },
    en: {
      greeting: "Hello" + (firstName ? " " + firstName : "") + "! Thank you for contacting ${process.env.ORG_NAME || "CaseHub"}.\n\nFor better assistance, can we continue on WhatsApp? It's faster and more secure.\n\nWhat's your WhatsApp number? (with country code)",

      ask_whatsapp: "To continue your consultation, I need your WhatsApp number.\n\nPlease send your number with country code.\nEx: +1 555 123-4567 or +55 11 99999-9999",

      followup_1: "Hi" + (firstName ? " " + firstName : "") + "! I saw you reached out to us.\n\nDo you still need help with immigration? I can assist you on WhatsApp - it's faster!\n\nCan you share your number?",

      followup_2: (firstName ? firstName + ", " : "") + "last attempt to reach you.\n\nIf you're still interested, send me your WhatsApp or click here to talk to us:\nhttps://wa.me/" + WPP,

      got_phone: "Perfect!\n\nI'll contact you on WhatsApp now. Please wait!\n\nOr click here to start: https://wa.me/" + WPP,

      no_phone_final: "No problem!\n\nWhen you want to talk to us, just click:\nhttps://wa.me/" + WPP + "\n\nWe assist in English, Portugues and Espanol."
    },
    es: {
      greeting: "Hola" + (firstName ? " " + firstName : "") + "! Gracias por contactar al ${process.env.ORG_NAME || "CaseHub"}.\n\nPara mejor asistencia, podemos continuar por WhatsApp? Es mas rapido y seguro.\n\nCual es tu numero de WhatsApp? (con codigo de pais)",

      ask_whatsapp: "Para continuar con tu consulta, necesito tu numero de WhatsApp.\n\nPor favor envia tu numero con codigo de pais.\nEj: +1 555 123-4567 o +55 11 99999-9999",

      followup_1: "Hola" + (firstName ? " " + firstName : "") + "! Vi que nos contactaste.\n\nTodavia necesitas ayuda con inmigracion? Puedo ayudarte por WhatsApp - es mas rapido!\n\nPuedes compartir tu numero?",

      followup_2: (firstName ? firstName + ", " : "") + "ultimo intento de contacto.\n\nSi aun estas interesado, enviame tu WhatsApp o haz clic aqui:\nhttps://wa.me/" + WPP,

      got_phone: "Perfecto!\n\nTe contactare por WhatsApp ahora. Espera!\n\nO haz clic aqui para iniciar: https://wa.me/" + WPP,

      no_phone_final: "Sin problema!\n\nCuando quieras hablar con nosotros, solo haz clic:\nhttps://wa.me/" + WPP + "\n\nAtendemos en Espanol, English y Portugues."
    }
  };

  const langMessages = messages[lang] || messages.en;
  return langMessages[state] || langMessages.greeting;
}

/**
 * Processar mensagem do Messenger
 */
async function processMessengerMessage(senderId, messageText, senderName) {
  const lockKey = "msg_" + senderId;

  // Evitar processamento duplicado
  if (processingMessenger.has(lockKey)) {
    console.log('[MSG-HANDLER] Ignorando duplicado:', senderId);
    return { success: true, duplicate: true };
  }

  processingMessenger.set(lockKey, Date.now());

  try {
    console.log("[MSG-HANDLER] Processando: " + senderId + " - " + (messageText ? messageText.substring(0, 50) : '') + "...");

    // Buscar ou criar lead do Messenger
    let lead = await db.getMessengerLead(senderId);

    if (!lead) {
      // Buscar perfil do Facebook
      const profile = await messenger.getUserProfile(senderId);
      const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(' ') || senderName || 'Usuario';

      // Detectar idioma da mensagem
      const lang = detectLanguage(messageText || '');

      // Criar nova lead
      await db.upsertMessengerLead(senderId, {
        lead_name: fullName,
        language: lang,
        conversation_state: MESSENGER_STATES.NEW,
        message_count: 1,
        followup_count: 0
      });

      lead = await db.getMessengerLead(senderId);
    } else {
      // Atualizar contagem de mensagens
      await db.upsertMessengerLead(senderId, {
        message_count: (lead.message_count || 0) + 1,
        last_activity: new Date()
      });
    }

    // Salvar mensagem recebida
    await db.saveMessengerMessage(senderId, 'user', messageText, lead ? lead.conversation_state : null);

    // Extrair dados da mensagem
    const extractedPhone = extractPhoneNumber(messageText);
    const extractedEmail = extractEmail(messageText);

    // Atualizar dados se encontrados
    if (extractedPhone || extractedEmail) {
      const updates = {};
      if (extractedPhone) updates.lead_phone = extractedPhone;
      if (extractedEmail) updates.lead_email = extractedEmail;
      await db.upsertMessengerLead(senderId, updates);
      lead = Object.assign({}, lead, updates);
    }

    // Determinar resposta baseada no estado e dados
    let response = '';
    let newState = lead ? lead.conversation_state : MESSENGER_STATES.NEW;
    const lang = lead ? lead.language : 'en';

    // Se enviou telefone
    if (extractedPhone) {
      response = getMessageForState('got_phone', lang, lead ? lead.lead_name : null);
      newState = MESSENGER_STATES.CONVERTED;

      // Marcar como convertido
      await db.markConvertedToWhatsApp(senderId, extractedPhone);

      console.log('[MSG-HANDLER] Lead convertida para WhatsApp:', extractedPhone);
    }
    // Se e nova conversa ou estado inicial
    else if (newState === MESSENGER_STATES.NEW || !lead || !lead.conversation_state) {
      response = getMessageForState('greeting', lang, lead ? lead.lead_name : null);
      newState = MESSENGER_STATES.GREETED;
    }
    // Se ja cumprimentou, pedir WhatsApp
    else if (newState === MESSENGER_STATES.GREETED || newState === MESSENGER_STATES.ASKED_INTEREST) {
      response = getMessageForState('ask_whatsapp', lang, lead ? lead.lead_name : null);
      newState = MESSENGER_STATES.ASKED_WHATSAPP;
    }
    // Se ja pediu WhatsApp e nao recebeu
    else if (newState === MESSENGER_STATES.ASKED_WHATSAPP) {
      response = getMessageForState('ask_whatsapp', lang, lead ? lead.lead_name : null);
    }
    // Estados de follow-up
    else if (newState === MESSENGER_STATES.FOLLOWUP_1 || newState === MESSENGER_STATES.FOLLOWUP_2) {
      response = getMessageForState('ask_whatsapp', lang, lead ? lead.lead_name : null);
      newState = MESSENGER_STATES.ASKED_WHATSAPP;
    }

    // Atualizar estado
    if (lead && newState !== lead.conversation_state) {
      await db.upsertMessengerLead(senderId, { conversation_state: newState });
    }

    // Enviar resposta
    if (response) {
      await messenger.markSeen(senderId);
      await messenger.showTyping(senderId, true);

      // Delay para parecer natural
      await new Promise(function(resolve) { setTimeout(resolve, 1500); });

      const sendResult = await messenger.sendMessage(senderId, response);

      if (sendResult.success) {
        await db.saveMessengerMessage(senderId, 'assistant', response, newState);
      }

      await messenger.showTyping(senderId, false);
    }

    return { success: true, state: newState, phone: extractedPhone };

  } catch (error) {
    console.error('[MSG-HANDLER] Erro:', error.message);
    return { success: false, error: error.message };
  } finally {
    // Limpar lock apos delay
    setTimeout(function() { processingMessenger.delete(lockKey); }, PROCESSING_TTL);
  }
}

/**
 * Processar follow-ups pendentes (chamar periodicamente)
 */
async function processFollowups() {
  try {
    // Buscar leads que precisam de follow-up
    const leads = await db.getMessengerLeadsForFollowup(
      MESSENGER_SETTINGS.FOLLOWUP_INTERVAL_HOURS,
      MESSENGER_SETTINGS.MAX_FOLLOWUPS
    );

    console.log("[MSG-HANDLER] Follow-ups pendentes: " + leads.length);

    for (const lead of leads) {
      const followupCount = lead.followup_count || 0;
      const lang = lead.language || 'en';

      let message = '';
      let newState = '';

      if (followupCount === 0) {
        message = getMessageForState('followup_1', lang, lead.lead_name);
        newState = MESSENGER_STATES.FOLLOWUP_1;
      } else if (followupCount === 1) {
        message = getMessageForState('followup_2', lang, lead.lead_name);
        newState = MESSENGER_STATES.FOLLOWUP_2;
      }

      if (message) {
        const sendResult = await messenger.sendMessage(lead.messenger_id, message);

        if (sendResult.success) {
          await db.upsertMessengerLead(lead.messenger_id, {
            followup_count: followupCount + 1,
            conversation_state: newState,
            last_followup_at: new Date()
          });
          await db.saveMessengerMessage(lead.messenger_id, 'assistant', message, newState);
          console.log("[MSG-HANDLER] Follow-up " + (followupCount + 1) + " enviado para: " + lead.messenger_id);
        }
      }

      // Delay entre envios
      await new Promise(function(resolve) { setTimeout(resolve, 2000); });
    }

  } catch (error) {
    console.error('[MSG-HANDLER] Erro no follow-up:', error.message);
  }
}

/**
 * Processar leads inativas para registro no Moskit (chamar periodicamente)
 */
async function processInactiveLeads(createMoskitContact) {
  try {
    // Buscar leads inativas que devem ser registradas
    const leads = await db.getInactiveMessengerLeads(MESSENGER_SETTINGS.INACTIVITY_TIMEOUT_HOURS);

    console.log("[MSG-HANDLER] Leads inativas para registrar: " + leads.length);

    for (const lead of leads) {
      // Verificar criterios de registro
      if (!shouldRegisterInMoskit(lead)) {
        continue;
      }

      // Calcular score
      const score = calculateMessengerScore(lead);

      // Preparar dados para Moskit
      const moskitData = {
        client_name: lead.lead_name || 'Lead Messenger',
        name: lead.lead_name,
        email: lead.lead_email || '',
        phone: lead.lead_phone || '',
        source: 'Messenger',
        source_platform: 'messenger',
        messenger_id: lead.messenger_id,
        lead_score: score,
        lead_status: score >= 35 ? 'warm' : 'cold',
        interest: lead.interest || 'Via Facebook Messenger',
        auto_registered: true
      };

      // Criar no Moskit
      const result = await createMoskitContact(moskitData);

      if (result.success) {
        await db.upsertMessengerLead(lead.messenger_id, {
          registered_in_moskit: true,
          moskit_id: result.id,
          registered_at: new Date()
        });
        console.log("[MSG-HANDLER] Lead registrada no Moskit: " + result.id + " - Score: " + score);
      }

      // Delay entre registros
      await new Promise(function(resolve) { setTimeout(resolve, 1000); });
    }

  } catch (error) {
    console.error('[MSG-HANDLER] Erro ao registrar inativas:', error.message);
  }
}

module.exports = {
  processMessengerMessage: processMessengerMessage,
  processFollowups: processFollowups,
  processInactiveLeads: processInactiveLeads,
  calculateMessengerScore: calculateMessengerScore,
  shouldRegisterInMoskit: shouldRegisterInMoskit,
  MESSENGER_STATES: MESSENGER_STATES,
  MESSENGER_SETTINGS: MESSENGER_SETTINGS
};
