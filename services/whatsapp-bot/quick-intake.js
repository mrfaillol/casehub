/**
 * Quick Intake - Formulario Condensado (12 perguntas)
 * CaseHub
 * v1.0 - Human Handoff Flow
 *
 * Perguntas mais qualificadoras do intake completo (46 perguntas)
 * condensadas em 12 perguntas essenciais para qualificacao rapida.
 */

const { detectLanguage, getMessages } = require('./languages');

// Estados do Quick Intake
const QUICK_INTAKE_STATES = {
  NOT_STARTED: 'quick_intake_not_started',
  INVITED: 'quick_intake_invited',
  Q1_NAME: 'quick_intake_q1',
  Q2_ENTRY: 'quick_intake_q2',
  Q3_GOAL: 'quick_intake_q3',
  Q4_DEPORTED: 'quick_intake_q4',
  Q5_FAMILY_US: 'quick_intake_q5',
  Q6_SPOUSE: 'quick_intake_q6',
  Q7_CRIMINAL: 'quick_intake_q7',
  Q8_ASYLUM: 'quick_intake_q8',
  Q9_VAWA: 'quick_intake_q9',
  Q10_UVISA: 'quick_intake_q10',
  Q11_EMPLOYMENT: 'quick_intake_q11',
  Q12_EMAIL: 'quick_intake_q12',
  COMPLETED: 'quick_intake_completed'
};

// Perguntas em 3 idiomas
const QUICK_INTAKE_QUESTIONS = {
  // Q1: Nome completo
  q1: {
    pt: 'Qual seu nome completo?',
    en: 'What is your full name?',
    es: 'Cual es tu nombre completo?'
  },

  // Q2: Como entrou nos EUA
  q2: {
    pt: 'Como voce entrou nos EUA?\n\n*1. Com visto\n*2. Sem documentos (checkpoint)\n*3. Fronteira sem inspecao',
    en: 'How did you enter the US?\n\n*1. With visa\n*2. Without documents (checkpoint)\n*3. Border without inspection',
    es: 'Como entraste a los EE.UU.?\n\n*1. Con visa\n*2. Sin documentos (checkpoint)\n*3. Frontera sin inspeccion'
  },

  // Q3: Objetivo/situacao
  q3: {
    pt: 'Qual seu objetivo principal com imigracao? Descreva brevemente sua situacao.',
    en: 'What is your main immigration goal? Briefly describe your situation.',
    es: 'Cual es tu objetivo principal con inmigracion? Describe brevemente tu situacion.'
  },

  // Q4: Deportacao
  q4: {
    pt: 'Voce ja foi deportado ou tem ordem de remocao?\n\n*1. Sim\n*2. Nao',
    en: 'Have you ever been deported or have a removal order?\n\n*1. Yes\n*2. No',
    es: 'Alguna vez fuiste deportado o tienes orden de remocion?\n\n*1. Si\n*2. No'
  },

  // Q5: Familia cidadaos americanos
  q5: {
    pt: 'Voce tem pais, avos ou filhos cidadaos americanos?\n\n*1. Sim\n*2. Nao',
    en: 'Do you have parents, grandparents, or children who are US citizens?\n\n*1. Yes\n*2. No',
    es: 'Tienes padres, abuelos o hijos ciudadanos americanos?\n\n*1. Si\n*2. No'
  },

  // Q6: Conjuge
  q6: {
    pt: 'Voce e casado(a) com cidadao americano ou portador de green card?\n\n*1. Sim, cidadao americano\n*2. Sim, green card holder\n*3. Nao',
    en: 'Are you married to a US citizen or green card holder?\n\n*1. Yes, US citizen\n*2. Yes, green card holder\n*3. No',
    es: 'Estas casado(a) con un ciudadano americano o portador de green card?\n\n*1. Si, ciudadano americano\n*2. Si, portador de green card\n*3. No'
  },

  // Q7: Problemas com policia
  q7: {
    pt: 'Voce ja teve problemas com a policia nos EUA?\n\n*1. Sim\n*2. Nao',
    en: 'Have you ever had problems with the police in the US?\n\n*1. Yes\n*2. No',
    es: 'Alguna vez tuviste problemas con la policia en EE.UU.?\n\n*1. Si\n*2. No'
  },

  // Q8: Medo de voltar (Asylum)
  q8: {
    pt: 'Voce tem medo de voltar ao seu pais? Se sim, por que? (se nao, responda "nao")',
    en: 'Are you afraid to return to your country? If yes, why? (if not, reply "no")',
    es: 'Tienes miedo de volver a tu pais? Si es asi, por que? (si no, responde "no")'
  },

  // Q9: VAWA
  q9: {
    pt: 'Voce ja foi vitima de abuso domestico ou violencia por parceiro?\n\n*1. Sim\n*2. Nao',
    en: 'Have you ever been a victim of domestic abuse or partner violence?\n\n*1. Yes\n*2. No',
    es: 'Alguna vez fuiste victima de abuso domestico o violencia de pareja?\n\n*1. Si\n*2. No'
  },

  // Q10: U-Visa
  q10: {
    pt: 'Voce ja foi vitima de algum crime nos EUA?\n\n*1. Sim\n*2. Nao',
    en: 'Have you ever been a victim of a crime in the US?\n\n*1. Yes\n*2. No',
    es: 'Alguna vez fuiste victima de algun crimen en EE.UU.?\n\n*1. Si\n*2. No'
  },

  // Q11: Employment
  q11: {
    pt: 'Voce tem diploma universitario ou experiencia profissional significativa (5+ anos)?\n\n*1. Sim, diploma universitario\n*2. Sim, experiencia profissional\n*3. Ambos\n*4. Nao',
    en: 'Do you have a university degree or significant professional experience (5+ years)?\n\n*1. Yes, university degree\n*2. Yes, professional experience\n*3. Both\n*4. No',
    es: 'Tienes diploma universitario o experiencia profesional significativa (5+ anos)?\n\n*1. Si, diploma universitario\n*2. Si, experiencia profesional\n*3. Ambos\n*4. No'
  },

  // Q12: Email
  q12: {
    pt: 'Qual seu email para contato?',
    en: 'What is your email for contact?',
    es: 'Cual es tu email de contacto?'
  }
};

// Mensagens do sistema
const QUICK_INTAKE_MESSAGES = {
  intro: {
    pt: 'Vou fazer algumas perguntas rapidas para entender melhor seu caso. Sao apenas 12 perguntas. Vamos comecar?',
    en: "I'll ask a few quick questions to better understand your case. Just 12 questions. Let's begin?",
    es: 'Voy a hacerte algunas preguntas rapidas para entender mejor tu caso. Son solo 12 preguntas. Empezamos?'
  },

  completed: {
    pt: 'Obrigado por responder! Nossa equipe vai analisar seu caso e entrara em contato em breve.',
    en: 'Thank you for answering! Our team will analyze your case and contact you soon.',
    es: 'Gracias por responder! Nuestro equipo analizara tu caso y te contactara pronto.'
  },

  invalid_response: {
    pt: 'Por favor, responda com uma das opcoes indicadas.',
    en: 'Please respond with one of the indicated options.',
    es: 'Por favor, responde con una de las opciones indicadas.'
  }
};

/**
 * Obter pergunta por numero e idioma
 */
function getQuestion(questionNumber, lang = 'en') {
  const key = `q${questionNumber}`;
  const question = QUICK_INTAKE_QUESTIONS[key];
  if (!question) return null;
  return question[lang] || question['en'];
}

/**
 * Obter mensagem do sistema
 */
function getMessage(messageKey, lang = 'en') {
  const message = QUICK_INTAKE_MESSAGES[messageKey];
  if (!message) return null;
  return message[lang] || message['en'];
}

/**
 * Calcular pontuacao do Quick Intake
 */
function calculateQuickIntakeScore(answers) {
  let score = 0;
  let pathways = [];

  // Q2: Entry method
  if (answers.q2 === '1') score += 5;  // Com visto
  else if (answers.q2 === '2') score -= 5;  // Checkpoint sem docs
  else if (answers.q2 === '3') score -= 10;  // Fronteira sem inspecao

  // Q4: Deportacao
  if (answers.q4 === '1') score -= 10;  // Deportado

  // Q5: Familia US citizens
  if (answers.q5 === '1') {
    score += 10;
    pathways.push('FAMILY_BASED');
  }

  // Q6: Conjuge
  if (answers.q6 === '1') {  // Cidadao americano
    score += 15;
    pathways.push('FAMILY_BASED');
  } else if (answers.q6 === '2') {  // Green card holder
    score += 10;
    pathways.push('FAMILY_BASED');
  }

  // Q7: Criminal history
  if (answers.q7 === '1') score -= 10;  // Problemas com policia

  // Q8: Asylum
  const asylumAnswer = (answers.q8 || '').toLowerCase();
  if (asylumAnswer && asylumAnswer !== 'nao' && asylumAnswer !== 'no') {
    score += 15;
    pathways.push('HUMANITARIAN_ASYLUM');
  }

  // Q9: VAWA
  if (answers.q9 === '1') {
    score += 10;
    pathways.push('HUMANITARIAN_VAWA');
  }

  // Q10: U-Visa
  if (answers.q10 === '1') {
    score += 10;
    pathways.push('HUMANITARIAN_U_VISA');
  }

  // Q11: Employment
  if (answers.q11 === '1' || answers.q11 === '2') {
    score += 5;
    pathways.push('EMPLOYMENT_BASED');
  } else if (answers.q11 === '3') {
    score += 8;
    pathways.push('EMPLOYMENT_BASED');
  }

  // Normalizar score para 0-100
  const normalizedScore = Math.max(0, Math.min(100, score + 50));

  // Determinar status
  let status;
  if (normalizedScore >= 90) status = 'HOT';
  else if (normalizedScore >= 70) status = 'QUALIFIED';
  else if (normalizedScore >= 50) status = 'WARM';
  else status = 'COLD';

  return {
    rawScore: score,
    normalizedScore,
    status,
    pathways: [...new Set(pathways)],  // Remove duplicates
    primaryPathway: pathways[0] || 'UNKNOWN'
  };
}

/**
 * Processar resposta do Quick Intake
 */
function processQuickIntakeResponse(message, currentState, lead, lang = 'en') {
  const msg = (message || '').trim();

  // v11.1: Parse JSON string to object (answers are stored as JSON string in DB)
  let answers = lead.quick_intake_answers || {};
  if (typeof answers === 'string') {
    try { answers = JSON.parse(answers); } catch(e) { answers = {}; }
  }

  // Mapear estado para numero da pergunta
  const stateToQuestion = {
    [QUICK_INTAKE_STATES.Q1_NAME]: 1,
    [QUICK_INTAKE_STATES.Q2_ENTRY]: 2,
    [QUICK_INTAKE_STATES.Q3_GOAL]: 3,
    [QUICK_INTAKE_STATES.Q4_DEPORTED]: 4,
    [QUICK_INTAKE_STATES.Q5_FAMILY_US]: 5,
    [QUICK_INTAKE_STATES.Q6_SPOUSE]: 6,
    [QUICK_INTAKE_STATES.Q7_CRIMINAL]: 7,
    [QUICK_INTAKE_STATES.Q8_ASYLUM]: 8,
    [QUICK_INTAKE_STATES.Q9_VAWA]: 9,
    [QUICK_INTAKE_STATES.Q10_UVISA]: 10,
    [QUICK_INTAKE_STATES.Q11_EMPLOYMENT]: 11,
    [QUICK_INTAKE_STATES.Q12_EMAIL]: 12
  };

  const currentQuestion = stateToQuestion[currentState];

  if (!currentQuestion) {
    // Estado inicial ou convite
    if (currentState === QUICK_INTAKE_STATES.INVITED) {
      const lowerMsg = msg.toLowerCase();
      if (lowerMsg === 'sim' || lowerMsg === 'yes' || lowerMsg === 'si' || lowerMsg === '1') {
        return {
          response: getQuestion(1, lang),
          newState: QUICK_INTAKE_STATES.Q1_NAME,
          answers: answers
        };
      } else {
        return {
          response: getMessage('intro', lang),
          newState: QUICK_INTAKE_STATES.INVITED,
          answers: answers
        };
      }
    }
    return null;
  }

  // Salvar resposta atual
  answers[`q${currentQuestion}`] = msg;

  // Determinar proxima pergunta
  const nextQuestion = currentQuestion + 1;

  if (nextQuestion > 12) {
    // Intake completo - calcular score
    const scoring = calculateQuickIntakeScore(answers);

    return {
      response: getMessage('completed', lang),
      newState: QUICK_INTAKE_STATES.COMPLETED,
      answers: answers,
      scoring: scoring,
      isCompleted: true
    };
  }

  // Mapear numero para estado
  const questionToState = {
    1: QUICK_INTAKE_STATES.Q1_NAME,
    2: QUICK_INTAKE_STATES.Q2_ENTRY,
    3: QUICK_INTAKE_STATES.Q3_GOAL,
    4: QUICK_INTAKE_STATES.Q4_DEPORTED,
    5: QUICK_INTAKE_STATES.Q5_FAMILY_US,
    6: QUICK_INTAKE_STATES.Q6_SPOUSE,
    7: QUICK_INTAKE_STATES.Q7_CRIMINAL,
    8: QUICK_INTAKE_STATES.Q8_ASYLUM,
    9: QUICK_INTAKE_STATES.Q9_VAWA,
    10: QUICK_INTAKE_STATES.Q10_UVISA,
    11: QUICK_INTAKE_STATES.Q11_EMPLOYMENT,
    12: QUICK_INTAKE_STATES.Q12_EMAIL
  };

  return {
    response: getQuestion(nextQuestion, lang),
    newState: questionToState[nextQuestion],
    answers: answers
  };
}

/**
 * Iniciar Quick Intake para um lead
 */
function startQuickIntake(lang = 'en') {
  const intro = getMessage('intro', lang);
  const firstQuestion = getQuestion(1, lang);

  return {
    response: `${intro}\n\n${firstQuestion}`,
    newState: QUICK_INTAKE_STATES.Q1_NAME,
    answers: {}
  };
}

/**
 * Verificar se estado e do Quick Intake
 */
function isQuickIntakeState(state) {
  return state && state.startsWith('quick_intake_');
}

module.exports = {
  QUICK_INTAKE_STATES,
  QUICK_INTAKE_QUESTIONS,
  QUICK_INTAKE_MESSAGES,
  getQuestion,
  getMessage,
  calculateQuickIntakeScore,
  processQuickIntakeResponse,
  startQuickIntake,
  isQuickIntakeState
};
