/**
 * Intake Scoring System - Calculo de pontuacao por categoria
 * CaseHub
 * v1.0 - Sistema de scoring baseado em respostas do intake form
 */

const db = require('./database');
const { CATEGORIES, PATHWAYS, INTAKE_QUESTIONS } = require('./intake-form-flow');

// Pesos por categoria (multiplicadores)
const CATEGORY_WEIGHTS = {
  [CATEGORIES.BASIC_INFO]: 1.0,        // Informacoes basicas
  [CATEGORIES.ENTRY_HISTORY]: 1.2,     // Historico de entrada (importante para elegibilidade)
  [CATEGORIES.PROBLEMS_GOALS]: 1.5,    // Problemas e objetivos (Gemini analisa)
  [CATEGORIES.LEGAL_HISTORY]: 1.3,     // Historico legal (pode ser negativo)
  [CATEGORIES.FAMILY_CONNECTIONS]: 1.5, // Conexoes familiares (alto valor para family-based)
  [CATEGORIES.WORK_AUTH]: 1.0,         // Autorizacao de trabalho
  [CATEGORIES.CRIMINAL_HISTORY]: 1.5,  // Historico criminal (pode penalizar muito)
  [CATEGORIES.ASYLUM]: 2.0,            // Asilo (alto peso para casos humanitarios)
  [CATEGORIES.VAWA]: 2.0,              // VAWA (alto peso)
  [CATEGORIES.U_VISA]: 2.0,            // U-Visa (alto peso)
  [CATEGORIES.T_VISA]: 2.0,            // T-Visa (alto peso)
  [CATEGORIES.SIJS]: 2.0,              // SIJS (alto peso)
  [CATEGORIES.EMPLOYMENT_BASED]: 1.3   // Employment-based
};

// Thresholds de qualificacao
const THRESHOLDS = {
  HOT: 90,
  QUALIFIED: 70,
  WARM: 50,
  COLD: 0
};

// Pontuacao maxima teorica por pathway
const MAX_PATHWAY_SCORES = {
  [PATHWAYS.FAMILY_BASED]: 40,
  [PATHWAYS.EMPLOYMENT_BASED]: 44,
  [PATHWAYS.HUMANITARIAN_ASYLUM]: 20,
  [PATHWAYS.HUMANITARIAN_VAWA]: 25,
  [PATHWAYS.HUMANITARIAN_U_VISA]: 25,
  [PATHWAYS.HUMANITARIAN_T_VISA]: 30,
  [PATHWAYS.HUMANITARIAN_SIJS]: 20,
  [PATHWAYS.INVESTOR]: 0, // Nao avaliado diretamente no form
  [PATHWAYS.UNKNOWN]: 0
};

/**
 * Calcular score total do intake form com pesos por categoria
 * v2.0 - Normaliza por pathway relevante, nao penaliza por categorias nao aplicaveis
 */
async function calculateTotalScore(phone) {
  try {
    const responses = await db.getIntakeFormResponses(phone);
    if (!responses || responses.length === 0) {
      return { totalScore: 0, breakdown: {} };
    }

    let totalScore = 0;
    const breakdown = {};

    // Agrupar respostas por categoria
    for (const response of responses) {
      const category = response.question_category;
      if (!breakdown[category]) {
        breakdown[category] = {
          rawPoints: 0,
          weight: CATEGORY_WEIGHTS[category] || 1.0,
          weightedPoints: 0,
          questionCount: 0
        };
      }

      breakdown[category].rawPoints += response.points_earned || 0;
      breakdown[category].questionCount++;
    }

    // Calcular pontos ponderados
    for (const category of Object.keys(breakdown)) {
      breakdown[category].weightedPoints = Math.round(
        breakdown[category].rawPoints * breakdown[category].weight
      );
      totalScore += breakdown[category].weightedPoints;
    }

    // v2.0: Calcular max apenas para categorias RELEVANTES (com respostas)
    // Nao penalizar por categorias humanitarias que nao se aplicam
    const relevantMaxScore = calculateRelevantMaxScore(breakdown);

    // Adicionar bonus de baseline para categorias basicas respondidas
    const baselineCategories = ['basic_info', 'entry_history', 'legal_history', 'work_authorization'];
    let baselineBonus = 0;
    for (const cat of baselineCategories) {
      if (breakdown[cat] && breakdown[cat].rawPoints >= 0) {
        baselineBonus += 5; // Bonus por responder categorias basicas
      }
    }

    // Normalizar com formula mais justa
    // Score = (pontos_obtidos + baseline_bonus) / max_relevante * 100
    const adjustedScore = totalScore + baselineBonus;
    const normalizedScore = Math.min(100, Math.round((adjustedScore / relevantMaxScore) * 100));

    return {
      totalScore: normalizedScore,
      rawScore: totalScore,
      adjustedScore: adjustedScore,
      maxPossible: relevantMaxScore,
      breakdown: breakdown
    };
  } catch (error) {
    console.error('[SCORING] Erro ao calcular score:', error.message);
    return { totalScore: 0, breakdown: {} };
  }
}

/**
 * Calcular max score apenas para categorias que o lead respondeu
 * Nao inclui categorias humanitarias se o lead respondeu "nao" a todas
 */
function calculateRelevantMaxScore(breakdown) {
  let maxScore = 0;

  // Categorias humanitarias que so contam se tiverem pontos positivos
  const humanitarianCategories = ['asylum', 'vawa', 'u_visa', 't_visa', 'sijs'];

  for (const question of INTAKE_QUESTIONS) {
    const category = question.category;
    const weight = CATEGORY_WEIGHTS[category] || 1.0;
    const maxPoints = question.max_points || 0;

    // Se e categoria humanitaria, so incluir se teve pontos positivos
    if (humanitarianCategories.includes(category)) {
      if (breakdown[category] && breakdown[category].rawPoints > 0) {
        maxScore += maxPoints * weight;
      }
      // Se nao teve pontos, nao adiciona ao max (nao penaliza)
    } else {
      // Categorias normais sempre contam
      maxScore += maxPoints * weight;
    }
  }

  return maxScore || 100; // Minimo 100 para evitar divisao problematica
}

/**
 * Calcular pontuacao maxima possivel
 */
function calculateMaxPossibleScore() {
  let maxScore = 0;

  for (const question of INTAKE_QUESTIONS) {
    const weight = CATEGORY_WEIGHTS[question.category] || 1.0;
    const maxPoints = question.max_points || 0;
    maxScore += maxPoints * weight;
  }

  return maxScore || 1; // Evitar divisao por zero
}

/**
 * Calcular scores por pathway
 */
async function calculatePathwayScores(phone) {
  try {
    const responses = await db.getIntakeFormResponses(phone);
    if (!responses || responses.length === 0) {
      return {};
    }

    const pathwayScores = {};

    // Inicializar pathways
    for (const pathway of Object.values(PATHWAYS)) {
      pathwayScores[pathway] = {
        score: 0,
        maxScore: MAX_PATHWAY_SCORES[pathway] || 0,
        confidence: 0,
        relevantResponses: []
      };
    }

    // Processar respostas
    for (const response of responses) {
      const question = INTAKE_QUESTIONS.find(q => q.id === response.question_id);
      if (!question || !question.pathway_impact) continue;

      const pathway = question.pathway_impact;
      const points = response.points_earned || 0;

      pathwayScores[pathway].score += points;
      pathwayScores[pathway].relevantResponses.push({
        questionId: response.question_id,
        response: response.response_text,
        points: points
      });
    }

    // Calcular confianca (0-1) para cada pathway
    for (const pathway of Object.keys(pathwayScores)) {
      const data = pathwayScores[pathway];
      if (data.maxScore > 0) {
        data.confidence = Math.min(1, data.score / data.maxScore);
      }
    }

    // Salvar scores no banco
    for (const [pathway, data] of Object.entries(pathwayScores)) {
      if (data.score > 0) {
        await db.savePathwayScore(phone, pathway, data.score, data.confidence);
      }
    }

    return pathwayScores;
  } catch (error) {
    console.error('[SCORING] Erro ao calcular pathway scores:', error.message);
    return {};
  }
}

/**
 * Determinar pathway primario
 */
async function determinePrimaryPathway(phone) {
  const pathwayScores = await calculatePathwayScores(phone);

  let primaryPathway = PATHWAYS.UNKNOWN;
  let highestScore = 0;
  let highestConfidence = 0;

  for (const [pathway, data] of Object.entries(pathwayScores)) {
    if (pathway === PATHWAYS.UNKNOWN) continue;

    // Priorizar score, depois confianca
    if (data.score > highestScore ||
        (data.score === highestScore && data.confidence > highestConfidence)) {
      highestScore = data.score;
      highestConfidence = data.confidence;
      primaryPathway = pathway;
    }
  }

  return {
    pathway: primaryPathway,
    score: highestScore,
    confidence: highestConfidence
  };
}

/**
 * Determinar status do lead baseado no score
 */
function determineLeadStatus(score) {
  if (score >= THRESHOLDS.HOT) return 'hot';
  if (score >= THRESHOLDS.QUALIFIED) return 'qualified';
  if (score >= THRESHOLDS.WARM) return 'warm';
  return 'cold';
}

/**
 * Verificar se lead e qualificado para consulta gratuita
 */
function isQualifiedForFreeCall(score) {
  return score >= THRESHOLDS.QUALIFIED;
}

/**
 * Gerar resumo de scoring para o Moskit
 */
async function generateScoringReport(phone) {
  try {
    const lead = await db.getLead(phone);
    if (!lead) return null;

    const responses = await db.getIntakeFormResponses(phone);
    const totalScoreData = await calculateTotalScore(phone);
    const pathwayScores = await calculatePathwayScores(phone);
    const primaryPathway = await determinePrimaryPathway(phone);

    // Identificar red flags
    const redFlags = [];
    const strengths = [];

    for (const response of responses) {
      const question = INTAKE_QUESTIONS.find(q => q.id === response.question_id);
      if (!question) continue;

      // Red flags (pontuacao negativa)
      if (response.points_earned < 0) {
        redFlags.push({
          question: question.question.en,
          response: response.response_text,
          impact: response.points_earned
        });
      }

      // Strengths (pontuacao alta)
      if (response.points_earned >= 5) {
        strengths.push({
          question: question.question.en,
          response: response.response_text,
          impact: response.points_earned
        });
      }
    }

    // Formatar codigo do pathway
    const pathwayCodes = {
      [PATHWAYS.FAMILY_BASED]: 'FAM',
      [PATHWAYS.EMPLOYMENT_BASED]: 'EMP',
      [PATHWAYS.HUMANITARIAN_ASYLUM]: 'ASY',
      [PATHWAYS.HUMANITARIAN_VAWA]: 'VAW',
      [PATHWAYS.HUMANITARIAN_U_VISA]: 'UVI',
      [PATHWAYS.HUMANITARIAN_T_VISA]: 'TVI',
      [PATHWAYS.HUMANITARIAN_SIJS]: 'SIJ',
      [PATHWAYS.INVESTOR]: 'INV',
      [PATHWAYS.UNKNOWN]: 'UNK'
    };

    const pathwayCode = pathwayCodes[primaryPathway.pathway] || 'UNK';
    const leadStatus = determineLeadStatus(totalScoreData.totalScore);
    const isQualified = isQualifiedForFreeCall(totalScoreData.totalScore);

    return {
      phone: phone,
      score: totalScoreData.totalScore,
      pathwayCode: pathwayCode,
      pathway: primaryPathway.pathway,
      pathwayConfidence: Math.round(primaryPathway.confidence * 100),
      leadStatus: leadStatus,
      isQualified: isQualified,
      redFlags: redFlags,
      strengths: strengths,
      breakdown: totalScoreData.breakdown,
      moskitNamePrefix: `[LEAD WPP ${totalScoreData.totalScore} ${pathwayCode}]`,
      summary: generateTextSummary(totalScoreData, primaryPathway, redFlags, strengths, isQualified)
    };
  } catch (error) {
    console.error('[SCORING] Erro ao gerar relatorio:', error.message);
    return null;
  }
}

/**
 * Gerar resumo em texto para notas do Moskit
 */
function generateTextSummary(scoreData, primaryPathway, redFlags, strengths, isQualified) {
  let summary = `=== INTAKE FORM SCORE: ${scoreData.totalScore}/100 ===\n`;
  summary += `Pathway: ${primaryPathway.pathway}\n`;
  summary += `Confianca: ${Math.round(primaryPathway.confidence * 100)}%\n`;
  summary += `Status: ${isQualified ? 'QUALIFICADO' : 'NAO QUALIFICADO'}\n\n`;

  if (strengths.length > 0) {
    summary += `--- PONTOS FORTES ---\n`;
    for (const s of strengths.slice(0, 5)) {
      summary += `+ ${s.response.substring(0, 50)}... (+${s.impact}pts)\n`;
    }
    summary += '\n';
  }

  if (redFlags.length > 0) {
    summary += `--- RED FLAGS ---\n`;
    for (const r of redFlags) {
      summary += `! ${r.response.substring(0, 50)}... (${r.impact}pts)\n`;
    }
    summary += '\n';
  }

  summary += `--- BREAKDOWN POR CATEGORIA ---\n`;
  for (const [category, data] of Object.entries(scoreData.breakdown)) {
    summary += `${category}: ${data.weightedPoints}pts (${data.questionCount} perguntas)\n`;
  }

  return summary;
}

/**
 * Recalcular score apos analise do Gemini
 */
async function recalculateAfterGeminiAnalysis(phone) {
  const responses = await db.getIntakeFormResponses(phone);

  // Identificar respostas que foram analisadas pelo Gemini
  const geminiResponses = responses.filter(r => r.gemini_analysis);

  for (const response of geminiResponses) {
    // Os pontos ja devem ter sido atualizados pela funcao de analise Gemini
    // Aqui so recalculamos os pathway scores
  }

  // Recalcular pathway scores e score total
  const totalScoreData = await calculateTotalScore(phone);
  const primaryPathway = await determinePrimaryPathway(phone);
  const isQualified = isQualifiedForFreeCall(totalScoreData.totalScore);

  // Atualizar lead
  await db.updateLead(phone, {
    intake_form_final_score: totalScoreData.totalScore,
    intake_form_primary_pathway: primaryPathway.pathway,
    eligible_for_free_call: isQualified,
    lead_score: totalScoreData.totalScore,
    lead_status: determineLeadStatus(totalScoreData.totalScore)
  });

  return {
    totalScore: totalScoreData.totalScore,
    primaryPathway: primaryPathway.pathway,
    isQualified: isQualified
  };
}

/**
 * Calcular score parcial (para leads que nao completaram)
 */
async function calculatePartialScore(phone) {
  const responses = await db.getIntakeFormResponses(phone);

  if (!responses || responses.length === 0) {
    return { partialScore: 0, completionPercentage: 0 };
  }

  const answeredQuestions = responses.filter(r => r.response_type !== 'skip');
  const totalQuestions = INTAKE_QUESTIONS.length;
  const completionPercentage = Math.round((answeredQuestions.length / totalQuestions) * 100);

  const scoreData = await calculateTotalScore(phone);

  return {
    partialScore: scoreData.totalScore,
    answeredQuestions: answeredQuestions.length,
    totalQuestions: totalQuestions,
    completionPercentage: completionPercentage
  };
}

module.exports = {
  CATEGORY_WEIGHTS,
  THRESHOLDS,
  MAX_PATHWAY_SCORES,
  calculateTotalScore,
  calculateMaxPossibleScore,
  calculatePathwayScores,
  determinePrimaryPathway,
  determineLeadStatus,
  isQualifiedForFreeCall,
  generateScoringReport,
  generateTextSummary,
  recalculateAfterGeminiAnalysis,
  calculatePartialScore
};
