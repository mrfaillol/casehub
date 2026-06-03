"""Quick-reply templates — Brazilian law-firm reality (advocacia BR).

Replaces the legacy ILC (US-immigration) set. Seeded as global defaults
(org_id NULL) into wa_templates; each firm can edit/add its own on top.

Placeholders:
  {ORG_NAME} / {ORG_WEBSITE}  -> substituted by _render_template_body (brand).
  [NOME] [DATA] [HORARIO]     -> substituted by personalize_template (contact).
"""

QUICK_REPLY_TEMPLATES = [
    # ── Saudação / primeiro contato ──────────────────────────────────────
    {
        "id": "saudacao", "category": "greeting", "name": "Saudação / Primeiro contato",
        "bodies": {
            "pt": "Olá! Aqui é do {ORG_NAME}. 👋\n\nObrigado pelo seu contato. Para entendermos melhor o seu caso e direcioná-lo ao advogado certo, poderia nos informar:\n\n1) Seu nome completo\n2) Um resumo do que está acontecendo\n3) A cidade/estado onde os fatos ocorreram\n\nAssim que recebermos, retornamos com os próximos passos.",
            "en": "Hello! This is {ORG_NAME}. 👋\n\nThank you for reaching out. To better understand your case and route you to the right attorney, could you share:\n\n1) Your full name\n2) A brief summary of the matter\n3) The city/state where it happened\n\nWe'll get back to you with the next steps shortly.",
            "es": "¡Hola! Le saluda {ORG_NAME}. 👋\n\nGracias por su contacto. Para entender mejor su caso, ¿podría indicarnos su nombre completo, un resumen del asunto y la ciudad/estado donde ocurrió? Le responderemos con los próximos pasos.",
        },
    },
    {
        "id": "agradecimento", "category": "greeting", "name": "Agradecimento pela resposta",
        "bodies": {
            "pt": "Perfeito, [NOME]. Muito obrigado pelas informações. 🙏\n\nJá encaminhamos ao advogado responsável pela sua área. Em breve entraremos em contato para dar sequência.",
            "en": "Perfect, [NOME]. Thank you for the details. 🙏\n\nWe've forwarded it to the responsible attorney and will follow up shortly.",
            "es": "Perfecto, [NOME]. Gracias por la información. 🙏 La hemos enviado al abogado responsable y le contactaremos en breve.",
        },
    },

    # ── Consulta / agendamento ───────────────────────────────────────────
    {
        "id": "agendar_consulta", "category": "scheduling", "name": "Agendar consulta",
        "bodies": {
            "pt": "[NOME], o próximo passo é uma **consulta com um de nossos advogados**, onde analisaremos o seu caso em detalhe e apresentaremos as opções.\n\nTemos disponibilidade nos seguintes horários:\n• [DATA] às [HORARIO]\n\nA consulta pode ser presencial, por telefone ou videochamada. Qual formato e horário ficam melhores para você?",
            "en": "[NOME], the next step is a **consultation with one of our attorneys** to review your case in detail and present your options.\n\nWe have availability on [DATA] at [HORARIO]. It can be in person, by phone or video call. Which format and time work best for you?",
            "es": "[NOME], el siguiente paso es una **consulta con uno de nuestros abogados** para analizar su caso. Tenemos disponibilidad el [DATA] a las [HORARIO]. Puede ser presencial, por teléfono o videollamada. ¿Qué prefiere?",
        },
    },
    {
        "id": "confirmar_consulta", "category": "scheduling", "name": "Confirmar consulta",
        "bodies": {
            "pt": "Sua consulta está **confirmada** para [DATA] às [HORARIO], com o {ORG_NAME}. ✅\n\nPara aproveitarmos melhor o tempo, se possível tenha em mãos os documentos relacionados ao caso. Qualquer imprevisto, é só nos avisar por aqui.",
            "en": "Your consultation is **confirmed** for [DATA] at [HORARIO] with {ORG_NAME}. ✅\n\nIf possible, please have the documents related to your case at hand. Let us know here if anything comes up.",
            "es": "Su consulta está **confirmada** para el [DATA] a las [HORARIO] con {ORG_NAME}. ✅ Si es posible, tenga a mano los documentos del caso. Cualquier imprevisto, avísenos por aquí.",
        },
    },
    {
        "id": "reagendar", "category": "scheduling", "name": "Reagendar",
        "bodies": {
            "pt": "Sem problema, [NOME]. Vamos reagendar. 🙂\n\nTenho estas novas opções:\n• [DATA] às [HORARIO]\n\nQual delas funciona melhor para você?",
            "en": "No problem, [NOME]. Let's reschedule. 🙂\n\nNew options: [DATA] at [HORARIO]. Which works best for you?",
            "es": "Sin problema, [NOME]. Reagendemos. 🙂 Nuevas opciones: [DATA] a las [HORARIO]. ¿Cuál prefiere?",
        },
    },

    # ── Honorários / pagamento ───────────────────────────────────────────
    {
        "id": "proposta_honorarios", "category": "payment", "name": "Proposta de honorários",
        "bodies": {
            "pt": "[NOME], conforme conversamos, segue a proposta de honorários do {ORG_NAME} para a atuação no seu caso.\n\nOs valores e a forma de pagamento estão detalhados no documento que enviaremos a seguir. Os honorários seguem a tabela da OAB e podem ser parcelados.\n\nFico à disposição para esclarecer qualquer ponto antes de seguirmos com o contrato.",
            "en": "[NOME], as discussed, here is {ORG_NAME}'s fee proposal for your case. Amounts and payment terms are detailed in the document we'll send next; fees follow the bar association schedule and may be paid in installments. I'm available to clarify anything before we proceed with the contract.",
            "es": "[NOME], según lo conversado, aquí está la propuesta de honorarios de {ORG_NAME}. Los valores y la forma de pago están en el documento que enviaremos; pueden pagarse en cuotas. Quedo a disposición antes de firmar el contrato.",
        },
    },
    {
        "id": "formas_pagamento", "category": "payment", "name": "Formas de pagamento",
        "bodies": {
            "pt": "Aceitamos as seguintes formas de pagamento:\n\n• PIX (confirmação na hora)\n• Cartão de crédito (com possibilidade de parcelamento)\n• Transferência bancária / boleto\n\nAssim que escolher, envio os dados para pagamento. 🙂",
            "en": "We accept PIX (instant), credit card (installments available) and bank transfer/boleto. Once you choose, I'll send the payment details. 🙂",
            "es": "Aceptamos PIX (al instante), tarjeta de crédito (en cuotas) y transferencia bancaria. Cuando elija, le envío los datos de pago. 🙂",
        },
    },
    {
        "id": "confirmar_pagamento", "category": "payment", "name": "Confirmação de pagamento",
        "bodies": {
            "pt": "Recebemos o seu pagamento, [NOME]. Muito obrigado! ✅\n\nSeu caso já está em andamento com a nossa equipe. Manteremos você informado a cada etapa.",
            "en": "We've received your payment, [NOME]. Thank you! ✅ Your case is now under way with our team and we'll keep you updated at every step.",
            "es": "Hemos recibido su pago, [NOME]. ¡Gracias! ✅ Su caso ya está en marcha y le mantendremos informado.",
        },
    },

    # ── Documentos ───────────────────────────────────────────────────────
    {
        "id": "pedir_documentos", "category": "documents", "name": "Solicitar documentos",
        "bodies": {
            "pt": "[NOME], para darmos andamento, precisaremos dos seguintes documentos:\n\n• RG e CPF\n• Comprovante de residência\n• Documentos relacionados ao caso (contratos, notificações, comprovantes, mensagens etc.)\n\nVocê pode enviá-los por aqui mesmo, em foto ou PDF. Qualquer dúvida sobre algum documento, é só perguntar. 📎",
            "en": "[NOME], to move forward we'll need: ID and tax number, proof of address, and any documents related to the case (contracts, notices, receipts, messages). You can send them here as photos or PDFs. 📎",
            "es": "[NOME], para avanzar necesitaremos: documento de identidad, comprobante de domicilio y los documentos del caso (contratos, notificaciones, recibos). Puede enviarlos por aquí en foto o PDF. 📎",
        },
    },

    # ── Áreas de atuação (resposta de triagem) ───────────────────────────
    {
        "id": "areas_atuacao", "category": "greeting", "name": "Áreas de atuação",
        "bodies": {
            "pt": "O {ORG_NAME} atua nas principais áreas do Direito, entre elas:\n\n• Trabalhista\n• Família e Sucessões (divórcio, inventário, pensão)\n• Cível e Contratos\n• Consumidor\n• Previdenciário (INSS, aposentadoria)\n• Criminal\n\nMe conte em qual dessas o seu caso se encaixa — ou descreva a situação que eu te direciono ao advogado certo.",
            "en": "{ORG_NAME} practices in the main areas of law: Labor, Family & Estates, Civil & Contracts, Consumer, Social Security, and Criminal. Tell me which fits your case — or describe the situation and I'll route you to the right attorney.",
            "es": "{ORG_NAME} actúa en las principales áreas del Derecho: Laboral, Familia y Sucesiones, Civil y Contratos, Consumidor, Previsional y Penal. Cuénteme cuál encaja con su caso.",
        },
    },

    # ── Follow-up ────────────────────────────────────────────────────────
    {
        "id": "followup_retomar", "category": "followup", "name": "Follow-up — retomar contato",
        "bodies": {
            "pt": "Olá, [NOME]! Tudo bem? 🙂\n\nEstou retomando o contato sobre o seu caso aqui no {ORG_NAME}. Ainda podemos seguir com o atendimento — você gostaria de agendar a consulta ou tirar alguma dúvida antes?",
            "en": "Hello, [NOME]! 🙂 Following up on your case with {ORG_NAME}. We can still move forward — would you like to schedule the consultation or clear any questions first?",
            "es": "¡Hola, [NOME]! 🙂 Retomo el contacto sobre su caso en {ORG_NAME}. ¿Desea agendar la consulta o aclarar alguna duda?",
        },
    },
    {
        "id": "followup_final", "category": "followup", "name": "Follow-up — última tentativa",
        "bodies": {
            "pt": "[NOME], passando para saber se ainda tem interesse em seguir com o seu caso. 🙂\n\nSe preferir retomar mais para frente, sem problema — é só nos chamar por aqui quando quiser. Estamos à disposição.",
            "en": "[NOME], just checking whether you'd still like to proceed with your case. 🙂 If you prefer to resume later, no problem — reach out here whenever you wish.",
            "es": "[NOME], ¿sigue interesado en avanzar con su caso? 🙂 Si prefiere retomarlo más adelante, sin problema — escríbanos cuando quiera.",
        },
    },

    # ── Atendimento / handoff ────────────────────────────────────────────
    {
        "id": "encaminhar_advogado", "category": "handoff", "name": "Encaminhar ao advogado",
        "bodies": {
            "pt": "[NOME], pela natureza do seu caso, vou encaminhá-lo diretamente ao advogado responsável pela área. Ele dará sequência ao atendimento por aqui. Um momento, por favor. 🤝",
            "en": "[NOME], given your case, I'll forward you directly to the responsible attorney, who will continue the conversation here. One moment, please. 🤝",
            "es": "[NOME], por la naturaleza de su caso, lo derivaré al abogado responsable, que continuará la atención por aquí. Un momento, por favor. 🤝",
        },
    },
    {
        "id": "atendimento_humano", "category": "handoff", "name": "Assumindo o atendimento",
        "bodies": {
            "pt": "Olá, [NOME], aqui é da equipe do {ORG_NAME}. A partir de agora eu sigo com o seu atendimento pessoalmente. Como posso ajudar?",
            "en": "Hello, [NOME], this is the {ORG_NAME} team. I'll be assisting you personally from here. How can I help?",
            "es": "Hola, [NOME], le habla el equipo de {ORG_NAME}. A partir de ahora le atiendo personalmente. ¿En qué puedo ayudar?",
        },
    },

    # ── Diversos ─────────────────────────────────────────────────────────
    {
        "id": "urgencia", "category": "misc", "name": "Urgência / prazo",
        "bodies": {
            "pt": "[NOME], entendi que o seu caso é **urgente** e pode envolver prazo. Vou priorizar o seu atendimento e acionar o advogado o quanto antes. Para agilizar, me envie o documento ou a notificação que recebeu, por favor.",
            "en": "[NOME], I understand your case is **urgent** and may involve a deadline. I'll prioritize it and reach the attorney right away. To speed things up, please send me the document or notice you received.",
            "es": "[NOME], entiendo que su caso es **urgente** y puede tener un plazo. Lo priorizaré y contactaré al abogado de inmediato. Para agilizar, envíeme el documento o la notificación que recibió.",
        },
    },
    {
        "id": "pedir_mais_info", "category": "misc", "name": "Pedir mais informações",
        "bodies": {
            "pt": "Obrigado, [NOME]. Para entender melhor e te orientar com precisão, poderia me contar:\n\n• Quando os fatos ocorreram?\n• Já existe algum processo, notificação ou contrato envolvido?\n• Qual resultado você espera?\n\nQuanto mais detalhes, melhor poderemos ajudar.",
            "en": "Thank you, [NOME]. To advise you accurately, could you tell me: when did it happen, is there any lawsuit/notice/contract involved, and what outcome do you expect? The more detail, the better we can help.",
            "es": "Gracias, [NOME]. Para orientarle bien: ¿cuándo ocurrió, hay algún proceso/notificación/contrato, y qué resultado espera? Cuantos más detalles, mejor.",
        },
    },
    {
        "id": "despedida", "category": "misc", "name": "Despedida",
        "bodies": {
            "pt": "Foi um prazer atender você, [NOME]. 🙂\n\nQualquer nova dúvida ou necessidade, é só chamar por aqui. O {ORG_NAME} está sempre à disposição. Tenha um ótimo dia!",
            "en": "It was a pleasure assisting you, [NOME]. 🙂 For anything else, just reach out here — {ORG_NAME} is always available. Have a great day!",
            "es": "Fue un placer atenderle, [NOME]. 🙂 Para cualquier consulta, escríbanos por aquí — {ORG_NAME} siempre a su disposición. ¡Que tenga un buen día!",
        },
    },
]
