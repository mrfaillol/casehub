/**
 * Moskit CRM Service - Lead management, scoring, and CRM operations
 * Extracted from server.js (Fase 2.2 decomposition)
 *
 * Exports: createMoskitContact, addMoskitActivity, findMoskitContactByPhone,
 *          calculateFormScore, calculateLeadScore, getFieldValue,
 *          generateRecommendation, formatMoskitName, MOSKIT_STAGES
 */

const appConfig = require('../config');

const MOSKIT_CONFIG = {
  apiKey: appConfig.moskit.apiKey,
  baseUrl: appConfig.moskit.baseUrl,
  responsibleId: appConfig.moskit.responsibleId,
  pipelineId: appConfig.moskit.pipelineId
};

const MOSKIT_STAGES = appConfig.moskit.stages;

// Dependency: conversionTracking (injected via init)
let conversionTracking = null;

function init(deps) {
  if (deps.conversionTracking) conversionTracking = deps.conversionTracking;
}

// ===== FORMATAR NOME PARA MOSKIT =====
function formatMoskitName(leadData) {
  let origem = 'WPP';  // Default para WhatsApp
  if (leadData.source === 'Messenger') origem = 'MSG';
  else if (leadData.source === 'Instagram') origem = 'IG';
  else if (leadData.source === 'Site' || leadData.source === 'Elementor' || leadData.source === 'Form') origem = 'SITE';
  else if (leadData.source && leadData.source.includes('Meta')) origem = 'META';

  const score = leadData.lead_score || 0;
  const clientName = leadData.client_name || leadData.whatsapp_name || leadData.name || 'Lead';

  return `[LEAD ${origem} ${score} ${clientName}]`;
}

// ===== CALCULAR SCORE PARA FORMULARIO DO SITE =====
function calculateFormScore(formData) {
  let score = 0;

  // Dados fornecidos (0-30) - Forms geralmente tem mais dados
  if (formData.name || formData.client_name) score += 5;
  if (formData.email && formData.email.includes('@')) score += 10;
  if (formData.phone) score += 10;
  if (formData.message && formData.message.length > 20) score += 5;

  // Tipo de visto / interesse (0-25)
  const highValue = ['E-2', 'EB-5', 'EB-1A', 'EB-1B', 'L-1', 'investor', 'investidor', 'empresa', 'business'];
  const medValue = ['H-1B', 'O-1', 'Green Card', 'Morar', 'Live', 'trabalho', 'work', 'cidadania', 'citizenship'];
  const interest = (formData.interest || formData.visa_interest || formData.message || '').toLowerCase();

  if (highValue.some(v => interest.includes(v.toLowerCase()))) {
    score += 25;
  } else if (medValue.some(v => interest.includes(v.toLowerCase()))) {
    score += 15;
  } else if (interest) {
    score += 5;
  }

  // Origem da pagina (0-15)
  const page = (formData.page || formData.form_name || '').toLowerCase();
  if (page.includes('e-2') || page.includes('eb-5') || page.includes('investor')) {
    score += 15;
  } else if (page.includes('green-card') || page.includes('work-visa')) {
    score += 10;
  } else if (page.includes('contact') || page.includes('consultation')) {
    score += 5;
  }

  // Idioma (0-10)
  const lang = formData.language || 'en';
  if (lang === 'en') score += 5;
  else if (lang === 'pt') score += 3;

  // Bonus se preencheu todos os campos (0-10)
  const fieldsCount = [formData.name, formData.email, formData.phone, formData.message].filter(Boolean).length;
  score += fieldsCount * 2;

  // Determinar status baseado no score
  let leadStatus = 'cold';
  if (score >= 70) leadStatus = 'hot';
  else if (score >= 50) leadStatus = 'qualified';
  else if (score >= 30) leadStatus = 'warm';

  return { score: Math.min(score, 100), status: leadStatus };
}

// ===== CALCULAR SCORE DA LEAD (WHATSAPP) =====
function calculateLeadScore(lead) {
  let score = 0;

  // Engajamento (0-20): 2 pontos por mensagem (max 20)
  const messageCount = lead.message_count || 0;
  score += Math.min(20, messageCount * 2);

  // Dados fornecidos (0-25)
  if (lead.client_name) score += 5;
  if (lead.email && lead.email !== 'pular' && lead.email !== 'nao') score += 5;
  if (lead.phone) score += 10;  // WhatsApp vale mais
  if (lead.profession) score += 5;

  // Tipo de visto (0-25)
  const highValue = ['E-2', 'EB-5', 'EB-1A', 'EB-1B', 'L-1'];
  const medValue = ['H-1B', 'O-1', 'Green Card', 'Morar', 'Live'];
  const interest = lead.visa_interest || '';

  if (highValue.some(v => interest.toUpperCase().includes(v.toUpperCase()))) {
    score += 25;
  } else if (medValue.some(v => interest.toUpperCase().includes(v.toUpperCase()))) {
    score += 15;
  } else if (interest) {
    score += 5;
  }

  // Urgencia (0-15)
  if (lead.is_urgent) score += 15;

  // Consulta (0-15)
  if (lead.payment_status === 'paid') score += 15;
  else if (lead.consultation_type === 'paid') score += 10;
  else if (lead.consultation_type === 'free') score += 5;

  // Determinar status baseado no score
  let leadStatus = 'cold';
  if (score >= 90) leadStatus = 'hot';
  else if (score >= 70) leadStatus = 'qualified';
  else if (score >= 50) leadStatus = 'warm';

  return { score, status: leadStatus };
}

// ===== HELPER: EXTRAIR VALOR DE CAMPO ELEMENTOR =====
function getFieldValue(field) {
  if (!field) return "";
  if (typeof field === "string") return field;
  if (typeof field === "object" && field.value !== undefined) return field.value;
  if (typeof field === "object" && field.raw_value !== undefined) return field.raw_value;
  return "";
}

// ===== GENERATE RECOMMENDATION FROM QUICK INTAKE =====
function generateRecommendation(scoring, lang) {
  var msg = '';
  var score = scoring.normalizedScore || 0;
  var pathways = scoring.pathways || [];

  if (lang === 'pt') {
    msg = 'Obrigado por responder! Analisei suas informacoes.\n\n';

    if (pathways.length > 0) {
      msg += '*Possiveis caminhos identificados:*\n';
      var namesPt = {
        'FAMILY_BASED': 'Imigracao baseada em familia',
        'HUMANITARIAN_ASYLUM': 'Asilo/Refugio',
        'HUMANITARIAN_VAWA': 'Protecao VAWA',
        'HUMANITARIAN_U_VISA': 'Visto U (vitima de crime)',
        'HUMANITARIAN_T_VISA': 'Visto T (trafico)',
        'EMPLOYMENT_BASED': 'Visto baseado em emprego',
        'REMOVAL_DEFENSE': 'Defesa contra deportacao'
      };
      for (var i = 0; i < pathways.length; i++) {
        msg += '- ' + (namesPt[pathways[i]] || pathways[i]) + '\n';
      }
      msg += '\n';
    }

    if (score >= 70) {
      msg += 'Seu caso parece ter boas possibilidades! Recomendamos fortemente uma *consulta com advogado* para analise completa:\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n';
      msg += 'Na consulta ($99), o advogado vai analisar seu caso especificamente e orientar os proximos passos.';
    } else if (score >= 50) {
      msg += 'Identificamos possibilidades no seu caso. Sugerimos uma *reuniao gratuita* para conversarmos mais:\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall\n\n';
      msg += 'Se preferir ir direto para analise completa com advogado ($99):\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting';
    } else {
      msg += 'Cada caso e unico e merece atencao. Agende uma *reuniao gratuita* para entendermos melhor:\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall';
    }
  } else {
    msg = "Thank you for your answers! I've analyzed your information.\n\n";

    if (pathways.length > 0) {
      msg += '*Possible pathways identified:*\n';
      var namesEn = {
        'FAMILY_BASED': 'Family-based immigration',
        'HUMANITARIAN_ASYLUM': 'Asylum/Refugee protection',
        'HUMANITARIAN_VAWA': 'VAWA protection',
        'HUMANITARIAN_U_VISA': 'U-Visa (crime victim)',
        'HUMANITARIAN_T_VISA': 'T-Visa (trafficking)',
        'EMPLOYMENT_BASED': 'Employment-based visa',
        'REMOVAL_DEFENSE': 'Removal defense'
      };
      for (var j = 0; j < pathways.length; j++) {
        msg += '- ' + (namesEn[pathways[j]] || pathways[j]) + '\n';
      }
      msg += '\n';
    }

    if (score >= 70) {
      msg += 'Your case appears to have strong possibilities! We strongly recommend a *consultation with our attorney* for a complete analysis:\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting\n\n';
      msg += 'In the consultation ($99), the attorney will analyze your specific case and guide you on next steps.';
    } else if (score >= 50) {
      msg += "We've identified possibilities in your case. We suggest a *free meeting* to discuss further:\n";
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall\n\n';
      msg += 'If you prefer to go directly to a full analysis with our attorney ($99):\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting';
    } else {
      msg += 'Every case is unique and deserves attention. Schedule a *free meeting* so we can better understand your situation:\n';
      msg += '${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall';
    }
  }

  return msg;
}

// ===== INTERNAL: STAGE BY SCORE =====
function getStageByScore(score) {
  if (score >= 80) return MOSKIT_STAGES.INTAKE_CALL;      // Hot - pronto para intake
  if (score >= 50) return MOSKIT_STAGES.LEAD_QUALIFICATION; // Morno - qualificando
  return MOSKIT_STAGES.NEW_LEAD;                           // Frio - novo lead
}

// ===== CRIAR LEAD NO MOSKIT =====
async function createMoskitContact(leadData) {
  try {
    const isFromForm = leadData.source === 'Site' || leadData.source === 'Elementor' || leadData.source === 'Form';

    const notes = [
      isFromForm ? "Lead via Formulario do Site" : "Lead via WhatsApp Bot",
      "Origem: " + (leadData.source || "Meta Ads"),
      "Interesse: " + (leadData.visa_interest || leadData.interest || leadData.message || "Nao informado"),
      "Score: " + (leadData.lead_score || 0),
      "Status: " + (leadData.lead_status || "new")
    ];

    if (leadData.phone) {
      notes.push("Telefone: " + leadData.phone);
    }

    if (leadData.page || leadData.form_name) {
      notes.push("Pagina: " + (leadData.page || leadData.form_name));
    }

    if (leadData.consultation_type === "paid" && leadData.payment_status === "paid") {
      notes.push("Consulta: PAGA (US$99)");
    } else if (leadData.consultation_type === "free") {
      notes.push("Consulta: Gratuita");
    }

    if (leadData.consultation_scheduled) {
      notes.push("Agendamento: Confirmado");
    } else if (leadData.auto_registered) {
      notes.push("Registro: Auto (sem resposta)");
    } else if (isFromForm) {
      notes.push("Registro: Formulario Site");
    } else {
      notes.push("Registro: Fluxo completo");
    }

    if (leadData.urgent || leadData.is_urgent) notes.unshift("URGENTE!");

    const formattedName = formatMoskitName(leadData);

    const body = {
      name: formattedName,
      notes: notes.join("\n"),
      createdBy: { id: MOSKIT_CONFIG.responsibleId },
      responsible: { id: MOSKIT_CONFIG.responsibleId }
    };

    // Formatar telefone
    if (leadData.phone) {
      let phone = leadData.phone.toString().replace(/\D/g, '');
      if (!phone.startsWith('+')) {
        phone = '+' + phone;
      }
      body.phones = [{ number: phone }];
    }

    if (leadData.email && leadData.email !== "pular" && leadData.email !== "nao" && leadData.email.includes('@')) {
      body.emails = [{ address: leadData.email }];
    }

    const response = await fetch(MOSKIT_CONFIG.baseUrl + "/contacts", {
      method: "POST",
      headers: {
        "apikey": MOSKIT_CONFIG.apiKey,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

    const result = await response.json();

    if (response.ok) {
      console.log("[MOSKIT] Lead criado:", result.id, "-", formattedName);

      // Criar negócio automaticamente
      try {
        const dealResult = await createMoskitDeal(result.id, leadData);
        if (dealResult.success) {
          console.log("[MOSKIT] Negócio criado:", dealResult.id, "para contato:", result.id);
        }
      } catch (dealError) {
        console.log("[MOSKIT] Erro ao criar negócio (contato OK):", dealError.message);
      }

      // Rastrear conversao se lead qualificada
      if (conversionTracking && leadData.lead_score >= 50) {
        conversionTracking.trackQualifiedLead(leadData).catch(e => console.log("[CONVERSION] Erro:", e.message));
      }
      return { success: true, id: result.id };
    } else {
      console.error("[MOSKIT] Erro:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("[MOSKIT] Erro:", error.message);
    return { success: false, error: error.message };
  }
}

// ===== CRIAR NEGÓCIO NO MOSKIT =====
async function createMoskitDeal(contactId, leadData) {
  try {
    const score = leadData.lead_score || leadData.intake_form_final_score || 0;
    const stageId = getStageByScore(score);
    const pathway = leadData.intake_form_primary_pathway || leadData.visa_interest || 'Immigration';
    const clientName = leadData.client_name || leadData.whatsapp_name || 'Lead WhatsApp';

    const dealName = `[LEAD WPP ${score}] ${clientName} - ${pathway}`;

    const body = {
      name: dealName,
      responsible: { id: MOSKIT_CONFIG.responsibleId },
      createdBy: { id: MOSKIT_CONFIG.responsibleId },
      stage: { id: stageId },
      status: "OPEN",
      contacts: [{ id: contactId }],
      source: "API",
      origin: "WhatsApp Bot",
      notes: `Lead via WhatsApp Bot\nScore: ${score}\nInteresse: ${pathway}\nWhatsApp: +${leadData.phone || 'N/A'}\nData: ${new Date().toLocaleString('pt-BR')}`
    };

    if (score >= 70) {
      body.price = 500000; // $5.000 em centavos
    }

    const response = await fetch(MOSKIT_CONFIG.baseUrl + "/deals", {
      method: "POST",
      headers: {
        "apikey": MOSKIT_CONFIG.apiKey,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

    const result = await response.json();

    if (response.ok) {
      console.log("[MOSKIT] Negócio criado:", result.id, "-", dealName, "| Stage:", stageId);
      return { success: true, id: result.id, stageId };
    } else {
      console.error("[MOSKIT] Erro ao criar negócio:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("[MOSKIT] Erro ao criar negócio:", error.message);
    return { success: false, error: error.message };
  }
}

// ===== BUSCAR CONTATO NO MOSKIT POR TELEFONE =====
async function findMoskitContactByPhone(phone) {
  try {
    const cleanPhone = phone.replace(/\D/g, '');

    const response = await fetch(MOSKIT_CONFIG.baseUrl + "/contacts?phones=" + cleanPhone, {
      method: "GET",
      headers: {
        "apikey": MOSKIT_CONFIG.apiKey,
        "Content-Type": "application/json"
      }
    });

    const result = await response.json();

    if (response.ok && result.length > 0) {
      console.log("[MOSKIT] Contato encontrado:", result[0].id);
      return { success: true, contact: result[0] };
    } else {
      console.log("[MOSKIT] Contato nao encontrado para:", cleanPhone);
      return { success: false, contact: null };
    }
  } catch (error) {
    console.error("[MOSKIT] Erro buscar contato:", error.message);
    return { success: false, error: error.message };
  }
}

// ===== ADICIONAR ATIVIDADE NO MOSKIT (HISTORICO) =====
async function addMoskitActivity(phone, messageText, messageType = 'received') {
  try {
    const contactResult = await findMoskitContactByPhone(phone);

    if (!contactResult.success || !contactResult.contact) {
      console.log("[MOSKIT-ACTIVITY] Contato nao encontrado, atividade nao criada");
      return { success: false, error: "Contato nao encontrado" };
    }

    const contactId = contactResult.contact.id;
    const direction = messageType === 'received' ? 'Recebida' : 'Enviada';
    const truncatedMsg = messageText.substring(0, 500);

    const now = new Date();
    const dueDate = now.toISOString().replace('Z', '-05:00');

    const body = {
      title: `WhatsApp - Msg ${direction}`,
      description: truncatedMsg,
      type: { id: 148475 }, // Tipo: E-mail (validado na API)
      contact: { id: contactId },
      responsible: { id: MOSKIT_CONFIG.responsibleId },
      createdBy: { id: MOSKIT_CONFIG.responsibleId },
      dueDate: dueDate,
      status: "DONE"
    };

    const response = await fetch(MOSKIT_CONFIG.baseUrl + "/activities", {
      method: "POST",
      headers: {
        "apikey": MOSKIT_CONFIG.apiKey,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

    const result = await response.json();

    if (response.ok) {
      console.log("[MOSKIT-ACTIVITY] Atividade criada:", result.id);
      return { success: true, id: result.id };
    } else {
      console.log("[MOSKIT-ACTIVITY] Erro ao criar:", JSON.stringify(result).substring(0, 200));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("[MOSKIT-ACTIVITY] Erro:", error.message);
    return { success: false, error: error.message };
  }
}

module.exports = {
  init,
  createMoskitContact,
  addMoskitActivity,
  findMoskitContactByPhone,
  calculateFormScore,
  calculateLeadScore,
  getFieldValue,
  generateRecommendation,
  formatMoskitName,
  MOSKIT_CONFIG,
  MOSKIT_STAGES
};
