/**
 * Auto Follow-up Module
 * CaseHub
 * v1.0 - Automatic follow-up for leads marked by human operators
 */

const db = require("./database");
const whatsappClient = require("./whatsapp-client");
const botConfig = require("./bot-config");
const notificationService = require("./services/notification-service");
const { detectLanguage, getMessages } = require("./languages");

// Follow-up messages por idioma (variações para parecer natural)
// IMPORTANTE: SEM EMOJIS (conforme CLAUDE.md)
const FOLLOWUP_MESSAGES = {
    pt: [
        "Oi\! Tudo bem? Só passando para ver se você ainda tem interesse em conversar sobre imigração. Nossa equipe está à disposição\!",
        "Olá\! Notei que não conseguimos conectar. Posso te ajudar com alguma dúvida sobre vistos americanos?",
        "Oi\! Aqui é do ${process.env.ORG_NAME || "CaseHub"}. Ficou alguma dúvida? Estamos prontos para te atender\!"
    ],
    en: [
        "Hi\! Just checking in to see if you're still interested in discussing your immigration options. Our team is here to help\!",
        "Hello\! I noticed we didn't get a chance to connect. Can I help answer any questions about US visas?",
        "Hi\! This is ${process.env.ORG_NAME || "CaseHub"}. Any questions remaining? We're ready to assist you\!"
    ],
    es: [
        "¡Hola\! Solo quería ver si todavía te interesa hablar sobre inmigración. ¡Nuestro equipo está a tu disposición\!",
        "¡Hola\! Noté que no pudimos conectar. ¿Puedo ayudarte con alguna pregunta sobre visas estadounidenses?",
        "¡Hola\! Aquí del ${process.env.ORG_NAME || "CaseHub"}. ¿Quedó alguna duda? ¡Estamos listos para atenderte\!"
    ]
};

/**
 * Get a random follow-up message for the language
 */
function getFollowupMessage(lang) {
    const messages = FOLLOWUP_MESSAGES[lang] || FOLLOWUP_MESSAGES.en;
    const randomIndex = Math.floor(Math.random() * messages.length);
    return messages[randomIndex];
}

/**
 * Mark a lead for auto follow-up
 */
async function markForFollowup(phone) {
    try {
        await db.query(
            `UPDATE leads SET 
                needs_auto_followup = 1, 
                auto_followup_requested_at = NOW(),
                auto_followup_completed_at = NULL
            WHERE phone = ?`,
            [phone]
        );
        console.log(`[AUTO-FOLLOWUP] Lead ${phone} marcada para follow-up`);
        return { success: true };
    } catch (error) {
        console.error("[AUTO-FOLLOWUP] Erro ao marcar:", error.message);
        return { success: false, error: error.message };
    }
}

/**
 * Unmark a lead from auto follow-up
 */
async function unmarkForFollowup(phone) {
    try {
        await db.query(
            `UPDATE leads SET needs_auto_followup = 0 WHERE phone = ?`,
            [phone]
        );
        console.log(`[AUTO-FOLLOWUP] Lead ${phone} desmarcada de follow-up`);
        return { success: true };
    } catch (error) {
        console.error("[AUTO-FOLLOWUP] Erro ao desmarcar:", error.message);
        return { success: false, error: error.message };
    }
}

/**
 * Get all leads that need follow-up
 */
async function getLeadsNeedingFollowup() {
    try {
        const leads = await db.query(`
            SELECT l.phone, l.whatsapp_name, l.client_name, l.language, 
                   l.auto_followup_requested_at, l.last_interaction,
                   (SELECT MAX(created_at) FROM conversations WHERE phone = l.phone AND role = 'user') as last_user_msg
            FROM leads l
            WHERE l.needs_auto_followup = 1 
              AND l.auto_followup_completed_at IS NULL
              AND l.auto_followup_requested_at IS NOT NULL
              AND TIMESTAMPDIFF(MINUTE, l.auto_followup_requested_at, NOW()) >= 30
            ORDER BY l.auto_followup_requested_at ASC
            LIMIT 10
        `);
        return leads || [];
    } catch (error) {
        console.error("[AUTO-FOLLOWUP] Erro ao buscar leads:", error.message);
        return [];
    }
}

/**
 * Process a single follow-up
 */
async function processFollowup(lead) {
    try {
        const lang = lead.language || detectLanguage(lead.phone);
        const message = getFollowupMessage(lang);

        // v6.0: Send via notification-service (guard + dedup enforced)
        const sendResult = await notificationService.send(lead.phone, message, {
            source: 'auto-followup',
            saveToDB: true
        });

        if (!sendResult.sent) {
            console.log(`[AUTO-FOLLOWUP] Bloqueado: ${sendResult.reason}`);
            return { success: false, phone: lead.phone, error: sendResult.reason };
        }

        // Mark as completed
        await db.query(`
            UPDATE leads SET
                auto_followup_completed_at = NOW(),
                auto_followup_message = ?,
                needs_auto_followup = 0
            WHERE phone = ?
        `, [message, lead.phone]);

        console.log(`[AUTO-FOLLOWUP] Follow-up enviado para ${lead.phone}`);
        return { success: true, phone: lead.phone, message };
    } catch (error) {
        console.error(`[AUTO-FOLLOWUP] Erro ao enviar para ${lead.phone}:`, error.message);
        return { success: false, phone: lead.phone, error: error.message };
    }
}

/**
 * Process all pending follow-ups
 */
async function processAllFollowups() {
    // Guard check moved to notification-service (per-message level)
    // Still do a quick check to avoid unnecessary DB queries
    if (botConfig.isHardOff()) {
        console.log("[AUTO-FOLLOWUP] Bot em HARD OFF, follow-ups cancelados.");
        return { processed: 0, results: [] };
    }

    console.log("[AUTO-FOLLOWUP] Verificando leads para follow-up...");

    const leads = await getLeadsNeedingFollowup();
    
    if (leads.length === 0) {
        console.log("[AUTO-FOLLOWUP] Nenhuma lead pendente");
        return { processed: 0, results: [] };
    }
    
    console.log(`[AUTO-FOLLOWUP] ${leads.length} leads para processar`);
    
    const results = [];
    for (const lead of leads) {
        const result = await processFollowup(lead);
        results.push(result);
        // Wait 5 seconds between messages to avoid spam detection
        await new Promise(resolve => setTimeout(resolve, 5000));
    }
    
    return { processed: results.length, results };
}

/**
 * Get follow-up status/stats
 */
async function getFollowupStats() {
    try {
        const stats = await db.query(`
            SELECT 
                COUNT(CASE WHEN needs_auto_followup = 1 AND auto_followup_completed_at IS NULL THEN 1 END) as pending,
                COUNT(CASE WHEN auto_followup_completed_at IS NOT NULL AND auto_followup_completed_at > DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 END) as completed_24h,
                COUNT(CASE WHEN needs_auto_followup = 1 THEN 1 END) as total_marked
            FROM leads
        `);
        return stats[0] || { pending: 0, completed_24h: 0, total_marked: 0 };
    } catch (error) {
        console.error("[AUTO-FOLLOWUP] Erro ao buscar stats:", error.message);
        return { pending: 0, completed_24h: 0, total_marked: 0 };
    }
}

/**
 * Get leads marked for follow-up
 */
async function getMarkedLeads() {
    try {
        const leads = await db.query(`
            SELECT l.phone, l.whatsapp_name, l.client_name, l.language,
                   l.auto_followup_requested_at, l.auto_followup_completed_at,
                   l.auto_followup_message,
                   TIMESTAMPDIFF(MINUTE, l.auto_followup_requested_at, NOW()) as minutes_waiting
            FROM leads l
            WHERE l.needs_auto_followup = 1 OR l.auto_followup_completed_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
            ORDER BY l.auto_followup_requested_at DESC
            LIMIT 50
        `);
        return leads || [];
    } catch (error) {
        console.error("[AUTO-FOLLOWUP] Erro ao buscar leads marcadas:", error.message);
        return [];
    }
}

// Setup scheduler (runs every 15 minutes)
let schedulerInterval = null;

function startScheduler() {
    if (schedulerInterval) return;
    
    schedulerInterval = setInterval(async () => {
        try {
            await processAllFollowups();
        } catch (error) {
            console.error("[AUTO-FOLLOWUP] Erro no scheduler:", error.message);
        }
    }, 15 * 60 * 1000); // Every 15 minutes
    
    console.log("[AUTO-FOLLOWUP] Scheduler iniciado (verificando a cada 15 minutos)");
    
    // Run immediately on start
    setTimeout(processAllFollowups, 10000);
}

function stopScheduler() {
    if (schedulerInterval) {
        clearInterval(schedulerInterval);
        schedulerInterval = null;
        console.log("[AUTO-FOLLOWUP] Scheduler parado");
    }
}

module.exports = {
    markForFollowup,
    unmarkForFollowup,
    getLeadsNeedingFollowup,
    processFollowup,
    processAllFollowups,
    getFollowupStats,
    getMarkedLeads,
    startScheduler,
    stopScheduler
};
