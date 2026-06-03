/**
 * Script de Migração COMPLETO - Criar Negócios para Contatos
 * CaseHub - WhatsApp Bot
 * v2.0
 *
 * Este script:
 * 1. Busca todos os contatos no Moskit
 * 2. Verifica quais são leads do WhatsApp (pelo telefone ou notas)
 * 3. Cria negócios para quem não tem
 *
 * USO: node migrate-deals.js
 */

const MOSKIT_CONFIG = {
  apiKey: process.env.MOSKIT_API_KEY || '',
  baseUrl: "https://api.moskitcrm.com/v2",
  responsibleId: 105810,
  pipelineId: 70006
};

const MOSKIT_STAGES = {
  NEW_LEAD: 322283,
  LEAD_QUALIFICATION: 322808,
  INTAKE_CALL: 322282,
  CONSULTATION: 322284,
  CLOSING: 322809,
  VISA_IN_PROGRESS: 371211
};

// Extrair score do nome do contato [LEAD WPP XX ...]
function extractScoreFromName(name) {
  const match = name.match(/\[LEAD\s+(?:WPP\s+)?(\d+)/i);
  return match ? parseInt(match[1]) : 0;
}

// Determinar etapa baseado no score
function getStageByScore(score) {
  if (score >= 80) return MOSKIT_STAGES.INTAKE_CALL;
  if (score >= 50) return MOSKIT_STAGES.LEAD_QUALIFICATION;
  return MOSKIT_STAGES.NEW_LEAD;
}

// Verificar se é uma lead do WhatsApp
function isWhatsAppLead(contact) {
  // Se já tem formato [LEAD...]
  if (contact.name && contact.name.toUpperCase().includes('[LEAD')) {
    return true;
  }

  // Se tem notas mencionando WhatsApp
  if (contact.notes && (
    contact.notes.toLowerCase().includes('whatsapp') ||
    contact.notes.toLowerCase().includes('wpp') ||
    contact.notes.toLowerCase().includes('lead via')
  )) {
    return true;
  }

  // Se tem telefone brasileiro ou internacional (não é parceria)
  if (contact.phones && contact.phones.length > 0) {
    const phone = contact.phones[0].number || '';
    // Telefone brasileiro começa com +55
    if (phone.startsWith('+55') || phone.startsWith('55')) {
      return true;
    }
  }

  return false;
}

// Buscar todos os contatos do Moskit
async function getAllContacts() {
  let allContacts = [];
  let page = 1;
  let hasMore = true;

  console.log("\n🔍 Buscando contatos no Moskit...\n");

  while (hasMore) {
    try {
      const response = await fetch(
        `${MOSKIT_CONFIG.baseUrl}/contacts?page=${page}&perPage=100`,
        {
          method: "GET",
          headers: {
            "apikey": MOSKIT_CONFIG.apiKey,
            "Content-Type": "application/json"
          }
        }
      );

      const contacts = await response.json();

      if (contacts && contacts.length > 0) {
        allContacts = allContacts.concat(contacts);
        console.log(`   Página ${page}: ${contacts.length} contatos encontrados`);
        page++;
      } else {
        hasMore = false;
      }

      if (page > 50) {
        console.log("⚠️ Limite de páginas atingido (50)");
        hasMore = false;
      }
    } catch (error) {
      console.error("❌ Erro ao buscar contatos:", error.message);
      hasMore = false;
    }
  }

  console.log(`\n✅ Total de contatos encontrados: ${allContacts.length}\n`);
  return allContacts;
}

// Buscar todos os negócios existentes
async function getAllDeals() {
  let allDeals = [];
  let page = 1;
  let hasMore = true;

  console.log("🔍 Buscando negócios existentes...\n");

  while (hasMore) {
    try {
      const response = await fetch(
        `${MOSKIT_CONFIG.baseUrl}/deals?page=${page}&perPage=100`,
        {
          method: "GET",
          headers: {
            "apikey": MOSKIT_CONFIG.apiKey,
            "Content-Type": "application/json"
          }
        }
      );

      const deals = await response.json();

      if (deals && deals.length > 0) {
        allDeals = allDeals.concat(deals);
        page++;
      } else {
        hasMore = false;
      }

      if (page > 50) hasMore = false;
    } catch (error) {
      console.error("❌ Erro ao buscar negócios:", error.message);
      hasMore = false;
    }
  }

  console.log(`✅ Total de negócios existentes: ${allDeals.length}\n`);
  return allDeals;
}

// Verificar se contato já tem negócio
function contactHasDeal(contactId, allDeals) {
  return allDeals.some(deal =>
    deal.contacts && deal.contacts.some(c => c.id === contactId)
  );
}

// Criar negócio para contato
async function createDealForContact(contact, score = 0) {
  const stageId = getStageByScore(score);
  const cleanName = contact.name || 'Lead';

  const dealName = `[DEAL WPP ${score}] ${cleanName}`;

  const body = {
    name: dealName,
    responsible: { id: MOSKIT_CONFIG.responsibleId },
    createdBy: { id: MOSKIT_CONFIG.responsibleId },  // OBRIGATÓRIO
    stage: { id: stageId },
    status: "OPEN",  // OBRIGATÓRIO: OPEN, WON, LOST
    contacts: [{ id: contact.id }],
    source: "API",
    origin: "WhatsApp Bot - Migration",
    notes: `Negócio migrado automaticamente\nContato: ${contact.name}\nScore: ${score}\nData: ${new Date().toLocaleString('pt-BR')}`
  };

  // Valor estimado para leads qualificados
  if (score >= 70) {
    body.price = 500000;
  }

  try {
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
      return { success: true, id: result.id, dealName };
    } else {
      return { success: false, error: result };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Função principal
async function migrate() {
  console.log("═══════════════════════════════════════════════════════════");
  console.log("   MIGRAÇÃO COMPLETA - CONTATOS PARA NEGÓCIOS - MOSKIT CRM");
  console.log("═══════════════════════════════════════════════════════════");

  // Buscar todos os contatos e negócios
  const contacts = await getAllContacts();
  const existingDeals = await getAllDeals();

  // Criar mapa de contatos que já têm negócios
  const contactsWithDeals = new Set();
  existingDeals.forEach(deal => {
    if (deal.contacts) {
      deal.contacts.forEach(c => contactsWithDeals.add(c.id));
    }
  });

  console.log(`📊 Contatos que já têm negócios: ${contactsWithDeals.size}\n`);

  // Filtrar contatos que são leads do WhatsApp e não têm negócio
  const contactsToProcess = contacts.filter(c => {
    // Pular se já tem negócio
    if (contactsWithDeals.has(c.id)) return false;

    // Verificar se é lead do WhatsApp
    return isWhatsAppLead(c);
  });

  console.log(`📋 Contatos para processar (leads sem negócio): ${contactsToProcess.length}\n`);

  if (contactsToProcess.length === 0) {
    console.log("✅ Todos os leads já têm negócios!");
    return;
  }

  // Estatísticas
  let created = 0;
  let errors = 0;

  console.log("🔄 Criando negócios...\n");

  for (let i = 0; i < contactsToProcess.length; i++) {
    const contact = contactsToProcess[i];
    const progress = `[${i + 1}/${contactsToProcess.length}]`;

    // Extrair score do nome se disponível
    const score = extractScoreFromName(contact.name);

    // Criar negócio
    const result = await createDealForContact(contact, score);

    if (result.success) {
      console.log(`${progress} ✅ ${result.dealName} - Deal #${result.id}`);
      created++;
    } else {
      console.log(`${progress} ❌ ${contact.name} - Erro: ${JSON.stringify(result.error)}`);
      errors++;
    }

    // Pequena pausa para não sobrecarregar API
    await new Promise(resolve => setTimeout(resolve, 300));
  }

  // Resumo final
  console.log("\n═══════════════════════════════════════════════════════════");
  console.log("                    RESUMO DA MIGRAÇÃO");
  console.log("═══════════════════════════════════════════════════════════");
  console.log(`   ✅ Negócios criados:  ${created}`);
  console.log(`   ❌ Erros:             ${errors}`);
  console.log(`   📊 Total processado:  ${contactsToProcess.length}`);
  console.log("═══════════════════════════════════════════════════════════\n");
}

// Executar
migrate().catch(console.error);
