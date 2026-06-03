/**
 * Intake Form Integration - Integracao com servidor principal
 * CaseHub
 * v1.1 - Handlers, follow-ups, campanha e restart de formulario
 */

const db = require('./database');
const intakeFlow = require('./intake-form-flow');
const scoring = require('./intake-scoring');
const geminiAnalyzer = require('./intake-gemini-analyzer');
const telegram = require('./telegram');
const email = require('./email');
const moskit = require('./moskit');
const crmSync = require('./crm-sync');
const botConfig = require('./bot-config');
const notificationService = require('./services/notification-service');

// Configuracao
const JOSH_HYDE_PHONE = '447884384443';
const CAMPAIGN_DELAY_MINUTES = 6; // 10 por hora
const FOLLOWUP_INTERVALS = {
  FIRST: 4,   // 4 horas
  SECOND: 24, // 24 horas
  THIRD: 48   // 48 horas
};

/**
 * Verificar se lead esta no fluxo de intake form (ativo)
 */
function isInIntakeFlow(lead) {
  const state = lead?.intake_form_state;
  return state === intakeFlow.INTAKE_STATES.INVITED ||
         state === intakeFlow.INTAKE_STATES.IN_PROGRESS;
}

/**
 * v1.1: Verificar se lead pode reiniciar o formulario (expired ou completed)
 */
function canRestartIntake(lead) {
  const state = lead?.intake_form_state;
  return state === intakeFlow.INTAKE_STATES.EXPIRED ||
         state === intakeFlow.INTAKE_STATES.COMPLETED;
}

/**
 * Processar mensagem se lead estiver no fluxo de intake
 * Retorna null se nao estiver no fluxo (para continuar com fluxo normal)
 * @param {string} phone - Numero do telefone
 * @param {string} messageBody - Texto da mensagem
 * @param {object} lead - Dados do lead
 * @param {object} whatsappClient - Cliente WhatsApp
 * @param {object} mediaInfo - Info de arquivo de midia (opcional)
 */
async function processIntakeMessage(phone, messageBody, lead, whatsappClient, mediaInfo = null) {
  // v1.1: Verificar se esta no fluxo ativo OU pode reiniciar
  if (!isInIntakeFlow(lead) && !canRestartIntake(lead)) {
    return null; // Nao esta no fluxo de intake e nao pode reiniciar
  }

  console.log('[INTAKE] Processando mensagem de lead no fluxo:', phone);
  if (mediaInfo && mediaInfo.success) {
    console.log('[INTAKE] Arquivo anexado:', mediaInfo.filename);
  }

  const result = await intakeFlow.processIntakeMessage(phone, messageBody, lead, mediaInfo);

  if (!result) {
    return null;
  }

  // Se completou o formulario, fazer analise Gemini e enviar notificacoes
  if (result.newState === intakeFlow.INTAKE_STATES.COMPLETED) {
    console.log('[INTAKE] Formulario completado! Score:', result.finalScore);

    // Analisar respostas com Gemini em background
    geminiAnalyzer.analyzeAllResponses(phone)
      .then(async () => {
        await geminiAnalyzer.performFinalAnalysis(phone);
        await scoring.recalculateAfterGeminiAnalysis(phone);
        console.log('[INTAKE] Analise Gemini concluida:', phone);
      })
      .catch(e => console.error('[INTAKE] Erro analise Gemini:', e.message));

    // Obter dados para notificacoes e Moskit
    const leadData = await db.getLead(phone);
    const scoringReport = await scoring.generateScoringReport(phone);

    // Atualizar Moskit com resultados do intake
    moskit.upsertMoskitContactWithIntake(leadData, scoringReport)
      .then(res => {
        if (res.success) {
          console.log('[INTAKE-MOSKIT] Contato atualizado com sucesso');
        }
      })
      .catch(e => console.error('[INTAKE-MOSKIT] Erro:', e.message));

    // v11.2: Update CRM with intake results
    crmSync.updateCRM(phone, {
      name: leadData.client_name || leadData.whatsapp_name || '',
      lead_score: result.finalScore || 0,
      intake_form_final_score: result.finalScore || 0,
      intake_form_primary_pathway: result.primaryPathway || '',
      visa_interest: leadData.visa_interest || '',
      notes: scoringReport?.summary || ''
    }).catch(e => console.error('[CRM-SYNC] Erro intake:', e.message));

    // Notificar equipe se qualificado
    if (result.isQualified) {
      telegram.notifyQualifiedIntake({
        phone: phone,
        client_name: leadData.client_name || leadData.whatsapp_name,
        score: result.finalScore,
        pathway: result.primaryPathway,
        summary: scoringReport?.summary || ''
      }).catch(e => console.error('[INTAKE-TELEGRAM] Erro:', e.message));

      email.sendQualifiedIntakeEmail({
        phone: phone,
        client_name: leadData.client_name || leadData.whatsapp_name,
        email: leadData.email,
        score: result.finalScore,
        pathway: result.primaryPathway,
        summary: scoringReport?.summary || ''
      }).catch(e => console.error('[INTAKE-EMAIL] Erro:', e.message));
    }
  }

  // Enviar resposta via notification-service (guard + dedup enforced)
  if (result.response) {
    try {
      await notificationService.send(phone, result.response, {
        source: 'intake-form',
        skipGuard: true,  // intake is in-progress, always respond
        saveToDB: true
      });
    } catch (e) {
      console.error('[INTAKE] Erro ao enviar mensagem:', e.message);
    }
  }

  return result;
}

/**
 * Enviar convite de intake form para um lead
 */
async function sendIntakeInvite(phone, lead, whatsappClient) {
  const language = lead.language || 'en';
  const name = lead.client_name || lead.whatsapp_name || '';

  const message = intakeFlow.getInviteMessage(name, language);

  try {
    const sendResult = await notificationService.send(phone, message, {
      source: 'intake-invite',
      saveToDB: true
    });
    if (sendResult.sent) {
      await db.updateLead(phone, {
        intake_form_state: intakeFlow.INTAKE_STATES.INVITED,
        intake_form_invite_sent_at: new Date()
      });
      console.log('[INTAKE] Convite enviado para:', phone);
      return true;
    }
    console.log('[INTAKE] Convite bloqueado para:', phone, sendResult.reason);
    return false;
  } catch (e) {
    console.error('[INTAKE] Erro ao enviar convite:', e.message);
    return false;
  }
}

/**
 * Verificar e enviar follow-ups do intake form
 */
async function checkIntakeFollowups(whatsappClient) {
  try {
    // v5.0: Não enviar follow-ups se bot em HARD OFF
    if (botConfig.isHardOff()) {
      console.log("[INTAKE-FOLLOWUP] Bot em HARD OFF, follow-ups cancelados.");
      return;
    }

    const leadsInProgress = await db.getLeadsWithIntakeInProgress();
    console.log('[INTAKE-FOLLOWUP] Verificando', leadsInProgress.length, 'leads em progresso...');

    for (const lead of leadsInProgress) {
      const followupCount = lead.intake_form_followup_count || 0;
      const lastFollowup = lead.intake_form_last_followup_at || lead.intake_form_started_at;
      const language = lead.language || 'en';
      const name = lead.client_name || lead.whatsapp_name || '';
      const currentQuestion = lead.intake_form_current_question || 1;

      if (!lastFollowup) continue;

      const hoursSinceLastAction = (Date.now() - new Date(lastFollowup).getTime()) / (1000 * 60 * 60);

      let shouldSend = false;
      let followupType = null;

      // Determinar qual follow-up enviar
      if (followupCount === 0 && hoursSinceLastAction >= FOLLOWUP_INTERVALS.FIRST) {
        shouldSend = true;
        followupType = '4h';
      } else if (followupCount === 1 && hoursSinceLastAction >= (FOLLOWUP_INTERVALS.SECOND - FOLLOWUP_INTERVALS.FIRST)) {
        shouldSend = true;
        followupType = '24h';
      } else if (followupCount === 2 && hoursSinceLastAction >= (FOLLOWUP_INTERVALS.THIRD - FOLLOWUP_INTERVALS.SECOND)) {
        shouldSend = true;
        followupType = '48h';

        // Apos 48h, calcular score parcial e marcar como expirado
        const partialData = await scoring.calculatePartialScore(lead.phone);
        await db.updateLead(lead.phone, {
          intake_form_state: intakeFlow.INTAKE_STATES.EXPIRED,
          intake_form_final_score: partialData.partialScore,
          lead_score: partialData.partialScore,
          lead_status: scoring.determineLeadStatus(partialData.partialScore)
        });
      }

      if (shouldSend) {
        const message = intakeFlow.getFollowupMessage(followupType, name, currentQuestion, language);

        if (message) {
          try {
            const sendResult = await notificationService.send(lead.phone, message, {
              source: 'intake-followup',
              saveToDB: true
            });
            if (sendResult.sent) {
              await db.updateLead(lead.phone, {
                intake_form_followup_count: followupCount + 1,
                intake_form_last_followup_at: new Date()
              });
              console.log('[INTAKE-FOLLOWUP]', followupType, 'enviado para:', lead.phone);
            } else {
              console.log('[INTAKE-FOLLOWUP] Bloqueado para:', lead.phone, sendResult.reason);
            }
          } catch (e) {
            console.error('[INTAKE-FOLLOWUP] Erro:', e.message);
          }
        }
      }
    }
  } catch (error) {
    console.error('[INTAKE-FOLLOWUP] Erro geral:', error.message);
  }
}

/**
 * Endpoint: Enviar campanha de intake form
 * POST /api/send-intake-campaign
 * Body: { limit: 10, dry_run: false }
 */
async function sendIntakeCampaign(limit = 10, dryRun = false, whatsappClient) {
  const results = {
    success: [],
    failed: [],
    skipped: [],
    dryRun: dryRun
  };

  try {
    // Buscar leads elegiveis (excluindo Josh Hyde)
    const leads = await db.getLeadsForIntakeCampaign(limit, JOSH_HYDE_PHONE);

    console.log('[INTAKE-CAMPAIGN]', dryRun ? 'DRY RUN -' : '', 'Processando', leads.length, 'leads...');

    for (let i = 0; i < leads.length; i++) {
      const lead = leads[i];

      // Verificar exclusoes
      if (lead.phone === JOSH_HYDE_PHONE || lead.phone.includes(JOSH_HYDE_PHONE)) {
        results.skipped.push({ phone: lead.phone, reason: 'Josh Hyde excluido' });
        continue;
      }

      // Verificar se ja esta em algum fluxo
      if (isInIntakeFlow(lead)) {
        results.skipped.push({ phone: lead.phone, reason: 'Ja em fluxo de intake' });
        continue;
      }

      // Verificar se ja completou
      if (lead.intake_form_state === intakeFlow.INTAKE_STATES.COMPLETED) {
        results.skipped.push({ phone: lead.phone, reason: 'Ja completou intake' });
        continue;
      }

      if (dryRun) {
        results.success.push({
          phone: lead.phone,
          name: lead.client_name || lead.whatsapp_name,
          score: lead.lead_score,
          note: 'Dry run - nao enviado'
        });
        continue;
      }

      // Enviar convite
      const sent = await sendIntakeInvite(lead.phone, lead, whatsappClient);

      if (sent) {
        results.success.push({
          phone: lead.phone,
          name: lead.client_name || lead.whatsapp_name,
          score: lead.lead_score
        });
      } else {
        results.failed.push({
          phone: lead.phone,
          reason: 'Erro ao enviar'
        });
      }

      // Delay entre envios (rate limiting)
      if (i < leads.length - 1 && !dryRun) {
        console.log('[INTAKE-CAMPAIGN] Aguardando', CAMPAIGN_DELAY_MINUTES, 'minutos...');
        await new Promise(resolve => setTimeout(resolve, CAMPAIGN_DELAY_MINUTES * 60 * 1000));
      }
    }

    return {
      success: true,
      summary: {
        total: leads.length,
        sent: results.success.length,
        failed: results.failed.length,
        skipped: results.skipped.length
      },
      details: results,
      estimatedTime: dryRun ? 0 : (leads.length - 1) * CAMPAIGN_DELAY_MINUTES + ' minutos'
    };
  } catch (error) {
    console.error('[INTAKE-CAMPAIGN] Erro:', error.message);
    return {
      success: false,
      error: error.message
    };
  }
}

/**
 * Endpoint: Estatisticas do intake form
 */
async function getIntakeStats() {
  try {
    const stats = await db.getIntakeFormStats();
    return {
      success: true,
      stats: stats
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
}

/**
 * Endpoint: Popular perguntas no banco
 */
async function populateQuestions() {
  try {
    await intakeFlow.populateQuestionsInDatabase();
    return {
      success: true,
      message: '46 perguntas populadas com sucesso!'
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
}

/**
 * Endpoint: Reiniciar intake form de um lead
 */
async function resetIntakeForm(phone) {
  try {
    const result = await db.clearIntakeFormResponses(phone);
    return {
      success: result,
      message: result ? 'Intake form resetado' : 'Erro ao resetar'
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
}

/**
 * Configurar rotas Express
 */
function setupRoutes(app, whatsappClient) {
  // Endpoint: Enviar campanha de intake
  app.post('/api/intake/campaign', async (req, res) => {
    try {
      const { limit = 10, dry_run = true } = req.body;
      const result = await sendIntakeCampaign(parseInt(limit), dry_run, whatsappClient);
      res.json(result);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Endpoint: Estatisticas do intake form
  app.get('/api/intake/stats', async (req, res) => {
    try {
      const result = await getIntakeStats();
      res.json(result);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Endpoint: Popular perguntas
  app.post('/api/intake/populate-questions', async (req, res) => {
    try {
      const result = await populateQuestions();
      res.json(result);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Endpoint: Resetar intake de um lead
  app.post('/api/intake/reset/:phone', async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, '');
      const result = await resetIntakeForm(phone);
      res.json(result);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Endpoint: Ver detalhes do intake de um lead
  app.get('/api/intake/lead/:phone', async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, '');
      const lead = await db.getLead(phone);

      if (!lead) {
        return res.status(404).json({ error: 'Lead nao encontrado' });
      }

      const responses = await db.getIntakeFormResponses(phone);
      const pathwayScores = await db.getPathwayScores(phone);
      const scoringReport = await scoring.generateScoringReport(phone);

      res.json({
        phone: phone,
        intake_state: lead.intake_form_state,
        current_question: lead.intake_form_current_question,
        final_score: lead.intake_form_final_score,
        primary_pathway: lead.intake_form_primary_pathway,
        eligible_for_free_call: lead.eligible_for_free_call,
        responses_count: responses.length,
        responses: responses,
        pathway_scores: pathwayScores,
        scoring_report: scoringReport
      });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Endpoint: Enviar convite manual para um lead
  app.post('/api/intake/invite/:phone', async (req, res) => {
    try {
      const phone = req.params.phone.replace(/\D/g, '');
      const lead = await db.getLead(phone);

      if (!lead) {
        return res.status(404).json({ error: 'Lead nao encontrado' });
      }

      const result = await sendIntakeInvite(phone, lead, whatsappClient);
      res.json({ success: result });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Endpoint: Forcar check de follow-ups
  app.post('/api/intake/check-followups', async (req, res) => {
    try {
      await checkIntakeFollowups(whatsappClient);
      res.json({ success: true, message: 'Follow-ups verificados' });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  console.log('[INTAKE] Rotas configuradas:');
  console.log('  POST /api/intake/campaign');
  console.log('  GET  /api/intake/stats');
  console.log('  POST /api/intake/populate-questions');
  console.log('  POST /api/intake/reset/:phone');
  console.log('  GET  /api/intake/lead/:phone');
  console.log('  POST /api/intake/invite/:phone');
  console.log('  POST /api/intake/check-followups');
}

/**
 * Iniciar intervalos de follow-up
 */
function startFollowupIntervals(whatsappClient) {
  // Check de follow-ups a cada 30 minutos
  setInterval(() => checkIntakeFollowups(whatsappClient), 30 * 60 * 1000);

  // Primeiro check apos 3 minutos do inicio
  setTimeout(() => checkIntakeFollowups(whatsappClient), 3 * 60 * 1000);

  console.log('[INTAKE] Follow-ups configurados (4h/24h/48h)');
}

module.exports = {
  isInIntakeFlow,
  processIntakeMessage,
  sendIntakeInvite,
  checkIntakeFollowups,
  sendIntakeCampaign,
  getIntakeStats,
  populateQuestions,
  resetIntakeForm,
  setupRoutes,
  startFollowupIntervals,
  JOSH_HYDE_PHONE
};
