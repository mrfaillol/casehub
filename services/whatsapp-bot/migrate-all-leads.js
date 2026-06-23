/**
 * Migração Completa - Criar Contatos e Negócios para TODAS as Leads
 * CaseHub - WhatsApp Bot
 * v2.0 - Usando moskit_id do banco como referência
 *
 * Este script:
 * 1. Busca TODAS as leads do banco MySQL que NÃO têm moskit_id
 * 2. Cria contatos no Moskit com formato [LEAD WPP XX]
 * 3. Cria negócios vinculados a cada contato
 *
 * USO: node migrate-all-leads.js
 */

const mysql = require('mysql2/promise');

const dbPassword = process.env.DB_PASSWORD;
if (!dbPassword) throw new Error("DB_PASSWORD environment variable is required");
const dbUser = process.env.DB_USER;
if (!dbUser) throw new Error("DB_USER environment variable is required");
const dbName = process.env.DB_NAME;
if (!dbName) throw new Error("DB_NAME environment variable is required");

const DB_CONFIG = {
  host: process.env.DB_HOST || 'localhost',
  user: dbUser,
  password: dbPassword,
  database: dbName
};

const moskitApiKey = process.env.MOSKIT_API_KEY;
if (!moskitApiKey) throw new Error("MOSKIT_API_KEY environment variable is required");

const MOSKIT_CONFIG = {
  apiKey: moskitApiKey,
  baseUrl: "https://api.moskitcrm.com/v2",
  responsibleId: parseInt(process.env.MOSKIT_RESPONSIBLE_ID || '105810'),
  pipelineId: parseInt(process.env.MOSKIT_PIPELINE_ID || '70006')
};

const MOSKIT_STAGES = {
  NEW_LEAD: 322283,
  LEAD_QUALIFICATION: 322808,
  INTAKE_CALL: 322282,
  CONSULTATION: 322284,
  CLOSING: 322809,
  VISA_IN_PROGRESS: 371211
};

// Determinar etapa baseado no score
function getStageByScore(score) {
  if (score >= 80) return MOSKIT_STAGES.INTAKE_CALL;
  if (score >= 50) return MOSKIT_STAGES.LEAD_QUALIFICATION;
  return MOSKIT_STAGES.NEW_LEAD;
}

// Extrair código do pathway do interesse
function getPathwayCode(visaInterest) {
  if (!visaInterest) return 'UNK';
  const interest = visaInterest.toLowerCase();

  if (interest.includes('green card') || interest.includes('família') || interest.includes('reunir')) return 'FAM';
  if (interest.includes('trabalho') || interest.includes('work') || interest.includes('emprego')) return 'EMP';
  if (interest.includes('asilo') || interest.includes('asylum')) return 'ASY';
  if (interest.includes('investor') || interest.includes('eb-5')) return 'INV';

  return 'UNK';
}

// Criar contato no Moskit
async function createMoskitContact(lead) {
  const score = lead.lead_score || 0;
  const pathwayCode = getPathwayCode(lead.visa_interest);
  const clientName = lead.client_name || lead.whatsapp_name || 'Lead WhatsApp';

  // Formato: [LEAD WPP 75 FAM] PessoaDemo Silva
  const formattedName = `[LEAD WPP ${score} ${pathwayCode}] ${clientName}`;

  const notes = [
    "Lead via WhatsApp Bot",
    `Score: ${score}`,
    `Interesse: ${lead.visa_interest || 'Não informado'}`,
    `WhatsApp: +${lead.phone}`,
    `Status: ${lead.lead_status || 'cold'}`,
    `Data: ${new Date().toLocaleString('pt-BR')}`
  ];

  if (lead.is_urgent) notes.unshift("⚠️ URGENTE!");

  const body = {
    name: formattedName,
    notes: notes.join("\n"),
    createdBy: { id: MOSKIT_CONFIG.responsibleId },
    responsible: { id: MOSKIT_CONFIG.responsibleId }
  };

  if (lead.phone) {
    let phone = lead.phone.toString().replace(/\D/g, '');
    if (!phone.startsWith('+')) phone = '+' + phone;
    body.phones = [{ number: phone }];
  }

  if (lead.email && lead.email.includes('@') && !['pular', 'nao', 'skip'].includes(lead.email.toLowerCase())) {
    body.emails = [{ address: lead.email }];
  }

  try {
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
      return { success: true, id: result.id, name: formattedName };
    } else {
      return { success: false, error: result };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Criar negócio no Moskit
async function createMoskitDeal(contactId, lead) {
  const score = lead.lead_score || 0;
  const stageId = getStageByScore(score);
  const pathwayCode = getPathwayCode(lead.visa_interest);
  const clientName = lead.client_name || lead.whatsapp_name || 'Lead WhatsApp';

  const dealName = `[DEAL WPP ${score} ${pathwayCode}] ${clientName}`;

  const body = {
    name: dealName,
    responsible: { id: MOSKIT_CONFIG.responsibleId },
    createdBy: { id: MOSKIT_CONFIG.responsibleId },
    stage: { id: stageId },
    status: "OPEN",
    contacts: [{ id: contactId }],
    source: "API",
    origin: "WhatsApp Bot",
    notes: `Lead via WhatsApp Bot\nScore: ${score}\nInteresse: ${lead.visa_interest || 'N/A'}\nWhatsApp: +${lead.phone}\nData: ${new Date().toLocaleString('pt-BR')}`
  };

  // Valor estimado para leads qualificados
  if (score >= 70) {
    body.price = 500000;
  } else if (score >= 50) {
    body.price = 300000;
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
      return { success: true, id: result.id, name: dealName, stageId };
    } else {
      return { success: false, error: result };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Função principal
async function migrate() {
  console.log("═══════════════════════════════════════════════════════════════════");
  console.log("   MIGRAÇÃO COMPLETA - TODAS AS LEADS PARA MOSKIT CRM");
  console.log("═══════════════════════════════════════════════════════════════════");

  // Conectar ao MySQL
  let connection;
  try {
    connection = await mysql.createConnection(DB_CONFIG);
    console.log("\n✅ Conectado ao MySQL\n");
  } catch (error) {
    console.error("❌ Erro ao conectar ao MySQL:", error.message);
    return;
  }

  // Buscar leads que NÃO têm moskit_id (não foram migradas ainda)
  console.log("🔍 Buscando leads SEM moskit_id...\n");

  const [leadsToMigrate] = await connection.execute(`
    SELECT
      phone,
      client_name,
      whatsapp_name,
      email,
      visa_interest,
      lead_score,
      lead_status,
      is_urgent,
      moskit_id,
      moskit_sent,
      created_at
    FROM leads
    WHERE moskit_id IS NULL
    ORDER BY lead_score DESC, created_at DESC
  `);

  // Também contar total e já migradas
  const [totalCount] = await connection.execute('SELECT COUNT(*) as total FROM leads');
  const [migratedCount] = await connection.execute('SELECT COUNT(*) as total FROM leads WHERE moskit_id IS NOT NULL');

  console.log(`📊 Status atual:`);
  console.log(`   Total de leads: ${totalCount[0].total}`);
  console.log(`   Já migradas: ${migratedCount[0].total}`);
  console.log(`   Para migrar: ${leadsToMigrate.length}\n`);

  if (leadsToMigrate.length === 0) {
    console.log("✅ Todas as leads já foram migradas!");
    await connection.end();
    return;
  }

  // Estatísticas
  let contactsCreated = 0;
  let dealsCreated = 0;
  let errors = 0;

  console.log("🔄 Criando contatos e negócios...\n");
  console.log("───────────────────────────────────────────────────────────────────");

  for (let i = 0; i < leadsToMigrate.length; i++) {
    const lead = leadsToMigrate[i];
    const progress = `[${String(i + 1).padStart(3)}/${leadsToMigrate.length}]`;
    const displayName = (lead.client_name || lead.whatsapp_name || lead.phone).substring(0, 30);
    const score = lead.lead_score || 0;

    try {
      // 1. Criar contato no Moskit
      const contactResult = await createMoskitContact(lead);

      if (!contactResult.success) {
        console.log(`${progress} ❌ ${displayName} - Erro contato: ${JSON.stringify(contactResult.error)}`);
        errors++;
        continue;
      }

      contactsCreated++;

      // 2. Criar negócio vinculado ao contato
      const dealResult = await createMoskitDeal(contactResult.id, lead);

      if (!dealResult.success) {
        console.log(`${progress} ⚠️ ${displayName} - Contato OK (#${contactResult.id}), negócio falhou`);

        // Ainda assim atualizar o banco com o contato
        await connection.execute(
          'UPDATE leads SET moskit_sent = 1, moskit_id = ? WHERE phone = ?',
          [contactResult.id, lead.phone]
        );
        errors++;
        continue;
      }

      dealsCreated++;

      // 3. Atualizar banco de dados
      await connection.execute(
        'UPDATE leads SET moskit_sent = 1, moskit_id = ? WHERE phone = ?',
        [contactResult.id, lead.phone]
      );

      // Emoji baseado no score/stage
      const stageEmoji = dealResult.stageId === MOSKIT_STAGES.INTAKE_CALL ? '🔥' :
                        dealResult.stageId === MOSKIT_STAGES.LEAD_QUALIFICATION ? '🟡' : '🔵';

      console.log(`${progress} ✅ ${displayName} | Score: ${score} ${stageEmoji} | Contato: #${contactResult.id} | Deal: #${dealResult.id}`);

      // Pausa para não sobrecarregar API
      await new Promise(resolve => setTimeout(resolve, 400));

    } catch (error) {
      console.log(`${progress} ❌ ${displayName} - Erro: ${error.message}`);
      errors++;
    }
  }

  // Fechar conexão MySQL
  await connection.end();

  // Resumo final
  console.log("\n───────────────────────────────────────────────────────────────────");
  console.log("═══════════════════════════════════════════════════════════════════");
  console.log("                         RESUMO DA MIGRAÇÃO");
  console.log("═══════════════════════════════════════════════════════════════════");
  console.log(`   📋 Leads processadas:      ${leadsToMigrate.length}`);
  console.log(`   ✅ Contatos criados:       ${contactsCreated}`);
  console.log(`   📊 Negócios criados:       ${dealsCreated}`);
  console.log(`   ❌ Erros:                  ${errors}`);
  console.log("═══════════════════════════════════════════════════════════════════\n");

  console.log("Legenda:");
  console.log("   🔥 = Intake Call (Score 80+) - Lead quente!");
  console.log("   🟡 = Lead Qualification (Score 50-79) - Lead morno");
  console.log("   🔵 = New Lead (Score 0-49) - Lead frio\n");
}

// Executar
migrate().catch(console.error);
