/**
 * Moskit CRM Integration
 * CaseHub
 * v2.0 - Com suporte a Intake Form Scoring
 */

const appConfig = require("./config");
const MOSKIT_CONFIG = {
  apiKey: appConfig.moskit.apiKey,
  baseUrl: appConfig.moskit.baseUrl,
  responsibleId: appConfig.moskit.responsibleId,
  pipelineId: appConfig.moskit.pipelineId
};

// IDs das etapas do funil de vendas
const MOSKIT_STAGES = appConfig.moskit.stages;

// Codigos de pathway para o nome
const PATHWAY_CODES = {
  'family_based': 'FAM',
  'employment_based': 'EMP',
  'humanitarian_asylum': 'ASY',
  'humanitarian_vawa': 'VAW',
  'humanitarian_u_visa': 'UVI',
  'humanitarian_t_visa': 'TVI',
  'humanitarian_sijs': 'SIJ',
  'investor': 'INV',
  'unknown': 'NEW'
};

/**
 * Formatar nome do lead com score e pathway
 * Formato: [LEAD WPP 75 FAM] Maria Silva
 */
function formatLeadName(name, score, pathway) {
  const pathwayCode = PATHWAY_CODES[pathway] || 'NEW';
  const cleanName = name || 'Lead WhatsApp';
  return `[LEAD WPP ${score || 0} ${pathwayCode}] ${cleanName}`;
}

/**
 * Criar contato no Moskit
 */
async function createMoskitContact(leadData) {
  try {
    const notes = [
      "Lead via WhatsApp Bot",
      "Interesse: " + (leadData.visa_interest || leadData.interest || "Nao informado"),
      "WhatsApp: +" + (leadData.phone || "N/A")
    ];
    if (leadData.urgent || leadData.is_urgent) {
      notes.unshift("URGENTE!");
    }
    // UTM Attribution
    const utm_source = leadData.utm_source || leadData.utmSource || '';
    if (utm_source) notes.push("Source: " + utm_source);

    const body = {
      name: leadData.client_name || leadData.name || "Lead WhatsApp",
      notes: notes.join("\n"),
      createdBy: { id: MOSKIT_CONFIG.responsibleId },
      responsible: { id: MOSKIT_CONFIG.responsibleId }
    };

    if (leadData.phone) {
      body.phones = [{ number: "+" + leadData.phone.replace(/\D/g, "") }];
    }
    if (leadData.email && leadData.email !== "pular" && leadData.email !== "nao") {
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
      console.log("✅ [MOSKIT] Lead criado:", result.id, "-", body.name);
      return { success: true, id: result.id };
    } else {
      console.error("❌ [MOSKIT] Erro:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("❌ [MOSKIT] Erro:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Buscar contato existente por telefone
 */
async function findMoskitContactByPhone(phone) {
  try {
    const cleanPhone = phone.replace(/\D/g, '');

    // Buscar por telefone
    const response = await fetch(
      `${MOSKIT_CONFIG.baseUrl}/contacts?search=${cleanPhone}`,
      {
        method: "GET",
        headers: {
          "apikey": MOSKIT_CONFIG.apiKey,
          "Content-Type": "application/json"
        }
      }
    );

    const result = await response.json();

    if (response.ok && result.length > 0) {
      // Retornar o primeiro resultado que corresponde
      return { success: true, contact: result[0] };
    }

    return { success: false, contact: null };
  } catch (error) {
    console.error("❌ [MOSKIT] Erro ao buscar:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Atualizar contato existente no Moskit
 */
async function updateMoskitContact(contactId, updateData) {
  try {
    // Adicionar campos obrigatorios do Moskit
    const dataWithRequired = {
      ...updateData,
      createdBy: { id: MOSKIT_CONFIG.responsibleId },
      responsible: { id: MOSKIT_CONFIG.responsibleId }
    };

    const response = await fetch(
      `${MOSKIT_CONFIG.baseUrl}/contacts/${contactId}`,
      {
        method: "PUT",
        headers: {
          "apikey": MOSKIT_CONFIG.apiKey,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(dataWithRequired)
      }
    );

    const result = await response.json();

    if (response.ok) {
      console.log("✅ [MOSKIT] Contato atualizado:", contactId);
      return { success: true, contact: result };
    } else {
      console.error("❌ [MOSKIT] Erro ao atualizar:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("❌ [MOSKIT] Erro:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Atualizar contato com resultados do Intake Form
 * Atualiza nome com score/pathway e adiciona notas com resumo
 */
async function updateMoskitWithIntakeResults(leadData, scoringReport) {
  try {
    const phone = leadData.phone;
    const score = scoringReport?.score || leadData.intake_form_final_score || 0;
    const pathway = scoringReport?.pathway || leadData.intake_form_primary_pathway || 'unknown';
    const clientName = leadData.client_name || leadData.whatsapp_name || 'Lead';

    // Buscar contato existente
    const findResult = await findMoskitContactByPhone(phone);

    if (!findResult.success || !findResult.contact) {
      console.log('[MOSKIT] Contato nao encontrado, criando novo...');

      // Criar novo contato com o formato correto
      const newContact = await createMoskitContact({
        ...leadData,
        client_name: formatLeadName(clientName, score, pathway)
      });

      if (newContact.success && scoringReport?.summary) {
        // Atualizar notas com o resumo
        await updateMoskitContact(newContact.id, {
          notes: scoringReport.summary
        });
      }

      return newContact;
    }

    // Atualizar contato existente
    const contactId = findResult.contact.id;
    const newName = formatLeadName(clientName, score, pathway);

    // Preparar notas atualizadas
    let notes = findResult.contact.notes || '';

    // Adicionar separador se ja tem notas
    if (notes) {
      notes += '\n\n--- INTAKE FORM RESULTS ---\n';
    }

    // Adicionar resumo do scoring
    if (scoringReport?.summary) {
      notes += scoringReport.summary;
    } else {
      notes += `Score: ${score}/100\nPathway: ${pathway}\nStatus: ${score >= 70 ? 'QUALIFICADO' : 'NAO QUALIFICADO'}`;
    }

    const updateResult = await updateMoskitContact(contactId, {
      name: newName,
      notes: notes
    });

    if (updateResult.success) {
      console.log(`✅ [MOSKIT] Lead atualizado com intake: ${newName}`);
    }

    return updateResult;
  } catch (error) {
    console.error("❌ [MOSKIT] Erro ao atualizar intake:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Criar ou atualizar contato com dados do Intake Form
 * Usa upsert: busca por telefone, atualiza se existe, cria se nao existe
 */
async function upsertMoskitContactWithIntake(leadData, scoringReport) {
  try {
    const phone = leadData.phone;
    const score = scoringReport?.score || leadData.intake_form_final_score || 0;
    const pathway = scoringReport?.pathway || leadData.intake_form_primary_pathway || 'unknown';
    const clientName = leadData.client_name || leadData.whatsapp_name || 'Lead';

    // Formatar nome com score e pathway
    const formattedName = formatLeadName(clientName, score, pathway);

    // Preparar notas
    let notes = `=== INTAKE FORM RESULTS ===\n`;
    notes += `Data: ${new Date().toLocaleString('pt-BR')}\n`;
    notes += `WhatsApp: +${phone}\n\n`;

    if (scoringReport?.summary) {
      notes += scoringReport.summary;
    } else {
      notes += `Score: ${score}/100\n`;
      notes += `Pathway: ${pathway}\n`;
      notes += `Status: ${score >= 70 ? 'QUALIFICADO PARA CONSULTA' : 'NAO QUALIFICADO'}\n`;
    }

    // Buscar contato existente
    const findResult = await findMoskitContactByPhone(phone);

    if (findResult.success && findResult.contact) {
      // Atualizar contato existente
      const contactId = findResult.contact.id;
      const existingNotes = findResult.contact.notes || '';

      // Concatenar notas antigas com novas
      const fullNotes = existingNotes
        ? existingNotes + '\n\n' + notes
        : notes;

      return await updateMoskitContact(contactId, {
        name: formattedName,
        notes: fullNotes
      });
    }

    // Criar novo contato
    const body = {
      name: formattedName,
      notes: notes,
      createdBy: { id: MOSKIT_CONFIG.responsibleId },
      responsible: { id: MOSKIT_CONFIG.responsibleId }
    };

    if (phone) {
      body.phones = [{ number: "+" + phone.replace(/\D/g, "") }];
    }
    if (leadData.email && leadData.email !== "pular" && leadData.email !== "nao") {
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
      console.log("✅ [MOSKIT] Lead criado com intake:", result.id, "-", formattedName);
      return { success: true, id: result.id };
    } else {
      console.error("❌ [MOSKIT] Erro:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("❌ [MOSKIT] Erro:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Determinar etapa do funil baseado no score do lead
 * @param {number} score - Score do lead (0-100)
 * @returns {number} ID da etapa no Moskit
 */
function getStageByScore(score) {
  if (score >= 80) return MOSKIT_STAGES.INTAKE_CALL;      // Hot - pronto para intake
  if (score >= 50) return MOSKIT_STAGES.LEAD_QUALIFICATION; // Morno - qualificando
  return MOSKIT_STAGES.NEW_LEAD;                           // Frio - novo lead
}

/**
 * Build structured notes for Moskit deal including UTM attribution data.
 */
function buildDealNotes(leadData, score, pathway) {
  const lines = [
    `Lead via WhatsApp Bot`,
    `Score: ${score}`,
    `Interesse: ${pathway}`,
    `WhatsApp: +${leadData.phone || 'N/A'}`,
    `Data: ${new Date().toLocaleString('pt-BR')}`
  ];

  // UTM Attribution data
  const utm_source = leadData.utm_source || leadData.utmSource || '';
  const utm_medium = leadData.utm_medium || leadData.utmMedium || '';
  const utm_campaign = leadData.utm_campaign || leadData.utmCampaign || '';
  const gclid = leadData.gclid || '';
  const fbclid = leadData.fbclid || '';

  if (utm_source || utm_medium || utm_campaign || gclid || fbclid) {
    lines.push('');
    lines.push('--- Attribution ---');
    if (utm_source) lines.push(`utm_source: ${utm_source}`);
    if (utm_medium) lines.push(`utm_medium: ${utm_medium}`);
    if (utm_campaign) lines.push(`utm_campaign: ${utm_campaign}`);
    if (gclid) lines.push(`gclid: ${gclid}`);
    if (fbclid) lines.push(`fbclid: ${fbclid}`);
  }

  return lines.join('\n');
}

/**
 * Criar negócio no Moskit
 * @param {number} contactId - ID do contato no Moskit
 * @param {Object} leadData - Dados do lead
 * @returns {Object} { success: boolean, id?: number, error?: any }
 */
async function createMoskitDeal(contactId, leadData) {
  try {
    const score = leadData.lead_score || leadData.intake_form_final_score || 0;
    const stageId = getStageByScore(score);
    const pathway = leadData.intake_form_primary_pathway || leadData.visa_interest || 'Immigration';
    const clientName = leadData.client_name || leadData.whatsapp_name || 'Lead WhatsApp';

    // Formatar nome do negócio
    const dealName = `[LEAD WPP ${score}] ${clientName} - ${pathway}`;

    const body = {
      name: dealName,
      responsible: { id: MOSKIT_CONFIG.responsibleId },
      stage: { id: stageId },
      contacts: [{ id: contactId }],
      source: "API",
      origin: "WhatsApp Bot",
      notes: buildDealNotes(leadData, score, pathway)
    };

    // Se tiver score alto, adicionar valor estimado
    if (score >= 70) {
      body.price = 500000; // $5.000 em centavos (valor médio de caso)
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
      console.log("✅ [MOSKIT] Negócio criado:", result.id, "-", dealName, "| Stage:", stageId);
      return { success: true, id: result.id, stageId };
    } else {
      console.error("❌ [MOSKIT] Erro ao criar negócio:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("❌ [MOSKIT] Erro ao criar negócio:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Criar contato E negócio no Moskit (função completa)
 * @param {Object} leadData - Dados do lead
 * @returns {Object} { success: boolean, contactId?: number, dealId?: number, error?: any }
 */
async function createMoskitContactAndDeal(leadData) {
  try {
    // Primeiro criar o contato
    const contactResult = await createMoskitContact(leadData);

    if (!contactResult.success) {
      return { success: false, error: contactResult.error };
    }

    // Depois criar o negócio vinculado ao contato
    const dealResult = await createMoskitDeal(contactResult.id, leadData);

    if (!dealResult.success) {
      // Contato foi criado mas negócio falhou
      console.log("⚠️ [MOSKIT] Contato criado mas negócio falhou:", contactResult.id);
      return {
        success: true,
        contactId: contactResult.id,
        dealId: null,
        dealError: dealResult.error
      };
    }

    console.log("✅ [MOSKIT] Contato + Negócio criados:", contactResult.id, "/", dealResult.id);
    return {
      success: true,
      contactId: contactResult.id,
      dealId: dealResult.id,
      stageId: dealResult.stageId
    };
  } catch (error) {
    console.error("❌ [MOSKIT] Erro ao criar contato+negócio:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Buscar negócio de um contato
 * @param {number} contactId - ID do contato no Moskit
 * @returns {Object} { success: boolean, deal?: Object }
 */
async function findDealByContact(contactId) {
  try {
    const response = await fetch(
      `${MOSKIT_CONFIG.baseUrl}/deals?contact=${contactId}`,
      {
        method: "GET",
        headers: {
          "apikey": MOSKIT_CONFIG.apiKey,
          "Content-Type": "application/json"
        }
      }
    );

    const result = await response.json();

    if (response.ok && result.length > 0) {
      return { success: true, deal: result[0] };
    }

    return { success: false, deal: null };
  } catch (error) {
    console.error("❌ [MOSKIT] Erro ao buscar negócio:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Atualizar etapa do negócio
 * @param {number} dealId - ID do negócio
 * @param {number} stageId - ID da nova etapa
 * @returns {Object} { success: boolean }
 */
async function updateDealStage(dealId, stageId) {
  try {
    const response = await fetch(
      `${MOSKIT_CONFIG.baseUrl}/deals/${dealId}`,
      {
        method: "PUT",
        headers: {
          "apikey": MOSKIT_CONFIG.apiKey,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          stage: { id: stageId },
          responsible: { id: MOSKIT_CONFIG.responsibleId }
        })
      }
    );

    const result = await response.json();

    if (response.ok) {
      console.log("✅ [MOSKIT] Negócio movido para etapa:", stageId);
      return { success: true, deal: result };
    } else {
      console.error("❌ [MOSKIT] Erro ao atualizar etapa:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("❌ [MOSKIT] Erro ao atualizar etapa:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Criar negócio para contato existente (para migração)
 * @param {number} contactId - ID do contato
 * @param {string} contactName - Nome do contato
 * @param {number} score - Score do lead (opcional)
 * @returns {Object} { success: boolean, dealId?: number }
 */
async function createDealForExistingContact(contactId, contactName, score = 0) {
  try {
    const stageId = getStageByScore(score);
    const dealName = `[LEAD WPP ${score}] ${contactName}`;

    const body = {
      name: dealName,
      responsible: { id: MOSKIT_CONFIG.responsibleId },
      stage: { id: stageId },
      contacts: [{ id: contactId }],
      source: "API",
      origin: "WhatsApp Bot - Migration",
      notes: `Negócio criado automaticamente\nScore: ${score}\nData: ${new Date().toLocaleString('pt-BR')}`
    };

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
      console.log("✅ [MOSKIT] Negócio migrado:", result.id, "-", dealName);
      return { success: true, id: result.id };
    } else {
      console.error("❌ [MOSKIT] Erro na migração:", JSON.stringify(result));
      return { success: false, error: result };
    }
  } catch (error) {
    console.error("❌ [MOSKIT] Erro na migração:", error.message);
    return { success: false, error: error.message };
  }
}

module.exports = {
  MOSKIT_CONFIG,
  MOSKIT_STAGES,
  PATHWAY_CODES,
  formatLeadName,
  getStageByScore,
  createMoskitContact,
  createMoskitDeal,
  createMoskitContactAndDeal,
  findMoskitContactByPhone,
  findDealByContact,
  updateMoskitContact,
  updateDealStage,
  updateMoskitWithIntakeResults,
  upsertMoskitContactWithIntake,
  createDealForExistingContact
};
