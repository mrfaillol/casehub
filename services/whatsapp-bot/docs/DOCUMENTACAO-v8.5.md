# WhatsApp Bot - Immigrant Law Center
## Documentacao Tecnica Completa - Versao 8.5

**Data:** 2024-12-22
**Versao:** 8.5 (Restrictive Mode + Language Fix)

---

## 1. VISAO GERAL

O bot e um sistema automatizado de atendimento via WhatsApp para o escritorio de imigracao Immigrant Law Center. Ele qualifica leads, coleta informacoes e agenda consultas.

### Integracoes Ativas
- **Moskit CRM** - Registro de leads
- **Calendly** - Agendamento de consultas
- **Stripe** - Pagamentos de consultas pagas
- **Resend** - Envio de emails
- **Telegram** - Notificacoes internas
- **Facebook CAPI** - Rastreamento de conversoes
- **Make.com** - Integracao com Facebook Lead Ads

---

## 2. ARQUIVOS PRINCIPAIS

### 2.1 server.js (v8.2)
**Funcao:** Servidor principal Express que gerencia todas as rotas e integracao

**Principais funcoes:**
- `shouldProcessMessage(messageId, phoneNumber)` - Evita processar mensagens duplicadas
- `formatMoskitName(leadData)` - Formata nome no padrao `[LEAD ORIGEM SCORE NOME]`
- `calculateFormScore(formData)` - Calcula score para leads do formulario
- `calculateLeadScore(lead)` - Calcula score para leads do WhatsApp
- `createMoskitContact(leadData)` - Cria contato no Moskit CRM
- `getWhatsAppName(message)` - Captura nome do perfil WhatsApp
- `checkIncompleteLeads()` - Verifica e faz follow-up de leads incompletas
- `checkLeadsAwaitingConsultation()` - Follow-up para leads aguardando consulta

**Rotas principais:**
- `GET /` - Status do bot
- `GET /qr` - QR Code para conexao WhatsApp
- `GET /health` - Health check
- `GET /stats` - Estatisticas
- `POST /webhook/form` - Webhook para formularios do site
- `POST /webhook/messenger` - Webhook do Facebook Messenger
- `POST /webhook/meta-leads` - Webhook para Facebook Lead Ads
- `POST /webhook/stripe` - Webhook do Stripe (pagamentos)
- `POST /webhook/calendly` - Webhook do Calendly (agendamentos)

**Configuracoes:**
```javascript
MOSKIT_CONFIG = {
  apiKey: "[REDACTED - see .env]",
  baseUrl: "https://api.moskitcrm.com/v2",
  responsibleId: 105810
}
INCOMPLETE_LEAD_TIMEOUT_HOURS = 2  // Timeout para auto-registro
MESSAGE_CACHE_TTL = 120000         // 2 minutos
LOCK_TTL = 5000                    // 5 segundos
FORM_CACHE_TTL = 300000            // 5 minutos
```

### 2.2 bot-flow.js (v8.5)
**Funcao:** Logica do fluxo de conversa com o usuario

**Estados do fluxo (STATES):**
1. `NEW` - Novo contato, envia boas-vindas
2. `ASKED_NAME` - Perguntou o nome, aguardando resposta
3. `ASKED_INTEREST` - Perguntou interesse (1-5), aguardando resposta
4. `ASKED_EMAIL` - Perguntou email, aguardando resposta
5. `ASKED_CONSULTATION_TYPE` - Perguntou tipo consulta (1-gratuita, 2-paga)
6. `AWAITING_PAYMENT` - Aguardando pagamento (consulta paga)
7. `ASKED_SCHEDULING` - Perguntou horario para agendamento
8. `TRANSFERRED` - Conversa transferida para equipe humana

**Principais funcoes:**
- `isValidName(str)` - Valida se string e um nome valido (Smart Name Detection)
- `extractRealName(msg, lang)` - Extrai nome de frases como "meu nome e X"
- `formatName(name)` - Capitaliza nome corretamente
- `extractOptionNumber(msg, maxOption)` - Extrai numero de opcao da mensagem
- `isValidInterestResponse(msg)` - **v8.5** Valida resposta de interesse
- `isValidConsultationResponse(msg)` - **v8.5** Valida resposta de consulta
- `processMessage(message, currentState, leadData, context)` - Processa mensagem

**Smart Name Detection (v8.5):**
O bot possui listas extensas para detectar o que NAO e um nome:
- `VERBOS_PT` - Verbos em portugues (~110 items)
- `VERBOS_EN` - Verbos em ingles (~150 items)
- `VERBOS_ES` - Verbos em espanhol (~70 items)
- `ADVERBIOS` - Adverbios em 3 idiomas
- `PREPOSICOES_ARTIGOS` - Preposicoes e artigos
- `CONJUNCOES` - Conjuncoes
- `PRONOMES` - Pronomes
- `SAUDACOES` - Saudacoes e despedidas
- `EXPRESSOES_COMUNS` - Expressoes comuns (~150 items)
- `NOT_A_NAME_PATTERNS` - Regex para detectar frases

**Modo Restritivo (v8.5):**
- No estado `ASKED_INTEREST`: So aceita numeros 1-5 ou palavras-chave validas
- No estado `ASKED_CONSULTATION_TYPE`: So aceita 1 ou 2
- Se resposta invalida: repete a pergunta (nao continua o fluxo)

### 2.3 languages.js (v1.0)
**Funcao:** Deteccao de idioma e mensagens multilíngue

**Idiomas suportados:**
- `pt` - Portugues (Brasil DDI 55, Portugal DDI 351)
- `en` - Ingles (EUA/Canada DDI 1, UK DDI 44, etc)
- `es` - Espanhol (Argentina 54, Chile 56, Mexico 52, etc)

**Principais funcoes:**
- `detectLanguage(phoneNumber)` - Detecta idioma pelo DDI do telefone
- `getMessages(lang)` - Retorna objeto com todas as mensagens no idioma
- `getLanguageName(lang)` - Retorna nome do idioma

**Mensagens por idioma:**
- `welcome` - Boas-vindas
- `ask_name_again` - Pedir nome novamente
- `ask_interest(name)` - Perguntar interesse
- `ask_email(interest)` - Perguntar email
- `ask_consultation_type(name)` - Perguntar tipo de consulta
- `invalid_consultation_choice` - Escolha invalida
- `free_consultation_confirmed(name)` - Confirmacao consulta gratuita
- `payment_pending` - Pagamento pendente
- `scheduling_prompt(slots)` - Mostrar horarios
- `confirmation(name, slotDisplay, url)` - Confirmacao de agendamento
- `transferred` - Mensagem de transferencia
- `urgent` - Mensagem de urgencia
- `error` - Mensagem de erro

### 2.4 database.js (v8.2)
**Funcao:** Persistencia de dados em MySQL

**Tabelas:**
1. `conversations` - Historico de mensagens
   - phone, role (user/assistant), content, created_at

2. `leads` - Dados dos leads
   - Campos principais: phone, name, email, visa_interest, conversation_state
   - Campos de score: lead_score, lead_status (cold/warm/qualified/hot)
   - Campos de consulta: consultation_type, payment_status, consultation_scheduled
   - Campos de follow-up: followup_count, last_followup_at, awaiting_consultation_followup
   - Campos de integracao: moskit_sent, moskit_id, auto_registered

**Principais funcoes:**
- `saveMessage(phone, role, content)` - Salva mensagem
- `getConversationHistory(phone, limit)` - Busca historico
- `getLead(phone)` - Busca lead por telefone
- `updateLead(phone, data)` - Atualiza dados do lead
- `getIncompleteLeads(cutoffTime)` - Leads para auto-registro
- `getLeadsAwaitingConsultation()` - Leads aguardando consulta
- `getStats()` - Estatisticas gerais
- `getConversationSummary(phone)` - Resumo da conversa

---

## 3. FLUXO DE CONVERSACAO

```
[Usuario envia mensagem]
        |
        v
[NEW] -> Envia boas-vindas + pergunta nome
        |
        v
[ASKED_NAME] -> Valida nome (Smart Name Detection)
        |
        +--> Nome invalido? Pede novamente
        |
        v
[ASKED_INTEREST] -> Pergunta interesse (1-5)
        |
        +--> v8.5: So aceita 1-5 ou palavras-chave
        |
        v
[ASKED_EMAIL] -> Pergunta email (ou "pular")
        |
        v
[ASKED_CONSULTATION_TYPE] -> Pergunta tipo (1-gratuita, 2-paga)
        |
        +--> v8.5: So aceita 1 ou 2
        |
        v
[Opcao 1: Gratuita]          [Opcao 2: Paga]
        |                            |
        v                            v
[TRANSFERRED]              [AWAITING_PAYMENT]
   Envia email                Envia link Stripe
   Notifica equipe                   |
                                     v
                           [Pagamento confirmado]
                                     |
                                     v
                           [ASKED_SCHEDULING]
                              Mostra horarios
                                     |
                                     v
                           [TRANSFERRED]
                              Confirma agendamento
```

---

## 4. SISTEMA DE SCORE

### Score de Leads WhatsApp (0-100):
- Engajamento: 2 pontos por mensagem (max 20)
- Dados fornecidos: nome (5), email (5), telefone (10), profissao (5)
- Tipo de visto: alto valor (25), medio valor (15), outros (5)
- Urgencia: sim (15)
- Consulta: paga (15), paga pendente (10), gratuita (5)

### Score de Leads Formulario (0-100):
- Dados: nome (5), email (10), telefone (10), mensagem longa (5)
- Tipo de visto/interesse: alto valor (25), medio valor (15), outros (5)
- Pagina origem: investidor (15), green-card (10), contato (5)
- Idioma: ingles (5), portugues (3)
- Bonus campos completos: 2 pontos por campo

### Status baseado no Score:
- `hot` - Score >= 70-90 (dependendo da fonte)
- `qualified` - Score >= 50-70
- `warm` - Score >= 30-50
- `cold` - Score < 30

---

## 5. SISTEMA DE FOLLOW-UPS

### Follow-up de Leads Incompletas:
- Timeout: 2 horas sem resposta
- Follow-up 1: Apos 2h - Perguntar interesse novamente
- Follow-up 2: Apos mais 2h - Ultima tentativa
- Apos 2 follow-ups sem resposta: Auto-registra no Moskit

### Follow-up de Consultas Pendentes:
- Stage 0 -> 1: Apos 4h - Mensagem tranquilizadora
- Stage 1 -> 2: Apos 24h - Oferece link Calendly
- Stage 2 -> 3: Apos 48h - Ultima tentativa

---

## 6. FORMATO DE NOMES NO MOSKIT

Padrao: `[LEAD <ORIGEM> <SCORE> <NOME>]`

Origens:
- `WPP` - WhatsApp
- `MSG` - Messenger
- `IG` - Instagram
- `SITE` - Formulario do site
- `META` - Facebook Lead Ads

Exemplos:
- `[LEAD WPP 75 Joao Silva]`
- `[LEAD META 45 Maria Santos]`
- `[LEAD SITE 80 John Smith]`

---

## 7. WEBHOOKS

### POST /webhook/form
Recebe leads de formularios do site (Elementor)
```json
{
  "Nome": "Joao Silva",
  "Email": "joao@email.com",
  "Telefone": "5511999999999",
  "Mensagem": "Interesse em Green Card"
}
```

### POST /webhook/meta-leads
Recebe leads do Facebook Lead Ads (via Make.com)
```json
{
  "name": "Maria Santos",
  "phone": "5511888888888",
  "email": "maria@email.com",
  "interest": "Green Card",
  "source": "Meta Ads"
}
```

### POST /webhook/stripe
Recebe eventos do Stripe (pagamentos)
- Evento: `checkout.session.completed`
- Atualiza payment_status para 'paid'
- Inicia fluxo de agendamento

### POST /webhook/calendly
Recebe eventos do Calendly (agendamentos)
- Atualiza consultation_scheduled para true
- Envia confirmacao por email

---

## 8. VARIAVEIS DE AMBIENTE (.env)

```
# WhatsApp
WHATSAPP_SESSION=immigrant-law

# Database
DB_HOST=localhost
DB_USER=immigrant_bot
DB_PASSWORD=[REDACTED - see .env]
DB_NAME=immigrant_whatsapp

# Integrações
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
RESEND_API_KEY=re_...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
CALENDLY_API_KEY=...
FACEBOOK_PIXEL_ID=...
FACEBOOK_ACCESS_TOKEN=...
```

---

## 9. COMANDOS DE MANUTENCAO

### Reiniciar bot:
```bash
cd /var/www/legacy.example/whatsapp-bot
pm2 restart whatsapp-bot
```

### Ver logs:
```bash
pm2 logs whatsapp-bot --lines 100
```

### Status:
```bash
pm2 status
```

### Verificar versao:
```bash
head -10 /var/www/legacy.example/whatsapp-bot/bot-flow.js
```

---

## 10. HISTORICO DE VERSOES

- **v8.5** (2024-12-22): Modo restritivo + fix de idioma
  - Bot so aceita respostas validas em cada estado
  - Repete pergunta se resposta invalida
  - Logs de deteccao de idioma

- **v8.4** (2024-12-22): Smart Name Detection expandido
  - Listas massivas de NOT_A_NAME (~500+ items)
  - Regex patterns para detectar frases
  - Funcao extractOptionNumber()

- **v8.3** (2024-12-22): Smart Name Detection inicial
  - Lista NOT_A_NAME basica

- **v8.2** (2024-12-19): Conversion Tracking + Consultation Follow-ups
  - Facebook CAPI integrado
  - Follow-ups para consultas pendentes
  - Formato de nome Moskit padronizado

- **v7.x** (2024-12-17/18): Integracao Moskit + Email + Telegram
  - Auto-registro de leads incompletas
  - Sistema de score
  - Notificacoes multicanal

---

## 11. ESTRUTURA DE ARQUIVOS

```
/var/www/legacy.example/whatsapp-bot/
├── server.js              # Servidor principal
├── bot-flow.js            # Logica de conversa
├── languages.js           # Mensagens multilíngue
├── database.js            # Persistencia MySQL
├── whatsapp-client.js     # Cliente WhatsApp Web.js
├── calendly.js            # Integracao Calendly
├── stripe.js              # Integracao Stripe
├── email.js               # Integracao Resend
├── telegram.js            # Integracao Telegram
├── conversion-tracking.js # Facebook CAPI
├── messenger.js           # Facebook Messenger
├── messenger-handler.js   # Handler Messenger
├── moskit.js              # Integracao Moskit (legacy)
├── .env                   # Variaveis de ambiente
├── package.json           # Dependencias
├── docs/                  # Documentacao
├── backups/               # Backups por versao
└── logs/                  # Logs locais
```
