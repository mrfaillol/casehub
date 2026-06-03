/**
 * Lead Monitor - Sistema de Monitoramento Ativo de Leads
 * CaseHub - WhatsApp Bot
 * v1.0 - 03/02/2026
 *
 * Funcoes:
 * - Monitora leads que precisam de atencao
 * - Gera resumos de conversas via Gemini
 * - Processa leads nao respondidas com LLM
 * - Notifica via Google Chat e Email quando precisa humano
 */

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent';

// Configuracao de notificacoes
// Helper: Limpar e parsear JSON da resposta do Gemini (v12.7)
function cleanAndParseJSON(text) {
  try {
    // Remover markdown code blocks se existir
    let cleanText = text.replace(/```json?\s*/gi, '').replace(/```/g, '');

    const jsonMatch = cleanText.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;
    let jsonStr = jsonMatch[0];

    // Sanitizacao progressiva
    // 1. Remover trailing commas (, seguido de ] ou })
    jsonStr = jsonStr.replace(/,([\s]*[\]\}])/g, '$1');

    // 2. Remover caracteres de controle (exceto newline)
    jsonStr = jsonStr.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, ' ');

    // 3. Tentar parse direto
    try {
      return JSON.parse(jsonStr);
    } catch (e1) {
      // 4. Fallback: remover newlines e tentar de novo
      jsonStr = jsonStr.replace(/\n/g, ' ').replace(/\r/g, ' ');
      try {
        return JSON.parse(jsonStr);
      } catch (e2) {
        // 5. Ultimo recurso: limpar arrays quebrados
        jsonStr = jsonStr.replace(/\[([^\]]*),\s*\]/g, '[$1]');
        return JSON.parse(jsonStr);
      }
    }
  } catch (e) {
    console.warn('[LEAD-MONITOR] JSON parse failed:', e.message?.substring(0, 100));
    return null;
  }
}

const NOTIFICATION_CONFIG = {
    googleChatWebhook: process.env.GOOGLE_CHAT_WEBHOOK_VICTOR || '',
    emailTo: 'victorexample.com',
    checkIntervalMinutes: 5,
    alertThresholdMinutes: 30,
    llmResponseThresholdMinutes: 5
};

// Estado do monitor
let monitorState = {
    isRunning: false,
    lastCheck: null,
    leadsNeedingAttention: [],
    schedulerInterval: null
};

// Track de leads ja notificadas (evita spam)
let notifiedLeads = new Map(); // phone -> { lastNotified: Date, reason: string }
const NOTIFICATION_COOLDOWN_HOURS = 2; // So notifica de novo apos 2 horas

// Dependencias (injetadas na inicializacao)
let db = null;
let whatsappClient = null;
let llmChatbot = null;
let emailService = null;
let notificationService = null;

/**
 * Inicializar o monitor com dependencias
 */
function initialize(dependencies) {
    db = dependencies.db;
    whatsappClient = dependencies.whatsappClient;
    llmChatbot = dependencies.llmChatbot;
    emailService = dependencies.emailService;
    notificationService = dependencies.notificationService || null;
    console.log('[LEAD-MONITOR] Inicializado' + (notificationService ? ' (with notification-service)' : ' (legacy mode)'));
}

/**
 * Iniciar o scheduler de monitoramento
 */
function startMonitorScheduler() {
    if (monitorState.schedulerInterval) {
        console.log('[LEAD-MONITOR] Scheduler ja esta rodando');
        return;
    }

    const intervalMs = NOTIFICATION_CONFIG.checkIntervalMinutes * 60 * 1000;

    // Executar imediatamente
    checkLeadsNeedingAttention();

    // Agendar execucoes periodicas
    monitorState.schedulerInterval = setInterval(() => {
        checkLeadsNeedingAttention();
    }, intervalMs);

    console.log(`[LEAD-MONITOR] Scheduler iniciado - verificando a cada ${NOTIFICATION_CONFIG.checkIntervalMinutes} minutos`);
}

/**
 * Parar o scheduler
 */
function stopMonitorScheduler() {
    if (monitorState.schedulerInterval) {
        clearInterval(monitorState.schedulerInterval);
        monitorState.schedulerInterval = null;
        console.log('[LEAD-MONITOR] Scheduler parado');
    }
}

/**
 * Verificar leads que precisam de atencao
 */
async function checkLeadsNeedingAttention() {
    if (monitorState.isRunning) {
        console.log('[LEAD-MONITOR] Verificacao ja em andamento, pulando...');
        return;
    }

    monitorState.isRunning = true;
    monitorState.lastCheck = new Date();
    console.log('[LEAD-MONITOR] Iniciando verificacao de leads...');

    try {
        // 1. Buscar leads que precisam de atencao
        const leadsNeedingAttention = await getLeadsNeedingAttention();

        monitorState.leadsNeedingAttention = leadsNeedingAttention;

        console.log(`[LEAD-MONITOR] ${leadsNeedingAttention.length} leads precisando de atencao`);

        // 2. Processar cada lead
        for (const lead of leadsNeedingAttention) {
            await processLeadNeedingAttention(lead);
        }

    } catch (error) {
        console.error('[LEAD-MONITOR] Erro na verificacao:', error.message);
    } finally {
        monitorState.isRunning = false;
    }
}

/**
 * Buscar leads que precisam de atencao do banco de dados
 */
async function getLeadsNeedingAttention() {
    if (!db) return [];

    const query = `
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
            l.lead_score DESC,
            l.last_interaction DESC
        LIMIT 50
    `;

    try {
        const results = await db.query(query);

        // Filtrar leads que realmente precisam de atencao
        return results.filter(lead => {
            // Lead urgente sempre precisa atencao
            if (lead.is_urgent) return true;

            // Ultima mensagem foi do cliente (user) e nao respondemos
            if (lead.last_message_role === 'user') {
                // Se passou mais de 5 minutos, precisa resposta
                if (lead.minutes_since_last_message >= NOTIFICATION_CONFIG.llmResponseThresholdMinutes) {
                    return true;
                }
            }

            // Marcada para revisao humana
            if (lead.needs_human_review) return true;

            return false;
        });
    } catch (error) {
        console.error('[LEAD-MONITOR] Erro ao buscar leads:', error.message);
        return [];
    }
}

/**
 * Processar uma lead que precisa de atencao
 */
async function processLeadNeedingAttention(lead) {
    console.log(`[LEAD-MONITOR] Processando: ${lead.phone} | Estado: ${lead.conversation_state} | Min sem resposta: ${lead.minutes_since_last_message}`);

    try {
        // 1. Se precisa de revisao humana, notificar
        if (lead.needs_human_review) {
            await notifyHumanNeeded(lead, lead.human_review_reason || 'Marcada para revisao');
            return;
        }

        // 2. Se urgente, notificar imediatamente
        if (lead.is_urgent) {
            await notifyHumanNeeded(lead, 'Lead URGENTE');
            return;
        }

        // 3. Se ultima mensagem foi do cliente e passou muito tempo
        if (lead.last_message_role === 'user' && lead.minutes_since_last_message >= NOTIFICATION_CONFIG.llmResponseThresholdMinutes) {

            // Tentar responder com LLM se disponivel
            if (llmChatbot && lead.minutes_since_last_message < NOTIFICATION_CONFIG.alertThresholdMinutes) {
                const responded = await tryLLMResponse(lead);
                if (responded) return;
            }

            // Se passou do threshold de alerta ou LLM nao conseguiu, notificar humano
            if (lead.minutes_since_last_message >= NOTIFICATION_CONFIG.alertThresholdMinutes) {
                await notifyHumanNeeded(lead, `Sem resposta ha ${lead.minutes_since_last_message} minutos`);
            }
        }

    } catch (error) {
        console.error(`[LEAD-MONITOR] Erro ao processar ${lead.phone}:`, error.message);
    }
}

/**
 * Tentar responder com LLM
 */
async function tryLLMResponse(lead) {
    if (!llmChatbot || !lead.last_message) {
        return false;
    }

    // v6.0: Use notification-service for centralized guard + dedup
    if (notificationService) {
        const check = notificationService.canSend(lead.phone, { source: 'lead-monitor' });
        if (!check.allowed) {
            console.log(`[LEAD-MONITOR] Bloqueado por notification-service: ${check.reason}`);
            return false;
        }
    } else {
        // Legacy fallback: manual hardOff check
        const botConfigModule = require("./bot-config");
        if (botConfigModule.isHardOff()) {
            console.log(`[LEAD-MONITOR] Bot em HARD OFF, resposta LLM NAO enviada para ${lead.phone}`);
            return false;
        }
        if (!whatsappClient) return false;
    }

    try {
        console.log(`[LEAD-MONITOR] Tentando resposta LLM para ${lead.phone}...`);

        const result = await llmChatbot.processMessage(lead.last_message, {
            phone: lead.phone,
            client_name: lead.client_name,
            whatsapp_name: lead.whatsapp_name,
            email: lead.email,
            visa_interest: lead.visa_interest,
            language: lead.language || 'pt'
        }, db);

        if (result.shouldRespond && result.response) {
            // v6.0: Send via notification-service (guard + dedup enforced)
            if (notificationService) {
                const sendResult = await notificationService.send(lead.phone, result.response, {
                    source: 'lead-monitor',
                    saveToDB: true
                });
                if (!sendResult.sent) {
                    console.log(`[LEAD-MONITOR] Envio bloqueado: ${sendResult.reason}`);
                    return false;
                }
            } else {
                console.error("[LEAD-MONITOR] notificationService not available - cannot send");
                return false;
            }

            console.log(`[LEAD-MONITOR] Resposta LLM enviada para ${lead.phone}`);

            // Se LLM sinalizou que precisa humano, marcar e notificar
            if (result.needsHuman) {
                await flagForHumanReview(lead.phone, result.metadata?.intent || 'LLM sinalizou');
                await notifyHumanNeeded(lead, `LLM respondeu mas sinalizou: ${result.metadata?.intent}`);
            }

            return true;
        }

        return false;
    } catch (error) {
        console.error(`[LEAD-MONITOR] Erro LLM para ${lead.phone}:`, error.message);
        return false;
    }
}

/**
 * Marcar lead para revisao humana
 */
async function flagForHumanReview(phone, reason) {
    if (!db) return;

    try {
        await db.query(`
            UPDATE leads
            SET needs_human_review = TRUE,
                human_review_reason = ?
            WHERE phone = ?
        `, [reason, phone]);

        console.log(`[LEAD-MONITOR] Lead ${phone} marcada para revisao: ${reason}`);
    } catch (error) {
        console.error(`[LEAD-MONITOR] Erro ao marcar ${phone}:`, error.message);
    }
}

/**
 * Limpar flag de revisao humana
 */
async function clearHumanReviewFlag(phone) {
    if (!db) return;

    try {
        await db.query(`
            UPDATE leads
            SET needs_human_review = FALSE,
                human_review_reason = NULL
            WHERE phone = ?
        `, [phone]);

        console.log(`[LEAD-MONITOR] Flag de revisao limpa para ${phone}`);
    } catch (error) {
        console.error(`[LEAD-MONITOR] Erro ao limpar flag ${phone}:`, error.message);
    }
}

/**
 * Notificar que precisa de atencao humana
 */
async function notifyHumanNeeded(lead, reason) {
    // CHECK DE DEDUPLICACAO - evita spam de notificacoes repetidas
    const lastNotification = notifiedLeads.get(lead.phone);
    if (lastNotification) {
        const hoursSinceNotified = (Date.now() - lastNotification.lastNotified) / (1000 * 60 * 60);
        if (hoursSinceNotified < NOTIFICATION_COOLDOWN_HOURS) {
            console.log(`[LEAD-MONITOR] Lead ${lead.phone} ja notificada ha ${hoursSinceNotified.toFixed(1)}h, pulando...`);
            return;
        }
    }

    // Registrar notificacao ANTES de enviar
    notifiedLeads.set(lead.phone, { lastNotified: Date.now(), reason });

    console.log(`[LEAD-MONITOR] Notificando humano sobre ${lead.phone}: ${reason}`);

    // Gerar resumo da conversa
    const summary = await generateConversationSummary(lead.phone);

    // Montar mensagem de alerta
    const alertMessage = formatAlertMessage(lead, reason, summary);

    // Enviar via Google Chat
    if (NOTIFICATION_CONFIG.googleChatWebhook) {
        await sendGoogleChatAlert(alertMessage);
    }

    // Enviar via Email
    if (NOTIFICATION_CONFIG.emailTo && emailService) {
        await sendEmailAlert(lead, reason, summary);
    }
}

/**
 * Gerar resumo da conversa via Gemini
 */
async function generateConversationSummary(phone) {
    if (!db || !GEMINI_API_KEY) {
        return {
            currentSituation: 'Resumo nao disponivel',
            history: [],
            nextSteps: [],
            pendingQuestions: []
        };
    }

    try {
        // Buscar historico de mensagens
        const messages = await db.query(`
            SELECT role, content, DATE_FORMAT(created_at, '%H:%i') as time
            FROM conversations
            WHERE phone = ?
            ORDER BY created_at DESC
            LIMIT 30
        `, [phone]);

        if (!messages || messages.length === 0) {
            return {
                currentSituation: 'Sem historico de conversa',
                history: [],
                nextSteps: ['Iniciar contato'],
                pendingQuestions: []
            };
        }

        // Buscar dados da lead
        const leadData = await db.query(`
            SELECT name, whatsapp_name, visa_interest, lead_status, lead_score
            FROM leads WHERE phone = ?
        `, [phone]);

        const lead = leadData[0] || {};
        const messagesText = messages.reverse().map(m =>
            `${m.time} [${m.role === 'user' ? 'Cliente' : 'Atendente'}]: ${m.content}`
        ).join('\n');

        // Prompt para o Gemini
        const prompt = `Analise esta conversa do WhatsApp de um escritorio de imigracao e gere um resumo estruturado.

DADOS DA LEAD:
Nome: ${lead.whatsapp_name || lead.name || 'Nao informado'}
Interesse: ${lead.visa_interest || 'Nao especificado'}
Score: ${lead.lead_score || 0}
Status: ${lead.lead_status || 'cold'}

HISTORICO DA CONVERSA:
${messagesText}

Responda APENAS em JSON valido com esta estrutura:
{
    "currentSituation": "Resumo em 1-2 frases da situacao atual",
    "history": [
        {"time": "HH:MM", "event": "Descricao curta do evento"}
    ],
    "nextSteps": ["Proximo passo 1", "Proximo passo 2"],
    "pendingQuestions": ["Pergunta pendente se houver"],
    "sentiment": "positive|neutral|negative",
    "priority": "high|medium|low"
}`;

        const response = await fetch(GEMINI_URL + '?key=' + GEMINI_API_KEY, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.3,
                    responseMimeType: "application/json",
                    maxOutputTokens: 1024
                }
            })
        });

        if (!response.ok) {
            throw new Error(`Gemini error: ${response.status}`);
        }

        const data = await response.json();
        const responseText = data.candidates?.[0]?.content?.parts?.[0]?.text || '';

        // Extrair e limpar JSON da resposta (v12.7)
        const parsed = cleanAndParseJSON(responseText);
        if (parsed) return parsed;

        throw new Error("JSON nao encontrado ou invalido na resposta");

    } catch (error) {
        console.error('[LEAD-MONITOR] Erro ao gerar resumo:', error.message);
        return {
            currentSituation: 'Erro ao gerar resumo',
            history: [],
            nextSteps: [],
            pendingQuestions: []
        };
    }
}

/**
 * Formatar mensagem de alerta
 */
function formatAlertMessage(lead, reason, summary) {
    const urgentEmoji = lead.is_urgent ? '🚨' : '⚠️';

    return `${urgentEmoji} LEAD PRECISA ATENCAO

Telefone: ${lead.phone}
Nome: ${lead.whatsapp_name || lead.client_name || 'Nao informado'}
Interesse: ${lead.visa_interest || 'Nao especificado'}
Score: ${lead.lead_score || 0}
Tempo sem resposta: ${lead.minutes_since_last_message || 0} minutos

Motivo: ${reason}

Ultima mensagem: "${(lead.last_message || '').substring(0, 100)}..."

Situacao: ${summary.currentSituation}

Proximos passos sugeridos:
${(summary.nextSteps || []).map((s, i) => `${i + 1}. ${s}`).join('\n')}

${summary.pendingQuestions?.length ? '\nDuvidas pendentes:\n' + summary.pendingQuestions.join('\n') : ''}

UI: ${process.env.ORG_WEBSITE || "https://casehub.app"}/whatsapp/ui`;
}

/**
 * Enviar alerta via Google Chat
 */
async function sendGoogleChatAlert(message) {
    if (!NOTIFICATION_CONFIG.googleChatWebhook) {
        console.log('[LEAD-MONITOR] Google Chat webhook nao configurado');
        return;
    }

    try {
        const response = await fetch(NOTIFICATION_CONFIG.googleChatWebhook, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: message })
        });

        if (response.ok) {
            console.log('[LEAD-MONITOR] Alerta Google Chat enviado');
        } else {
            console.error('[LEAD-MONITOR] Erro Google Chat:', response.status);
        }
    } catch (error) {
        console.error('[LEAD-MONITOR] Erro ao enviar Google Chat:', error.message);
    }
}

/**
 * Enviar alerta via Email
 */
async function sendEmailAlert(lead, reason, summary) {
    if (!emailService || !NOTIFICATION_CONFIG.emailTo) {
        console.log('[LEAD-MONITOR] Email nao configurado');
        return;
    }

    try {
        const subject = `[CaseHub] Lead precisa atencao: ${lead.phone}`;
        const htmlContent = `
            <h2>${lead.is_urgent ? '🚨 URGENTE' : '⚠️'} Lead Precisa de Atencao</h2>

            <table style="border-collapse: collapse; margin: 20px 0;">
                <tr><td style="padding: 5px; font-weight: bold;">Telefone:</td><td>${lead.phone}</td></tr>
                <tr><td style="padding: 5px; font-weight: bold;">Nome:</td><td>${lead.whatsapp_name || lead.client_name || 'Nao informado'}</td></tr>
                <tr><td style="padding: 5px; font-weight: bold;">Interesse:</td><td>${lead.visa_interest || 'Nao especificado'}</td></tr>
                <tr><td style="padding: 5px; font-weight: bold;">Score:</td><td>${lead.lead_score || 0}</td></tr>
                <tr><td style="padding: 5px; font-weight: bold;">Tempo sem resposta:</td><td>${lead.minutes_since_last_message || 0} minutos</td></tr>
            </table>

            <p><strong>Motivo:</strong> ${reason}</p>

            <p><strong>Ultima mensagem:</strong><br>
            "${(lead.last_message || '').substring(0, 200)}..."</p>

            <h3>Resumo da Conversa</h3>
            <p>${summary.currentSituation}</p>

            <h4>Proximos passos:</h4>
            <ul>
                ${(summary.nextSteps || []).map(s => `<li>${s}</li>`).join('')}
            </ul>

            ${summary.pendingQuestions?.length ? `
                <h4>Duvidas pendentes:</h4>
                <ul>
                    ${summary.pendingQuestions.map(q => `<li>${q}</li>`).join('')}
                </ul>
            ` : ''}

            <p><a href="${process.env.ORG_WEBSITE || "https://casehub.app"}/whatsapp/ui" style="background: #25D366; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Abrir WhatsApp UI</a></p>
        `;

        await emailService.sendEmail({
            to: NOTIFICATION_CONFIG.emailTo,
            subject: subject,
            html: htmlContent
        });

        console.log('[LEAD-MONITOR] Alerta email enviado');
    } catch (error) {
        console.error('[LEAD-MONITOR] Erro ao enviar email:', error.message);
    }
}

/**
 * Obter resumo de uma lead especifica (para API)
 */
async function getLeadSummary(phone) {
    if (!db) {
        return { error: 'Database nao disponivel' };
    }

    try {
        // Buscar dados da lead
        const leadData = await db.query(`
            SELECT
                phone,
                name as client_name,
                whatsapp_name,
                email,
                visa_interest,
                lead_status,
                lead_score,
                conversation_state,
                is_urgent,
                language,
                last_interaction,
                needs_human_review,
                human_review_reason
            FROM leads
            WHERE phone = ?
        `, [phone]);

        if (!leadData || leadData.length === 0) {
            return { error: 'Lead nao encontrada' };
        }

        const lead = leadData[0];

        // Buscar ultima mensagem
        const lastMsg = await db.query(`
            SELECT role, content, created_at
            FROM conversations
            WHERE phone = ?
            ORDER BY created_at DESC
            LIMIT 1
        `, [phone]);

        // Gerar resumo via Gemini
        const summary = await generateConversationSummary(phone);

        // Calcular tempo desde ultima atividade
        const lastActivity = lastMsg[0]?.created_at || lead.last_interaction;
        const minutesSince = lastActivity
            ? Math.floor((Date.now() - new Date(lastActivity).getTime()) / 60000)
            : null;

        // Determinar status
        let status = 'unknown';
        if (lastMsg[0]?.role === 'assistant') {
            status = 'responded';
        } else if (lastMsg[0]?.role === 'user') {
            status = minutesSince > 30 ? 'needs_attention' : 'pending';
        }

        return {
            phone: lead.phone,
            summary: {
                currentSituation: summary.currentSituation,
                history: summary.history || [],
                nextSteps: summary.nextSteps || [],
                pendingQuestions: summary.pendingQuestions || [],
                sentiment: summary.sentiment || 'neutral',
                priority: summary.priority || 'medium',
                status: status,
                lastActivity: lastActivity,
                minutesSinceLastActivity: minutesSince
            },
            lead: {
                name: lead.whatsapp_name || lead.client_name,
                score: lead.lead_score,
                status: lead.lead_status,
                interest: lead.visa_interest,
                urgent: lead.is_urgent,
                needsHumanReview: lead.needs_human_review,
                humanReviewReason: lead.human_review_reason
            },
            lastMessage: lastMsg[0] ? {
                role: lastMsg[0].role,
                content: lastMsg[0].content,
                time: lastMsg[0].created_at
            } : null
        };

    } catch (error) {
        console.error('[LEAD-MONITOR] Erro ao buscar resumo:', error.message);
        return { error: error.message };
    }
}

/**
 * Obter status do monitor (para API)
 */
function getMonitorStatus() {
    return {
        isRunning: monitorState.isRunning,
        lastCheck: monitorState.lastCheck,
        leadsNeedingAttention: monitorState.leadsNeedingAttention.length,
        config: {
            checkIntervalMinutes: NOTIFICATION_CONFIG.checkIntervalMinutes,
            alertThresholdMinutes: NOTIFICATION_CONFIG.alertThresholdMinutes,
            googleChatConfigured: !!NOTIFICATION_CONFIG.googleChatWebhook,
            emailConfigured: !!NOTIFICATION_CONFIG.emailTo
        }
    };
}

/**
 * Forcar verificacao manual (para API)
 */
async function forceCheck() {
    await checkLeadsNeedingAttention();
    return {
        success: true,
        leadsChecked: monitorState.leadsNeedingAttention.length,
        lastCheck: monitorState.lastCheck
    };
}

module.exports = {
    initialize,
    startMonitorScheduler,
    stopMonitorScheduler,
    checkLeadsNeedingAttention,
    generateConversationSummary,
    getLeadSummary,
    getMonitorStatus,
    forceCheck,
    flagForHumanReview,
    clearHumanReviewFlag,
    notifyHumanNeeded
};
