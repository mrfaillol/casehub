/**
 * Sistema de Idiomas - WhatsApp Bot
 * CaseHub
 * v1.1 - Suporte para PT, EN, ES (com acentos corrigidos)
 */

// Mapeamento de DDI para idioma
const COUNTRY_LANGUAGE = {
  // Português
  '55': 'pt',  // Brasil
  '351': 'pt', // Portugal

  // Espanhol
  '54': 'es',  // Argentina
  '56': 'es',  // Chile
  '57': 'es',  // Colombia
  '52': 'es',  // México
  '51': 'es',  // Peru
  '58': 'es',  // Venezuela
  '593': 'es', // Equador
  '591': 'es', // Bolivia
  '595': 'es', // Paraguai
  '598': 'es', // Uruguai
  '506': 'es', // Costa Rica
  '503': 'es', // El Salvador
  '502': 'es', // Guatemala
  '504': 'es', // Honduras
  '505': 'es', // Nicaragua
  '507': 'es', // Panama
  '53': 'es',  // Cuba
  '809': 'es', // República Dominicana
  '1809': 'es',
  '1829': 'es',
  '1849': 'es',
  '34': 'es',  // Espanha

  // Inglês (default)
  '1': 'en',   // EUA/Canadá
  '44': 'en',  // Reino Unido
  '61': 'en',  // Austrália
  '64': 'en',  // Nova Zelândia
  '27': 'en',  // África do Sul
  '91': 'en',  // Índia
  '63': 'en',  // Filipinas
};

// Textos em cada idioma
const MESSAGES = {
  // ===================== PORTUGUÊS =====================
  pt: {
    // NOVO FLUXO - Human Handoff
    welcome_handoff: `Olá! Obrigado por entrar em contato com o ${process.env.ORG_NAME || "CaseHub"}.

Um membro da nossa equipe já vai te atender em breve! 🙌

Enquanto isso, você pode agendar:

*1. *Reunião GRATUITA* - Informações gerais sobre imigração (sem aconselhamento jurídico)
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

*2. *Consulta com Advogado* ($99) - Aconselhamento jurídico personalizado
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Responda 1 ou 2 para saber mais, ou aguarde nosso atendimento.`,

    option_one_response: `Você pode agendar sua reunião GRATUITA diretamente aqui:
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

É uma conversa de 15 minutos sobre informações gerais de imigração.

Nossa equipe já vai te atender em breve! 🙌`,

    option_two_response: `Você pode agendar sua consulta com advogado ($99) diretamente aqui:
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Nessa consulta você recebe aconselhamento jurídico personalizado.

Nossa equipe já vai te atender em breve! 🙌`,

    // FLUXO ANTIGO (mantido para compatibilidade)
    welcome: `Olá! Bem-vindo ao ${process.env.ORG_NAME || "CaseHub"}!

Sou a assistente virtual do escritório. Para te direcionar melhor, qual é o seu nome?`,

    ask_name_again: `Desculpe, não entendi bem. Pode me dizer apenas seu nome?`,

    ask_interest: (name) => `Prazer, ${name}!

Qual é o seu interesse? Digite o número:

1 - Trabalhar nos EUA
2 - Morar nos EUA (Green Card)
3 - Investir nos EUA
4 - Reunir família
5 - Outros`,

    ask_email: (interest) => `Anotei: ${interest}.

Qual seu email para contato? (ou digite "pular" se preferir)`,

    ask_consultation_type: (name) => `Ótimo, ${name}!

Temos duas opções para você:

*1. *Ligação introdutória GRATUITA*
   Conheça nossa equipe, tire dúvidas gerais sobre processos, prazos e tipos de vistos.

*2. *Consulta com advogado (US$99 / R$499)*
   Análise específica do seu caso com estratégia personalizada.

Digite 1 ou 2:`,

    invalid_consultation_choice: `Por favor, digite apenas 1 ou 2:

*1. Ligação introdutória GRATUITA
*2. Consulta com advogado (US$99 / R$499)`,

    free_consultation_confirmed: (name) => `Perfeito, ${name}!

Acabamos de enviar um email para nossa equipe com algumas sugestões de horários para sua ligação introdutória gratuita.

Nossa equipe entrará em contato pelo WhatsApp em breve para confirmar o melhor horário para você.

Enquanto isso, se tiver alguma dúvida, pode enviar aqui mesmo!

Obrigada por escolher o ${process.env.ORG_NAME || "CaseHub"}!`,

    payment_pending: `Ainda não identifiquei o pagamento.

Se já pagou, aguarde alguns segundos e envie qualquer mensagem para verificar novamente.

Se ainda não pagou, use o link enviado anteriormente.

Se preferir a ligação introdutória *gratuita*, digite "1".`,

    scheduling_prompt: (slots) => {
      let msg = `Pagamento confirmado! Aqui estão os horários para sua *consulta com advogado*:\n\n`;
      slots.forEach(slot => { msg += `${slot.number}️⃣ ${slot.display}\n`; });
      msg += `\nDigite o número do horário desejado:`;
      return msg;
    },

    scheduling_fallback: `Desculpe, não consegui buscar os horários automaticamente.

Por favor, acesse o link abaixo para agendar:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Ou entre em contato: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    scheduling_invalid: `Por favor, digite apenas o número do horário desejado (1-6).

Se preferir agendar depois, digite "depois".`,

    confirmation: (name, slotDisplay, schedulingUrl) => `Perfeito, ${name}!

Sua consulta com advogado está sendo agendada para:
📅 ${slotDisplay}

Para confirmar, clique no link abaixo e preencha seus dados:
${schedulingUrl}

Você receberá um email de confirmação com o link da reunião.

Se precisar remarcar, entre em contato: ${process.env.ORG_EMAIL || "info@casehub.app"}

Obrigada por escolher o ${process.env.ORG_NAME || "CaseHub"}!`,

    transferred: `Obrigada pelo contato!

Se precisar de algo mais, nossa equipe está à disposição.

Email: ${process.env.ORG_EMAIL || "info@casehub.app"}
Site: ${process.env.ORG_WEBSITE || "https://casehub.app"}`,

    urgent: `Entendi que é urgente!

Nossa equipe foi notificada e vai te atender AGORA.

Se precisar, envie um email para: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    error: `Olá! Nossa equipe vai te atender em instantes.

Se for urgente, envie um email para: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    interests: {
      '1': 'Trabalhar nos EUA',
      '2': 'Morar nos EUA (Green Card)',
      '3': 'Investir nos EUA',
      '4': 'Reunir família',
      '5': 'Outros'
    },

    urgent_words: [
      'urgente', 'urgência', 'urgencia',
      'emergência', 'emergencia',
      'deportação', 'deportacao', 'deportando',
      'preso', 'detido',
      'vencendo', 'vence amanhã', 'vence amanha', 'vence hoje',
      'ajuda urgente'
    ],

    skip_words: ['pular', 'nao', 'não', 'nenhum']
  },

  // ===================== ENGLISH =====================
  en: {
    // NOVO FLUXO - Human Handoff
    welcome_handoff: `Hello! Thank you for contacting ${process.env.ORG_NAME || "CaseHub"}.

A team member will assist you shortly! 🙌

In the meantime, you can schedule:

*1. *FREE Meeting* - General immigration information (no legal advice)
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

*2. *Attorney Consultation* ($99) - Personalized legal advice
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Reply 1 or 2 to learn more, or wait for our team.`,

    option_one_response: `You can schedule your FREE meeting directly here:
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

It's a 15-minute conversation about general immigration information.

Our team will assist you shortly! 🙌`,

    option_two_response: `You can schedule your attorney consultation ($99) directly here:
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

In this consultation you receive personalized legal advice.

Our team will assist you shortly! 🙌`,

    // FLUXO ANTIGO (mantido para compatibilidade)
    welcome: `Hello! Welcome to ${process.env.ORG_NAME || "CaseHub"}!

I'm the office's virtual assistant. To better assist you, what is your name?`,

    ask_name_again: `Sorry, I didn't quite understand. Can you tell me just your name?`,

    ask_interest: (name) => `Nice to meet you, ${name}!

What is your interest? Type the number:

1 - Work in the USA
2 - Live in the USA (Green Card)
3 - Invest in the USA
4 - Family reunification
5 - Other`,

    ask_email: (interest) => `Got it: ${interest}.

What's your email for contact? (or type "skip" if you prefer)`,

    ask_consultation_type: (name) => `Great, ${name}!

We have two options for you:

*1. *FREE introductory call*
   Meet our team, ask general questions about processes, timelines and visa types.

*2. *Attorney consultation (US$99)*
   Specific analysis of your case with personalized strategy.

Type 1 or 2:`,

    invalid_consultation_choice: `Please type only 1 or 2:

*1. FREE introductory call
*2. Attorney consultation (US$99)`,

    free_consultation_confirmed: (name) => `Perfect, ${name}!

We just sent an email to our team with some schedule suggestions for your free introductory call.

Our team will contact you via WhatsApp soon to confirm the best time for you.

In the meantime, if you have any questions, feel free to ask here!

Thank you for choosing ${process.env.ORG_NAME || "CaseHub"}!`,

    payment_pending: `I haven't identified the payment yet.

If you've already paid, wait a few seconds and send any message to check again.

If you haven't paid yet, use the link sent previously.

If you prefer the *FREE* introductory call, type "1".`,

    scheduling_prompt: (slots) => {
      let msg = `Payment confirmed! Here are the available times for your *attorney consultation*:\n\n`;
      slots.forEach(slot => { msg += `${slot.number}️⃣ ${slot.display}\n`; });
      msg += `\nType the number of your preferred time:`;
      return msg;
    },

    scheduling_fallback: `Sorry, I couldn't fetch the schedules automatically.

Please access the link below to schedule:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Or contact us: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    scheduling_invalid: `Please type only the number of your preferred time (1-6).

If you prefer to schedule later, type "later".`,

    confirmation: (name, slotDisplay, schedulingUrl) => `Perfect, ${name}!

Your attorney consultation is being scheduled for:
📅 ${slotDisplay}

To confirm, click the link below and fill in your details:
${schedulingUrl}

You will receive a confirmation email with the meeting link.

If you need to reschedule, contact us: ${process.env.ORG_EMAIL || "info@casehub.app"}

Thank you for choosing ${process.env.ORG_NAME || "CaseHub"}!`,

    transferred: `Thank you for contacting us!

If you need anything else, our team is at your service.

Email: ${process.env.ORG_EMAIL || "info@casehub.app"}
Website: ${process.env.ORG_WEBSITE || "https://casehub.app"}`,

    urgent: `I understand this is urgent!

Our team has been notified and will assist you RIGHT NOW.

If needed, send an email to: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    error: `Hello! Our team will assist you shortly.

If it's urgent, send an email to: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    interests: {
      '1': 'Work in the USA',
      '2': 'Live in the USA (Green Card)',
      '3': 'Invest in the USA',
      '4': 'Family reunification',
      '5': 'Other'
    },

    urgent_words: [
      'urgent', 'urgency', 'emergency',
      'deportation', 'deporting', 'deported',
      'arrested', 'detained', 'jail', 'prison',
      'expiring', 'expires tomorrow', 'expires today',
      'help urgent', 'immediate help'
    ],

    skip_words: ['skip', 'no', 'none', 'pass']
  },

  // ===================== ESPAÑOL =====================
  es: {
    // NOVO FLUXO - Human Handoff
    welcome_handoff: `¡Hola! Gracias por contactar a ${process.env.ORG_NAME || "CaseHub"}.

¡Un miembro de nuestro equipo te atenderá pronto! 🙌

Mientras tanto, puedes agendar:

*1. *Reunión GRATIS* - Información general sobre inmigración (sin asesoría legal)
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

*2. *Consulta con Abogado* ($99) - Asesoría legal personalizada
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Responde 1 o 2 para más información, o espera nuestra atención.`,

    option_one_response: `Puedes agendar tu reunión GRATIS directamente aquí:
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Es una conversación de 15 minutos sobre información general de inmigración.

¡Nuestro equipo te atenderá pronto! 🙌`,

    option_two_response: `Puedes agendar tu consulta con abogado ($99) directamente aquí:
👉 ${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

En esta consulta recibes asesoría legal personalizada.

¡Nuestro equipo te atenderá pronto! 🙌`,

    // FLUXO ANTIGO (mantido para compatibilidade)
    welcome: `¡Hola! ¡Bienvenido a ${process.env.ORG_NAME || "CaseHub"}!

Soy la asistente virtual de la oficina. Para ayudarte mejor, ¿cuál es tu nombre?`,

    ask_name_again: `Disculpa, no entendí bien. ¿Puedes decirme solo tu nombre?`,

    ask_interest: (name) => `¡Mucho gusto, ${name}!

¿Cuál es tu interés? Escribe el número:

1 - Trabajar en EE.UU.
2 - Vivir en EE.UU. (Green Card)
3 - Invertir en EE.UU.
4 - Reunificación familiar
5 - Otros`,

    ask_email: (interest) => `Anotado: ${interest}.

¿Cuál es tu email de contacto? (o escribe "saltar" si prefieres)`,

    ask_consultation_type: (name) => `¡Genial, ${name}!

Tenemos dos opciones para ti:

*1. *Llamada introductoria GRATIS*
   Conoce a nuestro equipo, haz preguntas generales sobre procesos, plazos y tipos de visas.

*2. *Consulta con abogado (US$99)*
   Análisis específico de tu caso con estrategia personalizada.

Escribe 1 o 2:`,

    invalid_consultation_choice: `Por favor, escribe solo 1 o 2:

*1. Llamada introductoria GRATIS
*2. Consulta con abogado (US$99)`,

    free_consultation_confirmed: (name) => `¡Perfecto, ${name}!

Acabamos de enviar un email a nuestro equipo con algunas sugerencias de horarios para tu llamada introductoria gratuita.

Nuestro equipo se pondrá en contacto contigo por WhatsApp pronto para confirmar el mejor horario para ti.

Mientras tanto, si tienes alguna pregunta, ¡puedes enviarla aquí!

¡Gracias por elegir ${process.env.ORG_NAME || "CaseHub"}!`,

    payment_pending: `Aún no he identificado el pago.

Si ya pagaste, espera unos segundos y envía cualquier mensaje para verificar de nuevo.

Si aún no has pagado, usa el enlace enviado anteriormente.

Si prefieres la llamada introductoria *GRATIS*, escribe "1".`,

    scheduling_prompt: (slots) => {
      let msg = `¡Pago confirmado! Aquí están los horarios para tu *consulta con abogado*:\n\n`;
      slots.forEach(slot => { msg += `${slot.number}️⃣ ${slot.display}\n`; });
      msg += `\nEscribe el número del horario que prefieras:`;
      return msg;
    },

    scheduling_fallback: `Disculpa, no pude obtener los horarios automáticamente.

Por favor, accede al enlace a continuación para agendar:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

O contáctanos: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    scheduling_invalid: `Por favor, escribe solo el número del horario deseado (1-6).

Si prefieres agendar después, escribe "después".`,

    confirmation: (name, slotDisplay, schedulingUrl) => `¡Perfecto, ${name}!

Tu consulta con abogado está siendo agendada para:
📅 ${slotDisplay}

Para confirmar, haz clic en el enlace y completa tus datos:
${schedulingUrl}

Recibirás un email de confirmación con el enlace de la reunión.

Si necesitas reprogramar, contáctanos: ${process.env.ORG_EMAIL || "info@casehub.app"}

¡Gracias por elegir ${process.env.ORG_NAME || "CaseHub"}!`,

    transferred: `¡Gracias por contactarnos!

Si necesitas algo más, nuestro equipo está a tu disposición.

Email: ${process.env.ORG_EMAIL || "info@casehub.app"}
Sitio web: ${process.env.ORG_WEBSITE || "https://casehub.app"}`,

    urgent: `¡Entiendo que es urgente!

Nuestro equipo ha sido notificado y te atenderá AHORA MISMO.

Si lo necesitas, envía un email a: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    error: `¡Hola! Nuestro equipo te atenderá en un momento.

Si es urgente, envía un email a: ${process.env.ORG_EMAIL || "info@casehub.app"}`,

    interests: {
      '1': 'Trabajar en EE.UU.',
      '2': 'Vivir en EE.UU. (Green Card)',
      '3': 'Invertir en EE.UU.',
      '4': 'Reunificación familiar',
      '5': 'Otros'
    },

    urgent_words: [
      'urgente', 'urgencia', 'emergencia',
      'deportación', 'deportacion', 'deportando', 'deportado',
      'arrestado', 'detenido', 'cárcel', 'carcel', 'prisión', 'prision',
      'venciendo', 'vence mañana', 'vence manana', 'vence hoy',
      'ayuda urgente', 'ayuda inmediata'
    ],

    skip_words: ['saltar', 'no', 'ninguno', 'pasar']
  }
};

/**
 * Detectar idioma pelo número de telefone (DDI)
 */
function detectLanguage(phoneNumber) {
  if (!phoneNumber) return 'en';

  const phone = phoneNumber.replace(/\D/g, '');

  // Tentar DDIs de 4 dígitos primeiro
  for (const ddi of Object.keys(COUNTRY_LANGUAGE).sort((a, b) => b.length - a.length)) {
    if (phone.startsWith(ddi)) {
      return COUNTRY_LANGUAGE[ddi];
    }
  }

  // Default: inglês
  return 'en';
}

/**
 * Obter mensagens do idioma
 */
function getMessages(lang) {
  return MESSAGES[lang] || MESSAGES['en'];
}

/**
 * Obter idioma pelo código
 */
function getLanguageName(lang) {
  const names = {
    'pt': 'Português',
    'en': 'English',
    'es': 'Español'
  };
  return names[lang] || 'English';
}

module.exports = {
  COUNTRY_LANGUAGE,
  MESSAGES,
  detectLanguage,
  getMessages,
  getLanguageName
};
