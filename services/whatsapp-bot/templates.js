/**
 * Templates - WhatsApp Bot Response Templates
 * CaseHub
 * v1.0 - 30/01/2026
 */

const TEMPLATES = [
    // ===== GREETING (Primeiro Contato) =====
    { id: 1, cat: "Greeting", name: "Clientes Novos (EN)", text: `Hello! Thanks for reaching out to the ${process.env.ORG_NAME || "CaseHub"}.

Could you share your name and how we can help?

You can schedule a free intro call (15 min): ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall
Or a consultation with our attorney ($99): ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Our team will get back to you shortly!` },

    { id: 2, cat: "Greeting", name: "Clientes Novos (PT)", text: `Olá! Obrigado pelo contato com o ${process.env.ORG_NAME || "CaseHub"}.

Pode nos dizer seu nome e como podemos ajudar?

Agende uma reunião gratuita de 15 min: ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall
Ou uma consulta com nosso advogado ($99): ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Nossa equipe já vai te atender em breve!` },

    // ===== AGENDA (Reuniões) =====
    { id: 5, cat: "Agenda", name: "Confirmação de Reunião (EN)", text: `Hello,

Your meeting with the Attorney has been confirmed for [DATE] at [TIME] EST.

Here is your link to join:
[MEETING_LINK]

We look forward to meeting with you\!

Please don not hesitate to let us know in case you have any questions.

Warm Regards,` },

    { id: 6, cat: "Agenda", name: "Confirmação de Reunião (PT)", text: `Olá,

Sua reunião com o advogado está confirmada para dia [DATE], às [TIME] (EST).

Segue abaixo o link de acesso:
[MEETING_LINK]

Caso surja qualquer dúvida, não hesite em nos contatar. Estamos à disposição para auxiliá-lo no que for necessário\!

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` },

    { id: 7, cat: "Agenda", name: "Marcando Reunião (EN)", text: `Hello\!

We have availability for your meeting with Attorney on [DATE] at [TIME] EST.

If this time is not convenient, feel free to suggest an alternative.

Once confirmed, I will send a calendar invite with all the details.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}.` },

    // ===== NOVO: Marcando Reunião (PT) =====
    { id: 32, cat: "Agenda", name: "Marcando Reunião (PT)", text: `Olá\!

Temos disponibilidade para sua reunião com o Advogado no dia [DATA] às [HORARIO] (horário de Brasília).

Se esse horário não for conveniente, fique à vontade para sugerir uma alternativa.

Após a confirmação, enviarei um convite com todos os detalhes.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` },

    // ===== PAGAMENTO =====
    { id: 9, cat: "Pagamento", name: "Info Pagamento (EN)", text: `Dear Client,

We would like to share the payment options available for your visa process. Please find the details below:

Attorney Fees: USD $[VALOR]

Payment Methods:
- Bank Transfer - You may complete the payment via U.S. or international bank transfer to a US bank account. Bank details will be provided once you confirm this option.
- Credit or Debit Card (via Stripe link) - You can make a secure payment through a Stripe link that we will send to you upon request.

Payment Plans and Discounts:
- 10% OFF – Full Payment Upfront
- 5% OFF – Split Payment (50/50)
- Regular Plan – Monthly Installments (half upfront, remaining in 5 monthly installments)

Please let us know which payment option and plan you prefer so we can provide the appropriate instructions and links.

Warm regards,` },

    // ===== NOVO: Valores NIW (PT) =====
    { id: 33, cat: "Pagamento", name: "Valores NIW (PT)", text: `Olá [NOME]!

Obrigado pelo interesse no processo EB-2 NIW.

Sobre valores:
- Honorários advocatícios: USD $8,000
- Taxas governamentais (USCIS): ~$1,500-2,000
- Premium Processing (opcional): $2,805

Formas de pagamento:
- 10% desconto - Pagamento à vista
- 5% desconto - Parcelado em 2x (50/50)
- Parcelamento regular - 50% entrada + 5 parcelas mensais

Temos duas opções de reunião:

📞 Ligação introdutória GRATUITA (15 min):
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

💼 Consulta com advogado ($99):
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Qual você prefere?

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` },

    // ===== VISTOS =====
    { id: 16, cat: "Vistos", name: "Info EB-2 NIW", text: `O visto EB-2 NIW (National Interest Waiver) é uma categoria de Green Card para profissionais com grau avançado ou habilidade excepcional.

Requisitos principais:
- Mestrado ou equivalente, OU
- Graduação + 5 anos de experiência
- Trabalho deve beneficiar os EUA

Vantagens:
- Não precisa de oferta de emprego
- Não precisa de Labor Certification
- Pode trabalhar por conta própria

Tempo médio: 12-18 meses

Gostaria de agendar uma consulta para avaliar seu caso?
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting` },

    { id: 17, cat: "Vistos", name: "Info EB-1A", text: `O visto EB-1A (Extraordinary Ability) é para profissionais com habilidade extraordinária em sua área.

Critérios (precisa de 3):
- Prêmios/reconhecimento
- Publicações
- Contribuições originais
- Participação como juiz
- Salário alto
- Artigos sobre você
- Exposições (artes)
- Liderança em organizações
- Membros de associações
- Trabalho comercial

Vantagens:
- Prioridade máxima
- Sem Labor Certification
- Processo mais rápido

Gostaria de avaliar se você se qualifica?
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting` },

    { id: 18, cat: "Vistos", name: "Processo NIW Detalhado", text: `Gostaríamos de informar que, no processo NIW, nossa equipe cuidará de todas as etapas da aplicação, incluindo o preenchimento dos formulários necessários: G-1145, G-28, I-907 (caso opte pelo premium processing), I-140, ETA 9089, Appendix A e Final Determination.

Além disso, nossa equipe redige as cartas de recomendação, o personal statement ou proposed endeavor, revisa o business plan, redige o job offer, caso o cliente tenha um empregador em potencial, e prepara o legal brief. Também organizamos toda a documentação e preparamos o pacote final para envio.

O cliente tem direito a suporte contínuo e reuniões ilimitadas com nossa equipe legal e advogados durante todo o processo.

Estamos à disposição para esclarecer quaisquer dúvidas e garantir que o processo seja conduzido de forma completa e segura.` },

    // ===== FOLLOW-UP =====
    { id: 19, cat: "Follow-up", name: "Encaminhamento (EN)", text: `Hello\!

Your message has been sent to our legal team for review. We will get back to you with an update as soon as possible.

Please do not hesitate to let us know in case you have any questions.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}.` },

    { id: 20, cat: "Follow-up", name: "Encaminhamento (PT)", text: `Olá\!

Sua mensagem foi encaminhada para nossa equipe jurídica para análise. Entraremos em contato com você com uma atualização assim que possível.

Por favor, não hesite em nos avisar caso tenha alguma dúvida.

Atenciosamente,` },

    { id: 21, cat: "Follow-up", name: "Follow-up 1 (4 dias)", text: `Hello\!

We have not heard from you.

Would you like to schedule a free intro meeting? Or maybe a consultation with our attorneys?

We are here to help\!

Thank you\!` },

    { id: 23, cat: "Follow-up", name: "Aguardando Docs", text: `Olá\! Esperamos que esteja bem.

Gostaríamos de lembrar que ainda estamos aguardando os seguintes documentos:

[LISTA DE DOCUMENTOS]

Assim que recebermos, daremos continuidade ao processo.

Precisa de ajuda com algum documento específico?` },

    // ===== NOVO: Credenciais/Legitimidade =====
    { id: 34, cat: "Suporte", name: "Credenciais/Legitimidade", text: `Olá\!

Obrigado pela pergunta - é muito importante verificar a legitimidade de qualquer escritório de imigração.

Sobre o ${process.env.ORG_NAME || "CaseHub"}:
✅ Escritório registrado nos EUA
✅ Nosso advogado - Licenciado em NY e CT
✅ Membro da AILA (American Immigration Lawyers Association)
✅ Mestrado em Direito de Imigração

Você pode verificar a licença do advogado em:
- NY: https://iapps.courts.state.ny.us/attorneyservices
- CT: https://www.jud.ct.gov/attorneyfirminquiry

Ficamos à disposição para esclarecer qualquer dúvida\!` },

    // ===== NOVO: Suporte Técnico / Link Quebrado =====
    { id: 35, cat: "Suporte", name: "Suporte Técnico / Link Quebrado", text: `Olá\!

Pedimos desculpas pelo inconveniente com o link.

Aqui estão os links corretos:

📅 Reunião Introdutória GRATUITA:
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

💼 Consulta com Advogado ($99):
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Por favor, tente novamente. Se ainda tiver problemas, me avise\!

Obrigado pela paciência\!` },

    // ===== NOVO: Caso Urgente (EN) =====
    { id: 36, cat: "Urgente", name: "Caso Urgente (EN)", text: `Hello [NAME],

I understand you are in a time-sensitive situation.

We can prioritize your case. Here are your options:

1️⃣ Immediate Consultation - Available this week
   Schedule: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

2️⃣ Rush Processing - For urgent timelines, we offer expedited service

Please share more details about your deadline so we can best assist you.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}` },

    // ===== NOVO: Visto Revogado / Caso Complexo =====
    { id: 37, cat: "Urgente", name: "Visto Revogado / Caso Complexo", text: `Olá\!

Entendemos sua situação - casos de visto revogado são delicados, mas trabalhamos com eles regularmente.

Para seu caso específico, recomendamos uma consulta com o advogado ($99) para:
- Analisar o motivo da revogação
- Avaliar suas opções
- Definir a melhor estratégia

Agende aqui: ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Temos horários disponíveis esta semana\!

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` },

    // ===== NOVO: Desculpas Demora =====
    { id: 38, cat: "Follow-up", name: "Desculpas Demora", text: `Olá\!

Pedimos desculpas pela demora no retorno.

Estamos aqui para ajudá-lo\! Em que posso auxiliar?

Se preferir, agende uma reunião gratuita de 15 min:
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` },

    // ===== HANDOFF =====
    { id: 26, cat: "Handoff", name: "Assumindo Conversa", text: `Olá\! Meu nome é [NOME] e vou continuar seu atendimento a partir de agora.

Já vi o histórico da sua conversa. Como posso ajudá-lo(a) hoje?` },

    { id: 27, cat: "Handoff", name: "Voltando ao Bot", text: `Obrigado pelo contato\! A partir de agora, nosso assistente virtual continuará disponível para dúvidas gerais.

Para falar com um humano novamente, basta digitar "atendente" ou "humano".

Tenha um ótimo dia\!` },
    // ===== v10.6: Templates para LLM Chatbot =====
    { id: 39, cat: "Handoff", name: "Verificando Info", text: `Ola!

Essa e uma boa pergunta. Vou verificar com nossa equipe juridica para lhe dar uma resposta precisa.

Enquanto isso, gostaria de agendar uma reuniao para conversarmos melhor sobre seu caso?

Reuniao Gratuita (15 min):
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` },

    { id: 40, cat: "Agenda", name: "Incentivar Agendamento", text: `Ola [NOME]!

Obrigado pelo interesse em nossos servicos.

Para entender melhor seu caso e oferecer a melhor orientacao, recomendo agendar uma conversa com nossa equipe:

Reuniao Introdutoria GRATUITA (15 min):
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Nessa reuniao, voce pode:
- Conhecer nosso trabalho
- Tirar duvidas gerais
- Entender os proximos passos

Posso agendar para voce?

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}` }
];

/**
 * Get template by ID
 */
function getTemplateById(id) {
    return TEMPLATES.find(t => t.id === id);
}

/**
 * Get templates by category
 */
function getTemplatesByCategory(category) {
    return TEMPLATES.filter(t => t.cat === category);
}

/**
 * Replace template variables
 */
function replaceVars(text, data = {}) {
    let result = text;
    
    // Standard replacements
    const replacements = {
        "[NOME]": data.nome || data.client_name || data.whatsapp_name || "[NOME]",
        "[NAME]": data.nome || data.client_name || data.whatsapp_name || "[NAME]",
        "[DATA]": data.data || new Date().toLocaleDateString("pt-BR"),
        "[DATE]": data.date || new Date().toLocaleDateString("en-US"),
        "[HORARIO]": data.horario || "[HORARIO]",
        "[TIME]": data.time || "[TIME]",
        "[EMAIL]": data.email || "[EMAIL]",
        "[TELEFONE]": data.telefone || data.phone || "[TELEFONE]",
        "[VALOR]": data.valor || "[VALOR]"
    };
    
    for (const [key, value] of Object.entries(replacements)) {
        result = result.replace(new RegExp(key.replace(/[[\]]/g, "\\$&"), "gi"), value);
    }
    
    return result;
}

module.exports = {
    TEMPLATES,
    getTemplateById,
    getTemplatesByCategory,
    replaceVars
};
