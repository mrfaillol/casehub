# Documentacao Completa - WhatsApp Bot LLM
## Immigrant Law Center
### Versao 10.6 - 30/01/2026

---

# INDICE

1. [Visao Geral](#visao-geral)
2. [Arquitetura](#arquitetura)
3. [Templates Completos](#templates-completos)
4. [Regras do LLM Chatbot](#regras-do-llm-chatbot)
5. [Monitoramento](#monitoramento)
6. [Manutencao](#manutencao)

---

# VISAO GERAL

O WhatsApp Bot do Immigrant Law Center utiliza um sistema hibrido de:
- **Templates pre-definidos** como base soberana
- **LLM (Gemini)** para humanizar respostas
- **Classificacao de intents** para selecionar templates
- **Monitoramento em tempo real** de todas as conversas

## Fluxo de Mensagens

```
Mensagem Recebida
       |
       v
[template-matcher.js] --> Detecta idioma + Classifica intent
       |
       v
[llm-chatbot.js] --> Busca template + Chama Gemini + Adapta resposta
       |
       v
[llm-monitor.js] --> Registra atividade
       |
       v
Resposta Enviada
```

---

# ARQUITETURA

## Arquivos Principais

| Arquivo | Funcao |
|---------|--------|
| server.js | Servidor principal Express |
| llm-chatbot.js | Modulo LLM com Gemini |
| template-matcher.js | Classificacao de intents |
| templates.js | Definicao de templates |
| llm-monitor.js | Monitoramento de atividade |

## URLs de Acesso

| URL | Descricao |
|-----|-----------|
| /llm-monitor | Dashboard de monitoramento |
| /api/llm-monitor/activity | API de atividades |
| /api/llm-monitor/stats | Estatisticas |

---

# TEMPLATES COMPLETOS

## 1. PRIMEIRO CONTATO

### Template #1 - Clientes Novos (EN)
```
Hello! Thank you for reaching out to the Immigrant Law Center.

We specialize in employment-based immigration, particularly EB-2 NIW and EB-1A visas.

Would you like to schedule a free 15-minute intro call to discuss your case?

Best regards,
Immigrant Law Center
```

### Template #2 - Clientes Novos (PT)
```
Ola! Obrigado por entrar em contato com o Immigrant Law Center.

Somos especializados em imigracao baseada em emprego, especialmente vistos EB-2 NIW e EB-1A.

Gostaria de agendar uma chamada introdutoria gratuita de 15 minutos para discutir seu caso?

Atenciosamente,
Immigrant Law Center
```

---

## 2. AGENDAMENTO

### Template #5 - Confirmacao de Reuniao (EN)
```
Perfect! Your meeting is confirmed.

Date: [DATE]
Time: [TIME]

We look forward to speaking with you!

Best regards,
Immigrant Law Center
```

### Template #6 - Confirmacao de Reuniao (PT)
```
Perfeito! Sua reuniao esta confirmada.

Data: [DATA]
Horario: [HORARIO]

Estamos ansiosos para conversar com voce!

Atenciosamente,
Immigrant Law Center
```

### Template #7 - Marcando Reuniao (EN)
```
Great! Let's schedule a meeting.

Free 15-minute intro call:
https://calendly.com/center-immigrant/15min

Paid consultation ($99):
https://calendly.com/immigrant-info-swfe/consultation

Which would you prefer?

Best regards,
Immigrant Law Center
```

### Template #32 - Marcando Reuniao (PT)
```
Otimo! Vamos agendar uma reuniao.

Chamada introdutoria gratuita (15 min):
https://calendly.com/center-immigrant/15min

Consulta paga ($99):
https://calendly.com/immigrant-info-swfe/consultation

Qual voce prefere?

Atenciosamente,
Immigrant Law Center
```

### Template #40 - Incentivar Agendamento (PT)
```
Ola [NOME]!

Obrigado pelo interesse em nossos servicos.

Para entender melhor seu caso e oferecer a melhor orientacao, recomendo agendar uma conversa com nossa equipe:

Reuniao Introdutoria GRATUITA (15 min):
https://calendly.com/center-immigrant/15min

Nessa reuniao, voce pode:
- Conhecer nosso trabalho
- Tirar duvidas gerais
- Entender os proximos passos

Posso agendar para voce?

Atenciosamente,
Immigrant Law Center
```

---

## 3. INFORMACOES DE VISTOS

### Template #16 - Info EB-2 NIW
```
O EB-2 NIW (National Interest Waiver) e uma categoria de green card para profissionais com:

- Mestrado ou superior, OU
- Graduacao + 5 anos de experiencia progressiva

Diferenciais:
- Nao precisa de oferta de emprego
- Nao precisa de Labor Certification
- Auto-peticao (voce mesmo patrocina)

Ideal para: Pesquisadores, engenheiros, medicos, profissionais de TI, etc.

Gostaria de saber mais sobre sua elegibilidade?

Atenciosamente,
Immigrant Law Center
```

### Template #17 - Info EB-1A
```
O EB-1A e para individuos com habilidade extraordinaria em:

- Ciencias
- Artes
- Educacao
- Negocios
- Atletismo

Requisitos (precisa de 3 de 10 criterios):
- Premios nacionais/internacionais
- Membros de associacoes exclusivas
- Artigos publicados sobre seu trabalho
- Juiz de trabalhos de outros
- Contribuicoes originais significativas
- Artigos academicos
- Exposicoes artisticas
- Papel de lideranca
- Salario alto
- Sucesso comercial nas artes

Atenciosamente,
Immigrant Law Center
```

### Template #18 - Processo NIW Detalhado
```
O processo do EB-2 NIW envolve:

1. AVALIACAO INICIAL (1-2 semanas)
   - Analise de qualificacoes
   - Estrategia do caso

2. PREPARACAO (2-3 meses)
   - Coleta de documentos
   - Cartas de recomendacao
   - Peticao detalhada

3. SUBMISSAO AO USCIS
   - Formulario I-140
   - Taxas governamentais (~$700)
   - Premium Processing opcional (~$2,500)

4. AGUARDAR DECISAO
   - Regular: 12-18 meses
   - Premium: 45 dias

5. AJUSTE DE STATUS ou CONSULAR
   - I-485 se nos EUA
   - Entrevista no consulado se fora

Gostaria de discutir seu caso especifico?

Atenciosamente,
Immigrant Law Center
```

---

## 4. PAGAMENTO

### Template #9 - Info Pagamento (EN)
```
Our fee structure:

- Free intro call (15 min): No charge
- Paid consultation (1 hour): $99
- Full case representation: Discussed during consultation

Government fees (approximate):
- I-140 filing: $700
- Premium Processing: $2,805 (optional)
- I-485 (if applicable): $1,225

Payment methods: Credit card, bank transfer, payment plans available.

Would you like to schedule a consultation?

Best regards,
Immigrant Law Center
```

### Template #33 - Valores NIW (PT)
```
Nossos valores para o processo EB-2 NIW:

Honorarios advocaticios:
- Valores acessiveis definidos de acordo com a complexidade do caso
- Consulta inicial de $99 (1 hora)

Taxas governamentais (aproximadas):
- I-140: $700
- Premium Processing: $2,805 (opcional)
- I-485 (se aplicavel): $1,225

Formas de pagamento:
- Cartao de credito
- Transferencia bancaria
- Parcelamento disponivel

Gostaria de agendar uma consulta para discutir seu caso?

Atenciosamente,
Immigrant Law Center
```

---

## 5. FOLLOW-UP

### Template #19 - Encaminhamento (EN)
```
Thank you for your interest!

Our team will follow up with you shortly. In the meantime, feel free to schedule a meeting:

https://calendly.com/center-immigrant/15min

Best regards,
Immigrant Law Center
```

### Template #20 - Encaminhamento (PT)
```
Obrigado pelo interesse!

Nossa equipe entrara em contato em breve. Enquanto isso, fique a vontade para agendar uma reuniao:

https://calendly.com/center-immigrant/15min

Atenciosamente,
Immigrant Law Center
```

### Template #21 - Follow-up 1 (4 dias)
```
Ola [NOME]!

Notamos que voce demonstrou interesse em nossos servicos de imigracao. Gostaríamos de saber se ainda podemos ajuda-lo(a).

Temos horarios disponiveis esta semana para uma conversa gratuita de 15 minutos:

https://calendly.com/center-immigrant/15min

Atenciosamente,
Immigrant Law Center
```

### Template #23 - Aguardando Docs
```
Ola [NOME]!

Estamos aguardando a documentacao para dar continuidade ao seu processo.

Documentos pendentes:
- [Lista de documentos]

Por favor, envie assim que possivel para evitar atrasos.

Qualquer duvida, estamos a disposicao.

Atenciosamente,
Immigrant Law Center
```

### Template #38 - Desculpas Demora
```
Ola!

Pedimos desculpas pela demora no retorno.

Estamos aqui para ajuda-lo! Em que posso auxiliar?

Se preferir, agende uma reuniao gratuita de 15 min:
https://calendly.com/center-immigrant/15min

Atenciosamente,
Immigrant Law Center
```

---

## 6. SUPORTE

### Template #34 - Credenciais/Legitimidade
```
Obrigado pela pergunta!

O Immigrant Law Center e um escritorio de advocacia licenciado, especializado em imigracao.

Nossos advogados sao:
- Membros da American Immigration Lawyers Association (AILA)
- Licenciados para praticar nos Estados Unidos
- Especializados em vistos EB-2 NIW e EB-1A

Voce pode verificar nossas credenciais em nosso site ou agendar uma conversa:
https://calendly.com/center-immigrant/15min

Atenciosamente,
Immigrant Law Center
```

### Template #35 - Suporte Tecnico
```
Lamento pelo inconveniente!

Se voce esta tendo problemas com algum link ou acesso, por favor tente:

1. Atualizar a pagina
2. Limpar o cache do navegador
3. Tentar outro navegador

Se o problema persistir, envie um email para:
info@legacy.example

Enquanto isso, voce pode agendar diretamente:
https://calendly.com/center-immigrant/15min

Atenciosamente,
Immigrant Law Center
```

### Template #39 - Verificando Info
```
Ola!

Essa e uma boa pergunta. Vou verificar com nossa equipe juridica para lhe dar uma resposta precisa.

Enquanto isso, gostaria de agendar uma reuniao para conversarmos melhor sobre seu caso?

Reuniao Gratuita (15 min):
https://calendly.com/center-immigrant/15min

Atenciosamente,
Immigrant Law Center
```

---

## 7. CASOS ESPECIAIS

### Template #36 - Caso Urgente (EN)
```
I understand this is urgent.

Let me connect you with our team immediately.

In the meantime, you can schedule an expedited consultation:
https://calendly.com/immigrant-info-swfe/consultation

We'll prioritize your case.

Best regards,
Immigrant Law Center
```

### Template #37 - Visto Revogado / Caso Complexo
```
Entendo a gravidade da situacao.

Casos de visto revogado ou situacoes complexas requerem atencao especial de nossa equipe juridica.

Recomendo agendar uma consulta urgente:
https://calendly.com/immigrant-info-swfe/consultation

Nossa equipe ira avaliar seu caso com prioridade.

Atenciosamente,
Immigrant Law Center
```

---

## 8. HANDOFF (Transicao Humano/Bot)

### Template #26 - Assumindo Conversa
```
Ola! Meu nome e [NOME] e vou continuar seu atendimento a partir de agora.

Ja vi o historico da sua conversa. Como posso ajuda-lo(a) hoje?
```

### Template #27 - Voltando ao Bot
```
Obrigado pelo contato! A partir de agora, nosso assistente virtual continuara disponivel para duvidas gerais.

Para falar com um humano novamente, basta digitar "atendente" ou "humano".

Tenha um otimo dia!
```

---

# REGRAS DO LLM CHATBOT

## NUNCA FAZER

1. **Mencionar ser IA/Bot**
   - Errado: "Como uma IA, posso ajudar..."
   - Certo: "Posso ajudar..."

2. **Mencionar localizacao**
   - Errado: "Nosso escritorio fica em Connecticut"
   - Certo: "Atendemos clientes de todo o mundo"

3. **Mencionar valores exatos de honorarios**
   - Errado: "Cobramos $5,000 pelo processo"
   - Certo: "Valores acessiveis, discutidos na consulta"

4. **Dar conselhos juridicos especificos**
   - Errado: "Voce com certeza sera aprovado"
   - Certo: "Vamos avaliar seu caso na consulta"

## SEMPRE FAZER

1. Usar template como BASE (adaptar, nao substituir)
2. Incentivar agendamento de reuniao
3. Assinar como "Immigrant Law Center"
4. Usar idioma do cliente (PT ou EN)
5. Ser cordial, profissional e empatico

## SINALIZAR [PRECISA_HUMANO]

- Perguntas sobre estrategia especifica de caso
- Valores detalhados de honorarios
- Prazos especificos de processo
- Questoes juridicas complexas
- Cliente insistente ou irritado
- Qualquer incerteza

---

# MONITORAMENTO

## Dashboard

Acesse: `http://[VPS_IP]:3001/llm-monitor`

Mostra:
- Atividade em tempo real
- Estatisticas de 24h
- Filtros por telefone e status
- Indicacao de casos que precisam de humano

## API Endpoints

### GET /api/llm-monitor/activity
```json
{
  "success": true,
  "data": [
    {
      "id": "...",
      "timestamp": "2026-01-30T10:00:00Z",
      "phone": "5511999999999",
      "clientName": "Maria",
      "messageIn": "Quanto custa?",
      "messageOut": "Nossos valores...",
      "intent": "price_inquiry",
      "template": "Valores NIW (PT)",
      "needsHuman": false
    }
  ]
}
```

### GET /api/llm-monitor/stats
```json
{
  "success": true,
  "data": {
    "total": 150,
    "last24h": 45,
    "lastHour": 5,
    "needsHumanCount": 3,
    "successRate": 95,
    "topIntents": [
      { "intent": "schedule_request", "count": 15 },
      { "intent": "price_inquiry", "count": 12 }
    ]
  }
}
```

---

# MANUTENCAO

## Backup

Backup disponivel em:
```
/var/www/legacy.example/whatsapp-bot/backup-20260130/
```

## Rollback

Se necessario:
```bash
cp /var/www/legacy.example/whatsapp-bot/backup-20260130/* /var/www/legacy.example/whatsapp-bot/
pm2 restart whatsapp-bot
```

## Logs

```bash
# Ver logs em tempo real
pm2 logs whatsapp-bot

# Ver logs do LLM
cat /var/www/legacy.example/whatsapp-bot/logs/llm-activity.json
```

## Reiniciar

```bash
pm2 restart whatsapp-bot
```

---

*Documento gerado em 30/01/2026 - Versao 10.6*
