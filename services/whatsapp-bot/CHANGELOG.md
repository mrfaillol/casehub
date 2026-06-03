# WhatsApp Bot - Immigrant Law Center
## Changelog

---

## v8.2 - Full Conversion Tracking (19/12/2024)

### Novidades
- **Conversion Tracking Completo** para Google Ads e Facebook CAPI
- Rastreamento em 7 pontos de conversão:
  - Nova lead WhatsApp → Facebook: `Lead`
  - Nova lead Site/Form → Facebook: `Lead`
  - Lead qualificada (score ≥50) → Facebook: `CompleteRegistration`
  - Lead urgente → Facebook: `CompleteRegistration`
  - Consulta agendada → Facebook: `Schedule`
  - Pagamento confirmado → Facebook: `Purchase` ($99)

### Configuração
- `FB_PIXEL_ID=828419255275165`
- `FB_CAPI_TOKEN` configurado no `.env`

---

## v8.1.1 - Smart Name Detection Completo (19/12/2024)

### Novidades
- **Detecção inteligente de nome em campo errado** expandida
- Lista completa de "não-nomes":
  - Saudações PT: oi, olá, bom dia, boa tarde, boa noite, opa, eai, fala, salve
  - Saudações EN: hi, hello, hey, good morning, good afternoon, good evening
  - Saudações ES: hola, buenos dias, buenas tardes, buenas noches
  - Respostas: sim, não, ok, obrigado, valeu, blz
  - Pedidos: ajuda, preciso de ajuda, como funciona, quanto custa
  - Vistos: green card, visto, cidadania, eb1, h1b, etc.
  - Profissões: advogado, médico, engenheiro

### Extração de Nome
- Detecta padrões como:
  - "Meu nome é João"
  - "Me chamo Maria"
  - "Sou o Carlos"
  - "My name is John"
  - "Me llamo Pedro"

### Validação
- Nome válido: 2-50 chars, 1-4 palavras, sem números
- Corrige automaticamente quando detecta erro

---

## v8.1 - Smart Name Detection (19/12/2024)

### Novidades
- Detecção básica de nome em campo errado
- Correção automática de saudações como nome

---

## v8.0 - Conversion Tracking Module (19/12/2024)

### Novidades
- Novo módulo `conversion-tracking.js`
- Integração com Facebook Conversions API (CAPI)
- Preparação para Google Ads API

### Funções
- `trackNewLead()` - Nova lead
- `trackQualifiedLead()` - Lead qualificada
- `trackConsultationScheduled()` - Consulta agendada
- `trackPaymentCompleted()` - Pagamento confirmado

---

## v7.9 - WhatsApp Follow-ups (19/12/2024)

### Novidades
- **2 follow-ups obrigatórios** antes de registrar lead no Moskit
- Mensagens personalizadas por idioma (PT/EN/ES)

### Fluxo
1. Lead inativa por 2h → Primeiro follow-up
2. Ainda sem resposta +2h → Segundo follow-up
3. Após 2 follow-ups sem resposta → Registra no Moskit automaticamente

### Banco de Dados
- Nova coluna: `followup_count` (INT DEFAULT 0)
- Nova coluna: `last_followup_at` (DATETIME)

---

## v7.8 - Messenger Handler (19/12/2024)

### Novidades
- Novo módulo `messenger-handler.js`
- Gerenciamento inteligente de leads do Messenger
- Objetivo: migrar leads para WhatsApp

### Configuração
- Timeout inatividade: 4 horas
- Intervalo follow-up: 2 horas
- Máximo follow-ups: 2
- Score base Messenger: 15
- Score máximo Messenger: 45

### Regras
- Só registra no Moskit se:
  - Tem contato real (telefone ou email)
  - Não migrou para WhatsApp
  - Inativo por 4h após follow-ups

---

## v7.7.2 - Elementor Form Integration (19/12/2024)

### Novidades
- Suporte completo ao formato `form_fields` do Elementor
- Mapeamento expandido de campos:
  - Nome: `Nome`, `Nome Completo`, `name`, `nome`
  - Email: `Email`, `E-mail`, `email`
  - Telefone: `Telefone ou Celular`, `Telefone`, `telefone`, `phone`
  - Mensagem: `Mensagem`, `Como podemos te ajudar?`, `message`
  - UTM: `utm_source`, `utm_campaign`, `utm_medium`, `utm_term`, `utm_content`

### Endpoint
- `POST /webhook/site-lead`
- Aceita dados diretos ou dentro de `form_fields`

---

## Arquivos do Projeto

```
/var/www/legacy.example/whatsapp-bot/
├── server.js              # Servidor principal (v8.2)
├── bot-flow.js            # Fluxo de conversa e estados
├── database.js            # Banco de dados MySQL
├── conversion-tracking.js # Rastreamento Google/Facebook
├── messenger-handler.js   # Handler do Messenger
├── email.js               # Notificações por email
├── telegram.js            # Notificações Telegram
├── stripe-handler.js      # Processamento de pagamentos
├── .env                   # Variáveis de ambiente
└── CHANGELOG.md           # Este arquivo
```

---

## Variáveis de Ambiente (.env)

```env
# MySQL
DB_HOST=localhost
DB_USER=xxx
DB_PASS=xxx
DB_NAME=whatsapp_bot

# APIs
MOSKIT_API_KEY=xxx
CALENDLY_TOKEN=xxx
STRIPE_SECRET_KEY=xxx
STRIPE_WEBHOOK_SECRET=xxx

# Notificações
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
EMAIL_USER=xxx
EMAIL_PASS=xxx

# Facebook CAPI
FB_PIXEL_ID=828419255275165
FB_CAPI_TOKEN=xxx

# Google Ads (futuro)
# GOOGLE_ADS_API_KEY=xxx
```

---

## Sistema de Score

| Critério | Pontos | Descrição |
|----------|--------|-----------|
| Engajamento | 0-20 | 2 pts/mensagem (máx 20) |
| Dados fornecidos | 0-25 | Nome: 5, Email: 5, WhatsApp: 10, Profissão: 5 |
| Tipo de visto | 0-25 | Alto valor: 25, Médio: 15, Baixo: 5 |
| Urgência | 0-15 | Crítica: 15, Alta: 10, Normal: 0 |
| Consulta | 0-15 | Paga+confirmada: 15, Paga: 10, Gratuita: 5 |

### Classificação
- **HOT** (90-100): Prioridade máxima
- **QUALIFIED** (70-89): Qualificado
- **WARM** (50-69): Morno
- **COLD** (0-49): Frio

---

## Formato Moskit

```
[LEAD <ORIGEM> <SCORE> <NOME>]
```

Exemplos:
- `[LEAD WPP 85 João Silva]`
- `[LEAD META 72 Maria Santos]`
- `[LEAD SITE 60 Carlos Lima]`
- `[LEAD MSG 45 Ana Costa]`

---

## Conversion Tracking - Eventos

| Momento | Facebook | Google |
|---------|----------|--------|
| Nova lead WhatsApp | `Lead` | `generate_lead` |
| Nova lead Site | `Lead` | `generate_lead` |
| Lead qualificada | `CompleteRegistration` | `qualified_lead` |
| Lead urgente | `CompleteRegistration` | `qualified_lead` |
| Consulta agendada | `Schedule` | `consultation_scheduled` |
| Pagamento | `Purchase` ($99) | `purchase` |

---

## Contato

- **WhatsApp Bot**: +1 (940) 618-8140
- **Site**: https://legacy.example
- **Servidor**: REDACTED-HOST

---

## v11.1 - Auto Quick Intake + Lead Qualification (2026-02-05 10:33 BRT)

**Autor:** Claude Opus 4.5 + Admin
**Data:** 2026-02-05 10:33:22 BRT
**Arquivos modificados:**

### bot-flow.js
- Atualizado de v10.0 para v11.1
- Adicionado auto-trigger do Quick Intake apos 4+ mensagens do usuario
- Verifica `lead.message_count >= 4` e `!lead.quick_intake_completed`
- Retorna `shouldStartIntake: true` para server.js processar
- Mantido fluxo LLM para mensagens anteriores ao trigger

### server.js
- **Removido** bloco de reset do Quick Intake (v10.3) que resetava estados de intake para `awaiting_human`
- **Adicionado** processamento ativo do Quick Intake em andamento (perguntas/respostas)
- **Adicionado** contagem de mensagens do usuario (`db.getConversationHistory`) antes de chamar botFlow
- **Adicionado** handler para `shouldStartIntake` com mensagem de transicao trilíngue (PT/EN/ES)
- **Adicionado** funcao `generateRecommendation(scoring, lang)` - gera recomendacao personalizada trilíngue baseada no score:
  - Score >= 70: Recomenda consulta paga ($99)
  - Score 50-69: Sugere reuniao gratuita + opcao paga
  - Score < 50: Oferece reuniao gratuita
  - Inclui pathways de imigracao identificados (FAMILY, ASYLUM, VAWA, U-VISA, EMPLOYMENT)
- **Adicionado** case `start_quick_intake` no switch de acoes
- **Adicionado** registro no Moskit ao completar Quick Intake (score + pathways)

### llm-chatbot.js
- **Adicionado** secao "OBJETIVO PRINCIPAL - AGENDAMENTO (v11.1)" no SYSTEM_PROMPT do Gemini
- LLM agora guia naturalmente a conversa para agendamento de reuniao
- Links Calendly incluidos: gratuita (15min) e consulta paga ($99)

### database (MariaDB)
- **Criadas** colunas: `quick_intake_answers` (TEXT), `quick_intake_scoring` (TEXT), `quick_intake_completed` (BOOLEAN DEFAULT FALSE) na tabela `leads`

### Fluxo Novo
```
Lead nova → welcome_handoff → aguarda resposta
  "1" → link gratuito
  "2" → link pago
  Outra msg → LLM responde (com guia para agendamento)
  4+ msgs sem intake → Auto Quick Intake (12 perguntas)
  Intake completo → Score + Recomendacao personalizada + Links Calendly
```

### Backups
- `bot-flow.js.bak.20260205_*`
- `server.js.bak.20260205_*`
- `llm-chatbot.js.bak.20260205_*`

