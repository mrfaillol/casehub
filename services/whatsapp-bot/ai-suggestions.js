/**
 * AI Suggestions Module - Gemini API
 * CaseHub
 * Generates response suggestions for WhatsApp chat
 */

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent';

const SYSTEM_PROMPT = `Voce e um assistente do ${process.env.ORG_NAME || "CaseHub"}, escritorio de advocacia especializado em imigracao para os EUA.
Seu papel e ajudar os atendentes a responder mensagens de WhatsApp de clientes potenciais.

Diretrizes:
- Gere sugestoes de resposta profissionais e amigaveis
- Use portugues brasileiro
- Seja conciso (maximo 2-3 frases)
- Foque em empatia com a situacao do cliente
- Mencione proximos passos quando apropriado
- NAO faca promessas sobre resultados de casos
- NAO de aconselhamento juridico especifico
- Sugira agendar uma consulta para casos complexos

Tipos de visto que trabalhamos:
- EB-2 NIW (National Interest Waiver)
- EB-1A (Extraordinary Ability)
- E-2 (Treaty Investor)
- L-1 (Intracompany Transfer)
- H-1B (Specialty Occupation)
- Green Card (varias categorias)`;

/**
 * Generate a response suggestion based on conversation history
 * @param {string} historyText - Formatted conversation history
 * @param {string} lastMessage - Last message from the user
 * @returns {Promise<string|null>} - Suggested response or null
 */
async function generateSuggestion(historyText, lastMessage) {
    if (!GEMINI_API_KEY) {
        console.log('[AI] No GEMINI_API_KEY configured');
        return null;
    }

    const prompt = `${SYSTEM_PROMPT}

Historico da conversa:
${historyText}

Ultima mensagem do cliente: ${lastMessage}

Sugira uma resposta apropriada para o atendente enviar:`;

    try {
        const response = await fetch(`${GEMINI_URL}?key=${GEMINI_API_KEY}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{
                    parts: [{ text: prompt }]
                }],
                generationConfig: {
                    temperature: 0.7,
                    maxOutputTokens: 250,
                    topP: 0.8,
                    topK: 40
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
            console.error('[AI] Gemini API error:', response.status, await response.text());
            return null;
        }

        const data = await response.json();
        const suggestion = data.candidates?.[0]?.content?.parts?.[0]?.text;

        if (suggestion) {
            // Clean up the suggestion (remove quotes if wrapped)
            let cleaned = suggestion.trim();
            if ((cleaned.startsWith('"') && cleaned.endsWith('"')) ||
                (cleaned.startsWith("'") && cleaned.endsWith("'"))) {
                cleaned = cleaned.slice(1, -1);
            }
            console.log('[AI] Generated suggestion:', cleaned.substring(0, 50) + '...');
            return cleaned;
        }

        return null;
    } catch (error) {
        console.error('[AI] Error generating suggestion:', error.message);
        return null;
    }
}

/**
 * Format conversation history for the prompt
 * @param {Array} messages - Array of message objects
 * @returns {string} - Formatted history
 */
function formatHistory(messages) {
    return messages.map(m => {
        const sender = m.role === 'user' ? 'Cliente' : 'Atendente';
        return `${sender}: ${m.content}`;
    }).join('\n');
}

const CASE_SUMMARY_PROMPT = `Voce e um assistente do ${process.env.ORG_NAME || "CaseHub"} especializado em resumir casos de imigracao.

Analise os dados da lead e historico de conversas para gerar um resumo estruturado.

Formato do resumo (OBRIGATORIO):
RESUMO DO CASO
==============
Nome: [nome do cliente]
Interesse: [tipo de visto/processo]
Status: [frio/morno/quente baseado no score e engajamento]
Urgencia: [sim/nao]

SITUACAO ATUAL
- [bullet points com informacoes relevantes extraidas da conversa]

PROXIMOS PASSOS SUGERIDOS
1. [acao recomendada]
2. [acao recomendada]

TEMPLATE RECOMENDADO
[nome do template mais adequado: greeting, ask_info, offer_free, offer_paid, followup, etc]

Regras:
- Seja conciso e direto
- Extraia informacoes concretas da conversa
- Se nao houver informacao suficiente, indique "Informacao nao disponivel"
- Classifique urgencia baseado em palavras como "urgente", "prazo", "deportacao", etc.
- Recomende template baseado na situacao atual`;

/**
 * Generate a case summary based on lead data and conversation history
 * @param {Object} leadData - Lead information from database
 * @param {Array} messages - Array of message objects
 * @returns {Promise<Object|null>} - Structured case summary or null
 */
async function generateCaseSummary(leadData, messages) {
    if (!GEMINI_API_KEY) {
        console.log('[AI] No GEMINI_API_KEY configured for case summary');
        return null;
    }

    const historyText = formatHistory(messages.slice(-20)); // Last 20 messages

    const leadInfo = `
Dados da Lead:
- Nome: ${leadData.client_name || leadData.whatsapp_name || 'Nao informado'}
- Telefone: ${leadData.phone || 'N/A'}
- Email: ${leadData.email || 'Nao informado'}
- Interesse: ${leadData.visa_interest || 'Nao especificado'}
- Score: ${leadData.lead_score || 0}
- Status: ${leadData.lead_status || 'cold'}
- Urgente: ${leadData.is_urgent ? 'Sim' : 'Nao'}
- Estado conversa: ${leadData.conversation_state || 'N/A'}
- Data primeiro contato: ${leadData.created_at || 'N/A'}
- Ultima interacao: ${leadData.last_interaction || 'N/A'}
`;

    const prompt = `${CASE_SUMMARY_PROMPT}

${leadInfo}

Historico da Conversa (ultimas mensagens):
${historyText || 'Nenhuma mensagem registrada'}

Gere o resumo do caso:`;

    try {
        const response = await fetch(`${GEMINI_URL}?key=${GEMINI_API_KEY}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{
                    parts: [{ text: prompt }]
                }],
                generationConfig: {
                    temperature: 0.3, // Lower temperature for more consistent output
                    maxOutputTokens: 500,
                    topP: 0.8,
                    topK: 40
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
            console.error('[AI] Gemini API error (case summary):', response.status, await response.text());
            return null;
        }

        const data = await response.json();
        const summary = data.candidates?.[0]?.content?.parts?.[0]?.text;

        if (summary) {
            console.log('[AI] Generated case summary for:', leadData.phone);

            // Parse the summary to extract recommended template
            let recommendedTemplate = null;
            const templateMatch = summary.match(/TEMPLATE RECOMENDADO[\s\n]*([a-z_]+)/i);
            if (templateMatch) {
                recommendedTemplate = templateMatch[1].toLowerCase();
            }

            return {
                summary: summary.trim(),
                recommendedTemplate,
                generatedAt: new Date().toISOString()
            };
        }

        return null;
    } catch (error) {
        console.error('[AI] Error generating case summary:', error.message);
        return null;
    }
}

/**
 * Generate conversation context/summary for quick understanding
 * @param {string} historyText - Formatted conversation history
 * @returns {Promise<Object|null>} - Context object with stage, interest, nextStep
 */
async function generateConversationContext(historyText) {
    if (!GEMINI_API_KEY) {
        console.log('[AI-CONTEXT] No GEMINI_API_KEY configured');
        return null;
    }

    if (!historyText || historyText.trim().length < 10) {
        return null;
    }

    const prompt = `Analise esta conversa de atendimento de imigração e extraia:

1. ESTÁGIO: Escolha UM entre:
   - Novo Lead
   - Demonstrando Interesse
   - Agendando Consulta
   - Cliente Ativo
   - Aguardando Resposta
   - Follow-up

2. INTERESSE: Escolha UM entre:
   - EB-2 NIW
   - EB-1A
   - E-2
   - L-1
   - H-1B
   - Green Card
   - Múltiplos Vistos
   - Dúvida Geral
   - Não Identificado

3. PRÓXIMO PASSO: Uma frase curta (max 10 palavras) recomendando a ação do atendente.

Histórico da conversa:
${historyText}

Responda APENAS no formato JSON exato abaixo, sem explicações:
{"stage": "...", "interest": "...", "nextStep": "..."}`;

    try {
        const response = await fetch(`${GEMINI_URL}?key=${GEMINI_API_KEY}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{
                    parts: [{ text: prompt }]
                }],
                generationConfig: {
                    temperature: 0.3,
                    maxOutputTokens: 100,
                    topP: 0.8,
                    topK: 40
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
            console.error('[AI-CONTEXT] Gemini API error:', response.status);
            return null;
        }

        const data = await response.json();
        const text = data.candidates?.[0]?.content?.parts?.[0]?.text;

        if (text) {
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                try {
                    const context = JSON.parse(jsonMatch[0]);
                    console.log('[AI-CONTEXT] Generated:', JSON.stringify(context));
                    return context;
                } catch (e) {
                    console.error('[AI-CONTEXT] JSON parse error:', e.message);
                }
            }
        }

        return null;
    } catch (error) {
        console.error('[AI-CONTEXT] Error:', error.message);
        return null;
    }
}

module.exports = {
    generateSuggestion,
    generateCaseSummary,
    generateConversationContext,
    formatHistory
};
