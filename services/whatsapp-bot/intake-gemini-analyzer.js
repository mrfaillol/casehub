/**
 * Intake Form Gemini Analyzer - Analise de respostas via IA
 * CaseHub
 * v1.0 - Analise de texto livre do intake form
 */

const { GoogleGenerativeAI } = require("@google/generative-ai");
const db = require('./database');
const { CATEGORIES, PATHWAYS, INTAKE_QUESTIONS } = require('./intake-form-flow');
const scoring = require('./intake-scoring');

let genAI = null;
let model = null;

// Prompts de analise por tipo de pergunta
const ANALYSIS_PROMPTS = {
  // Q14: Problemas e objetivos
  problems_goals: `You are an immigration case analyst. Analyze this client's statement about their immigration problems and goals.

Client's statement: "{response}"

Evaluate:
1. CLARITY (1-10): How clear is their situation and goals?
2. VIABILITY (1-10): Based on US immigration law, how viable does this case appear?
3. URGENCY (1-3): 1=low, 2=medium, 3=high/emergency
4. SUGGESTED_PATHWAYS: List potential visa categories (family-based, employment-based, asylum, VAWA, U-visa, T-visa, SIJS)
5. RED_FLAGS: Any concerning elements that might complicate the case
6. STRENGTHS: Positive factors for their case

Respond in JSON format only:
{
  "clarity": <number>,
  "viability": <number>,
  "urgency": <number>,
  "suggested_pathways": ["pathway1", "pathway2"],
  "red_flags": ["flag1", "flag2"],
  "strengths": ["strength1", "strength2"],
  "points": <0-10 based on overall assessment>,
  "summary": "<brief summary in 2-3 sentences>"
}`,

  // Q27: Criminal history
  criminal_history: `You are an immigration case analyst. Analyze this client's statement about their criminal history.

Client's statement: "{response}"

Evaluate:
1. SEVERITY (1-10): 1=minor/none, 10=very serious crimes
2. IMMIGRATION_IMPACT: How might this affect immigration benefits?
3. BARS_TO_ADJUSTMENT: Any potential bars to adjustment of status?
4. WAIVERS_POSSIBLE: Are there potential waivers available?

For "No", "N/A", "None", or similar negative responses, return neutral assessment.

Respond in JSON format only:
{
  "severity": <number>,
  "immigration_impact": "none|minimal|moderate|significant|severe",
  "bars_possible": <boolean>,
  "waivers_available": <boolean>,
  "points": <-15 to 0, where 0 is no issues and -15 is severe>,
  "summary": "<brief assessment>"
}`,

  // Q28: Fear of return (Asylum)
  asylum_fear: `You are an immigration case analyst specializing in humanitarian cases. Analyze this client's statement about their fear of returning to their country.

Client's statement: "{response}"

Evaluate based on asylum eligibility criteria:
1. PERSECUTION_TYPE: What type of persecution is described (political, religious, nationality, social group, racial)?
2. CREDIBILITY (1-10): How credible and detailed is the fear described?
3. NEXUS (1-10): How strong is the connection to a protected ground?
4. COUNTRY_CONDITIONS: Is this consistent with known country conditions?
5. PAST_PERSECUTION: Is there evidence of past persecution?

For "No", "N/A", or negative responses, return low assessment.

Respond in JSON format only:
{
  "persecution_type": "<type or 'none'>",
  "credibility": <number>,
  "nexus": <number>,
  "past_persecution": <boolean>,
  "asylum_viable": <boolean>,
  "points": <0-20 based on asylum eligibility strength>,
  "summary": "<brief assessment>"
}`,

  // Q30: VAWA circumstances
  vawa_circumstances: `You are an immigration case analyst specializing in VAWA (Violence Against Women Act) cases. Analyze this client's statement about domestic abuse.

Client's statement: "{response}"

Evaluate based on VAWA eligibility:
1. ABUSE_TYPE: Physical, emotional, sexual, economic, or multiple
2. SEVERITY (1-10): Severity of abuse described
3. DOCUMENTATION_LIKELY: Could this be documented with evidence?
4. RELATIONSHIP: Relationship to abuser
5. GOOD_FAITH_MARRIAGE: Any indicators of good faith marriage?

Respond in JSON format only:
{
  "abuse_type": ["type1", "type2"],
  "severity": <number>,
  "documentation_possible": <boolean>,
  "vawa_viable": <boolean>,
  "points": <0-10 based on VAWA eligibility>,
  "summary": "<brief assessment>"
}`,

  // Q33: U-visa crime details
  u_visa_crime: `You are an immigration case analyst specializing in U-visa cases. Analyze this client's statement about the crime they were victim of.

Client's statement: "{response}"

Evaluate based on U-visa eligibility:
1. QUALIFYING_CRIME: Is this a U-visa qualifying crime (domestic violence, sexual assault, trafficking, kidnapping, extortion, torture, etc)?
2. SUBSTANTIAL_HARM (1-10): Level of physical or mental harm suffered
3. LAW_ENFORCEMENT_COOPERATION: Any indication of cooperation with police?
4. CERTIFICATION_LIKELY: Could law enforcement certify this?

Respond in JSON format only:
{
  "qualifying_crime": <boolean>,
  "crime_type": "<type>",
  "substantial_harm": <number>,
  "cooperation_indicated": <boolean>,
  "certification_likely": <boolean>,
  "points": <0-10 based on U-visa eligibility>,
  "summary": "<brief assessment>"
}`,

  // Q22: Marriage to citizen/LPR
  spouse_status: `Analyze this client's statement about their marital status and spouse's immigration status.

Client's statement: "{response}"

Extract:
1. IS_MARRIED: Are they married?
2. SPOUSE_STATUS: citizen, green_card, visa_holder, undocumented, or unknown
3. MARRIAGE_DURATION: If mentioned
4. FAMILY_BASED_VIABLE: Is family-based immigration viable?

Respond in JSON format only:
{
  "is_married": <boolean>,
  "spouse_status": "<status>",
  "family_based_viable": <boolean>,
  "points": <0-15 based on family-based eligibility>,
  "summary": "<brief assessment>"
}`,

  // Q23: Children born in US
  children_us: `Analyze this client's statement about their children.

Client's statement: "{response}"

Extract:
1. HAS_CHILDREN: Do they have children?
2. US_BORN_CHILDREN: Are any children US citizens (born in US)?
3. CHILDREN_COUNT: How many children?
4. CANCELLATION_ELIGIBLE: Might qualify for cancellation of removal?

Respond in JSON format only:
{
  "has_children": <boolean>,
  "us_born_children": <boolean>,
  "children_count": <number or "unknown">,
  "cancellation_possible": <boolean>,
  "points": <0-10 based on family ties>,
  "summary": "<brief assessment>"
}`,

  // Final analysis of all responses
  final_analysis: `You are a senior immigration attorney reviewing a complete intake form. Analyze all responses and provide a comprehensive assessment.

INTAKE FORM RESPONSES:
{responses}

CURRENT SCORES BY PATHWAY:
{pathway_scores}

Provide:
1. PRIMARY_PATHWAY: Most viable immigration pathway
2. SECONDARY_PATHWAY: Alternative pathway if primary fails
3. CASE_STRENGTH (1-10): Overall strength of the case
4. IMMEDIATE_ACTION: What should happen next?
5. RED_FLAGS: Critical issues to address
6. OPPORTUNITIES: Positive factors to leverage
7. ESTIMATED_TIMELINE: General timeline expectation
8. CONSULTATION_PRIORITY: "urgent", "high", "normal", "low"

Respond in JSON format only:
{
  "primary_pathway": "<pathway>",
  "secondary_pathway": "<pathway or null>",
  "case_strength": <number>,
  "immediate_action": "<recommendation>",
  "red_flags": ["flag1", "flag2"],
  "opportunities": ["opp1", "opp2"],
  "estimated_timeline": "<timeline>",
  "consultation_priority": "<priority>",
  "summary": "<comprehensive 3-4 sentence summary for attorney review>",
  "recommended_visa_types": ["visa1", "visa2"]
}`
};

/**
 * Inicializar Gemini para analise
 */
function init() {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey === "your_gemini_api_key_here") {
    console.warn("[GEMINI-ANALYZER] API key nao configurada");
    return false;
  }

  try {
    genAI = new GoogleGenerativeAI(apiKey);
    model = genAI.getGenerativeModel({
      model: "gemini-2.0-flash",
      generationConfig: {
        temperature: 0.3, // Mais deterministico para analise
        maxOutputTokens: 1000,
        topP: 0.8,
        topK: 20
      }
    });
    console.log("[GEMINI-ANALYZER] Inicializado com sucesso");
    return true;
  } catch (error) {
    console.error("[GEMINI-ANALYZER] Erro ao inicializar:", error.message);
    return false;
  }
}

/**
 * Analisar resposta individual com Gemini
 */
async function analyzeResponse(questionId, responseText) {
  if (!model) {
    console.warn("[GEMINI-ANALYZER] Modelo nao inicializado");
    return null;
  }

  // Determinar o tipo de prompt baseado na pergunta
  let promptTemplate = null;
  let promptKey = null;

  switch (questionId) {
    case 14: // Problems and goals
      promptTemplate = ANALYSIS_PROMPTS.problems_goals;
      promptKey = 'problems_goals';
      break;
    case 27: // Criminal history
      promptTemplate = ANALYSIS_PROMPTS.criminal_history;
      promptKey = 'criminal_history';
      break;
    case 28: // Fear of return (Asylum)
      promptTemplate = ANALYSIS_PROMPTS.asylum_fear;
      promptKey = 'asylum_fear';
      break;
    case 30: // VAWA circumstances
      promptTemplate = ANALYSIS_PROMPTS.vawa_circumstances;
      promptKey = 'vawa_circumstances';
      break;
    case 33: // U-visa crime details
      promptTemplate = ANALYSIS_PROMPTS.u_visa_crime;
      promptKey = 'u_visa_crime';
      break;
    case 22: // Spouse status
      promptTemplate = ANALYSIS_PROMPTS.spouse_status;
      promptKey = 'spouse_status';
      break;
    case 23: // Children
      promptTemplate = ANALYSIS_PROMPTS.children_us;
      promptKey = 'children_us';
      break;
    default:
      return null; // Pergunta nao requer analise Gemini
  }

  try {
    const prompt = promptTemplate.replace('{response}', responseText);
    const result = await model.generateContent(prompt);
    const text = result.response.text();

    // Extrair JSON da resposta
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.error("[GEMINI-ANALYZER] JSON nao encontrado na resposta");
      return null;
    }

    const analysis = JSON.parse(jsonMatch[0]);
    analysis.prompt_type = promptKey;
    analysis.analyzed_at = new Date().toISOString();

    return analysis;
  } catch (error) {
    console.error("[GEMINI-ANALYZER] Erro na analise:", error.message);
    return null;
  }
}

/**
 * Analisar todas as respostas que requerem Gemini
 */
async function analyzeAllResponses(phone) {
  if (!model) {
    init(); // Tentar inicializar
    if (!model) return null;
  }

  const responses = await db.getIntakeFormResponses(phone);
  const geminiQuestions = INTAKE_QUESTIONS.filter(q => q.gemini_analyze);

  const analyses = {};

  for (const question of geminiQuestions) {
    const response = responses.find(r => r.question_id === question.id);
    if (!response || response.response_type === 'skip') continue;

    // Pular se ja foi analisado
    if (response.gemini_analysis) {
      try {
        analyses[question.id] = JSON.parse(response.gemini_analysis);
        continue;
      } catch (e) {
        // Reanalisar se JSON invalido
      }
    }

    console.log(`[GEMINI-ANALYZER] Analisando Q${question.id}...`);
    const analysis = await analyzeResponse(question.id, response.response_text);

    if (analysis) {
      analyses[question.id] = analysis;

      // Salvar analise e atualizar pontos
      await db.updateIntakeResponseGeminiAnalysis(
        phone,
        question.id,
        JSON.stringify(analysis),
        analysis.points || 0
      );
    }

    // Delay para evitar rate limiting
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  return analyses;
}

/**
 * Realizar analise final de todas as respostas
 */
async function performFinalAnalysis(phone) {
  if (!model) {
    init();
    if (!model) return null;
  }

  // Obter todas as respostas
  const responses = await db.getIntakeFormResponses(phone);
  const pathwayScores = await db.getPathwayScores(phone);

  // Formatar respostas para o prompt
  let responsesText = '';
  for (const response of responses) {
    if (response.response_type === 'skip') continue;
    const question = INTAKE_QUESTIONS.find(q => q.id === response.question_id);
    if (!question) continue;

    responsesText += `Q${response.question_id} (${question.category}): ${response.response_text}\n`;
    if (response.gemini_analysis) {
      try {
        const analysis = JSON.parse(response.gemini_analysis);
        responsesText += `  -> Analysis: ${analysis.summary || 'N/A'}\n`;
      } catch (e) {}
    }
    responsesText += '\n';
  }

  // Formatar pathway scores
  let pathwayText = '';
  for (const ps of pathwayScores) {
    pathwayText += `${ps.pathway}: ${ps.score} (confidence: ${Math.round(ps.confidence * 100)}%)\n`;
  }

  try {
    const prompt = ANALYSIS_PROMPTS.final_analysis
      .replace('{responses}', responsesText)
      .replace('{pathway_scores}', pathwayText);

    const result = await model.generateContent(prompt);
    const text = result.response.text();

    // Extrair JSON
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.error("[GEMINI-ANALYZER] JSON nao encontrado na analise final");
      return null;
    }

    const finalAnalysis = JSON.parse(jsonMatch[0]);
    finalAnalysis.analyzed_at = new Date().toISOString();

    // Salvar no lead
    await db.updateLead(phone, {
      intake_form_gemini_summary: JSON.stringify(finalAnalysis)
    });

    return finalAnalysis;
  } catch (error) {
    console.error("[GEMINI-ANALYZER] Erro na analise final:", error.message);
    return null;
  }
}

/**
 * Gerar resumo para Moskit
 */
async function generateMoskitSummary(phone) {
  const lead = await db.getLead(phone);
  if (!lead) return null;

  // Analise final
  let finalAnalysis = null;
  if (lead.intake_form_gemini_summary) {
    try {
      finalAnalysis = JSON.parse(lead.intake_form_gemini_summary);
    } catch (e) {}
  }

  if (!finalAnalysis) {
    finalAnalysis = await performFinalAnalysis(phone);
  }

  if (!finalAnalysis) return null;

  // Gerar texto formatado
  const score = lead.intake_form_final_score || 0;
  const pathway = lead.intake_form_primary_pathway || 'unknown';

  const pathwayCodes = {
    'family_based': 'FAM',
    'employment_based': 'EMP',
    'humanitarian_asylum': 'ASY',
    'humanitarian_vawa': 'VAW',
    'humanitarian_u_visa': 'UVI',
    'humanitarian_t_visa': 'TVI',
    'humanitarian_sijs': 'SIJ',
    'investor': 'INV',
    'unknown': 'UNK'
  };

  const code = pathwayCodes[pathway] || 'UNK';

  let summary = `=== INTAKE FORM SCORE: ${score}/100 ===\n`;
  summary += `Pathway: ${pathway}\n`;
  summary += `Status: ${score >= 70 ? 'QUALIFICADO' : 'NAO QUALIFICADO'}\n\n`;

  summary += `--- RESUMO GEMINI ---\n`;
  summary += finalAnalysis.summary + '\n\n';

  summary += `--- RECOMENDACOES ---\n`;
  summary += `Acao Imediata: ${finalAnalysis.immediate_action || 'N/A'}\n`;
  summary += `Prioridade: ${finalAnalysis.consultation_priority || 'normal'}\n`;
  summary += `Vistos Recomendados: ${(finalAnalysis.recommended_visa_types || []).join(', ') || 'N/A'}\n\n`;

  if (finalAnalysis.red_flags && finalAnalysis.red_flags.length > 0) {
    summary += `--- RED FLAGS ---\n`;
    finalAnalysis.red_flags.forEach(f => summary += `! ${f}\n`);
    summary += '\n';
  }

  if (finalAnalysis.opportunities && finalAnalysis.opportunities.length > 0) {
    summary += `--- OPORTUNIDADES ---\n`;
    finalAnalysis.opportunities.forEach(o => summary += `+ ${o}\n`);
    summary += '\n';
  }

  return {
    moskitPrefix: `[LEAD WPP ${score} ${code}]`,
    notes: summary,
    priority: finalAnalysis.consultation_priority,
    recommendedVisas: finalAnalysis.recommended_visa_types
  };
}

// Inicializar na importacao
init();

module.exports = {
  init,
  analyzeResponse,
  analyzeAllResponses,
  performFinalAnalysis,
  generateMoskitSummary,
  ANALYSIS_PROMPTS
};
