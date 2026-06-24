/**
 * Agent Templates - Templates prontos para equipe
 * CaseHub
 * v11.0 - Templates Oficiais Sincronizados (29/01/2026)
 *
 * Templates para uso da equipe ao responder leads manualmente
 * Sincronizado com Google Docs oficiais da pasta Admin/Templates/
 * Uso: copiar e personalizar com [NOME], [AGENTE], [INTERESSE]
 */

const EIMMIGRATION_URL = process.env.EIMMIGRATION_URL || "https://example.com/client-portal";

const TEMPLATES = {
  // ============================================
  // GREETING - Primeiro Contato
  // ============================================

  // Template 1: Clientes Novos (Primeiro Contato Completo)
  greeting: {
    en: `Hello.

We are glad to help.

We specialize in U.S. visas and immigration, providing clear and straightforward guidance. Could you please share your name and email? How can we assist you with your case? Feel free to send your questions.

We offer a free intro call with our team. This meeting does not include attorney time nor legal advice, case strategy, or analysis. It's an opportunity for you to meet our team without any initial costs, ask questions about our work, which visas we handle, our client reviews, timelines, common pitfalls, and general questions.

Would you like to schedule this free intro call? Here is the link to book it:
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

For specific case analysis and questions, the needed step is a consultation with one of our attorneys to define the best strategy ($99). Would you prefer to schedule a consultation? Here is the link to book it:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

To complete your booking, please proceed with payment here:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Warm Regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá,

Ficamos felizes em ajudar.

Somos especializados em vistos e imigração para os Estados Unidos, oferecendo orientação clara e objetiva. Poderia, por favor, informar seu nome e e-mail? Como podemos ajudar no seu caso? Fique à vontade para enviar suas dúvidas.

Oferecemos uma ligação inicial gratuita com nossa equipe. Essa reunião não inclui tempo com advogado, nem aconselhamento jurídico, estratégia ou análise do caso. É uma oportunidade para você conhecer nossa equipe sem nenhum custo inicial, tirar dúvidas sobre nosso trabalho, quais vistos atendemos, avaliações de clientes, prazos, erros comuns e outras perguntas gerais.

Gostaria de agendar essa ligação inicial gratuita? Aqui está o link para marcar:
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Para análise específica do caso e dúvidas personalizadas, o próximo passo é uma consulta com um de nossos advogados para definir a melhor estratégia ($99). Gostaria de agendar uma consulta? Aqui está o link para marcar:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Para confirmar o agendamento, favor efetuar o pagamento aqui:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Hola,

Nos alegra poder ayudarte.

Nos especializamos en visas e inmigración a Estados Unidos, brindando orientación clara y directa. ¿Podrías compartir tu nombre y correo electrónico? ¿Cómo podemos ayudarte con tu caso? No dudes en enviar tus preguntas.

Ofrecemos una llamada introductoria gratuita con nuestro equipo. Esta reunión no incluye tiempo con abogado ni asesoría legal, estrategia o análisis del caso. Es una oportunidad para conocer a nuestro equipo sin costos iniciales.

¿Te gustaría agendar esta llamada gratuita?
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Para análisis específico del caso, el siguiente paso es una consulta con uno de nuestros abogados ($99):
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Para confirmar tu cita, por favor realiza el pago aquí:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 2: Resposta Rápida (Agradecimento)
  quick_response: {
    en: `Dear [NAME],

Thank you very much for your response.

Should you have any further questions or require additional information, please do not hesitate to reach out. We are always at your disposal and happy to assist you.

Thank you once again, and we remain available should you need any further support.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Prezado(a) [NOME],

Muito obrigado pela sua resposta.

Caso tenha mais perguntas ou precise de informações adicionais, não hesite em entrar em contato. Estamos sempre à disposição para ajudá-lo(a).

Agradecemos novamente e permanecemos disponíveis caso precise de mais suporte.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Estimado(a) [NOMBRE],

Muchas gracias por tu respuesta.

Si tienes más preguntas o necesitas información adicional, no dudes en contactarnos. Siempre estamos a tu disposición.

Gracias nuevamente, y quedamos disponibles para cualquier cosa que necesites.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // OFFER - Ofertas de Serviços
  // ============================================

  // Template 3: Oferecer Free Intro Call
  offer_free: {
    en: `Hello. We are glad to help.

We offer a free intro call with our team. This meeting does not include attorney time nor legal advice, case strategy or analysis.

It's an opportunity for you to meet our team without any initial costs, ask questions about our work, which visas we handle, our client reviews, timelines, common pitfalls, and general questions.

Would you like to schedule this free intro call?
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

For specific case analysis and questions, the needed step is a consultation with one of our attorneys to define the best strategy ($99).
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

To complete your booking, please proceed with payment here:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá. Ficamos felizes em ajudar.

Oferecemos uma ligação inicial gratuita com nossa equipe. Essa reunião não inclui tempo com advogado, nem aconselhamento jurídico, estratégia ou análise do caso.

É uma oportunidade para você conhecer nossa equipe sem nenhum custo inicial, tirar dúvidas sobre nosso trabalho, quais vistos atendemos, avaliações de clientes, prazos e erros comuns.

Gostaria de agendar essa ligação inicial gratuita?
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Para análise específica do caso, o próximo passo é uma consulta com um de nossos advogados ($99):
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Para confirmar o agendamento, favor efetuar o pagamento aqui:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Hola. Nos alegra poder ayudarte.

Ofrecemos una llamada introductoria gratuita con nuestro equipo. Esta reunión no incluye tiempo con abogado ni asesoría legal.

Es una oportunidad para conocer a nuestro equipo sin costos iniciales, hacer preguntas sobre nuestro trabajo, qué visas manejamos, reseñas de clientes y preguntas generales.

¿Te gustaría agendar esta llamada gratuita?
${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall

Para análisis específico del caso, la consulta con abogado es $99:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Para confirmar tu cita, por favor realiza el pago aquí:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 4: Oferecer Consulta Paga
  offer_paid: {
    en: `If you need specific legal guidance for your case, I recommend scheduling a consultation with our attorney ($99). In this consultation you receive personalized legal advice.

Here is the link to book it:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

To complete your booking, please proceed with payment here:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Se você precisa de orientação jurídica específica para seu caso, recomendo agendar uma consulta com nosso advogado ($99). Nessa consulta você recebe aconselhamento legal personalizado.

Aqui está o link para agendar:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Para confirmar o agendamento, favor efetuar o pagamento aqui:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Si necesitas orientación legal específica para tu caso, te recomiendo agendar una consulta con nuestro abogado ($99). En esta consulta recibes asesoría legal personalizada.

Aquí está el enlace para agendar:
${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting

Para confirmar tu cita, por favor realiza el pago aquí:
https://buy.stripe.com/3cI5kD1I4aZC5mHeOkdjO2q

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // SCHEDULING - Agendamento
  // ============================================

  // Template 5: Marcando Reunião
  schedule_meeting: {
    en: `Hello!

We have availability for your meeting with Attorney on [DATE], at [TIME] EST.

If this time isn't convenient, feel free to suggest an alternative.

Once confirmed, I will send a calendar invite with all the details.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá!

Temos disponibilidade para sua reunião com o advogado em [DATA], às [HORÁRIO] EST.

Se esse horário não for conveniente, sinta-se à vontade para sugerir uma alternativa.

Após a confirmação, enviaremos um convite de calendário com todos os detalhes.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Hola!

Tenemos disponibilidad para tu reunión con el abogado el [FECHA], a las [HORA] EST.

Si este horario no te conviene, no dudes en sugerir una alternativa.

Una vez confirmado, enviaremos una invitación de calendario con todos los detalles.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 6: Confirmação de Reunião
  confirm_meeting: {
    en: `Hello,

Your meeting with the Attorney has been confirmed for [DATE] at [TIME] EST.

Here is your link to join:
[MEETING_LINK]

We look forward to meeting with you!

Please don't hesitate to let us know in case you have any questions.

Warm Regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá,

Sua reunião com o advogado está confirmada para [DATA] às [HORÁRIO] EST.

Segue abaixo o link de acesso:
[LINK_REUNIÃO]

Aguardamos sua presença!

Caso surja qualquer dúvida, não hesite em nos contatar.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Hola,

Tu reunión con el abogado ha sido confirmada para el [FECHA] a las [HORA] EST.

Aquí está tu enlace para unirte:
[ENLACE_REUNIÓN]

¡Esperamos verte!

No dudes en contactarnos si tienes alguna pregunta.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 7: Reagendamento
  reschedule: {
    en: `Dear [NAME],

No problem, we will gladly reschedule this meeting for you. Would you be available for a meeting with our attorney on [DATE] at [TIME] EST?

Please let me know if this 30-minute slot works for you. If this time isn't convenient, feel free to suggest two or three more alternatives.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Prezado(a) [NOME],

Sem problemas, ficaremos felizes em reagendar essa reunião. Você estaria disponível para uma reunião com nosso advogado em [DATA] às [HORÁRIO] EST?

Por favor, confirme se esse horário de 30 minutos funciona para você. Se não for conveniente, sinta-se à vontade para sugerir duas ou três alternativas.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Estimado(a) [NOMBRE],

No hay problema, con gusto reagendaremos esta reunión. ¿Estarías disponible para una reunión con nuestro abogado el [FECHA] a las [HORA] EST?

Por favor, confirma si este horario de 30 minutos te funciona. Si no te conviene, no dudes en sugerir dos o tres alternativas.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // PAYMENT - Pagamento
  // ============================================

  // Template 8: Informações de Pagamento
  payment_info: {
    en: `Dear [NAME],

We would like to share the payment options available for your EB-2 NIW visa process. Please find the details below:

Attorney Fees: USD $8,000

Payment Methods:
• Bank Transfer - You may complete the payment via U.S. or international bank transfer. Bank details will be provided once you confirm this option.
• Credit or Debit Card (via Stripe link) - You can make a secure payment through a Stripe link that we will send to you upon request.

Payment Plans and Discounts:
• 10% OFF – Full Payment Upfront - Pay the total amount in one payment before we begin the process.
• 5% OFF – Split Payment (50/50) - Pay half upfront and the remaining half when we file your case.
• Regular Plan – Monthly Installments - Pay half upfront and the remaining balance in 5 monthly installments via credit card subscription.

Please let us know which payment option and plan you prefer so we can provide the appropriate instructions and links.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Prezado(a) [NOME],

Gostaríamos de compartilhar as opções de pagamento disponíveis para seu processo de visto EB-2 NIW. Seguem os detalhes abaixo:

Honorários Advocatícios: USD $8.000

Métodos de Pagamento:
• Transferência Bancária - Você pode realizar o pagamento via transferência bancária americana ou internacional. Os dados bancários serão fornecidos após a confirmação desta opção.
• Cartão de Crédito ou Débito (via link Stripe) - Você pode fazer um pagamento seguro através de um link Stripe que enviaremos mediante solicitação.

Planos de Pagamento e Descontos:
• 10% OFF – Pagamento Integral Antecipado - Pague o valor total em um único pagamento antes de iniciarmos o processo.
• 5% OFF – Pagamento Dividido (50/50) - Pague metade adiantado e o restante quando protocolarmos seu caso.
• Plano Regular – Parcelas Mensais - Pague metade adiantado e o saldo restante em 5 parcelas mensais via assinatura de cartão de crédito.

Por favor, informe qual opção e plano de pagamento você prefere para que possamos fornecer as instruções e links apropriados.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Estimado(a) [NOMBRE],

Nos gustaría compartir las opciones de pago disponibles para tu proceso de visa EB-2 NIW. Encuentra los detalles a continuación:

Honorarios de Abogado: USD $8,000

Métodos de Pago:
• Transferencia Bancaria - Puedes completar el pago vía transferencia bancaria estadounidense o internacional. Los datos bancarios se proporcionarán una vez que confirmes esta opción.
• Tarjeta de Crédito o Débito (vía enlace Stripe) - Puedes hacer un pago seguro a través de un enlace Stripe que te enviaremos bajo solicitud.

Planes de Pago y Descuentos:
• 10% OFF – Pago Total por Adelantado
• 5% OFF – Pago Dividido (50/50)
• Plan Regular – Cuotas Mensuales

Por favor, infórmanos qué opción y plan de pago prefieres.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 9: Cobrando Segunda Parcela
  payment_second: {
    en: `Hello!

Dear [NAME],

We hope you are doing well.

Please find below the payment link in the amount of $[AMOUNT], which corresponds to the second part of your legal fees under our retainer agreement.

Link: [PAYMENT_LINK]

Kindly complete this payment at your earliest convenience so that we may proceed with the next steps in your immigration process.

Please let us know once the payment has been submitted or if you encounter any issues accessing the link.

Thank you very much for your prompt attention and cooperation.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá!

Prezado(a) [NOME],

Esperamos que esteja bem.

Segue abaixo o link de pagamento no valor de $[VALOR], correspondente à segunda parcela dos seus honorários advocatícios conforme nosso contrato.

Link: [LINK_PAGAMENTO]

Por gentileza, complete este pagamento o mais breve possível para que possamos prosseguir com as próximas etapas do seu processo imigratório.

Por favor, nos avise quando o pagamento for realizado ou se tiver algum problema para acessar o link.

Muito obrigado pela sua atenção e cooperação.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Hola!

Estimado(a) [NOMBRE],

Esperamos que estés bien.

Encuentra a continuación el enlace de pago por el monto de $[MONTO], que corresponde a la segunda parte de tus honorarios legales según nuestro contrato.

Enlace: [ENLACE_PAGO]

Por favor, completa este pago a tu conveniencia para que podamos proceder con los siguientes pasos de tu proceso migratorio.

Avísanos cuando el pago haya sido realizado o si tienes algún problema para acceder al enlace.

Muchas gracias por tu pronta atención y cooperación.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 10: Confirmação de Pagamento
  payment_confirm: {
    en: `Dear [NAME],

We are pleased to confirm that we have received your payment.

Thank you very much for your prompt attention and cooperation.

Please don't hesitate to let us know in case you have any questions.

Warm Regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Prezado(a) [NOME],

Temos o prazer de confirmar que recebemos seu pagamento.

Muito obrigado pela sua atenção e cooperação.

Por favor, não hesite em nos contatar caso tenha alguma dúvida.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `Estimado(a) [NOMBRE],

Nos complace confirmar que hemos recibido tu pago.

Muchas gracias por tu pronta atención y cooperación.

No dudes en contactarnos si tienes alguna pregunta.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 11: Reembolso
  refund: {
    en: `Hello!

We process refunds via bank transfer. To proceed, please provide the following details:

• Full account holder name
• Bank name
• Account number
• Routing number
• Full address

Thank you!

Please don't hesitate to let us know in case you have any questions.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá!

Processamos reembolsos via transferência bancária. Para prosseguir, por favor forneça os seguintes dados:

• Nome completo do titular da conta
• Nome do banco
• Número da conta
• Número de roteamento (routing number)
• Endereço completo

Obrigado!

Por favor, não hesite em nos contatar caso tenha alguma dúvida.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Hola!

Procesamos reembolsos vía transferencia bancaria. Para proceder, por favor proporciona los siguientes datos:

• Nombre completo del titular de la cuenta
• Nombre del banco
• Número de cuenta
• Número de ruta (routing number)
• Dirección completa

¡Gracias!

No dudes en contactarnos si tienes alguna pregunta.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // ONBOARDING - Novos Clientes
  // ============================================

  // Template 12: Onboarding Novo Cliente
  onboarding: {
    en: `Hello!

Thank you for choosing our firm to assist with your immigration matter. Nice to meet you. My name is Advogado Demo, and I am the attorney who will manage your case.

Quick introduction: I am an Immigration Lawyer with years of experience, licensed in the US, and I have a master's degree in Immigration Law as well. I'll make sure to complete your case in the best and quickest way possible.

To get started, let's schedule an onboarding call to discuss your case in more detail. Please let me know a few times that you're available for a call. Would [DATE] at [TIME] EST work for you?

Here are your credentials to log into your e-immigration account:
${EIMMIGRATION_URL}

Username: [USERNAME]
Password: [PASSWORD]

You can use this link to upload all documents as you gather them. In your e-immigration account you will also find the signed retainer agreement for your records, the list of documents we need from you, and two documents you must complete: expansion questionnaire and testimonial letter questionnaire.

Please don't hesitate to contact us via SMS, email or WhatsApp. All questions are important - if you have current queries, please let me know before our first meeting so I can better prepare myself.

My goal is clear: making sure you have someone knowledgeable and trustworthy handling ALL immigration issues so you can focus on your family, work, and life as a whole. I'll do my best to grab your hand and walk you through every step until we file the case and get your visa.

I'm looking forward to working with you!

Warm Regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá!

Obrigado por escolher nosso escritório para auxiliá-lo(a) com sua questão imigratória. É um prazer conhecê-lo(a). Meu nome é Advogado Demo, e serei o advogado responsável pela condução do seu caso.

Fazendo uma breve apresentação: sou advogado de imigração, com anos de experiência, licenciado nos Estados Unidos, e possuo também um mestrado em Direito de Imigração. Farei o possível para conduzir o seu caso da melhor e mais eficiente forma.

Para darmos início, gostaríamos de agendar uma chamada de onboarding para discutir seu caso com mais detalhes. Por gentileza, informe alguns horários em que você estará disponível para essa conversa. [DATA] às [HORÁRIO] BRT funcionaria para você?

Abaixo estão suas credenciais para acesso à sua conta na plataforma e-immigration:
${EIMMIGRATION_URL}

Usuário: [USERNAME]
Senha: [PASSWORD]

Você pode utilizar esse link para enviar todos os documentos à medida que for reunindo-os. Em sua conta na plataforma e-immigration, você também encontrará o contrato de prestação de serviços assinado para seus registros, a lista de documentos necessários, e dois documentos que precisam ser preenchidos: o questionário de expansão e o questionário da carta de testemunho.

Por favor, não hesite em entrar em contato conosco por SMS, e-mail ou WhatsApp. Todas as perguntas são importantes — caso você já tenha alguma dúvida, sinta-se à vontade para enviá-la antes da nossa primeira reunião.

Meu objetivo é claro: garantir que você tenha um profissional experiente e confiável cuidando de todas as questões imigratórias, para que você possa focar em sua família, trabalho e qualidade de vida.

Estou ansioso para trabalharmos juntos!

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Hola!

Gracias por elegir nuestro despacho para ayudarte con tu asunto migratorio. Mucho gusto. Mi nombre es Advogado Demo, y soy el abogado que manejará tu caso.

Breve presentación: Soy abogado de inmigración con años de experiencia, licenciado en EE.UU., y también tengo una maestría en Derecho Migratorio. Me aseguraré de completar tu caso de la mejor y más rápida manera posible.

Para comenzar, agendemos una llamada de onboarding para discutir tu caso con más detalle. Por favor, indícame algunos horarios en que estés disponible.

Aquí están tus credenciales para acceder a tu cuenta e-immigration:
${EIMMIGRATION_URL}

Usuario: [USERNAME]
Contraseña: [PASSWORD]

¡Espero trabajar contigo!

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // FORWARDING - Encaminhamento
  // ============================================

  // Template 13: Encaminhamento para Equipe Jurídica
  forwarding: {
    en: `Hello!

Your message has been sent to our legal team for review. We will get back to you with an update as soon as possible.

All legal inquiries will be addressed by our legal team via SMS or email.

Please don't hesitate to let us know in case you have any questions.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Olá!

Sua mensagem foi encaminhada para nossa equipe jurídica para análise. Entraremos em contato com você com uma atualização assim que possível.

Por favor, não hesite em nos avisar caso tenha alguma dúvida.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Hola!

Tu mensaje ha sido enviado a nuestro equipo legal para revisión. Te responderemos con una actualización lo antes posible.

No dudes en contactarnos si tienes alguna pregunta.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // FOLLOW-UP
  // ============================================

  // Template 14: Follow-up 1 (4 dias)
  followup_1: {
    en: `Hello!

We haven't heard from you.

Would you like to schedule a free intro meeting? Or maybe a consultation with our attorneys?

We are here to help!

Thank you!`,

    pt: `Olá!

Não tivemos notícias suas.

Gostaria de agendar uma reunião introdutória gratuita? Ou talvez uma consulta com nossos advogados?

Estamos aqui para ajudar!

Obrigado!`,

    es: `¡Hola!

No hemos tenido noticias tuyas.

¿Te gustaría agendar una reunión introductoria gratuita? ¿O tal vez una consulta con nuestros abogados?

¡Estamos aquí para ayudarte!

¡Gracias!`
  },

  // Template 15: Follow-up 2 (7 dias - Final)
  followup_2: {
    en: `Hello.

We haven't heard from you, so we will archive your contact for future needs.

If you would like to schedule a free initial meeting, just let us know. We are here to help.

Thank you very much!`,

    pt: `Olá.

Não tivemos retorno seu, então arquivaremos seu contato para necessidades futuras.

Se quiser agendar uma reunião inicial gratuita, é só nos avisar. Estamos aqui para ajudar.

Muito obrigado!`,

    es: `Hola.

No hemos tenido noticias tuyas, así que archivaremos tu contacto para futuras necesidades.

Si deseas agendar una reunión inicial gratuita, solo avísanos. Estamos aquí para ayudarte.

¡Muchas gracias!`
  },

  // Template 16: Follow-up Geral
  followup: {
    en: `Hi [NAME]! I wanted to follow up on our conversation. Have you had a chance to review the options we discussed? Can I help with anything else?

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Oi [NOME]! Gostaria de fazer um follow-up sobre nosso contato. Você teve a chance de revisar as opções que conversamos? Posso ajudar com algo mais?

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Hola [NOMBRE]! Quería hacer un seguimiento de nuestra conversación. ¿Tuviste la oportunidad de revisar las opciones que hablamos? ¿Puedo ayudar con algo más?

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // HANDOFF - Transição Humano/Bot
  // ============================================

  // Template 17: Assumindo Conversa
  takeover: {
    en: `Hi [NAME]! This is [AGENT] from CaseHub. I'm taking over this conversation to assist you personally. How can I help you today?`,

    pt: `Oi [NOME]! Aqui é [AGENTE] do CaseHub. Estou assumindo essa conversa para te atender pessoalmente. Como posso te ajudar hoje?`,

    es: `¡Hola [NOMBRE]! Soy [AGENTE] del CaseHub. Estoy tomando esta conversación para atenderte personalmente. ¿Cómo puedo ayudarte hoy?`
  },

  // Template 18: Voltando ao Bot
  return_to_bot: {
    en: `Thank you for chatting with us! If you have any more questions in the future, feel free to message us anytime. Our automated assistant will be available to help you.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Obrigado por conversar conosco! Se tiver mais perguntas no futuro, sinta-se à vontade para nos enviar mensagem a qualquer momento. Nosso assistente automatizado estará disponível para ajudá-lo.

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Gracias por chatear con nosotros! Si tienes más preguntas en el futuro, no dudes en enviarnos un mensaje. Nuestro asistente automatizado estará disponible para ayudarte.

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // ============================================
  // MISC - Outros
  // ============================================

  // Template 19: Pedir Documentos
  ask_documents: {
    en: `To proceed with your case, I'll need some documents. Can you send me: passport, I-94, and any immigration documents you have?

Thank you!`,

    pt: `Para dar continuidade ao seu caso, vou precisar de alguns documentos. Você pode me enviar: passaporte, I-94, e qualquer documento de imigração que tenha?

Obrigado!`,

    es: `Para continuar con tu caso, voy a necesitar algunos documentos. ¿Puedes enviarme: pasaporte, I-94, y cualquier documento de inmigración que tengas?

¡Gracias!`
  },

  // Template 20: Despedida
  goodbye: {
    en: `Thank you for reaching out! If you have more questions, we're here to help. Have a great day!

Warm regards,
${process.env.ORG_NAME || "CaseHub"}`,

    pt: `Obrigado pelo contato! Se tiver mais dúvidas, estamos à disposição. Tenha um ótimo dia!

Atenciosamente,
${process.env.ORG_NAME || "CaseHub"}`,

    es: `¡Gracias por contactarnos! Si tienes más preguntas, estamos a tu disposición. ¡Que tengas un excelente día!

Saludos cordiales,
${process.env.ORG_NAME || "CaseHub"}`
  },

  // Template 21: Urgência
  urgent_response: {
    en: `I understand your situation is urgent. Let me check with our team and get back to you as soon as possible. Can you give me more details about the urgency?`,

    pt: `Entendo que sua situação é urgente. Deixa eu verificar com nossa equipe e te retorno o mais rápido possível. Pode me passar mais detalhes sobre a urgência?`,

    es: `Entiendo que tu situación es urgente. Déjame verificar con nuestro equipo y te respondo lo más rápido posible. ¿Puedes darme más detalles sobre la urgencia?`
  },

  // Template 22: Pedir Mais Informações
  ask_info: {
    en: `To better understand your situation, can you tell me: what's your current status in the US and how long have you been here?`,

    pt: `Para entender melhor sua situação, pode me contar: qual seu status atual nos EUA e há quanto tempo está no país?`,

    es: `Para entender mejor tu situación, ¿puedes contarme: cuál es tu estatus actual en EE.UU. y cuánto tiempo llevas en el país?`
  }
};

// Calendly URLs configured by the office.
const CALENDLY_URLS = {
  free: `${process.env.ORG_WEBSITE || "https://casehub.app"}/freecall`,
  paid: `${process.env.ORG_WEBSITE || "https://casehub.app"}/meeting`
};

/**
 * Obter template por nome e idioma
 */
function getTemplate(templateName, lang = 'en') {
  const template = TEMPLATES[templateName];
  if (!template) return null;
  return template[lang] || template['en'];
}

/**
 * Obter todos os templates de um idioma
 */
function getAllTemplates(lang = 'en') {
  const result = {};
  for (const [name, template] of Object.entries(TEMPLATES)) {
    result[name] = template[lang] || template['en'];
  }
  return result;
}

/**
 * Listar todos os nomes de templates disponíveis
 */
function listTemplates() {
  return Object.keys(TEMPLATES);
}

/**
 * Personalizar template com dados da lead
 */
function personalizeTemplate(templateText, leadData = {}) {
  let text = templateText;

  // Nome do cliente
  text = text.replace(/\[NOME\]|\[NAME\]|\[NOMBRE\]/gi, leadData.client_name || leadData.whatsapp_name || '');

  // Nome do agente
  text = text.replace(/\[AGENTE\]|\[AGENT\]/gi, leadData.agent_name || 'Equipe CaseHub');

  // Interesse/Visto
  text = text.replace(/\[INTERESSE\]|\[INTEREST\]|\[INTERES\]/gi, leadData.visa_interest || leadData.interest || '');

  // Data/Hora
  text = text.replace(/\[DATA\]|\[DATE\]|\[FECHA\]/gi, leadData.date || '[DATA]');
  text = text.replace(/\[HORÁRIO\]|\[HORARIO\]|\[TIME\]|\[HORA\]/gi, leadData.time || '[HORÁRIO]');

  // Credenciais
  text = text.replace(/\[USERNAME\]/gi, leadData.username || '[USERNAME]');
  text = text.replace(/\[PASSWORD\]/gi, leadData.password || '[PASSWORD]');

  // Valores
  text = text.replace(/\[VALOR\]|\[AMOUNT\]|\[MONTO\]/gi, leadData.amount || '[VALOR]');

  // Links
  text = text.replace(/\[LINK_REUNIÃO\]|\[MEETING_LINK\]|\[ENLACE_REUNIÓN\]/gi, leadData.meeting_link || '[LINK]');
  text = text.replace(/\[LINK_PAGAMENTO\]|\[PAYMENT_LINK\]|\[ENLACE_PAGO\]/gi, leadData.payment_link || '[LINK]');

  return text;
}

/**
 * Buscar template por palavra-chave no conteúdo
 */
function searchTemplates(keyword, lang = 'en') {
  const results = [];
  const searchTerm = keyword.toLowerCase();

  for (const [name, template] of Object.entries(TEMPLATES)) {
    const text = (template[lang] || template['en']).toLowerCase();
    if (text.includes(searchTerm) || name.toLowerCase().includes(searchTerm)) {
      results.push({
        name,
        template: template[lang] || template['en']
      });
    }
  }

  return results;
}

module.exports = {
  TEMPLATES,
  CALENDLY_URLS,
  EIMMIGRATION_URL,
  getTemplate,
  getAllTemplates,
  listTemplates,
  personalizeTemplate,
  searchTemplates
};
