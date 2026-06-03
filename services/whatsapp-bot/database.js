/**
 * Database Module - WhatsApp Bot
 * CaseHub
 * Versao 9.0 - Com suporte a Intake Form de 46 perguntas e novo sistema de scoring
 */
const mysql = require("mysql2/promise");
const pgSync = require("./pg-sync");

let pool;
let initPromise = null;

// v11.0: Garantir que pool está inicializado antes de qualquer operação
async function ensurePool() {
  if (pool) return pool;
  if (initPromise) return initPromise;
  initPromise = init();
  await initPromise;
  return pool;
}

// Inicializar pool de conexoes
async function init() {
  const dbUser = process.env.DB_USER;
  if (!dbUser) throw new Error("DB_USER environment variable is required");
  const dbPassword = process.env.DB_PASSWORD;
  if (!dbPassword) throw new Error("DB_PASSWORD environment variable is required");
  const dbName = process.env.DB_NAME;
  if (!dbName) throw new Error("DB_NAME environment variable is required");

  pool = mysql.createPool({
    host: process.env.DB_HOST || "localhost",
    user: dbUser,
    password: dbPassword,
    database: dbName,
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0
  });

  // Criar tabelas se nao existirem
  const createConversations = `
    CREATE TABLE IF NOT EXISTS conversations (
      id INT AUTO_INCREMENT PRIMARY KEY,
      phone VARCHAR(30) NOT NULL,
      role ENUM("user", "assistant") NOT NULL,
      content TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_phone (phone),
      INDEX idx_created (created_at)
    )
  `;

  // ===== v9.0: TABELA DE RESPOSTAS DO INTAKE FORM =====
  const createIntakeFormResponses = `
    CREATE TABLE IF NOT EXISTS intake_form_responses (
      id INT AUTO_INCREMENT PRIMARY KEY,
      phone VARCHAR(30) NOT NULL,
      question_id INT NOT NULL,
      question_text TEXT,
      response_text TEXT,
      response_type ENUM('text', 'boolean', 'choice', 'date', 'skip') DEFAULT 'text',
      question_category VARCHAR(50),
      points_earned INT DEFAULT 0,
      gemini_analysis TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_phone (phone),
      INDEX idx_question_id (question_id),
      INDEX idx_category (question_category)
    )
  `;

  // ===== v9.0: TABELA DE SCORES POR PATHWAY =====
  const createPathwayScores = `
    CREATE TABLE IF NOT EXISTS pathway_scores (
      id INT AUTO_INCREMENT PRIMARY KEY,
      phone VARCHAR(30) NOT NULL,
      pathway ENUM('family_based', 'employment_based', 'humanitarian_asylum',
                   'humanitarian_vawa', 'humanitarian_u_visa', 'humanitarian_t_visa',
                   'humanitarian_sijs', 'investor', 'unknown') NOT NULL,
      score INT DEFAULT 0,
      confidence DECIMAL(3,2) DEFAULT 0.00,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY idx_phone_pathway (phone, pathway)
    )
  `;

  // ===== v9.0: TABELA DE PERGUNTAS DO INTAKE FORM =====
  const createIntakeQuestions = `
    CREATE TABLE IF NOT EXISTS intake_questions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      question_id INT UNIQUE NOT NULL,
      question_pt TEXT NOT NULL,
      question_en TEXT NOT NULL,
      question_es TEXT NOT NULL,
      response_type ENUM('text', 'boolean', 'choice', 'date', 'file') DEFAULT 'text',
      category VARCHAR(50) NOT NULL,
      max_points INT DEFAULT 0,
      pathway_impact VARCHAR(50),
      skip_if_question_id INT,
      skip_if_answer VARCHAR(50),
      options_pt TEXT,
      options_en TEXT,
      options_es TEXT,
      is_active BOOLEAN DEFAULT true,
      display_order INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `;

  const createLeads = `
    CREATE TABLE IF NOT EXISTS leads (
      id INT AUTO_INCREMENT PRIMARY KEY,
      phone VARCHAR(30) UNIQUE NOT NULL,
      name VARCHAR(255),
      email VARCHAR(255),
      visa_type VARCHAR(100),
      visa_interest VARCHAR(100),
      conversation_state VARCHAR(50),
      current_status VARCHAR(100),
      profession VARCHAR(255),
      timeline VARCHAR(100),
      lead_score INT DEFAULT 0,
      lead_status ENUM("cold", "warm", "qualified", "hot") DEFAULT "cold",
      urgency ENUM("normal", "alta", "critica") DEFAULT "normal",
      status ENUM("new", "qualified", "contacted", "scheduled", "converted", "lost") DEFAULT "new",
      transfer_to_human BOOLEAN DEFAULT false,
      escalated BOOLEAN DEFAULT false,
      consultation_scheduled BOOLEAN DEFAULT false,
      notes TEXT,
      source VARCHAR(100) DEFAULT "Meta Ads",
      whatsapp_name VARCHAR(255),
      moskit_sent BOOLEAN DEFAULT false,
      moskit_id INT,
      auto_registered BOOLEAN DEFAULT false,
      is_urgent BOOLEAN DEFAULT false,
      message_count INT DEFAULT 0,
      language VARCHAR(10) DEFAULT "en",
      consultation_type VARCHAR(20),
      payment_status VARCHAR(20),
      followup_count INT DEFAULT 0,
      last_followup_at DATETIME,
      awaiting_consultation_followup INT DEFAULT 0,
      last_consultation_followup_at DATETIME,
      first_contact TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_status (status),
      INDEX idx_lead_status (lead_status),
      INDEX idx_lead_score (lead_score),
      INDEX idx_moskit_sent (moskit_sent),
      INDEX idx_conversation_state (conversation_state)
    )
  `;

  try {
    await pool.query(createConversations);
    await pool.query(createLeads);
    // v9.0: Criar tabelas de intake form
    await pool.query(createIntakeFormResponses);
    await pool.query(createPathwayScores);
    await pool.query(createIntakeQuestions);

    // Adicionar novas colunas se nao existirem (para migracao)
    await addColumnIfNotExists("leads", "lead_score", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "lead_status", 'ENUM("cold", "warm", "qualified", "hot") DEFAULT "cold"');
    await addColumnIfNotExists("leads", "current_status", "VARCHAR(100)");
    await addColumnIfNotExists("leads", "profession", "VARCHAR(255)");
    await addColumnIfNotExists("leads", "timeline", "VARCHAR(100)");
    await addColumnIfNotExists("leads", "urgency", 'ENUM("normal", "alta", "critica") DEFAULT "normal"');
    await addColumnIfNotExists("leads", "escalated", "BOOLEAN DEFAULT false");
    await addColumnIfNotExists("leads", "consultation_scheduled", "BOOLEAN DEFAULT false");
    await addColumnIfNotExists("leads", "notes", "TEXT");
    await addColumnIfNotExists("leads", "source", 'VARCHAR(100) DEFAULT "Meta Ads"');
    await addColumnIfNotExists("leads", "message_count", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "visa_interest", "VARCHAR(100)");
    await addColumnIfNotExists("leads", "conversation_state", "VARCHAR(50)");
    await addColumnIfNotExists("leads", "is_urgent", "BOOLEAN DEFAULT false");
    // Colunas v3.0
    await addColumnIfNotExists("leads", "whatsapp_name", "VARCHAR(255)");
    await addColumnIfNotExists("leads", "moskit_sent", "BOOLEAN DEFAULT false");
    await addColumnIfNotExists("leads", "moskit_id", "INT");
    await addColumnIfNotExists("leads", "auto_registered", "BOOLEAN DEFAULT false");
    // Colunas v7.9 - Follow-ups
    await addColumnIfNotExists("leads", "language", 'VARCHAR(10) DEFAULT "en"');
    await addColumnIfNotExists("leads", "consultation_type", "VARCHAR(20)");
    await addColumnIfNotExists("leads", "payment_status", "VARCHAR(20)");
    await addColumnIfNotExists("leads", "followup_count", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "last_followup_at", "DATETIME");
    // Colunas v8.2 - Consultation Follow-ups
    await addColumnIfNotExists("leads", "awaiting_consultation_followup", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "last_consultation_followup_at", "DATETIME");
    await addColumnIfNotExists("leads", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP");
    await addColumnIfNotExists("leads", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP");
    // Colunas v9.0 - Intake Form System
    await addColumnIfNotExists("leads", "intake_form_state", 'ENUM("not_started", "invited", "in_progress", "completed", "expired", "skipped") DEFAULT "not_started"');
    await addColumnIfNotExists("leads", "intake_form_current_question", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "intake_form_started_at", "DATETIME");
    await addColumnIfNotExists("leads", "intake_form_completed_at", "DATETIME");
    await addColumnIfNotExists("leads", "intake_form_final_score", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "intake_form_primary_pathway", "VARCHAR(50)");
    await addColumnIfNotExists("leads", "intake_form_gemini_summary", "TEXT");
    await addColumnIfNotExists("leads", "eligible_for_free_call", "BOOLEAN DEFAULT false");
    await addColumnIfNotExists("leads", "intake_form_invite_sent_at", "DATETIME");
    await addColumnIfNotExists("leads", "intake_form_followup_count", "INT DEFAULT 0");
    await addColumnIfNotExists("leads", "intake_form_last_followup_at", "DATETIME");
    // v10.5 - Lead Monitor columns
    await addColumnIfNotExists("leads", "needs_human_review", "BOOLEAN DEFAULT false");
    await addColumnIfNotExists("leads", "human_review_reason", "VARCHAR(255)");

    console.log("[DB] Tabelas criadas/verificadas v10.5");
  } catch (error) {
    console.error("[DB] Erro ao criar tabelas:", error.message);
    throw error;
  }
}

// Adicionar coluna se nao existir
async function addColumnIfNotExists(table, column, definition) {
  try {
    const [rows] = await pool.query(
      `SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
       WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?`,
      [process.env.DB_NAME || "immigrant_whatsapp", table, column]
    );

    if (rows.length === 0) {
      await pool.query(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
      console.log(`  [DB] Coluna ${column} adicionada`);
    }
  } catch (error) {
    if (!error.message.includes("Duplicate column")) {
      console.error(`  [DB] Erro coluna ${column}:`, error.message);
    }
  }
}

// Testar conexao com o banco
async function testConnection() {
  try {
    if (!pool) {
      await init();
    }
    const [rows] = await pool.query("SELECT 1");
    return true;
  } catch (error) {
    console.error("[DB] Falha na conexao:", error.message);
    return false;
  }
}

// Salvar mensagem na conversa
async function saveMessage(phone, role, content, timestamp = null) {
  try {
    await ensurePool();
    // v13.0: Accept optional timestamp (WhatsApp msg.timestamp in seconds)
    // and set from_bot correctly based on role
    const ts = timestamp ? new Date(timestamp * 1000) : new Date();
    const fromBot = role === "assistant" ? 1 : 0;
    const [result] = await pool.query(
      "INSERT INTO conversations (phone, role, content, created_at, from_bot) VALUES (?, ?, ?, ?, ?)",
      [phone, role, content, ts, fromBot]
    );

    // Sync to PostgreSQL unified_messages
    if (result && result.insertId) {
      pgSync.syncMessage(result.insertId, phone, role, content);
    }

    // Atualizar ou criar lead e incrementar contador de mensagens
    await pool.query(
      `INSERT INTO leads (phone, message_count) VALUES (?, 1)
       ON DUPLICATE KEY UPDATE
         last_interaction = CURRENT_TIMESTAMP,
         message_count = message_count + 1`,
      [phone]
    );
  } catch (error) {
    console.error("[DB] Erro ao salvar mensagem:", error.message);
  }
}

// Obter historico de conversa
async function getConversationHistory(phone, limit = 20) {
  try {
    const [rows] = await pool.query(
      "SELECT role, content FROM conversations WHERE phone = ? ORDER BY created_at DESC LIMIT ?",
      [phone, limit]
    );
    return rows.reverse();
  } catch (error) {
    console.error("[DB] Erro ao buscar historico:", error.message);
    return [];
  }
}

// Obter lead por telefone
async function getLead(phone) {
  try {
    await ensurePool();
    const [rows] = await pool.query(
      "SELECT * FROM leads WHERE phone = ?",
      [phone]
    );
    return rows[0] || null;
  } catch (error) {
    console.error("[DB] Erro ao buscar lead:", error.message);
    return null;
  }
}

// Obter lead por email
async function getLeadByEmail(email) {
  try {
    const [rows] = await pool.query(
      "SELECT * FROM leads WHERE email = ?",
      [email]
    );
    return rows[0] || null;
  } catch (error) {
    console.error("[DB] Erro ao buscar lead por email:", error.message);
    return null;
  }
}

// Atualizar dados do lead
async function updateLead(phone, data) {
  try {
    const fields = [];
    const values = [];

    const allowedFields = [
      "name", "client_name", "email", "visa_type", "visa_interest", "conversation_state",
      "is_urgent", "current_status", "profession", "timeline", "lead_score", "lead_status",
      "urgency", "status", "transfer_to_human", "escalated", "consultation_scheduled",
      "notes", "source", "whatsapp_name", "moskit_sent", "moskit_id", "auto_registered",
      "language", "consultation_type", "payment_status", "followup_count", "last_followup_at",
      "awaiting_consultation_followup", "last_consultation_followup_at",
      // v9.0 - Intake Form fields
      "intake_form_state", "intake_form_current_question", "intake_form_started_at",
      "intake_form_completed_at", "intake_form_final_score", "intake_form_primary_pathway",
      "intake_form_gemini_summary", "eligible_for_free_call", "intake_form_invite_sent_at",
      "intake_form_followup_count", "intake_form_last_followup_at",
      // v10.5 - Lead Monitor fields
      "needs_human_review", "human_review_reason"
    ];

    for (const field of allowedFields) {
      if (data[field] !== undefined) {
        fields.push(`${field} = ?`);
        values.push(data[field]);
      }
    }

    if (fields.length > 0) {
      values.push(phone);
      await pool.query(
        `INSERT INTO leads (phone) VALUES (?) ON DUPLICATE KEY UPDATE ${fields.join(", ")}`,
        [phone, ...values.slice(0, -1)]
      );
    }
  } catch (error) {
    console.error("[DB] Erro ao atualizar lead:", error.message);
  }
}

// Atualizar status de pagamento
async function updatePaymentStatus(phone, status) {
  try {
    await pool.query(
      `UPDATE leads SET payment_status = ? WHERE phone = ?`,
      [status, phone]
    );
  } catch (error) {
    console.error("[DB] Erro ao atualizar status de pagamento:", error.message);
  }
}

// Salvar sessao de pagamento
async function savePaymentSession(phone, sessionId, amount, currency) {
  try {
    await pool.query(
      `UPDATE leads SET payment_status = 'pending' WHERE phone = ?`,
      [phone]
    );
    // Poderia salvar em tabela separada se necessario
  } catch (error) {
    console.error("[DB] Erro ao salvar sessao de pagamento:", error.message);
  }
}

// Salvar evento do Calendly
async function saveCalendlyEvent(phone, url, startTime) {
  try {
    await pool.query(
      `UPDATE leads SET consultation_scheduled = 1 WHERE phone = ?`,
      [phone]
    );
  } catch (error) {
    console.error("[DB] Erro ao salvar evento Calendly:", error.message);
  }
}

// Obter leads agendados
async function getScheduledLeads() {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM leads WHERE consultation_scheduled = 1 ORDER BY last_interaction DESC`
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads agendados:", error.message);
    return [];
  }
}

// Obter leads incompletas (para auto-registro)
async function getIncompleteLeads(cutoffTime) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM leads
       WHERE (conversation_state IS NULL OR conversation_state NOT IN ('transferred', 'asked_scheduling'))
       AND (moskit_sent IS NULL OR moskit_sent = 0)
       AND first_contact < ?
       AND (followup_count IS NULL OR followup_count < 2)
       ORDER BY first_contact ASC`,
      [cutoffTime]
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads incompletas:", error.message);
    return [];
  }
}

// ===== NOVA FUNCAO v8.2 =====
// Obter leads aguardando consulta (para follow-ups de consulta)
async function getLeadsAwaitingConsultation() {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM leads
       WHERE conversation_state = 'transferred'
       AND (consultation_scheduled IS NULL OR consultation_scheduled = 0)
       AND (awaiting_consultation_followup IS NULL OR awaiting_consultation_followup < 3)
       ORDER BY updated_at ASC`
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads aguardando consulta:", error.message);
    return [];
  }
}

// Calcular e atualizar score do lead
async function updateLeadScore(phone) {
  try {
    const lead = await getLead(phone);
    if (!lead) return 0;

    let score = 0;

    // Pontuacao por engajamento (0-15)
    const messageScore = Math.min(lead.message_count * 2, 15);
    score += messageScore;

    // Pontuacao por informacoes fornecidas (0-20)
    if (lead.name) score += 5;
    if (lead.email) score += 5;
    if (lead.profession) score += 5;
    if (lead.visa_type) score += 5;

    // Pontuacao por tipo de visto (indica capacidade financeira) (0-25)
    const highValueVisas = ["E-2", "EB-5", "EB-1A", "EB-1C", "L-1A"];
    const mediumValueVisas = ["EB-2 NIW", "H-1B", "O-1", "Green Card"];

    if (lead.visa_type) {
      if (highValueVisas.some(v => lead.visa_type.includes(v))) {
        score += 25;
      } else if (mediumValueVisas.some(v => lead.visa_type.includes(v))) {
        score += 15;
      } else {
        score += 5;
      }
    }

    // Pontuacao por urgencia (0-20)
    if (lead.urgency === "critica") score += 20;
    else if (lead.urgency === "alta") score += 10;

    // Pontuacao por interesse em consulta (0-20)
    if (lead.consultation_scheduled) score += 20;
    else if (lead.status === "contacted") score += 10;

    // Determinar status do lead
    let leadStatus = "cold";
    if (score >= 90) leadStatus = "hot";
    else if (score >= 70) leadStatus = "qualified";
    else if (score >= 50) leadStatus = "warm";

    // Atualizar no banco
    await updateLead(phone, { lead_score: score, lead_status: leadStatus });

    return { score, status: leadStatus };
  } catch (error) {
    console.error("[DB] Erro ao calcular score:", error.message);
    return { score: 0, status: "cold" };
  }
}

// Marcar lead para transferencia humana
async function markForHumanTransfer(phone) {
  await updateLead(phone, {
    transfer_to_human: true,
    escalated: true,
    status: "contacted"
  });
}

// Obter leads qualificados (para notificacao)
async function getQualifiedLeads(minScore = 70) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM leads
       WHERE lead_score >= ?
       AND status NOT IN ("scheduled", "converted", "lost")
       ORDER BY lead_score DESC, last_interaction DESC`,
      [minScore]
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads qualificados:", error.message);
    return [];
  }
}

// Obter estatisticas
async function getStats() {
  try {
    const [totalLeads] = await pool.query("SELECT COUNT(*) as count FROM leads");
    const [hotLeads] = await pool.query('SELECT COUNT(*) as count FROM leads WHERE lead_status = "hot"');
    const [qualifiedLeads] = await pool.query('SELECT COUNT(*) as count FROM leads WHERE lead_status = "qualified"');
    const [todayLeads] = await pool.query(
      "SELECT COUNT(*) as count FROM leads WHERE DATE(first_contact) = CURDATE()"
    );
    const [avgScore] = await pool.query("SELECT AVG(lead_score) as avg FROM leads WHERE lead_score > 0");
    const [moskitSent] = await pool.query("SELECT COUNT(*) as count FROM leads WHERE moskit_sent = 1");
    const [autoRegistered] = await pool.query("SELECT COUNT(*) as count FROM leads WHERE auto_registered = 1");
    const [paidConsultations] = await pool.query("SELECT COUNT(*) as count FROM leads WHERE consultation_type = 'paid'");
    const [freeConsultations] = await pool.query("SELECT COUNT(*) as count FROM leads WHERE consultation_type = 'free'");
    const [scheduledTotal] = await pool.query("SELECT COUNT(*) as count FROM leads WHERE consultation_scheduled = 1");

    return {
      total: totalLeads[0].count,
      hot: hotLeads[0].count,
      qualified: qualifiedLeads[0].count,
      today: todayLeads[0].count,
      avgScore: Math.round(avgScore[0].avg || 0),
      moskitSent: moskitSent[0].count,
      autoRegistered: autoRegistered[0].count,
      paidConsultations: paidConsultations[0].count,
      freeConsultations: freeConsultations[0].count,
      scheduledTotal: scheduledTotal[0].count
    };
  } catch (error) {
    console.error("[DB] Erro ao obter estatisticas:", error.message);
    return { total: 0, hot: 0, qualified: 0, today: 0, avgScore: 0, moskitSent: 0, autoRegistered: 0, paidConsultations: 0, freeConsultations: 0, scheduledTotal: 0 };
  }
}

// Obter resumo da conversa
async function getConversationSummary(phone) {
  try {
    const [rows] = await pool.query(
      `SELECT role, content, created_at
       FROM conversations
       WHERE phone = ?
       ORDER BY created_at ASC`,
      [phone]
    );

    if (rows.length === 0) return null;

    let summary = `Conversa com ${phone}:\n`;
    summary += `Total de mensagens: ${rows.length}\n`;
    summary += `Periodo: ${rows[0].created_at} a ${rows[rows.length-1].created_at}\n\n`;

    // Ultimas 5 interacoes
    summary += "Ultimas mensagens:\n";
    const lastMessages = rows.slice(-10);
    lastMessages.forEach(msg => {
      const role = msg.role === "user" ? "Cliente" : "Bot";
      const content = msg.content.substring(0, 100) + (msg.content.length > 100 ? "..." : "");
      summary += `[${role}]: ${content}\n`;
    });

    return summary;
  } catch (error) {
    console.error("[DB] Erro ao gerar resumo:", error.message);
    return null;
  }
}

// ===== v8.6: RESUMO COMPLETO DA LEAD PARA EQUIPE =====
async function getLeadSummary(phone) {
  try {
    // Buscar dados da lead
    const lead = await getLead(phone);
    if (!lead) return null;

    // Buscar historico de conversa
    const [messages] = await pool.query(
      `SELECT role, content, created_at
       FROM conversations
       WHERE phone = ?
       ORDER BY created_at ASC`,
      [phone]
    );

    // Formatar resumo
    const firstContact = lead.first_contact ? new Date(lead.first_contact).toLocaleString('pt-BR') : 'N/A';
    const lastInteraction = lead.last_interaction ? new Date(lead.last_interaction).toLocaleString('pt-BR') : 'N/A';

    let summary = `====================================
RESUMO DA LEAD
====================================
Nome: ${lead.client_name || lead.whatsapp_name || lead.name || 'Nao informado'}
Telefone: ${phone}
Email: ${lead.email || 'Nao informado'}
Idioma: ${lead.language === 'pt' ? 'Portugues' : lead.language === 'es' ? 'Espanhol' : 'Ingles'}

------------------------------------
INTERESSE E STATUS
------------------------------------
Interesse: ${lead.visa_interest || 'Nao informado'}
Score: ${lead.lead_score || 0}/100 (${lead.lead_status || 'cold'})
Urgente: ${lead.is_urgent ? 'SIM!' : 'Nao'}
Estado atual: ${lead.conversation_state || 'new'}

------------------------------------
CONSULTA
------------------------------------
Tipo: ${lead.consultation_type === 'paid' ? 'PAGA (US)' : lead.consultation_type === 'free' ? 'Gratuita' : 'Nao escolheu'}
Pagamento: ${lead.payment_status === 'paid' ? 'PAGO' : lead.payment_status || 'N/A'}
Agendada: ${lead.consultation_scheduled ? 'SIM' : 'Nao'}

------------------------------------
DATAS
------------------------------------
Primeiro contato: ${firstContact}
Ultima interacao: ${lastInteraction}
Follow-ups enviados: ${lead.followup_count || 0}

------------------------------------
CONVERSA (${messages.length} mensagens)
------------------------------------\n`;

    // Adicionar ultimas 10 mensagens
    const lastMessages = messages.slice(-10);
    lastMessages.forEach(msg => {
      const time = new Date(msg.created_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      const role = msg.role === 'user' ? 'CLIENTE' : 'BOT';
      const content = msg.content.length > 150 ? msg.content.substring(0, 150) + '...' : msg.content;
      summary += `[${time}] ${role}: ${content}\n`;
    });

    summary += `====================================`;

    return summary;
  } catch (error) {
    console.error('[DB] Erro ao gerar resumo da lead:', error.message);
    return null;
  }
}

// ===== v8.6: METRICAS E RELATORIOS =====
async function getMetricsReport(days = 7) {
  try {
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    // Total de leads no periodo
    const [totalPeriod] = await pool.query(
      `SELECT COUNT(*) as count FROM leads WHERE first_contact >= ?`,
      [startDate]
    );

    // Leads por dia
    const [leadsPerDay] = await pool.query(
      `SELECT DATE(first_contact) as date, COUNT(*) as count
       FROM leads
       WHERE first_contact >= ?
       GROUP BY DATE(first_contact)
       ORDER BY date ASC`,
      [startDate]
    );

    // Leads por status
    const [leadsByStatus] = await pool.query(
      `SELECT lead_status, COUNT(*) as count
       FROM leads
       WHERE first_contact >= ?
       GROUP BY lead_status`,
      [startDate]
    );

    // Leads por interesse
    const [leadsByInterest] = await pool.query(
      `SELECT visa_interest, COUNT(*) as count
       FROM leads
       WHERE first_contact >= ? AND visa_interest IS NOT NULL
       GROUP BY visa_interest
       ORDER BY count DESC
       LIMIT 10`,
      [startDate]
    );

    // Taxa de conversao (consultas / total)
    const [consultations] = await pool.query(
      `SELECT
         SUM(CASE WHEN consultation_type = 'free' THEN 1 ELSE 0 END) as free,
         SUM(CASE WHEN consultation_type = 'paid' THEN 1 ELSE 0 END) as paid,
         SUM(CASE WHEN consultation_scheduled = 1 THEN 1 ELSE 0 END) as scheduled
       FROM leads
       WHERE first_contact >= ?`,
      [startDate]
    );

    // Leads por idioma
    const [leadsByLanguage] = await pool.query(
      `SELECT language, COUNT(*) as count
       FROM leads
       WHERE first_contact >= ?
       GROUP BY language`,
      [startDate]
    );

    // Score medio
    const [avgScore] = await pool.query(
      `SELECT AVG(lead_score) as avg
       FROM leads
       WHERE first_contact >= ? AND lead_score > 0`,
      [startDate]
    );

    // Leads urgentes
    const [urgentLeads] = await pool.query(
      `SELECT COUNT(*) as count
       FROM leads
       WHERE first_contact >= ? AND is_urgent = 1`,
      [startDate]
    );

    // Tempo medio ate primeira resposta (aproximado)
    const [responseTime] = await pool.query(
      `SELECT AVG(TIMESTAMPDIFF(MINUTE, first_contact, last_interaction)) as avg_minutes
       FROM leads
       WHERE first_contact >= ? AND last_interaction IS NOT NULL`,
      [startDate]
    );

    return {
      period: `Ultimos ${days} dias`,
      startDate: startDate.toISOString().split('T')[0],
      endDate: new Date().toISOString().split('T')[0],
      totalLeads: totalPeriod[0].count,
      leadsPerDay: leadsPerDay,
      byStatus: {
        cold: leadsByStatus.find(s => s.lead_status === 'cold')?.count || 0,
        warm: leadsByStatus.find(s => s.lead_status === 'warm')?.count || 0,
        qualified: leadsByStatus.find(s => s.lead_status === 'qualified')?.count || 0,
        hot: leadsByStatus.find(s => s.lead_status === 'hot')?.count || 0
      },
      byInterest: leadsByInterest,
      byLanguage: {
        pt: leadsByLanguage.find(l => l.language === 'pt')?.count || 0,
        en: leadsByLanguage.find(l => l.language === 'en')?.count || 0,
        es: leadsByLanguage.find(l => l.language === 'es')?.count || 0
      },
      consultations: {
        free: consultations[0].free || 0,
        paid: consultations[0].paid || 0,
        scheduled: consultations[0].scheduled || 0
      },
      avgScore: Math.round(avgScore[0].avg || 0),
      urgentLeads: urgentLeads[0].count,
      avgResponseMinutes: Math.round(responseTime[0].avg_minutes || 0)
    };
  } catch (error) {
    console.error('[DB] Erro ao gerar metricas:', error.message);
    return null;
  }
}

// ===== NOVA FUNCAO: Verificar conversa ativa =====
// Retorna informacoes sobre atividade recente na conversa
async function getConversationActivity(phone) {
  try {
    // Ultima mensagem do CLIENTE (role = 'user')
    const [lastClientMsg] = await pool.query(
      `SELECT created_at, content FROM conversations
       WHERE phone = ? AND role = 'user'
       ORDER BY created_at DESC LIMIT 1`,
      [phone]
    );

    // Ultima mensagem do BOT/EQUIPE (role = 'assistant')
    const [lastAssistantMsg] = await pool.query(
      `SELECT created_at, content FROM conversations
       WHERE phone = ? AND role = 'assistant'
       ORDER BY created_at DESC LIMIT 1`,
      [phone]
    );

    // Contar mensagens nas ultimas 24h
    const [recentMsgs] = await pool.query(
      `SELECT COUNT(*) as count FROM conversations
       WHERE phone = ? AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)`,
      [phone]
    );

    // Verificar se ultima resposta parece ser HUMANA (nao do bot)
    // Indicadores: links do google meet, horarios especificos, nomes de pessoas, etc.
    const humanIndicators = ['meet.google.com', 'zoom.us', 'teams.microsoft',
      'PM (', 'AM (', 'scheduled for', 'agendada para', 'programada para',
      'Dear ', 'Caro ', 'Estimado ', 'confirm your', 'confirmar sua'];

    let hasHumanResponse = false;
    if (lastAssistantMsg.length > 0) {
      const content = lastAssistantMsg[0].content || '';
      hasHumanResponse = humanIndicators.some(indicator => content.includes(indicator));
    }

    return {
      lastClientMessage: lastClientMsg.length > 0 ? lastClientMsg[0] : null,
      lastAssistantMessage: lastAssistantMsg.length > 0 ? lastAssistantMsg[0] : null,
      recentMessageCount: recentMsgs[0].count,
      hasHumanResponse: hasHumanResponse,
      isActiveConversation: recentMsgs[0].count > 0
    };
  } catch (error) {
    console.error("[DB] Erro ao verificar atividade:", error.message);
    return null;
  }
}

// =====================================
// ===== v9.0: INTAKE FORM FUNCTIONS =====
// =====================================

// Salvar resposta do intake form
async function saveIntakeFormResponse(phone, questionId, questionText, responseText, responseType, category, pointsEarned = 0, geminiAnalysis = null) {
  try {
    await pool.query(
      `INSERT INTO intake_form_responses
       (phone, question_id, question_text, response_text, response_type, question_category, points_earned, gemini_analysis)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [phone, questionId, questionText, responseText, responseType, category, pointsEarned, geminiAnalysis]
    );
    return true;
  } catch (error) {
    console.error("[DB] Erro ao salvar resposta do intake form:", error.message);
    return false;
  }
}

// Obter todas as respostas do intake form de um lead
async function getIntakeFormResponses(phone) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM intake_form_responses WHERE phone = ? ORDER BY question_id ASC`,
      [phone]
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar respostas do intake form:", error.message);
    return [];
  }
}

// Obter resposta especifica de uma pergunta
async function getIntakeFormResponse(phone, questionId) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM intake_form_responses WHERE phone = ? AND question_id = ?`,
      [phone, questionId]
    );
    return rows[0] || null;
  } catch (error) {
    console.error("[DB] Erro ao buscar resposta:", error.message);
    return null;
  }
}

// Atualizar analise Gemini de uma resposta
async function updateIntakeResponseGeminiAnalysis(phone, questionId, analysis, pointsEarned) {
  try {
    await pool.query(
      `UPDATE intake_form_responses SET gemini_analysis = ?, points_earned = ? WHERE phone = ? AND question_id = ?`,
      [analysis, pointsEarned, phone, questionId]
    );
    return true;
  } catch (error) {
    console.error("[DB] Erro ao atualizar analise:", error.message);
    return false;
  }
}

// Salvar/atualizar score de pathway
async function savePathwayScore(phone, pathway, score, confidence = 0) {
  try {
    await pool.query(
      `INSERT INTO pathway_scores (phone, pathway, score, confidence)
       VALUES (?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE score = ?, confidence = ?, updated_at = CURRENT_TIMESTAMP`,
      [phone, pathway, score, confidence, score, confidence]
    );
    return true;
  } catch (error) {
    console.error("[DB] Erro ao salvar pathway score:", error.message);
    return false;
  }
}

// Obter todos os pathway scores de um lead
async function getPathwayScores(phone) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM pathway_scores WHERE phone = ? ORDER BY score DESC`,
      [phone]
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar pathway scores:", error.message);
    return [];
  }
}

// Obter primary pathway (maior score)
async function getPrimaryPathway(phone) {
  try {
    const [rows] = await pool.query(
      `SELECT pathway, score, confidence FROM pathway_scores
       WHERE phone = ? ORDER BY score DESC, confidence DESC LIMIT 1`,
      [phone]
    );
    return rows[0] || null;
  } catch (error) {
    console.error("[DB] Erro ao buscar primary pathway:", error.message);
    return null;
  }
}

// Obter pergunta do intake form por ID
async function getIntakeQuestion(questionId) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM intake_questions WHERE question_id = ? AND is_active = true`,
      [questionId]
    );
    return rows[0] || null;
  } catch (error) {
    console.error("[DB] Erro ao buscar pergunta:", error.message);
    return null;
  }
}

// Obter todas as perguntas do intake form
async function getAllIntakeQuestions() {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM intake_questions WHERE is_active = true ORDER BY display_order ASC, question_id ASC`
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar perguntas:", error.message);
    return [];
  }
}

// Inserir pergunta no intake form
async function insertIntakeQuestion(questionData) {
  try {
    const {
      question_id, question_pt, question_en, question_es, response_type = 'text',
      category, max_points = 0, pathway_impact = null, skip_if_question_id = null,
      skip_if_answer = null, options_pt = null, options_en = null, options_es = null, display_order
    } = questionData;

    await pool.query(
      `INSERT INTO intake_questions
       (question_id, question_pt, question_en, question_es, response_type, category,
        max_points, pathway_impact, skip_if_question_id, skip_if_answer,
        options_pt, options_en, options_es, display_order)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE
         question_pt = VALUES(question_pt),
         question_en = VALUES(question_en),
         question_es = VALUES(question_es),
         response_type = VALUES(response_type),
         category = VALUES(category),
         max_points = VALUES(max_points),
         pathway_impact = VALUES(pathway_impact),
         skip_if_question_id = VALUES(skip_if_question_id),
         skip_if_answer = VALUES(skip_if_answer),
         options_pt = VALUES(options_pt),
         options_en = VALUES(options_en),
         options_es = VALUES(options_es),
         display_order = VALUES(display_order)`,
      [question_id, question_pt, question_en, question_es, response_type, category,
       max_points, pathway_impact, skip_if_question_id, skip_if_answer,
       options_pt, options_en, options_es, display_order]
    );
    return true;
  } catch (error) {
    console.error("[DB] Erro ao inserir pergunta:", error.message);
    return false;
  }
}

// Obter leads para campanha de intake form
async function getLeadsForIntakeCampaign(limit = 10, excludePhone = null) {
  try {
    let query = `
      SELECT * FROM leads
      WHERE (intake_form_state IS NULL OR intake_form_state = 'not_started')
      AND phone != ?
      AND (intake_form_invite_sent_at IS NULL OR intake_form_invite_sent_at < DATE_SUB(NOW(), INTERVAL 7 DAY))
      AND last_interaction > DATE_SUB(NOW(), INTERVAL 30 DAY)
      ORDER BY lead_score DESC, last_interaction DESC
      LIMIT ?
    `;
    const [rows] = await pool.query(query, [excludePhone || '', limit]);
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads para campanha:", error.message);
    return [];
  }
}

// Obter leads com intake form em progresso (para follow-ups)
async function getLeadsWithIntakeInProgress() {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM leads
       WHERE intake_form_state = 'in_progress'
       AND (intake_form_followup_count IS NULL OR intake_form_followup_count < 3)
       ORDER BY intake_form_started_at ASC`
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads com intake em progresso:", error.message);
    return [];
  }
}

// Obter leads que completaram intake form
async function getLeadsWithCompletedIntake(minScore = 0) {
  try {
    const [rows] = await pool.query(
      `SELECT * FROM leads
       WHERE intake_form_state = 'completed'
       AND intake_form_final_score >= ?
       ORDER BY intake_form_final_score DESC, intake_form_completed_at DESC`,
      [minScore]
    );
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads com intake completo:", error.message);
    return [];
  }
}

// Calcular score total do intake form
async function calculateIntakeFormScore(phone) {
  try {
    const [result] = await pool.query(
      `SELECT SUM(points_earned) as total_score FROM intake_form_responses WHERE phone = ?`,
      [phone]
    );
    return result[0]?.total_score || 0;
  } catch (error) {
    console.error("[DB] Erro ao calcular score:", error.message);
    return 0;
  }
}

// Obter estatisticas do intake form
async function getIntakeFormStats() {
  try {
    const [totalInvited] = await pool.query(`SELECT COUNT(*) as count FROM leads WHERE intake_form_state = 'invited'`);
    const [totalInProgress] = await pool.query(`SELECT COUNT(*) as count FROM leads WHERE intake_form_state = 'in_progress'`);
    const [totalCompleted] = await pool.query(`SELECT COUNT(*) as count FROM leads WHERE intake_form_state = 'completed'`);
    const [totalExpired] = await pool.query(`SELECT COUNT(*) as count FROM leads WHERE intake_form_state = 'expired'`);
    const [totalQualified] = await pool.query(`SELECT COUNT(*) as count FROM leads WHERE intake_form_state = 'completed' AND intake_form_final_score >= 70`);
    const [avgScore] = await pool.query(`SELECT AVG(intake_form_final_score) as avg FROM leads WHERE intake_form_state = 'completed' AND intake_form_final_score > 0`);

    // Pathway distribution
    const [pathwayDist] = await pool.query(
      `SELECT intake_form_primary_pathway as pathway, COUNT(*) as count
       FROM leads WHERE intake_form_state = 'completed' AND intake_form_primary_pathway IS NOT NULL
       GROUP BY intake_form_primary_pathway ORDER BY count DESC`
    );

    return {
      invited: totalInvited[0].count,
      inProgress: totalInProgress[0].count,
      completed: totalCompleted[0].count,
      expired: totalExpired[0].count,
      qualified: totalQualified[0].count,
      avgScore: Math.round(avgScore[0].avg || 0),
      pathwayDistribution: pathwayDist
    };
  } catch (error) {
    console.error("[DB] Erro ao obter estatisticas do intake:", error.message);
    return { invited: 0, inProgress: 0, completed: 0, expired: 0, qualified: 0, avgScore: 0, pathwayDistribution: [] };
  }
}

// Limpar respostas do intake form (para reiniciar)
async function clearIntakeFormResponses(phone) {
  try {
    await pool.query(`DELETE FROM intake_form_responses WHERE phone = ?`, [phone]);
    await pool.query(`DELETE FROM pathway_scores WHERE phone = ?`, [phone]);
    await updateLead(phone, {
      intake_form_state: 'not_started',
      intake_form_current_question: 0,
      intake_form_started_at: null,
      intake_form_completed_at: null,
      intake_form_final_score: 0,
      intake_form_primary_pathway: null,
      intake_form_gemini_summary: null,
      eligible_for_free_call: false,
      intake_form_followup_count: 0
    });
    return true;
  } catch (error) {
    console.error("[DB] Erro ao limpar intake form:", error.message);
    return false;
  }
}

// ===== CHAT INTERFACE SUPPORT =====

// Método query genérico para consultas SQL diretas
async function query(sql, params = []) {
  try {
    await ensurePool();
    const [rows] = await pool.execute(sql, params);
    return rows;
  } catch (e) {
    console.error("[DB] Query error:", e.message);
    throw e;
  }
}

// Adicionar colunas bot_enabled e from_bot se não existirem
async function ensureChatColumns() {
  try {
    // Adicionar bot_enabled à tabela leads
    await pool.execute(`
      ALTER TABLE leads ADD COLUMN IF NOT EXISTS bot_enabled TINYINT(1) DEFAULT 1
    `).catch(() => {});

    // Adicionar last_read_at à tabela leads
    await pool.execute(`
      ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMP NULL
    `).catch(() => {});

    // Adicionar from_bot à tabela conversations
    await pool.execute(`
      ALTER TABLE conversations ADD COLUMN IF NOT EXISTS from_bot TINYINT(1) DEFAULT 1
    `).catch(() => {});

    console.log("[DB] Chat columns checked/added");
  } catch (e) {
    // Ignore errors - columns might already exist
  }
}

// Chamar ao inicializar
setTimeout(ensureChatColumns, 3000);

// ===== v10.5: LEAD MONITOR FUNCTIONS =====

// Obter leads que precisam de atencao (para o monitor)
async function getLeadsNeedingAttention(options = {}) {
  const { minutesSinceLastMessage = 5, limit = 50 } = options;
  try {
    const [rows] = await pool.query(`
      SELECT
        l.phone,
        l.name as client_name,
        l.whatsapp_name,
        l.email,
        l.visa_interest,
        l.lead_status,
        l.lead_score,
        l.conversation_state,
        l.is_urgent,
        l.language,
        l.last_interaction,
        l.needs_human_review,
        l.human_review_reason,
        (SELECT content FROM conversations WHERE phone = l.phone ORDER BY created_at DESC LIMIT 1) as last_message,
        (SELECT role FROM conversations WHERE phone = l.phone ORDER BY created_at DESC LIMIT 1) as last_message_role,
        (SELECT created_at FROM conversations WHERE phone = l.phone ORDER BY created_at DESC LIMIT 1) as last_message_time,
        TIMESTAMPDIFF(MINUTE,
          (SELECT created_at FROM conversations WHERE phone = l.phone ORDER BY created_at DESC LIMIT 1),
          NOW()
        ) as minutes_since_last_message
      FROM leads l
      WHERE
        l.conversation_state IN ('awaiting_human', 'initial_contact', 'asked_name')
        AND l.last_interaction > NOW() - INTERVAL 7 DAY
      ORDER BY
        l.is_urgent DESC,
        l.needs_human_review DESC,
        l.lead_score DESC,
        l.last_interaction DESC
      LIMIT ?
    `, [limit]);
    return rows;
  } catch (error) {
    console.error("[DB] Erro ao buscar leads para monitor:", error.message);
    return [];
  }
}

// Marcar lead para revisao humana
async function flagLeadForHumanReview(phone, reason) {
  try {
    await pool.query(`
      UPDATE leads
      SET needs_human_review = TRUE,
          human_review_reason = ?
      WHERE phone = ?
    `, [reason, phone]);
    console.log(`[DB] Lead ${phone} marcada para revisao: ${reason}`);
    return true;
  } catch (error) {
    console.error(`[DB] Erro ao marcar lead ${phone}:`, error.message);
    return false;
  }
}

// Limpar flag de revisao humana
async function clearHumanReviewFlag(phone) {
  try {
    await pool.query(`
      UPDATE leads
      SET needs_human_review = FALSE,
          human_review_reason = NULL
      WHERE phone = ?
    `, [phone]);
    console.log(`[DB] Flag de revisao limpa para ${phone}`);
    return true;
  } catch (error) {
    console.error(`[DB] Erro ao limpar flag ${phone}:`, error.message);
    return false;
  }
}

// Obter historico de mensagens completo para resumo
async function getMessagesForSummary(phone, limit = 30) {
  try {
    const [rows] = await pool.query(`
      SELECT role, content, DATE_FORMAT(created_at, '%H:%i') as time, created_at
      FROM conversations
      WHERE phone = ?
      ORDER BY created_at DESC
      LIMIT ?
    `, [phone, limit]);
    return rows.reverse();
  } catch (error) {
    console.error("[DB] Erro ao buscar mensagens para resumo:", error.message);
    return [];
  }
}

// Obter estatisticas do monitor
async function getMonitorStats() {
  try {
    const [responded] = await pool.query(`
      SELECT COUNT(DISTINCT l.phone) as count
      FROM leads l
      WHERE l.last_interaction > NOW() - INTERVAL 24 HOUR
      AND (SELECT role FROM conversations WHERE phone = l.phone ORDER BY created_at DESC LIMIT 1) = 'assistant'
    `);

    const [awaiting] = await pool.query(`
      SELECT COUNT(DISTINCT l.phone) as count
      FROM leads l
      WHERE l.last_interaction > NOW() - INTERVAL 24 HOUR
      AND (SELECT role FROM conversations WHERE phone = l.phone ORDER BY created_at DESC LIMIT 1) = 'user'
    `);

    const [urgent] = await pool.query(`
      SELECT COUNT(*) as count FROM leads
      WHERE is_urgent = TRUE AND last_interaction > NOW() - INTERVAL 24 HOUR
    `);

    const [needsHuman] = await pool.query(`
      SELECT COUNT(*) as count FROM leads
      WHERE needs_human_review = TRUE
    `);

    return {
      responded: responded[0].count,
      awaiting: awaiting[0].count,
      urgent: urgent[0].count,
      needsHuman: needsHuman[0].count
    };
  } catch (error) {
    console.error("[DB] Erro ao obter stats do monitor:", error.message);
    return { responded: 0, awaiting: 0, urgent: 0, needsHuman: 0 };
  }
}

// Exportar novas funcoes - adicionar ao module.exports

module.exports = {
  query,
  init,
  testConnection,
  saveMessage,
  getConversationHistory,
  getLead,
  getLeadByEmail,
  updateLead,
  updatePaymentStatus,
  savePaymentSession,
  saveCalendlyEvent,
  getScheduledLeads,
  updateLeadScore,
  markForHumanTransfer,
  getQualifiedLeads,
  getIncompleteLeads,
  getLeadsAwaitingConsultation,
  getConversationActivity,
  getStats,
  getConversationSummary,
  getLeadSummary,
  getMetricsReport,
  // v9.0 - Intake Form Functions
  saveIntakeFormResponse,
  getIntakeFormResponses,
  getIntakeFormResponse,
  updateIntakeResponseGeminiAnalysis,
  savePathwayScore,
  getPathwayScores,
  getPrimaryPathway,
  getIntakeQuestion,
  getAllIntakeQuestions,
  insertIntakeQuestion,
  getLeadsForIntakeCampaign,
  getLeadsWithIntakeInProgress,
  getLeadsWithCompletedIntake,
  calculateIntakeFormScore,
  getIntakeFormStats,
  clearIntakeFormResponses,
  // v9.1 - Messenger stub functions (para evitar erros)
  getMessengerLeadsForFollowup: async () => [],
  getInactiveMessengerLeads: async () => [],
  // v10.5 - Lead Monitor functions
  getLeadsNeedingAttention,
  flagLeadForHumanReview,
  clearHumanReviewFlag,
  getMessagesForSummary,
  getMonitorStats
};
