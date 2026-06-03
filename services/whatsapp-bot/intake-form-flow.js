/**
 * Intake Form Flow - Sistema de 46 perguntas via WhatsApp
 * CaseHub
 * v1.0 - Fluxo completo de qualificacao de leads
 */

const db = require('./database');

// Estados do formulario
const INTAKE_STATES = {
  NOT_STARTED: 'not_started',
  INVITED: 'invited',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  EXPIRED: 'expired',
  SKIPPED: 'skipped'
};

// Categorias de perguntas
const CATEGORIES = {
  BASIC_INFO: 'basic_info',
  ENTRY_HISTORY: 'entry_history',
  PROBLEMS_GOALS: 'problems_goals',
  LEGAL_HISTORY: 'legal_history',
  FAMILY_CONNECTIONS: 'family_connections',
  WORK_AUTH: 'work_authorization',
  CRIMINAL_HISTORY: 'criminal_history',
  ASYLUM: 'asylum',
  VAWA: 'vawa',
  U_VISA: 'u_visa',
  T_VISA: 't_visa',
  SIJS: 'sijs',
  EMPLOYMENT_BASED: 'employment_based'
};

// Pathways de visto
const PATHWAYS = {
  FAMILY_BASED: 'family_based',
  EMPLOYMENT_BASED: 'employment_based',
  HUMANITARIAN_ASYLUM: 'humanitarian_asylum',
  HUMANITARIAN_VAWA: 'humanitarian_vawa',
  HUMANITARIAN_U_VISA: 'humanitarian_u_visa',
  HUMANITARIAN_T_VISA: 'humanitarian_t_visa',
  HUMANITARIAN_SIJS: 'humanitarian_sijs',
  INVESTOR: 'investor',
  UNKNOWN: 'unknown'
};

// Definicao das 46 perguntas
const INTAKE_QUESTIONS = [
  // ===== BASIC INFO (Q1-8) =====
  {
    id: 1,
    category: CATEGORIES.BASIC_INFO,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "What is your e-mail address?",
      pt: "Qual e o seu endereco de e-mail?",
      es: "Cual es su direccion de correo electronico?"
    }
  },
  {
    id: 2,
    category: CATEGORIES.BASIC_INFO,
    type: 'text',
    required: true,
    max_points: 2,
    question: {
      en: "What is your full name? (Please provide your first, middle and last name)",
      pt: "Qual e o seu nome completo? (Por favor, forneca seu primeiro nome, nome do meio e sobrenome)",
      es: "Cual es su nombre completo? (Por favor, proporcione su primer nombre, segundo nombre y apellido)"
    }
  },
  {
    id: 3,
    category: CATEGORIES.BASIC_INFO,
    type: 'date',
    required: true,
    max_points: 0,
    question: {
      en: "What is your date of birth? (MM/DD/YYYY)",
      pt: "Qual e a sua data de nascimento? (DD/MM/AAAA)",
      es: "Cual es su fecha de nacimiento? (DD/MM/AAAA)"
    }
  },
  {
    id: 4,
    category: CATEGORIES.BASIC_INFO,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "What is your nationality? If you have more than one, please provide all of them.",
      pt: "Qual e a sua nacionalidade? Se voce tiver mais de uma, por favor liste todas.",
      es: "Cual es su nacionalidad? Si tiene mas de una, por favor proporcione todas."
    }
  },
  {
    id: 5,
    category: CATEGORIES.BASIC_INFO,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "What is your city, state and country of birth?",
      pt: "Qual e a sua cidade, estado e pais de nascimento?",
      es: "Cual es su ciudad, estado y pais de nacimiento?"
    }
  },
  {
    id: 6,
    category: CATEGORIES.BASIC_INFO,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "What is your phone number?",
      pt: "Qual e o seu numero de telefone?",
      es: "Cual es su numero de telefono?"
    }
  },
  {
    id: 7,
    category: CATEGORIES.BASIC_INFO,
    type: 'text',
    required: true,
    max_points: 2,
    question: {
      en: "What is your full street address with zip code? When did you start living at this address?",
      pt: "Qual e o seu endereco completo com CEP? Quando voce comecou a morar nesse endereco?",
      es: "Cual es su direccion completa con codigo postal? Cuando empezo a vivir en esta direccion?"
    }
  },

  // ===== ENTRY HISTORY (Q8-14) =====
  {
    id: 8,
    category: CATEGORIES.ENTRY_HISTORY,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "When did you first enter the U.S.? (If you have never been to the U.S. before, please answer 'N/A')",
      pt: "Quando voce entrou pela primeira vez nos EUA? (Se voce nunca esteve nos EUA, responda 'N/A')",
      es: "Cuando entro por primera vez a los EE.UU.? (Si nunca ha estado en los EE.UU., responda 'N/A')"
    }
  },
  {
    id: 9,
    category: CATEGORIES.ENTRY_HISTORY,
    type: 'choice',
    required: true,
    max_points: 5,
    negative_points: -10,
    pathway_impact: null,
    question: {
      en: "How did you enter on the first time?",
      pt: "Como voce entrou pela primeira vez?",
      es: "Como entro la primera vez?"
    },
    options: {
      en: ["1. With a visa", "2. With no papers, but at a checkpoint", "3. I was not inspected/Other", "4. I have never been to the U.S."],
      pt: ["1. Com visto", "2. Sem documentos, mas em um ponto de controle", "3. Nao fui inspecionado/Outro", "4. Nunca estive nos EUA"],
      es: ["1. Con visa", "2. Sin papeles, pero en un punto de control", "3. No fui inspeccionado/Otro", "4. Nunca he estado en los EE.UU."]
    },
    scoring: {
      "1": 5,  // With visa = +5
      "2": -5, // No papers at checkpoint = -5
      "3": -10, // Not inspected = -10
      "4": 0   // Never been = 0
    }
  },
  {
    id: 10,
    category: CATEGORIES.ENTRY_HISTORY,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "Please provide us with further information regarding your status/visa and when your status/visa/authorization expired when you first entered the U.S. (If not applicable, please answer 'N/A')",
      pt: "Por favor, forneca mais informacoes sobre seu status/visto e quando seu status/visto/autorizacao expirou quando voce entrou nos EUA pela primeira vez. (Se nao aplicavel, responda 'N/A')",
      es: "Por favor, proporcionenos mas informacion sobre su estatus/visa y cuando expiro su estatus/visa/autorizacion cuando entro por primera vez a los EE.UU. (Si no aplica, responda 'N/A')"
    }
  },
  {
    id: 11,
    category: CATEGORIES.ENTRY_HISTORY,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "When did you last enter the U.S.? (If you have never been to the U.S. before, please answer 'N/A')",
      pt: "Quando foi a ultima vez que voce entrou nos EUA? (Se voce nunca esteve nos EUA, responda 'N/A')",
      es: "Cuando fue la ultima vez que entro a los EE.UU.? (Si nunca ha estado en los EE.UU., responda 'N/A')"
    }
  },
  {
    id: 12,
    category: CATEGORIES.ENTRY_HISTORY,
    type: 'choice',
    required: true,
    max_points: 5,
    negative_points: -10,
    question: {
      en: "How did you enter last time?",
      pt: "Como voce entrou da ultima vez?",
      es: "Como entro la ultima vez?"
    },
    options: {
      en: ["1. With a visa", "2. With no papers, but at a checkpoint", "3. I was not inspected/Other", "4. I have never been to the U.S."],
      pt: ["1. Com visto", "2. Sem documentos, mas em um ponto de controle", "3. Nao fui inspecionado/Outro", "4. Nunca estive nos EUA"],
      es: ["1. Con visa", "2. Sin papeles, pero en un punto de control", "3. No fui inspeccionado/Otro", "4. Nunca he estado en los EE.UU."]
    },
    scoring: {
      "1": 5,
      "2": -5,
      "3": -10,
      "4": 0
    }
  },
  {
    id: 13,
    category: CATEGORIES.ENTRY_HISTORY,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "Please provide us with further information regarding your status/visa and when your status/visa/authorization expired when you last entered the U.S. (If not applicable, please answer 'N/A')",
      pt: "Por favor, forneca mais informacoes sobre seu status/visto e quando seu status/visto/autorizacao expirou quando voce entrou nos EUA pela ultima vez. (Se nao aplicavel, responda 'N/A')",
      es: "Por favor, proporcionenos mas informacion sobre su estatus/visa y cuando expiro su estatus/visa/autorizacion cuando entro por ultima vez a los EE.UU. (Si no aplica, responda 'N/A')"
    }
  },

  // ===== PROBLEMS & GOALS (Q14) =====
  {
    id: 14,
    category: CATEGORIES.PROBLEMS_GOALS,
    type: 'text',
    required: true,
    max_points: 10,
    gemini_analyze: true,
    question: {
      en: "What problems have brought you to our office? What do you hope that the Immigration Attorneys can do about those problems?",
      pt: "Quais problemas trouxeram voce ao nosso escritorio? O que voce espera que os advogados de imigracao possam fazer sobre esses problemas?",
      es: "Que problemas lo han traido a nuestra oficina? Que espera que los abogados de inmigracion puedan hacer sobre esos problemas?"
    }
  },

  // ===== LEGAL HISTORY (Q15-20) =====
  {
    id: 15,
    category: CATEGORIES.LEGAL_HISTORY,
    type: 'boolean',
    required: true,
    max_points: 0,
    negative_points: -10,
    question: {
      en: "Have you ever been ordered removed or deported from the U.S.?",
      pt: "Voce ja foi ordenado a ser removido ou deportado dos EUA?",
      es: "Alguna vez le han ordenado ser removido o deportado de los EE.UU.?"
    },
    scoring: {
      "yes": -10,
      "no": 0
    }
  },
  {
    id: 16,
    category: CATEGORIES.LEGAL_HISTORY,
    type: 'boolean',
    required: true,
    max_points: 0,
    negative_points: -5,
    question: {
      en: "Have you ever been in Immigration Court?",
      pt: "Voce ja esteve em um Tribunal de Imigracao?",
      es: "Alguna vez ha estado en un Tribunal de Inmigracion?"
    },
    scoring: {
      "yes": -5,
      "no": 0
    }
  },
  {
    id: 17,
    category: CATEGORIES.LEGAL_HISTORY,
    type: 'boolean',
    required: true,
    max_points: 0,
    negative_points: -3,
    question: {
      en: "Have you ever been stopped by Immigration Officials?",
      pt: "Voce ja foi parado por oficiais de imigracao?",
      es: "Alguna vez ha sido detenido por oficiales de inmigracion?"
    },
    scoring: {
      "yes": -3,
      "no": 0
    }
  },
  {
    id: 18,
    category: CATEGORIES.LEGAL_HISTORY,
    type: 'text',
    required: true,
    max_points: 0,
    question: {
      en: "If you answered 'Yes' to any of the above, please describe the circumstances in detail below. If you answered 'No', just write 'N/A'.",
      pt: "Se voce respondeu 'Sim' a alguma das perguntas acima, por favor descreva as circunstancias em detalhes abaixo. Se voce respondeu 'Nao', apenas escreva 'N/A'.",
      es: "Si respondio 'Si' a alguna de las preguntas anteriores, por favor describa las circunstancias en detalle a continuacion. Si respondio 'No', simplemente escriba 'N/A'."
    }
  },
  {
    id: 19,
    category: CATEGORIES.LEGAL_HISTORY,
    type: 'text',
    required: true,
    max_points: 3,
    question: {
      en: "Have you ever applied for any immigration benefits? (i.e.: Permanent residency, asylum, amnesty, TPS, cancellation, suspension, Family Unity, DACA, visa petition, U visa, T visa, SIJS, or others). If so, please tell us when did you apply, to what categories have you applied and what was the result of the application (if any). If not, just write 'N/A'.",
      pt: "Voce ja solicitou algum beneficio de imigracao? (ex: Residencia permanente, asilo, anistia, TPS, cancelamento, suspensao, Unidade Familiar, DACA, peticao de visto, visto U, visto T, SIJS, ou outros). Se sim, por favor nos diga quando voce solicitou, quais categorias voce solicitou e qual foi o resultado da solicitacao (se houver). Se nao, apenas escreva 'N/A'.",
      es: "Alguna vez ha solicitado algun beneficio de inmigracion? (ej: Residencia permanente, asilo, amnistia, TPS, cancelacion, suspension, Unidad Familiar, DACA, peticion de visa, visa U, visa T, SIJS, u otros). Si es asi, por favor diganos cuando solicito, a que categorias ha solicitado y cual fue el resultado de la solicitud (si lo hay). Si no, simplemente escriba 'N/A'."
    }
  },
  {
    id: 20,
    category: CATEGORIES.LEGAL_HISTORY,
    type: 'text',
    required: true,
    max_points: 3,
    question: {
      en: "Has any paperwork been filed on your behalf? (i.e. visa petition by family). If not, just write 'N/A'.",
      pt: "Algum documento foi preenchido em seu nome? (ex: peticao de visto por familiar). Se nao, apenas escreva 'N/A'.",
      es: "Se ha presentado algun documento en su nombre? (ej: peticion de visa por familia). Si no, simplemente escriba 'N/A'."
    }
  },

  // ===== FAMILY CONNECTIONS (Q21-25) =====
  {
    id: 21,
    category: CATEGORIES.FAMILY_CONNECTIONS,
    type: 'boolean',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.FAMILY_BASED,
    question: {
      en: "Were your parent(s) or grandparent(s) U.S. citizens?",
      pt: "Seus pais ou avos eram cidadaos americanos?",
      es: "Sus padres o abuelos eran ciudadanos estadounidenses?"
    },
    scoring: {
      "yes": 10,
      "no": 0
    }
  },
  {
    id: 22,
    category: CATEGORIES.FAMILY_CONNECTIONS,
    type: 'text',
    required: true,
    max_points: 15,
    pathway_impact: PATHWAYS.FAMILY_BASED,
    gemini_analyze: true,
    question: {
      en: "Are you married? If so, is your spouse a U.S. citizen or green card holder?",
      pt: "Voce e casado(a)? Se sim, seu conjuge e cidadao americano ou portador de green card?",
      es: "Esta casado(a)? Si es asi, su conyuge es ciudadano estadounidense o titular de green card?"
    }
  },
  {
    id: 23,
    category: CATEGORIES.FAMILY_CONNECTIONS,
    type: 'text',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.FAMILY_BASED,
    gemini_analyze: true,
    question: {
      en: "Do you have children? Were they born in the U.S.?",
      pt: "Voce tem filhos? Eles nasceram nos EUA?",
      es: "Tiene hijos? Nacieron en los EE.UU.?"
    }
  },
  {
    id: 24,
    category: CATEGORIES.FAMILY_CONNECTIONS,
    type: 'text',
    required: true,
    max_points: 5,
    pathway_impact: PATHWAYS.FAMILY_BASED,
    question: {
      en: "Are any of your children or family members in the U.S. now? What is their current immigration status?",
      pt: "Algum de seus filhos ou familiares esta nos EUA agora? Qual e o status de imigracao atual deles?",
      es: "Alguno de sus hijos o familiares esta en los EE.UU. ahora? Cual es su estatus migratorio actual?"
    }
  },

  // ===== WORK AUTHORIZATION (Q25-26) =====
  {
    id: 25,
    category: CATEGORIES.WORK_AUTH,
    type: 'boolean',
    required: true,
    max_points: 5,
    question: {
      en: "Do you have authorization to work in the U.S.?",
      pt: "Voce tem autorizacao para trabalhar nos EUA?",
      es: "Tiene autorizacion para trabajar en los EE.UU.?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },
  {
    id: 26,
    category: CATEGORIES.WORK_AUTH,
    type: 'text',
    required: true,
    max_points: 3,
    question: {
      en: "Please provide us information about your current employment.",
      pt: "Por favor, forneca informacoes sobre seu emprego atual.",
      es: "Por favor, proporcionenos informacion sobre su empleo actual."
    }
  },

  // ===== CRIMINAL HISTORY (Q27) =====
  {
    id: 27,
    category: CATEGORIES.CRIMINAL_HISTORY,
    type: 'text',
    required: true,
    max_points: 0,
    negative_points: -15,
    gemini_analyze: true,
    question: {
      en: "Have you ever had trouble with the police or been arrested in the U.S.? If so, when and for what? What sentence did you receive?",
      pt: "Voce ja teve problemas com a policia ou foi preso nos EUA? Se sim, quando e por que? Qual sentenca voce recebeu?",
      es: "Alguna vez ha tenido problemas con la policia o ha sido arrestado en los EE.UU.? Si es asi, cuando y por que? Que sentencia recibio?"
    }
  },

  // ===== ASYLUM (Q28) =====
  {
    id: 28,
    category: CATEGORIES.ASYLUM,
    type: 'text',
    required: true,
    max_points: 20,
    pathway_impact: PATHWAYS.HUMANITARIAN_ASYLUM,
    gemini_analyze: true,
    question: {
      en: "Do you have any reason to fear going back to your country? Who do you fear and why?",
      pt: "Voce tem alguma razao para temer voltar ao seu pais? De quem voce tem medo e por que?",
      es: "Tiene alguna razon para temer regresar a su pais? A quien teme y por que?"
    }
  },

  // ===== VAWA (Q29-31) =====
  {
    id: 29,
    category: CATEGORIES.VAWA,
    type: 'boolean',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_VAWA,
    question: {
      en: "Have you ever been a victim of domestic abuse by a spouse, parent or child?",
      pt: "Voce ja foi vitima de abuso domestico por um conjuge, pai/mae ou filho?",
      es: "Alguna vez ha sido victima de abuso domestico por parte de un conyuge, padre/madre o hijo?"
    },
    scoring: {
      "yes": 10,
      "no": 0
    }
  },
  {
    id: 30,
    category: CATEGORIES.VAWA,
    type: 'text',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_VAWA,
    gemini_analyze: true,
    skip_if: { question_id: 29, answer: 'no' },
    question: {
      en: "If so, please describe the circumstances in detail:",
      pt: "Se sim, por favor descreva as circunstancias em detalhes:",
      es: "Si es asi, por favor describa las circunstancias en detalle:"
    }
  },
  {
    id: 31,
    category: CATEGORIES.VAWA,
    type: 'boolean',
    required: true,
    max_points: 5,
    pathway_impact: PATHWAYS.HUMANITARIAN_VAWA,
    skip_if: { question_id: 29, answer: 'no' },
    question: {
      en: "If so, did your spouse, parent or child have U.S. citizenship status or lawful permanent residency?",
      pt: "Se sim, seu conjuge, pai/mae ou filho tinha cidadania americana ou residencia permanente legal?",
      es: "Si es asi, su conyuge, padre/madre o hijo tenia ciudadania estadounidense o residencia permanente legal?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },

  // ===== U-VISA (Q32-34) =====
  {
    id: 32,
    category: CATEGORIES.U_VISA,
    type: 'boolean',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_U_VISA,
    question: {
      en: "Have you ever been the victim of a crime?",
      pt: "Voce ja foi vitima de um crime?",
      es: "Alguna vez ha sido victima de un crimen?"
    },
    scoring: {
      "yes": 10,
      "no": 0
    }
  },
  {
    id: 33,
    category: CATEGORIES.U_VISA,
    type: 'text',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_U_VISA,
    gemini_analyze: true,
    skip_if: { question_id: 32, answer: 'no' },
    question: {
      en: "If so, what crime? Please describe the situation in detail:",
      pt: "Se sim, qual crime? Por favor descreva a situacao em detalhes:",
      es: "Si es asi, que crimen? Por favor describa la situacion en detalle:"
    }
  },
  {
    id: 34,
    category: CATEGORIES.U_VISA,
    type: 'boolean',
    required: true,
    max_points: 5,
    pathway_impact: PATHWAYS.HUMANITARIAN_U_VISA,
    skip_if: { question_id: 32, answer: 'no' },
    question: {
      en: "Did you report it to the police or help with the criminal investigation?",
      pt: "Voce reportou a policia ou ajudou com a investigacao criminal?",
      es: "Lo reporto a la policia o ayudo con la investigacion criminal?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },

  // ===== T-VISA (Q35-37) =====
  {
    id: 35,
    category: CATEGORIES.T_VISA,
    type: 'boolean',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_T_VISA,
    question: {
      en: "Did anyone recruit you in your home country to work in the U.S.?",
      pt: "Alguem recrutou voce no seu pais de origem para trabalhar nos EUA?",
      es: "Alguien lo recluto en su pais de origen para trabajar en los EE.UU.?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },
  {
    id: 36,
    category: CATEGORIES.T_VISA,
    type: 'boolean',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_T_VISA,
    skip_if: { question_id: 35, answer: 'no' },
    question: {
      en: "Did you feel forced to work or tricked into working?",
      pt: "Voce se sentiu forcado a trabalhar ou enganado para trabalhar?",
      es: "Se sintio forzado a trabajar o enganado para trabajar?"
    },
    scoring: {
      "yes": 10,
      "no": 0
    }
  },
  {
    id: 37,
    category: CATEGORIES.T_VISA,
    type: 'boolean',
    required: true,
    max_points: 10,
    pathway_impact: PATHWAYS.HUMANITARIAN_T_VISA,
    skip_if: { question_id: 35, answer: 'no' },
    question: {
      en: "Were you required to work without pay? (or less pay than allowed or expected?)",
      pt: "Voce foi obrigado a trabalhar sem pagamento? (ou com pagamento menor do que o permitido ou esperado?)",
      es: "Se le exigio trabajar sin pago? (o con menos pago de lo permitido o esperado?)"
    },
    scoring: {
      "yes": 10,
      "no": 0
    }
  },

  // ===== SIJS (Q38) =====
  {
    id: 38,
    category: CATEGORIES.SIJS,
    type: 'boolean',
    required: true,
    max_points: 20,
    pathway_impact: PATHWAYS.HUMANITARIAN_SIJS,
    question: {
      en: "Have you been abandoned, abused, or neglected by a parent? Are you currently under the jurisdiction of a juvenile court (dependency, delinquency or probate guardianship)?",
      pt: "Voce foi abandonado, abusado ou negligenciado por um dos pais? Voce esta atualmente sob a jurisdicao de um tribunal juvenil (dependencia, delinquencia ou tutela)?",
      es: "Ha sido abandonado, abusado o descuidado por un padre? Esta actualmente bajo la jurisdiccion de un tribunal de menores (dependencia, delincuencia o tutela testamentaria)?"
    },
    scoring: {
      "yes": 20,
      "no": 0
    }
  },

  // ===== EMPLOYMENT-BASED (Q39-45) =====
  {
    id: 39,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'file',
    required: false,
    max_points: 5,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Please attach your updated CV/resume in case you are applying for an employment-based visa. (You can send a PDF, DOCX file, or describe your qualifications in text)",
      pt: "Por favor, anexe seu CV/curriculo atualizado caso esteja solicitando um visto baseado em emprego. (Voce pode enviar um arquivo PDF, DOCX, ou descrever suas qualificacoes em texto)",
      es: "Por favor, adjunte su CV/curriculum actualizado en caso de que este solicitando una visa basada en empleo. (Puede enviar un archivo PDF, DOCX, o describir sus calificaciones en texto)"
    }
  },
  {
    id: 40,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'boolean',
    required: true,
    max_points: 8,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Do you have an advanced degree or its foreign equivalent (a baccalaureate or foreign equivalent degree plus 5 years of post-baccalaureate, progressive work experience in the field)?",
      pt: "Voce possui um grau avancado ou seu equivalente estrangeiro (bacharelado ou grau equivalente estrangeiro mais 5 anos de experiencia de trabalho progressiva pos-bacharelado na area)?",
      es: "Tiene un titulo avanzado o su equivalente extranjero (un bachillerato o titulo extranjero equivalente mas 5 anos de experiencia laboral progresiva post-bachillerato en el campo)?"
    },
    scoring: {
      "yes": 8,
      "no": 0
    }
  },
  {
    id: 41,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'boolean',
    required: true,
    max_points: 5,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Do you have an official academic record showing that you have a degree, diploma, certificate, or similar award from a college, university, school, or other institution of learning relating to your area of exceptional ability?",
      pt: "Voce possui um registro academico oficial mostrando que voce tem um diploma, certificado ou premio similar de uma faculdade, universidade, escola ou outra instituicao de ensino relacionada a sua area de habilidade excepcional?",
      es: "Tiene un registro academico oficial que muestre que tiene un titulo, diploma, certificado o premio similar de una universidad, escuela u otra institucion de aprendizaje relacionada con su area de habilidad excepcional?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },
  {
    id: 42,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'boolean',
    required: true,
    max_points: 5,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Do you have a license to practice your profession or certification for your profession or occupation?",
      pt: "Voce possui uma licenca para exercer sua profissao ou certificacao para sua profissao ou ocupacao?",
      es: "Tiene una licencia para ejercer su profesion o certificacion para su profesion u ocupacion?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },
  {
    id: 43,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'boolean',
    required: true,
    max_points: 5,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Do you have evidence that you have commanded a salary or other remuneration for services that demonstrates your exceptional ability?",
      pt: "Voce tem evidencias de que recebeu um salario ou outra remuneracao por servicos que demonstrem sua habilidade excepcional?",
      es: "Tiene evidencia de que ha recibido un salario u otra remuneracion por servicios que demuestre su habilidad excepcional?"
    },
    scoring: {
      "yes": 5,
      "no": 0
    }
  },
  {
    id: 44,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'boolean',
    required: true,
    max_points: 4,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Do you have a membership in a professional association(s)?",
      pt: "Voce e membro de alguma associacao profissional?",
      es: "Tiene membresia en alguna(s) asociacion(es) profesional(es)?"
    },
    scoring: {
      "yes": 4,
      "no": 0
    }
  },
  {
    id: 45,
    category: CATEGORIES.EMPLOYMENT_BASED,
    type: 'boolean',
    required: true,
    max_points: 7,
    pathway_impact: PATHWAYS.EMPLOYMENT_BASED,
    question: {
      en: "Do you have recognition for your achievements and significant contributions to your industry or field by your peers, government entities, professional or business organizations?",
      pt: "Voce possui reconhecimento por suas conquistas e contribuicoes significativas para sua industria ou area por seus pares, entidades governamentais, organizacoes profissionais ou empresariais?",
      es: "Tiene reconocimiento por sus logros y contribuciones significativas a su industria o campo por parte de sus pares, entidades gubernamentales, organizaciones profesionales o empresariales?"
    },
    scoring: {
      "yes": 7,
      "no": 0
    }
  }
];

// Mensagens do sistema
const MESSAGES = {
  invite: {
    en: `Hello {name}!

We are from ${process.env.ORG_NAME || "CaseHub"} and we would like to better understand your immigration case.

We have prepared a quick questionnaire (about 15-20 minutes) that will help us evaluate your visa options.

*IMPORTANT*: Completing this form is essential for us to analyze your case and offer you an appropriate consultation.

Would you like to start now? Reply *YES* to begin or *NO* if you prefer not to participate.`,
    pt: `Ola {name}!

Somos do ${process.env.ORG_NAME || "CaseHub"} e gostariamos de entender melhor seu caso de imigracao.

Preparamos um questionario rapido (cerca de 15-20 minutos) que nos ajudara a avaliar suas opcoes de visto.

*IMPORTANTE*: Completar este formulario e essencial para que possamos analisar seu caso e oferecer uma consulta adequada.

Quer comecar agora? Responda *SIM* para iniciar ou *NAO* se preferir nao participar.`,
    es: `Hola {name}!

Somos del ${process.env.ORG_NAME || "CaseHub"} y nos gustaria entender mejor su caso de inmigracion.

Hemos preparado un cuestionario rapido (aproximadamente 15-20 minutos) que nos ayudara a evaluar sus opciones de visa.

*IMPORTANTE*: Completar este formulario es esencial para que podamos analizar su caso y ofrecerle una consulta adecuada.

Quiere comenzar ahora? Responda *SI* para iniciar o *NO* si prefiere no participar.`
  },
  started: {
    en: "Great! Let's begin. I'll ask you some questions one at a time. Please answer each one before we move to the next.\n\n*Question 1 of 45:*",
    pt: "Otimo! Vamos comecar. Vou fazer algumas perguntas uma de cada vez. Por favor, responda cada uma antes de passarmos para a proxima.\n\n*Pergunta 1 de 45:*",
    es: "Genial! Comencemos. Le hare algunas preguntas una a la vez. Por favor, responda cada una antes de pasar a la siguiente.\n\n*Pregunta 1 de 45:*"
  },
  next_question: {
    en: "*Question {current} of {total}:*",
    pt: "*Pergunta {current} de {total}:*",
    es: "*Pregunta {current} de {total}:*"
  },
  completed_qualified: {
    en: `Congratulations, {name}!

We analyzed your answers and your case appears to have good chances of success.

We would like to offer you a *FREE CONSULTATION* with one of our attorneys to discuss your options.

Click here to schedule: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

We look forward to helping you!`,
    pt: `Parabens, {name}!

Analisamos suas respostas e seu caso parece ter boas chances de sucesso.

Gostariamos de oferecer uma *CONSULTA GRATUITA* com um de nossos advogados para discutir suas opcoes.

Clique aqui para agendar: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Estamos ansiosos para ajuda-lo!`,
    es: `Felicidades, {name}!

Analizamos sus respuestas y su caso parece tener buenas posibilidades de exito.

Nos gustaria ofrecerle una *CONSULTA GRATUITA* con uno de nuestros abogados para discutir sus opciones.

Haga clic aqui para programar: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Esperamos poder ayudarlo!`
  },
  completed_not_qualified: {
    en: `Thank you for completing the questionnaire, {name}!

We have received your information and our team will analyze it carefully.

We will contact you soon if we identify any opportunity for your case.

In the meantime, visit our website for more information: ${process.env.ORG_WEBSITE || "https://casehub.app"}`,
    pt: `Obrigado por completar o questionario, {name}!

Recebemos suas informacoes e nossa equipe ira analisa-las com cuidado.

Entraremos em contato em breve caso identifiquemos alguma oportunidade para seu caso.

Enquanto isso, visite nosso site para mais informacoes: ${process.env.ORG_WEBSITE || "https://casehub.app"}`,
    es: `Gracias por completar el cuestionario, {name}!

Hemos recibido su informacion y nuestro equipo la analizara cuidadosamente.

Nos pondremos en contacto pronto si identificamos alguna oportunidad para su caso.

Mientras tanto, visite nuestro sitio web para mas informacion: ${process.env.ORG_WEBSITE || "https://casehub.app"}`
  },
  declined: {
    en: "No problem! If you change your mind, just send us a message. We're here to help!",
    pt: "Sem problema! Se voce mudar de ideia, e so nos enviar uma mensagem. Estamos aqui para ajudar!",
    es: "No hay problema! Si cambia de opinion, solo envienos un mensaje. Estamos aqui para ayudar!"
  },
  followup_4h: {
    en: "Hi {name}! I noticed you paused at question {question}. Would you like to continue? Your progress has been saved.",
    pt: "Ola {name}! Notei que voce parou na pergunta {question}. Gostaria de continuar? Seu progresso foi salvo.",
    es: "Hola {name}! Note que se detuvo en la pregunta {question}. Le gustaria continuar? Su progreso ha sido guardado."
  },
  followup_24h: {
    en: "Hi {name}! Only {remaining} questions left to complete your immigration assessment. Want to finish it now?",
    pt: "Ola {name}! Faltam apenas {remaining} perguntas para completar sua avaliacao de imigracao. Quer terminar agora?",
    es: "Hola {name}! Solo quedan {remaining} preguntas para completar su evaluacion de inmigracion. Quiere terminarla ahora?"
  },
  followup_48h: {
    en: "Hi {name}! This is your last chance to complete the questionnaire. I'll calculate your score with the current answers if you don't respond.",
    pt: "Ola {name}! Esta e sua ultima chance de completar o questionario. Vou calcular sua pontuacao com as respostas atuais se voce nao responder.",
    es: "Hola {name}! Esta es su ultima oportunidad de completar el cuestionario. Calculare su puntuacion con las respuestas actuales si no responde."
  },
  invalid_response: {
    en: "I didn't understand your response. Please try again.",
    pt: "Nao entendi sua resposta. Por favor, tente novamente.",
    es: "No entendi su respuesta. Por favor, intente de nuevo."
  },
  boolean_hint: {
    en: "(Please answer *Yes* or *No*)",
    pt: "(Por favor, responda *Sim* ou *Nao*)",
    es: "(Por favor, responda *Si* o *No*)"
  },
  choice_hint: {
    en: "(Please reply with the number of your choice)",
    pt: "(Por favor, responda com o numero da sua escolha)",
    es: "(Por favor, responda con el numero de su eleccion)"
  },
  file_hint: {
    en: "(Please upload a PDF or DOCX file, or describe your qualifications in a text message)",
    pt: "(Por favor, envie um arquivo PDF ou DOCX, ou descreva suas qualificacoes em uma mensagem de texto)",
    es: "(Por favor, envie un archivo PDF o DOCX, o describa sus calificaciones en un mensaje de texto)"
  },
  file_received: {
    en: "File received! Thank you.",
    pt: "Arquivo recebido! Obrigado.",
    es: "Archivo recibido! Gracias."
  }
};

// =====================================
// FUNCOES DO FLUXO
// =====================================

/**
 * Obter pergunta por ID
 */
function getQuestion(questionId) {
  return INTAKE_QUESTIONS.find(q => q.id === questionId) || null;
}

/**
 * Obter texto da pergunta no idioma correto
 */
function getQuestionText(questionId, language = 'en') {
  const question = getQuestion(questionId);
  if (!question) return null;
  return question.question[language] || question.question.en;
}

/**
 * Obter opcoes da pergunta no idioma correto
 */
function getQuestionOptions(questionId, language = 'en') {
  const question = getQuestion(questionId);
  if (!question || !question.options) return null;
  return question.options[language] || question.options.en;
}

/**
 * Verificar se pergunta deve ser pulada baseado em resposta anterior
 */
async function shouldSkipQuestion(phone, questionId) {
  const question = getQuestion(questionId);
  if (!question || !question.skip_if) return false;

  const skipCondition = question.skip_if;
  const previousResponse = await db.getIntakeFormResponse(phone, skipCondition.question_id);

  if (!previousResponse) return false;

  const answer = previousResponse.response_text.toLowerCase().trim();
  const skipAnswer = skipCondition.answer.toLowerCase();

  // Verificar se a resposta corresponde ao criterio de skip
  if (skipAnswer === 'no') {
    return answer === 'no' || answer === 'nao' || answer === 'n';
  } else if (skipAnswer === 'yes') {
    return answer === 'yes' || answer === 'sim' || answer === 'si' || answer === 's';
  }

  return answer === skipAnswer;
}

/**
 * Obter proxima pergunta (considerando skip logic)
 */
async function getNextQuestion(phone, currentQuestionId) {
  let nextId = currentQuestionId + 1;

  while (nextId <= INTAKE_QUESTIONS.length) {
    const shouldSkip = await shouldSkipQuestion(phone, nextId);
    if (!shouldSkip) {
      return getQuestion(nextId);
    }

    // Se pular, salvar resposta como 'skipped'
    const skippedQuestion = getQuestion(nextId);
    if (skippedQuestion) {
      await db.saveIntakeFormResponse(
        phone,
        nextId,
        skippedQuestion.question.en,
        'SKIPPED',
        'skip',
        skippedQuestion.category,
        0
      );
    }

    nextId++;
  }

  return null; // Formulario completo
}

/**
 * Processar resposta do usuario
 */
function parseResponse(response, questionType, language = 'en') {
  const text = response.trim().toLowerCase();

  if (questionType === 'boolean') {
    // Detectar Yes/No em multiplos idiomas
    const yesPatterns = ['yes', 'sim', 'si', 's', 'y', '1', 'true'];
    const noPatterns = ['no', 'nao', 'n', '0', 'false'];

    if (yesPatterns.includes(text)) return { valid: true, value: 'yes', normalized: 'yes' };
    if (noPatterns.includes(text)) return { valid: true, value: 'no', normalized: 'no' };

    return { valid: false, value: null };
  }

  if (questionType === 'choice') {
    // Extrair numero da resposta
    const match = text.match(/^(\d+)/);
    if (match) {
      return { valid: true, value: match[1], normalized: match[1] };
    }
    return { valid: false, value: null };
  }

  // Para text, date, file - aceitar qualquer resposta
  if (text.length > 0) {
    return { valid: true, value: response.trim(), normalized: response.trim() };
  }

  return { valid: false, value: null };
}

/**
 * Calcular pontos para uma resposta
 */
function calculatePoints(question, normalizedResponse) {
  if (!question.scoring) {
    // Para perguntas de texto, Gemini vai analisar depois
    return question.gemini_analyze ? 0 : (question.max_points || 0);
  }

  const score = question.scoring[normalizedResponse];
  return score !== undefined ? score : 0;
}

/**
 * Formatar mensagem da pergunta
 */
function formatQuestionMessage(question, currentNum, totalQuestions, language = 'en') {
  let message = MESSAGES.next_question[language]
    .replace('{current}', currentNum)
    .replace('{total}', totalQuestions);

  message += '\n\n' + getQuestionText(question.id, language);

  // Adicionar opcoes se for choice
  if (question.type === 'choice' && question.options) {
    const options = getQuestionOptions(question.id, language);
    message += '\n\n' + options.join('\n');
  }

  // Adicionar dica para boolean
  if (question.type === 'boolean') {
    message += '\n\n' + MESSAGES.boolean_hint[language];
  }

  return message;
}

/**
 * v9.2: Detectar intencao de reiniciar formulario
 */
function detectRestartIntent(message, language = 'en') {
  const text = message.toLowerCase().trim();
  const restartPatterns = [
    // Portugues
    'reiniciar', 'recomecar', 'comecar de novo', 'começar de novo', 'novamente',
    'de novo', 'repetir', 'refazer', 'quero responder', 'responder novamente',
    'continuar', 'continue', 'voltar', 'retomar',
    // English
    'restart', 'start over', 'begin again', 'redo', 'again', 'continue',
    'resume', 'want to answer', 'answer again',
    // Spanish
    'reiniciar', 'empezar de nuevo', 'otra vez', 'repetir', 'continuar'
  ];
  return restartPatterns.some(pattern => text.includes(pattern));
}

/**
 * v9.2: Verificar se mensagem indica interesse (texto detalhado = quer participar)
 */
function isDetailedCaseDescription(message) {
  const text = message.trim();
  // Se a mensagem tem mais de 50 caracteres e contem palavras relacionadas a imigracao
  // provavelmente e uma descricao do caso (interpreta como "sim, quero participar")
  if (text.length > 50) {
    const immigrationKeywords = [
      'visto', 'visa', 'green card', 'trabalho', 'work', 'eua', 'usa', 'estados unidos',
      'imigracao', 'immigration', 'deporta', 'documento', 'legal', 'ilegal',
      'fronteira', 'border', 'mexico', 'familia', 'family', 'asilo', 'asylum',
      'trabalhe', 'trabalhei', 'morei', 'morar', 'live', 'lived'
    ];
    const lower = text.toLowerCase();
    return immigrationKeywords.some(kw => lower.includes(kw));
  }
  return false;
}

/**
 * Processar mensagem durante o intake form
 */
async function processIntakeMessage(phone, message, lead, mediaInfo = null) {
  const language = lead.language || 'en';
  const currentQuestion = lead.intake_form_current_question || 0;

  // v9.2: Se lead com intake EXPIRED ou COMPLETED quer reiniciar
  if (lead.intake_form_state === INTAKE_STATES.EXPIRED || lead.intake_form_state === INTAKE_STATES.COMPLETED) {
    if (detectRestartIntent(message, language)) {
      // Limpar respostas anteriores e reiniciar
      await db.clearIntakeFormResponses(phone);
      await db.updateLead(phone, {
        intake_form_state: INTAKE_STATES.IN_PROGRESS,
        intake_form_current_question: 1,
        intake_form_started_at: new Date(),
        intake_form_followup_count: 0,
        intake_form_final_score: null,
        intake_form_primary_pathway: null
      });

      const restartMessages = {
        en: "Great! Let's start fresh. I'll ask you the questions again.\n\n*Question 1 of 45:*",
        pt: "Otimo! Vamos comecar do zero. Vou fazer as perguntas novamente.\n\n*Pergunta 1 de 45:*",
        es: "Genial! Comencemos de nuevo. Le hare las preguntas otra vez.\n\n*Pregunta 1 de 45:*"
      };

      const questionMessage = '\n\n' + getQuestionText(1, language);
      return {
        response: restartMessages[language] + questionMessage,
        newState: INTAKE_STATES.IN_PROGRESS,
        currentQuestion: 1,
        restarted: true
      };
    }
    // Se nao quer reiniciar, retorna null para fluxo normal
    return null;
  }

  // Se ainda nao comecou, verificar se e resposta ao convite
  if (lead.intake_form_state === INTAKE_STATES.INVITED) {
    const parsed = parseResponse(message, 'boolean', language);

    // v9.2: Se enviou texto detalhado sobre o caso, interpretar como "sim"
    const isDetailedCase = isDetailedCaseDescription(message);

    if ((parsed.valid && parsed.normalized === 'yes') || isDetailedCase) {
      // Iniciar formulario
      await db.updateLead(phone, {
        intake_form_state: INTAKE_STATES.IN_PROGRESS,
        intake_form_current_question: 1,
        intake_form_started_at: new Date()
      });

      // Se enviou descricao detalhada, salvar como contexto inicial
      if (isDetailedCase) {
        await db.saveIntakeFormResponse(
          phone,
          0, // ID 0 = contexto inicial
          'Initial case description',
          message,
          'text',
          'initial_context',
          5, // Bonus por fornecer detalhes
          null
        );
        console.log('[INTAKE] Descricao detalhada interpretada como SIM para:', phone);
      }

      const firstQuestion = getQuestion(1);
      const startMessage = MESSAGES.started[language];
      const questionMessage = '\n\n' + getQuestionText(1, language);

      return {
        response: startMessage + questionMessage,
        newState: INTAKE_STATES.IN_PROGRESS,
        currentQuestion: 1
      };
    } else if (parsed.valid && parsed.normalized === 'no') {
      // Recusou participar
      await db.updateLead(phone, {
        intake_form_state: INTAKE_STATES.SKIPPED
      });

      return {
        response: MESSAGES.declined[language],
        newState: INTAKE_STATES.SKIPPED
      };
    } else {
      // v9.2: Resposta curta nao reconhecida - dar uma chance
      // Se e uma saudacao como "bom dia", "ola", etc, perguntar novamente gentilmente
      const greetings = ['bom dia', 'boa tarde', 'boa noite', 'ola', 'oi', 'hello', 'hi', 'good morning', 'hola', 'buenos dias'];
      const isGreeting = greetings.some(g => message.toLowerCase().trim().includes(g));

      if (isGreeting) {
        const greetingResponse = {
          en: "Hello! Would you like to continue with our questionnaire? Reply *YES* to begin.",
          pt: "Ola! Gostaria de continuar com nosso questionario? Responda *SIM* para comecar.",
          es: "Hola! Le gustaria continuar con nuestro cuestionario? Responda *SI* para comenzar."
        };
        return {
          response: greetingResponse[language],
          newState: INTAKE_STATES.INVITED
        };
      }

      // Resposta invalida
      return {
        response: MESSAGES.invalid_response[language] + '\n\n' + MESSAGES.invite[language].replace('{name}', lead.client_name || lead.whatsapp_name || ''),
        newState: INTAKE_STATES.INVITED
      };
    }
  }

  // Se em progresso, processar resposta
  if (lead.intake_form_state === INTAKE_STATES.IN_PROGRESS) {
    const question = getQuestion(currentQuestion);
    if (!question) {
      return { response: 'Error: Question not found', newState: lead.intake_form_state };
    }

    // v9.1: Se e pergunta tipo 'file' e recebemos um arquivo
    let parsed;
    let fileResponse = null;

    if (question.type === 'file' && mediaInfo && mediaInfo.success) {
      // Arquivo recebido com sucesso para pergunta de arquivo
      parsed = {
        valid: true,
        value: `[FILE] ${mediaInfo.filename}`,
        normalized: mediaInfo.filename
      };
      fileResponse = {
        filename: mediaInfo.filename,
        filePath: mediaInfo.filePath,
        mimetype: mediaInfo.mimetype,
        size: mediaInfo.size,
        extractedText: mediaInfo.extractedText
      };
      console.log('[INTAKE] Arquivo aceito para Q' + question.id + ':', mediaInfo.filename);
    } else if (question.type === 'file') {
      // Pergunta de arquivo mas pode aceitar texto como alternativa
      // (mensagem de texto descrevendo qualificacoes)
      if (message && message.trim().length > 10) {
        parsed = {
          valid: true,
          value: message.trim(),
          normalized: 'text_description'
        };
        console.log('[INTAKE] Descricao em texto aceita para Q' + question.id);
      } else {
        parsed = { valid: false };
      }
    } else {
      // Parsing normal para outros tipos
      parsed = parseResponse(message, question.type, language);
    }

    if (!parsed.valid) {
      let hint = '';
      if (question.type === 'boolean') {
        hint = '\n\n' + MESSAGES.boolean_hint[language];
      } else if (question.type === 'choice') {
        hint = '\n\n' + MESSAGES.choice_hint[language];
      } else if (question.type === 'file') {
        hint = '\n\n' + (MESSAGES.file_hint ? MESSAGES.file_hint[language] : 'Please upload a PDF/DOCX file or describe your qualifications in text.');
      }

      return {
        response: MESSAGES.invalid_response[language] + hint + '\n\n' + getQuestionText(question.id, language),
        newState: INTAKE_STATES.IN_PROGRESS,
        currentQuestion: currentQuestion
      };
    }

    // Calcular pontos (arquivo recebe pontos se foi enviado)
    let points = calculatePoints(question, parsed.normalized);
    if (fileResponse) {
      points = question.max_points || 5; // Pontos por enviar arquivo
    }

    // Salvar resposta (com info de arquivo se houver)
    const responseValue = fileResponse
      ? JSON.stringify({ text: parsed.value, file: fileResponse })
      : parsed.value;

    await db.saveIntakeFormResponse(
      phone,
      question.id,
      question.question.en,
      responseValue,
      fileResponse ? 'file' : question.type,
      question.category,
      points,
      null // Gemini analysis sera feita depois
    );

    // Atualizar pathway score se aplicavel
    if (question.pathway_impact && points > 0) {
      const currentPathwayScores = await db.getPathwayScores(phone);
      const existingScore = currentPathwayScores.find(p => p.pathway === question.pathway_impact);
      const newScore = (existingScore?.score || 0) + points;
      await db.savePathwayScore(phone, question.pathway_impact, newScore);
    }

    // Obter proxima pergunta
    const nextQuestion = await getNextQuestion(phone, currentQuestion);

    if (!nextQuestion) {
      // Formulario completo - calcular score final
      const totalScore = await db.calculateIntakeFormScore(phone);
      const primaryPathway = await db.getPrimaryPathway(phone);
      const isQualified = totalScore >= 70;

      await db.updateLead(phone, {
        intake_form_state: INTAKE_STATES.COMPLETED,
        intake_form_completed_at: new Date(),
        intake_form_final_score: totalScore,
        intake_form_primary_pathway: primaryPathway?.pathway || PATHWAYS.UNKNOWN,
        eligible_for_free_call: isQualified
      });

      const name = lead.client_name || lead.whatsapp_name || '';
      const completionMessage = isQualified
        ? MESSAGES.completed_qualified[language].replace('{name}', name)
        : MESSAGES.completed_not_qualified[language].replace('{name}', name);

      return {
        response: completionMessage,
        newState: INTAKE_STATES.COMPLETED,
        finalScore: totalScore,
        primaryPathway: primaryPathway?.pathway,
        isQualified: isQualified
      };
    }

    // Atualizar pergunta atual
    await db.updateLead(phone, {
      intake_form_current_question: nextQuestion.id
    });

    // Contar perguntas restantes (sem skip)
    const totalQuestions = INTAKE_QUESTIONS.length;

    return {
      response: formatQuestionMessage(nextQuestion, nextQuestion.id, totalQuestions, language),
      newState: INTAKE_STATES.IN_PROGRESS,
      currentQuestion: nextQuestion.id
    };
  }

  return null;
}

/**
 * Enviar convite para intake form
 */
function getInviteMessage(name, language = 'en') {
  return MESSAGES.invite[language].replace('{name}', name || '');
}

/**
 * Obter mensagem de follow-up
 */
function getFollowupMessage(type, name, currentQuestion, language = 'en') {
  const totalQuestions = INTAKE_QUESTIONS.length;
  const remaining = totalQuestions - currentQuestion + 1;

  let messageKey;
  switch (type) {
    case '4h': messageKey = 'followup_4h'; break;
    case '24h': messageKey = 'followup_24h'; break;
    case '48h': messageKey = 'followup_48h'; break;
    default: return null;
  }

  return MESSAGES[messageKey][language]
    .replace('{name}', name || '')
    .replace('{question}', currentQuestion)
    .replace('{remaining}', remaining);
}

/**
 * Popular perguntas no banco de dados
 */
async function populateQuestionsInDatabase() {
  console.log('[INTAKE] Populando perguntas no banco de dados...');

  for (const question of INTAKE_QUESTIONS) {
    await db.insertIntakeQuestion({
      question_id: question.id,
      question_pt: question.question.pt,
      question_en: question.question.en,
      question_es: question.question.es,
      response_type: question.type,
      category: question.category,
      max_points: question.max_points || 0,
      pathway_impact: question.pathway_impact || null,
      skip_if_question_id: question.skip_if?.question_id || null,
      skip_if_answer: question.skip_if?.answer || null,
      options_pt: question.options?.pt ? JSON.stringify(question.options.pt) : null,
      options_en: question.options?.en ? JSON.stringify(question.options.en) : null,
      options_es: question.options?.es ? JSON.stringify(question.options.es) : null,
      display_order: question.id
    });
  }

  console.log(`[INTAKE] ${INTAKE_QUESTIONS.length} perguntas populadas com sucesso!`);
}

module.exports = {
  INTAKE_STATES,
  CATEGORIES,
  PATHWAYS,
  INTAKE_QUESTIONS,
  MESSAGES,
  getQuestion,
  getQuestionText,
  getQuestionOptions,
  shouldSkipQuestion,
  getNextQuestion,
  parseResponse,
  calculatePoints,
  formatQuestionMessage,
  processIntakeMessage,
  getInviteMessage,
  getFollowupMessage,
  populateQuestionsInDatabase
};
