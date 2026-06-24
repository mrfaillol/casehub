/**
 * LLM Chatbot - Respostas Humanizadas Baseadas em Templates
 * CaseHub - WhatsApp Bot
 * v3.0 - 03/02/2026 - PROFESSIONAL TONE, NO EMOJIS, CONVERSION FOCUSED
 *
 * Improvements:
 * - Professional, human tone without emojis
 * - Focus on converting leads to schedule meetings
 * - Non-lead filtering (Europe, UK, spam, partners)
 * - Clear differentiation: free 15-min vs paid $99 consultation
 */

const llmMonitor = require('./llm-monitor');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent';

// Calendly URLs
const CALENDLY_FREE = '${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall';
const CALENDLY_PAID = '${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting';

/**
 * CRITICAL: Legal Advice Detection Patterns
 * Bot CANNOT give legal advice - unauthorized practice of law
 * If detected, block response and redirect to consultation
 */
const LEGAL_ADVICE_PATTERNS = [
  // Portuguese
  /voc[eê]\s+(deve|deveria|precisa|pode|consegue|se qualifica)/gi,
  /seu\s+caso\s+(é|seria|pode|deve|se enquadra)/gi,
  /(você|voce)\s+tem\s+(direito|chance|possibilidade)/gi,
  /recomendo\s+que\s+(você|voce)/gi,
  /sua\s+situa(ç|c)(ã|a)o\s+(permite|qualifica|se enquadra)/gi,
  /pode\s+aplicar\s+para/gi,
  /você\s+consegue/gi,
  /seu\s+perfil\s+(se encaixa|qualifica)/gi,

  // English
  /you\s+(should|must|can|qualify)/gi,
  /your\s+case\s+(is|qualifies|allows)/gi,
  /you\s+have\s+(the right|a chance)/gi,
  /I\s+recommend\s+that\s+you/gi,
  /your\s+situation\s+(qualifies|allows)/gi,
  /you\s+can\s+apply\s+for/gi,
  /you\s+are\s+eligible/gi,
  /your\s+profile\s+(fits|qualifies)/gi,

  // Spanish
  /usted\s+(debe|puede|califica)/gi,
  /su\s+caso\s+(califica|permite)/gi,
  /tiene\s+(derecho|posibilidad)/gi,
  /recomiendo\s+que/gi,
  /puede\s+aplicar\s+para/gi
];

/**
 * NON-LEAD DETECTION
 * Identifies contacts that are NOT qualified leads
 */
const NON_LEAD_PATTERNS = {
    // Europe/UK requests - we don't handle
    europe: {
        patterns: [
            /\b(europa|europe|portugal|espanha|spain|londres|london|uk|reino unido|united kingdom|irlanda|ireland|italia|italy|franca|france|alemanha|germany|holanda|netherlands|suica|switzerland)\b/i,
            /\bvisto.*(europeu|europeia|schengen)\b/i,
            /\b(schengen|union europea|european union)\b/i
        ],
        response: {
            pt: `Olá. Obrigado pelo contato. Infelizmente, nosso escritório é especializado exclusivamente em imigração para os Estados Unidos. Não trabalhamos com processos para Europa, Reino Unido ou outros países. Desejamos sucesso na sua busca e recomendamos procurar um advogado especializado na região de seu interesse. Atenciosamente, ${process.env.ORG_NAME || "CaseHub"}`,
            en: `Hello. Thank you for reaching out. Unfortunately, our firm specializes exclusively in United States immigration. We do not handle cases for Europe, the UK, or other countries. We wish you success in your search and recommend finding an attorney who specializes in your region of interest. Warm regards, ${process.env.ORG_NAME || "CaseHub"}`,
            es: `Hola. Gracias por contactarnos. Lamentablemente, nuestro despacho se especializa exclusivamente en inmigración a Estados Unidos. No manejamos casos para Europa, Reino Unido u otros países. Le deseamos éxito en su búsqueda. Saludos cordiales, ${process.env.ORG_NAME || "CaseHub"}`
        }
    },

    // Spam/irrelevant
    spam: {
        patterns: [
            /\b(vend|comprar|promoc|desconto|gratis|free money|bitcoin|crypto|investimento garantido|emprestimo|loan|marketing|seo|backlink)\b/i,
            /^\d+$/,
            /^(ok|k|👍|🙏|❤️)$/i
        ],
        response: null // Don't respond to spam
    },

    // Partners/vendors - politely acknowledge
    partner: {
        patterns: [
            /\b(parceria|partnership|parceiro|partner|colaboracao|collaboration|representante|representative|indicacao|referral|comissao|commission)\b/i
        ],
        response: {
            pt: `Olá. Agradecemos seu interesse em parcerias. Por gentileza, envie sua proposta detalhada para nosso e-mail: ${process.env.CONTACT_EMAIL || "contact@casehub.app"}. Nossa equipe administrativa avaliará e entrará em contato caso haja interesse. Atenciosamente, ${process.env.ORG_NAME || "CaseHub"}`,
            en: `Hello. Thank you for your interest in partnerships. Please send your detailed proposal to our email: ${process.env.CONTACT_EMAIL || "contact@casehub.app"}. Our administrative team will review and contact you if interested. Warm regards, ${process.env.ORG_NAME || "CaseHub"}`,
            es: `Hola. Gracias por su interés en asociaciones. Por favor envíe su propuesta detallada a nuestro correo: ${process.env.CONTACT_EMAIL || "contact@casehub.app"}. Nuestro equipo administrativo revisará y se comunicará si hay interés. Saludos cordiales, ${process.env.ORG_NAME || "CaseHub"}`
        }
    },

    // Service providers offering their services (translators, etc)
    // Enhanced patterns to catch more business/vendor messages
    service_provider: {
        patterns: [
            // Translation services
            /\b(traducao|translation|tradutor|translator|interprete|interpreter)\b.*\b(servic|oferec|disponiv|preco|orcamento|cotac)\b/i,
            /\b(servic|oferec|disponiv|preco|orcamento|cotac)\b.*\b(traducao|translation|tradutor|translator)\b/i,
            /\b(traducao juramentada|sworn translation|certified translation)\b/i,

            // General business proposals
            /\b(apresent|proposta comercial|nossos servicos|our services|nuestros servicios)\b/i,
            /\b(somos uma empresa|we are a company|somos una empresa)\b/i,
            /\b(oferecemos|ofrecemos|we offer)\b.*\b(servic|product|solu(c|ç)(a|ã)o)\b/i,

            // Marketing/Sales pitches
            /\b(marketing digital|seo|publicidade|advertising|divulga(c|ç)(a|ã)o)\b/i,
            /\b(parceria comercial|business partnership|asociaci(o|ó)n comercial)\b/i,
            /\b(representa(c|ç)(a|ã)o comercial|commercial representation)\b/i,

            // Vendor signals
            /\b(catalogo|catalog|cat(a|á)logo|portfolio|portf(o|ó)lio)\b.*\b(produto|product|servic)\b/i,
            /\b(vender|sell|venta)\b.*\b(produto|product|servic)\b/i
        ],
        response: {
            pt: `Agradecemos o contato e a apresentacao dos seus servicos. Para propostas comerciais, por favor envie um email detalhado para ${process.env.ORG_EMAIL || "info@casehub.app"}. Nossa equipe administrativa avaliara a proposta.\n\nAtenciosamente,\n${process.env.ORG_NAME || "CaseHub"}`,
            en: `Thank you for reaching out about your services. For business proposals, please send a detailed email to ${process.env.ORG_EMAIL || "info@casehub.app"}. Our administrative team will review it.\n\nWarm regards,\n${process.env.ORG_NAME || "CaseHub"}`,
            es: `Gracias por contactarnos sobre sus servicios. Para propuestas comerciales, envie un email detallado a ${process.env.ORG_EMAIL || "info@casehub.app"}. Nuestro equipo administrativo lo revisara.\n\nSaludos cordiales,\n${process.env.ORG_NAME || "CaseHub"}`
        }
    },

    // Already a client checking case status
    existing_client: {
        patterns: [
            /\b(meu caso|my case|numero do caso|case number|status do processo|case status|ja sou cliente|already a client|cliente atual|current client)\b/i
        ],
        response: {
            pt: `Olá. Para informações sobre o status do seu caso, por gentileza entre em contato diretamente com nossa equipe jurídica pelo e-mail ${process.env.CONTACT_EMAIL || "contact@casehub.app"} ou acesse sua conta no portal do cliente: ${process.env.EIMMIGRATION_URL || "https://example.com/client-portal"}. Se precisar agendar uma reunião de acompanhamento, nossa equipe pode ajudá-lo a organizar isso. Atenciosamente, ${process.env.ORG_NAME || "CaseHub"}`,
            en: `Hello. For information about your case status, please contact our legal team directly at ${process.env.CONTACT_EMAIL || "contact@casehub.app"} or access your client portal account: ${process.env.EIMMIGRATION_URL || "https://example.com/client-portal"}. If you need to schedule a follow-up meeting, our team can help arrange that. Warm regards, ${process.env.ORG_NAME || "CaseHub"}`,
            es: `Hola. Para información sobre el estado de su caso, por favor contacte a nuestro equipo legal directamente en ${process.env.CONTACT_EMAIL || "contact@casehub.app"} o acceda a su portal del cliente: ${process.env.EIMMIGRATION_URL || "https://example.com/client-portal"}. Saludos cordiales, ${process.env.ORG_NAME || "CaseHub"}`
        }
    }
};

/**
 * Check if message is from a non-lead
 * Returns: { isNonLead: boolean, type: string, response: string|null }
 */
function checkNonLead(message, language = 'pt') {
    if (!message) return { isNonLead: false };

    const msg = message.toLowerCase();

    for (const [type, config] of Object.entries(NON_LEAD_PATTERNS)) {
        for (const pattern of config.patterns) {
            if (pattern.test(msg)) {
                const response = config.response ? (config.response[language] || config.response['en']) : null;
                console.log(`[NON-LEAD] Detected type: ${type} | Message: "${msg.substring(0, 50)}..."`);
                return {
                    isNonLead: true,
                    type: type,
                    response: response
                };
            }
        }
    }

    return { isNonLead: false };
}

/**
 * INTENT CLASSIFICATION - More refined for conversion focus
 */
const INTENT_KEYWORDS = {
    // Ready to schedule - HIGH PRIORITY
    ready_to_schedule: {
        patterns: [/quero (agendar|marcar)/, /want to (schedule|book)/, /vamos (agendar|marcar)/, /let'?s (schedule|book)/],
        keywords: ['agendar', 'marcar', 'schedule', 'book', 'calendly', 'reuniao', 'reunião', 'meeting', 'call', 'chamada'],
        priority: 10
    },

    // Asking about meetings - needs guidance
    meeting_inquiry: {
        patterns: [/como (funciona|agendar)/, /how (does it work|to schedule)/],
        keywords: ['disponibilidade', 'availability', 'horario', 'horário', 'quando', 'when', 'como funciona', 'how it works'],
        priority: 9
    },

    // Price/payment questions - close to conversion
    payment_inquiry: {
        patterns: [],
        keywords: ['valor', 'preco', 'preço', 'quanto custa', 'how much', 'cost', 'price', 'fee', 'pagar', 'pagamento', 'payment', 'parcela', 'installment'],
        priority: 8
    },

    // Specific visa questions - needs consultation
    niw_inquiry: {
        patterns: [/\bniw\b/i, /\beb-?2\s*niw\b/i, /national interest/i],
        keywords: ['niw', 'eb2', 'eb-2', 'national interest', 'interesse nacional'],
        priority: 7
    },

    eb1_inquiry: {
        patterns: [/\beb-?1[ab]?\b/i],
        keywords: ['eb1', 'eb-1', 'eb1a', 'eb-1a', 'eb1b', 'extraordinary', 'habilidade extraordinaria'],
        priority: 7
    },

    greencard_inquiry: {
        patterns: [/green\s*card/i],
        keywords: ['green card', 'greencard', 'residencia permanente', 'permanent residence'],
        priority: 7
    },

    work_visa_inquiry: {
        patterns: [/\bh-?1b\b/i, /\bl-?1[ab]?\b/i, /\bo-?1[ab]?\b/i],
        keywords: ['h1b', 'h-1b', 'l1', 'l-1', 'o1', 'o-1', 'trabalho', 'work visa', 'trabalhar', 'emprego'],
        priority: 6
    },

    investor_inquiry: {
        patterns: [/\be-?2\b/i],
        keywords: ['e2', 'e-2', 'investidor', 'investor', 'negocio', 'negócio', 'business', 'empresa'],
        priority: 6
    },

    family_inquiry: {
        patterns: [/\bk-?1\b/i],
        keywords: ['casado', 'casada', 'esposa', 'esposo', 'spouse', 'married', 'familia', 'família', 'family', 'noivo', 'noiva', 'fiance', 'k1'],
        priority: 6
    },

    // Urgent cases - needs immediate attention
    urgent: {
        patterns: [],
        keywords: ['urgente', 'urgent', 'emergencia', 'emergência', 'emergency', 'deporta', 'deportação', 'deportation', 'revogado', 'revoked', 'denied', 'negado', 'ilegal', 'overstay', 'expirado', 'expired'],
        priority: 10
    },

    // General greeting - start conversion
    greeting: {
        patterns: [/^(oi|olá|ola|hi|hello|hey|bom dia|boa tarde|boa noite|good morning|good afternoon|good evening|hola|buenas)/i],
        keywords: [],
        priority: 1
    },

    // Thank you - opportunity to close
    thanks: {
        patterns: [/^(obrigad|thank|gracias|valeu|brigad)/i],
        keywords: ['obrigado', 'obrigada', 'thank', 'thanks', 'gracias'],
        priority: 2
    },

    // Question - needs engagement
    question: {
        patterns: [/\?$/],
        keywords: ['como', 'quanto', 'onde', 'quando', 'qual', 'how', 'what', 'where', 'when', 'which', 'can i', 'posso', 'preciso'],
        priority: 3
    }
};

/**
 * Detect language from message
 */
function detectLanguage(message) {
    if (!message) return 'en';
    const msg = message.toLowerCase();

    const ptIndicators = [
        'olá', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'obrigado', 'obrigada',
        'por favor', 'como', 'quero', 'preciso', 'tenho', 'meu', 'minha', 'você',
        'voce', 'gostaria', 'poderia', 'seria', 'está', 'esta', 'são', 'sao',
        'não', 'nao', 'sim', 'qual', 'quando', 'onde', 'porque', 'então', 'entao'
    ];

    const esIndicators = [
        'hola', 'buenos', 'buenas', 'gracias', 'cómo', 'quiero', 'necesito',
        'tengo', 'usted', 'está', 'qué', 'cuándo', 'dónde', 'por favor'
    ];

    let ptScore = 0;
    let esScore = 0;

    for (const word of ptIndicators) {
        if (msg.includes(word)) ptScore++;
    }
    for (const word of esIndicators) {
        if (msg.includes(word)) esScore++;
    }

    if (ptScore > esScore && ptScore > 0) return 'pt';
    if (esScore > ptScore && esScore > 0) return 'es';
    return 'en';
}

/**
 * Match message to intent
 */
function matchIntent(message) {
    if (!message) return { intent: 'greeting', confidence: 0.1 };

    const msg = message.toLowerCase().trim();
    let bestMatch = { intent: 'greeting', confidence: 0.1 };

    for (const [intent, config] of Object.entries(INTENT_KEYWORDS)) {
        let score = 0;

        // Check patterns (regex)
        if (config.patterns) {
            for (const pattern of config.patterns) {
                if (pattern.test(msg)) {
                    score += 3;
                }
            }
        }

        // Check keywords
        if (config.keywords) {
            for (const keyword of config.keywords) {
                if (msg.includes(keyword.toLowerCase())) {
                    score += 1;
                }
            }
        }

        // Apply priority weight
        const weightedScore = score * (config.priority || 1);

        if (weightedScore > bestMatch.confidence) {
            bestMatch = { intent, confidence: weightedScore };
        }
    }

    return bestMatch;
}

/**
 * SYSTEM PROMPT - Professional, Human, Conversion-Focused
 * NO EMOJIS - Formal tone - Focus on scheduling meetings
 */
const SYSTEM_PROMPT = `Voce e um atendente do ${process.env.ORG_NAME || "CaseHub"}, escritorio de advocacia especializado em imigracao para os Estados Unidos.

DATA DE HOJE: {TODAY}
DIA DA SEMANA: {WEEKDAY}

REGRAS ABSOLUTAS DE TOM E ESTILO:
1. NUNCA use emojis em nenhuma circunstancia
2. NUNCA mencione que voce e uma IA, bot, assistente virtual ou automatizado
3. Mantenha tom FORMAL e PROFISSIONAL, mas humano e acolhedor
4. Use linguagem clara e direta, sem rodeios
5. Seja cordial mas objetivo - evite excesso de formalidades
6. Sempre assine como "Atenciosamente, ${process.env.ORG_NAME || "CaseHub"}"
7. Use o idioma do cliente (portugues, ingles ou espanhol)
8. Mensagens devem ter no maximo 4 paragrafos curtos
9. NUNCA mencione o nome do advogado. Use apenas "nosso advogado" ou "nosso advogado de imigracao"
10. NUNCA use "Dr.", "Esq.", ou qualquer nome proprio do advogado em nenhuma circunstancia

REGRAS DE NEGOCIO - NUNCA VIOLE (CRITICO - ILEGAL SE VIOLADO):
1. NUNCA de LEGAL ADVICE (aconselhamento juridico) - isso e ILEGAL
2. NUNCA explique requisitos especificos de vistos (EB-2 NIW, EB-1A, H-1B, etc)
3. NUNCA explique processos, formularios, prazos ou etapas de imigracao
4. NUNCA mencione a localizacao do escritorio (Connecticut, EUA, etc)
5. NUNCA mencione valores de honorarios do processo - APENAS a consulta $99
6. NUNCA prometa resultados ou prazos especificos
7. NUNCA sugira datas especificas para reuniao - use o link do Calendly

SOBRE CUSTOS E VALORES (MUITO IMPORTANTE):
- O UNICO valor que podemos mencionar e a consulta de $99 com nosso advogado
- Se perguntarem "quanto custa o processo?" ou "qual o valor?", responda:
  "Os custos variam dependendo do tipo de visto e da complexidade do caso. Na consulta com nosso advogado ($99), ele analisa seu caso e apresenta um orcamento detalhado com todas as opcoes."
- NUNCA mencione valores como $8.000, parcelas, planos de pagamento, ou qualquer outro numero
- Direcione SEMPRE para a consulta paga para discutir valores do processo

QUANDO CLIENTE PERGUNTAR SOBRE VISTOS OU PROCESSOS:
- NAO responda com detalhes tecnicos
- Diga que esse tipo de informacao requer analise juridica personalizada
- Apresente AMBAS as opcoes: reuniao gratuita para conhecer o escritorio E consulta paga ($99) para analise do caso

SEU OBJETIVO PRINCIPAL:
Converter o lead para agendar uma reuniao. SEMPRE apresente AS DUAS opcoes abaixo, NESTA ORDEM EXATA:

**HIERARQUIA DE LINKS (MUITO IMPORTANTE):**

PARA NOVOS LEADS (primeira conversa, perguntas gerais, leads que NUNCA agendaram):
>>> SEMPRE oferecer o link GRATUITO PRIMEIRO <<<

1. REUNIAO INICIAL GRATUITA (15 min) - OFERECA ESTA PRIMEIRO:
   Link: {CALENDLY_FREE}
   - GRATUITA, sem custo, sem compromisso
   - Para conhecer a equipe e tirar duvidas gerais
   - NAO inclui aconselhamento juridico
   - Ideal para primeira conversa

2. CONSULTA COM ADVOGADO ($99) - Ofereça como SEGUNDA opcao:
   Link: {CALENDLY_PAID}
   - Consulta PAGA de $99
   - Inclui analise personalizada do caso
   - Aconselhamento juridico com nosso advogado
   - Estrategia e proximos passos definidos
   - Para quem quer ir direto para analise completa

REGRA ABSOLUTA (NUNCA VIOLAR):
- SEMPRE mencione o link GRATUITO ({CALENDLY_FREE}) PRIMEIRO
- SEMPRE mencione os DOIS links em TODA resposta sobre reuniao
- NUNCA ofereça apenas o link pago ($99)
- NUNCA inverta a ordem (gratuito SEMPRE primeiro)

ESTRATEGIA DE CONVERSAO:
1. Responda a duvida do cliente de forma clara e breve
2. Relacione a situacao dele com a necessidade de uma reuniao
3. Apresente AMBAS as opcoes: gratuita PRIMEIRO, paga como alternativa avancada
4. Forneca os DOIS links e incentive o agendamento
5. Se o cliente hesitar, reforce os beneficios sem pressionar
6. SEMPRE termine a mensagem com uma variacao de "Nossa equipe ja vai te atender em breve!" para indicar que tera atendimento humano

EXEMPLO DE RESPOSTA CORRETA (novo lead perguntando sobre reuniao):

PT: "Para avaliar melhor sua situacao, oferecemos duas opcoes:

1. Reuniao GRATUITA de 15 minutos: {CALENDLY_FREE}
   (Ideal para conhecer nossa equipe e entender o basico do seu caso)

2. Consulta detalhada com nosso advogado ($99): {CALENDLY_PAID}
   (Analise juridica completa com estrategia personalizada)

Qual opcao prefere?

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}"

EN: "To better evaluate your situation, we offer two options:

1. FREE 15-minute meeting: {CALENDLY_FREE}
   (Perfect to meet our team and understand the basics of your case)

2. Detailed consultation with our attorney ($99): {CALENDLY_PAID}
   (Complete legal analysis with personalized strategy)

Which option would you prefer?

Warm regards,
${process.env.ORG_NAME || "CaseHub"}"

LEMBRETE FINAL: Use apenas "nosso advogado" - NUNCA nomes proprios, "Dr.", ou "Esq."

QUANDO SINALIZAR [PRECISA_HUMANO]:
- Perguntas sobre estrategia especifica do caso
- Cliente irritado ou insatisfeito
- Reclamacoes sobre erro do escritorio
- Questoes sobre valores detalhados (exceto $99)
- Qualquer situacao que voce nao tenha certeza

CONTEXTO DA CONVERSA:
Nome do cliente: {CLIENT_NAME}
Interesse declarado: {INTEREST}
Idioma detectado: {LANGUAGE}

HISTORICO RECENTE:
{HISTORY}

MENSAGEM ATUAL DO CLIENTE:
{MESSAGE}

Responda de forma profissional, humanizada e focada em converter para agendamento. Sem emojis.`;

/**
 * Generate humanized response via LLM
 */
async function generateHumanizedResponse(message, lead, conversationHistory, isActiveClient = false) {
    const language = detectLanguage(message);
    const intent = matchIntent(message);
    const historyText = formatHistory(conversationHistory);

    // Current date info
    const now = new Date();
    const weekdays = {
        pt: ['Domingo', 'Segunda-feira', 'Terca-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sabado'],
        en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
        es: ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']
    };
    const today = now.toLocaleDateString(language === 'pt' ? 'pt-BR' : (language === 'es' ? 'es-ES' : 'en-US'));
    const weekday = (weekdays[language] || weekdays['en'])[now.getDay()];

    // Correção #7: Modificar SYSTEM_PROMPT para clientes ativos (SOMENTE /meeting)
    let systemPrompt = SYSTEM_PROMPT;
    if (isActiveClient) {
        systemPrompt = SYSTEM_PROMPT + `

**ATENÇÃO: ESTE É UM CLIENTE ATIVO (já pagou ou está em processo)**

PARA CLIENTES ATIVOS:
- NUNCA ofereça o link gratuito (/freecall)
- Ofereça SOMENTE o link de consulta paga: ${CALENDLY_PAID}
- Cliente ativo = já tem relacionamento com o escritório
- Reunião gratuita é para NOVOS leads apenas
- Use tom mais próximo e menos "vendedor"

EXEMPLO de resposta para cliente ativo:
"Olá! Notei que você entrou em contato. Como posso te ajudar hoje? Se precisar agendar uma reunião com nossa equipe jurídica, você pode usar este link: ${CALENDLY_PAID}

Estamos à disposição!
${process.env.ORG_NAME || "CaseHub"}"
`;
    }

    const prompt = systemPrompt
        .replace('{TODAY}', today)
        .replace('{WEEKDAY}', weekday)
        .replace('{CALENDLY_FREE}', CALENDLY_FREE)
        .replace('{CALENDLY_PAID}', CALENDLY_PAID)
        .replace('{CLIENT_NAME}', lead.client_name || lead.whatsapp_name || 'Cliente')
        .replace('{INTEREST}', lead.visa_interest || 'Nao especificado')
        .replace('{LANGUAGE}', language === 'pt' ? 'Portugues' : (language === 'es' ? 'Espanhol' : 'Ingles'))
        .replace('{HISTORY}', historyText || 'Primeira mensagem')
        .replace('{MESSAGE}', message);

    try {
        const response = await fetch(GEMINI_URL + '?key=' + GEMINI_API_KEY, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.6,  // Slightly lower for more consistent professional tone
                    maxOutputTokens: 400,
                    topP: 0.85,
                    topK: 30
                },
                safetySettings: [
                    { category: "HARM_CATEGORY_HARASSMENT", threshold: "BLOCK_MEDIUM_AND_ABOVE" },
                    { category: "HARM_CATEGORY_HATE_SPEECH", threshold: "BLOCK_MEDIUM_AND_ABOVE" },
                    { category: "HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold: "BLOCK_MEDIUM_AND_ABOVE" },
                    { category: "HARM_CATEGORY_DANGEROUS_CONTENT", threshold: "BLOCK_MEDIUM_AND_ABOVE" }
                ]
            })
        });

        if (!response.ok) {
            const errBody = await response.text(); console.error('[LLM-CHATBOT] Gemini error:', response.status, errBody);
            return { success: false, needsHuman: true };
        }

        const data = await response.json();
        const responseText = data.candidates?.[0]?.content?.parts?.[0]?.text;

        if (!responseText) {
            return { success: false, needsHuman: true };
        }

        const needsHuman = responseText.includes('[PRECISA_HUMANO]');
        let cleanResponse = responseText.replace('[PRECISA_HUMANO]', '').trim();

        // Remove any emojis that might have slipped through
        cleanResponse = cleanResponse.replace(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{1F600}-\u{1F64F}]|[\u{1F680}-\u{1F6FF}]/gu, '');

        // Sanitize configured attorney names so the bot does not invent or expose a person.
        const configuredAttorneyName = (process.env.PRIMARY_ATTORNEY_NAME || '').trim();
        if (configuredAttorneyName) {
            const escapedName = configuredAttorneyName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const attorneyNamePattern = new RegExp(`\\b(?:Dr\\.?\\s*)?${escapedName}(?:\\s+\\w+)?(?:,?\\s*Esq\\.?)?\\b`, 'gi');
            cleanResponse = cleanResponse.replace(attorneyNamePattern, 'nosso advogado');
        }

        // CRITICAL: Block legal advice - unauthorized practice of law
        // Priority guard: prevent unauthorized legal advice from automated replies.
        let legalAdviceDetected = false;
        let blockedPattern = '';
        for (const pattern of LEGAL_ADVICE_PATTERNS) {
            if (pattern.test(cleanResponse)) {
                console.error('[LEGAL-ADVICE-FILTER] ⚠️  BLOCKED - Pattern:', pattern.source);
                console.error('[LEGAL-ADVICE-FILTER] Original response:', cleanResponse.substring(0, 200));
                legalAdviceDetected = true;
                blockedPattern = pattern.source;
                break;
            }
        }

        if (legalAdviceDetected) {
            // REPLACE response with safe redirection to consultation
            const orgName = process.env.ORG_NAME || "CaseHub";
            const safeResponses = {
                pt: "Para avaliar sua situação específica e fornecer orientações adequadas, recomendamos agendar uma consulta com nossa equipe. Oferecemos:\n\n1. Reunião GRATUITA de 15 minutos: " + CALENDLY_FREE + "\n   (Para conhecer o escritório e tirar dúvidas gerais)\n\n2. Consulta detalhada com nosso advogado ($99): " + CALENDLY_PAID + "\n   (Para análise jurídica personalizada do seu caso)\n\nQual opção prefere?\n\nAtenciosamente,\n" + orgName,
                en: "To properly evaluate your specific situation and provide appropriate guidance, we recommend scheduling a consultation with our team. We offer:\n\n1. FREE 15-minute meeting: " + CALENDLY_FREE + "\n   (To learn about our firm and ask general questions)\n\n2. Detailed consultation with our attorney ($99): " + CALENDLY_PAID + "\n   (For personalized legal analysis of your case)\n\nWhich option would you prefer?\n\nWarm regards,\n" + orgName,
                es: "Para evaluar adecuadamente su situación específica y brindar orientación apropiada, recomendamos agendar una consulta con nuestro equipo. Ofrecemos:\n\n1. Reunión GRATUITA de 15 minutos: " + CALENDLY_FREE + "\n   (Para conocer el despacho y hacer preguntas generales)\n\n2. Consulta detallada con nuestro abogado ($99): " + CALENDLY_PAID + "\n   (Para análisis legal personalizado de su caso)\n\n¿Cuál opción prefiere?\n\nSaludos cordiales,\n" + orgName
            };

            cleanResponse = safeResponses[language] || safeResponses.en;

            console.warn('[LEGAL-ADVICE-FILTER] Response replaced with safe consultation redirect');

            return {
                success: true,
                response: cleanResponse,
                needsHuman: true,  // Flag for human review
                intent: intent.intent,
                language: language,
                confidence: intent.confidence,
                blocked: 'legal_advice',  // Metadata for logging
                blockedPattern: blockedPattern
            };
        }

        return {
            success: true,
            response: cleanResponse,
            needsHuman: needsHuman,
            intent: intent.intent,
            language: language,
            confidence: intent.confidence
        };

    } catch (error) {
        console.error('[LLM-CHATBOT] Error:', error.message);
        return { success: false, needsHuman: true };
    }
}

function formatHistory(messages) {
    if (!messages || messages.length === 0) return '';
    return messages
        .slice(-8)
        .map(m => (m.role === 'user' ? 'Cliente' : 'Atendente') + ': ' + m.content)
        .join('\n');
}

/**
 * Main message processing function
 * @param {string} message - User message
 * @param {object} lead - Lead data from database
 * @param {object} db - Database connection
 * @param {boolean} isActiveClient - Whether lead is an active client (Correção #7)
 */
async function processMessage(message, lead, db, isActiveClient = false) {
    const phone = lead.phone;
    const clientName = lead.client_name || lead.whatsapp_name || 'Unknown';
    const language = detectLanguage(message);

    console.log('[LLM-CHATBOT-V3] Processing:', phone, '-', message.substring(0, 50));
    if (isActiveClient) {
        console.log('[LLM-CHATBOT-V3] ACTIVE CLIENT - will offer ONLY /meeting link');
    }

    // 1. Check for non-leads first
    const nonLeadCheck = checkNonLead(message, language);
    if (nonLeadCheck.isNonLead) {
        console.log('[LLM-CHATBOT-V3] Non-lead detected:', nonLeadCheck.type);

        llmMonitor.logActivity({
            phone: phone,
            clientName: clientName,
            messageIn: message,
            messageOut: nonLeadCheck.response || '',
            intent: 'non_lead_' + nonLeadCheck.type,
            template: 'non_lead',
            language: language,
            needsHuman: false,
            success: true
        });

        if (nonLeadCheck.response) {
            return {
                shouldRespond: true,
                response: nonLeadCheck.response,
                needsHuman: false,
                metadata: {
                    intent: 'non_lead_' + nonLeadCheck.type,
                    isNonLead: true
                }
            };
        } else {
            // Spam - don't respond
            return {
                shouldRespond: false,
                needsHuman: false,
                metadata: {
                    intent: 'spam',
                    isNonLead: true
                }
            };
        }
    }

    // 2. Get conversation history
    let history = [];
    try {
        if (db && typeof db.getConversationHistory === 'function') {
            history = await db.getConversationHistory(phone, 8);
        }
    } catch (e) {
        console.log('[LLM-CHATBOT-V3] Error getting history:', e.message);
    }

    // 3. Generate response (Correção #7: pass isActiveClient flag)
    const result = await generateHumanizedResponse(message, lead, history, isActiveClient);

    if (!result.success) {
        console.log('[LLM-CHATBOT-V3] Failed - forwarding to human');

        llmMonitor.logActivity({
            phone: phone,
            clientName: clientName,
            messageIn: message,
            messageOut: '',
            intent: 'error',
            template: 'none',
            language: language,
            needsHuman: true,
            success: false,
            error: 'LLM generation failed'
        });

        return { shouldRespond: false, needsHuman: true };
    }

    console.log('[LLM-CHATBOT-V3] Intent:', result.intent, '| Confidence:', result.confidence, '| NeedsHuman:', result.needsHuman);

    llmMonitor.logActivity({
        phone: phone,
        clientName: clientName,
        messageIn: message,
        messageOut: result.response,
        intent: result.intent,
        template: 'llm_generated',
        language: result.language,
        needsHuman: result.needsHuman,
        success: true
    });

    return {
        shouldRespond: true,
        response: result.response,
        needsHuman: result.needsHuman,
        metadata: {
            intent: result.intent,
            language: result.language,
            confidence: result.confidence
        }
    };
}

module.exports = {
    processMessage,
    generateHumanizedResponse,
    checkNonLead,
    matchIntent,
    detectLanguage,
    CALENDLY_FREE,
    CALENDLY_PAID
};
