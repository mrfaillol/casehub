/**
 * Calendly Integration Module
 * CaseHub - WhatsApp Bot
 * v1.0
 */

const appConfig = require("./config");

// Calendly configuration. Event type URIs must be supplied by the tenant.
const CALENDLY_CONFIG = {
  apiKey: appConfig.calendly.apiKey,
  baseUrl: "https://api.calendly.com",
  userUri: process.env.CALENDLY_USER_URI || "",
  freeEventTypeUri: process.env.CALENDLY_FREE_EVENT_TYPE_URI || "",
  freeEventUrl: `${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall`,
  paidEventTypeUri: process.env.CALENDLY_PAID_EVENT_TYPE_URI || "",
  paidEventUrl: `${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting`
};

// Configuracao NOVA (center-immigrant) - Reuniao Gratuita (15min)
const CALENDLY_CENTER = {
  apiKey: process.env.CALENDLY_CENTER_API_KEY || appConfig.calendly.apiKey,
  email: (process.env.CENTER_EMAIL || "center@casehub.app"),
  freeEventUrl: `${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall`
};

// URLs para o novo fluxo Human Handoff (CORRETOS)
const HANDOFF_URLS = {
  freeConsultation: `${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall`,
  paidConsultation: `${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting`
};

/**
 * Buscar horarios disponiveis para um tipo de evento
 * @param {string} eventTypeUri - URI do tipo de evento
 * @param {number} daysAhead - Quantos dias a frente buscar (default: 7)
 * @returns {Array} Lista de horarios disponiveis
 */
async function getAvailableTimes(eventTypeUri, daysAhead = 7) {
  if (!CALENDLY_CONFIG.apiKey || !eventTypeUri) {
    return [];
  }

  try {
    const startTime = new Date();
    const endTime = new Date();
    endTime.setDate(endTime.getDate() + daysAhead);

    const url = new URL(`${CALENDLY_CONFIG.baseUrl}/event_type_available_times`);
    url.searchParams.append("event_type", eventTypeUri);
    url.searchParams.append("start_time", startTime.toISOString());
    url.searchParams.append("end_time", endTime.toISOString());

    const response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${CALENDLY_CONFIG.apiKey}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      const error = await response.json();
      console.error("[CALENDLY] Erro ao buscar horarios:", JSON.stringify(error));
      return [];
    }

    const data = await response.json();
    return data.collection || [];

  } catch (error) {
    console.error("[CALENDLY] Erro:", error.message);
    return [];
  }
}

/**
 * Buscar horarios para consulta gratuita
 */
async function getFreeConsultationTimes(daysAhead = 7) {
  return getAvailableTimes(CALENDLY_CONFIG.freeEventTypeUri, daysAhead);
}

/**
 * Buscar horarios para consulta paga
 */
async function getPaidConsultationTimes(daysAhead = 7) {
  return getAvailableTimes(CALENDLY_CONFIG.paidEventTypeUri, daysAhead);
}

/**
 * Formatar horarios para exibicao no WhatsApp
 * @param {Array} times - Lista de horarios do Calendly
 * @param {number} maxSlots - Maximo de slots para mostrar (default: 6)
 * @returns {Object} { message: string, slots: Array }
 */
function formatTimesForWhatsApp(times, maxSlots = 6) {
  if (!times || times.length === 0) {
    return {
      message: `Desculpe, nao encontrei horarios disponiveis nos proximos dias. Por favor, entre em contato pelo email: ${process.env.ORG_EMAIL || "info@casehub.app"}`,
      slots: []
    };
  }

  // Pegar apenas os primeiros slots
  const slots = times.slice(0, maxSlots);

  // Formatar para exibicao
  const formattedSlots = slots.map((slot, index) => {
    const date = new Date(slot.start_time);

    // Formatar dia da semana em portugues
    const weekdays = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"];
    const weekday = weekdays[date.getDay()];

    // Formatar data
    const day = date.getDate().toString().padStart(2, "0");
    const month = (date.getMonth() + 1).toString().padStart(2, "0");

    // Formatar hora (converter para timezone America/Sao_Paulo)
    const options = {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Sao_Paulo"
    };
    const time = date.toLocaleTimeString("pt-BR", options);

    return {
      number: index + 1,
      display: `${weekday} ${day}/${month} - ${time}`,
      start_time: slot.start_time,
      scheduling_url: slot.scheduling_url
    };
  });

  // Montar mensagem
  let message = "Horarios disponiveis:\n\n";
  formattedSlots.forEach(slot => {
    message += `${slot.number}️⃣ ${slot.display}\n`;
  });
  message += "\nDigite o numero do horario desejado:";

  return {
    message,
    slots: formattedSlots
  };
}

/**
 * Gerar link de agendamento com pre-preenchimento
 * @param {string} baseUrl - URL base do evento
 * @param {Object} leadData - Dados do lead (name, email, phone)
 * @returns {string} URL com parametros
 */
function generateSchedulingLink(baseUrl, leadData = {}) {
  const url = new URL(baseUrl);

  if (leadData.name || leadData.client_name) {
    url.searchParams.append("name", leadData.name || leadData.client_name);
  }
  if (leadData.email) {
    url.searchParams.append("email", leadData.email);
  }
  // Nota: Calendly nao suporta pre-preenchimento de telefone na URL padrao

  return url.toString();
}

/**
 * Gerar link para consulta gratuita
 */
function getFreeConsultationLink(leadData = {}) {
  return generateSchedulingLink(CALENDLY_CONFIG.freeEventUrl, leadData);
}

/**
 * Gerar link para consulta paga
 */
function getPaidConsultationLink(leadData = {}) {
  return generateSchedulingLink(CALENDLY_CONFIG.paidEventUrl, leadData);
}

/**
 * Criar agendamento via API (requer scope scheduled_events:write)
 * NOTA: Calendly API v2 nao permite criar agendamentos diretamente
 * O metodo recomendado e usar o scheduling_url
 */
async function createScheduledEvent(eventTypeUri, invitee, startTime) {
  // Calendly API v2 nao suporta criacao direta de eventos
  // Retornar o link de agendamento ao inves
  console.log("[CALENDLY] Criacao direta nao suportada, use scheduling_url");
  return {
    success: false,
    message: "Use o link de agendamento",
    url: CALENDLY_CONFIG.freeEventUrl
  };
}

/**
 * Verificar status de um agendamento
 */
async function getScheduledEvent(eventUri) {
  try {
    const response = await fetch(eventUri, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${CALENDLY_CONFIG.apiKey}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data.resource;

  } catch (error) {
    console.error("[CALENDLY] Erro ao buscar evento:", error.message);
    return null;
  }
}

/**
 * Listar eventos agendados de um usuario
 */
async function listScheduledEvents(status = "active", count = 10) {
  try {
    const url = new URL(`${CALENDLY_CONFIG.baseUrl}/scheduled_events`);
    url.searchParams.append("user", CALENDLY_CONFIG.userUri);
    url.searchParams.append("status", status);
    url.searchParams.append("count", count);

    const response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${CALENDLY_CONFIG.apiKey}`,
        "Content-Type": "application/json"
      }
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return data.collection || [];

  } catch (error) {
    console.error("[CALENDLY] Erro ao listar eventos:", error.message);
    return [];
  }
}

module.exports = {
  CALENDLY_CONFIG,
  CALENDLY_CENTER,
  HANDOFF_URLS,
  getAvailableTimes,
  getFreeConsultationTimes,
  getPaidConsultationTimes,
  formatTimesForWhatsApp,
  generateSchedulingLink,
  getFreeConsultationLink,
  getPaidConsultationLink,
  createScheduledEvent,
  getScheduledEvent,
  listScheduledEvents
};
