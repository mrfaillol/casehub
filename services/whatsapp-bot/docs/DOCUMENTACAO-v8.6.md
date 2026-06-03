# WhatsApp Bot - Immigrant Law Center
## Documentacao Tecnica Completa - Versao 8.6

**Data:** 2024-12-22
**Versao:** 8.6 (Smart Features + API + Metrics)

---

## 1. NOVIDADES DA VERSAO 8.6

### 1.1 Validacao Inteligente de Email
O bot agora detecta erros de digitacao comuns em emails e sugere correcoes:

```javascript
COMMON_EMAIL_TYPOS = {
  'gmail.con': 'gmail.com',
  'gmail.co': 'gmail.com',
  'gmial.com': 'gmail.com',
  'gmal.com': 'gmail.com',
  'gmaill.com': 'gmail.com',
  'gamil.com': 'gmail.com',
  'hotmail.con': 'hotmail.com',
  'hotmal.com': 'hotmail.com',
  'outlook.con': 'outlook.com',
  'outloo.com': 'outlook.com',
  'yahoo.con': 'yahoo.com',
  'yaho.com': 'yahoo.com',
  // ... e mais
}
```

**Exemplo de uso:**
- Usuario digita: `joao@gmail.con`
- Bot responde: "Voce quis dizer joao@gmail.com? (responda 'sim' ou digite o email correto)"

### 1.2 Mensagens Variadas
O bot agora usa mensagens variadas para nao parecer repetitivo:

```javascript
VARIED_MESSAGES = {
  pt: {
    ask_name_again: [
      "Desculpe, nao entendi bem. Pode me dizer apenas seu nome?",
      "Hmm, nao consegui identificar seu nome. Pode digitar so o seu primeiro nome?",
      "Parece que houve um mal-entendido. Qual e o seu nome?",
      "Nao consegui captar seu nome. Pode repetir, por favor?"
    ],
    invalid_interest: [
      "Por favor, escolha uma opcao de 1 a 5 digitando apenas o numero.",
      "Preciso que voce digite um numero de 1 a 5 para continuar.",
      "Para seguirmos, por favor digite o numero da opcao desejada (1-5).",
      "Nao entendi sua escolha. Digite apenas o numero (1, 2, 3, 4 ou 5)."
    ],
    invalid_consultation: [
      "Por favor, digite 1 para consulta gratuita ou 2 para consulta paga.",
      "Preciso que voce escolha: 1 (gratuita) ou 2 (paga).",
      "Para continuar, digite apenas 1 ou 2.",
      "Nao entendi. Voce prefere 1 (gratuita) ou 2 (paga)?"
    ]
  },
  // en e es tambem tem 4 variacoes cada
}
```

### 1.3 Deteccao de Urgencia
O bot detecta situacoes de urgencia em qualquer momento da conversa:

```javascript
URGENCY_PATTERNS = {
  pt: [
    /\b(urgente|urgência|urgencia|emergência|emergencia)\b/i,
    /\b(deporta(do|ndo|ção|cao)|preso|detido|pris[aã]o)\b/i,
    /\b(visto\s*(vence|vencendo|expirado|expirando))\b/i,
    /\b(preciso\s*viajar\s*(urgente|amanha|hoje))\b/i,
    /\b(audiência|audiencia|tribunal|corte|juiz)\b/i,
    /\b(removal|deportation\s*order)\b/i
  ],
  en: [
    /\b(urgent|emergency|asap|immediately)\b/i,
    /\b(deport(ed|ing|ation)|detained|arrest(ed)?|jail|prison)\b/i,
    // ...
  ],
  es: [
    /\b(urgente|emergencia|ayuda)\b/i,
    /\b(deporta(do|ndo|ción|cion))\b/i,
    // ...
  ]
}
```

**Quando detectada urgencia:**
1. Lead e marcada como urgente no banco
2. Bot envia mensagem especial de urgencia com contato direto
3. Notificacao enviada ao Telegram (se configurado)
4. Score aumentado em 15 pontos

### 1.4 FAQ Automatico
O bot responde automaticamente perguntas frequentes:

**Perguntas detectadas:**
- **Preco/Valor:** "quanto custa", "qual o valor", "how much", "precio"
- **Localizacao:** "onde fica", "qual endereco", "where are you", "direccion"
- **Tempo de processo:** "quanto tempo demora", "how long", "cuanto tiempo"
- **Documentos:** "que documentos", "what documents", "que documentos"

**Exemplo:**
- Usuario: "Quanto custa uma consulta?"
- Bot: "Temos duas opcoes:

1️⃣ *Ligacao introdutoria GRATUITA*
   Conheca nossa equipe, tire duvidas gerais...

2️⃣ *Consulta PAGA (US$ 200)*
   Analise completa do seu caso...

Quer que eu explique mais sobre alguma opcao?"

### 1.5 API de Metricas e Historico

**GET /api/metrics**
Retorna metricas do bot (padrao: ultimos 7 dias)
```json
{
  "period": "7 dias",
  "metrics": {
    "totalLeads": 26,
    "leadsPerDay": [...],
    "byStatus": {"cold": 20, "warm": 6, "qualified": 0, "hot": 0},
    "byInterest": [...],
    "byLanguage": {"pt": 22, "en": 4, "es": 0},
    "consultations": {"free": "7", "paid": "0", "scheduled": "0"},
    "avgScore": 46,
    "urgentLeads": 0,
    "avgResponseMinutes": 934
  }
}
```

**GET /api/metrics?days=30**
Metricas dos ultimos 30 dias

**GET /api/metrics/html**
Dashboard HTML com metricas visuais (pode ser acessado pelo navegador)

**GET /api/lead/:phone**
Retorna resumo formatado de um lead especifico
```json
{
  "phone": "15084008485",
  "summary": "====================================\nRESUMO DA LEAD\n====================================\nNome: Sebastiao Nunes\nTelefone: 15084008485\nEmail: nunessgn@gmail.com\n..."
}
```

---

## 2. VISAO GERAL DO SISTEMA

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

## 3. ARQUIVOS PRINCIPAIS

### 3.1 server.js (v8.6)
**Funcao:** Servidor principal Express que gerencia todas as rotas e integracao

**Rotas principais:**
- `GET /` - Status do bot
- `GET /qr` - QR Code para conexao WhatsApp
- `GET /health` - Health check
- `GET /stats` - Estatisticas basicas
- `GET /api/metrics` - **v8.6** Metricas completas (JSON)
- `GET /api/metrics/html` - **v8.6** Dashboard de metricas (HTML)
- `GET /api/lead/:phone` - **v8.6** Resumo de lead especifico
- `GET /api/leads` - Lista de leads qualificados
- `POST /webhook/form` - Webhook para formularios do site
- `POST /webhook/messenger` - Webhook do Facebook Messenger
- `POST /webhook/meta-leads` - Webhook para Facebook Lead Ads
- `POST /webhook/stripe` - Webhook do Stripe (pagamentos)
- `POST /webhook/calendly` - Webhook do Calendly (agendamentos)

### 3.2 bot-flow.js (v8.6)
**Funcao:** Logica do fluxo de conversa com o usuario

**Estados do fluxo (STATES):**
1. `NEW` - Novo contato, envia boas-vindas
2. `ASKED_NAME` - Perguntou o nome, aguardando resposta
3. `ASKED_INTEREST` - Perguntou interesse (1-5), aguardando resposta
4. `ASKED_EMAIL` - Perguntou email, aguardando resposta
5. `ASKED_EMAIL_CONFIRM` - **v8.6** Aguardando confirmacao de email corrigido
6. `ASKED_CONSULTATION_TYPE` - Perguntou tipo consulta (1-gratuita, 2-paga)
7. `AWAITING_PAYMENT` - Aguardando pagamento (consulta paga)
8. `ASKED_SCHEDULING` - Perguntou horario para agendamento
9. `TRANSFERRED` - Conversa transferida para equipe humana

**Funcoes principais v8.6:**
- `validateAndSuggestEmail(email)` - Valida email e sugere correcoes
- `detectUrgency(msg, lang)` - Detecta situacoes de urgencia
- `detectAndAnswerFAQ(msg, lang)` - Detecta e responde perguntas frequentes
- `getVariedMessage(lang, type, phone)` - Retorna mensagem variada

### 3.3 database.js (v8.6)
**Funcao:** Persistencia de dados em MySQL

**Novas funcoes v8.6:**
- `getLeadSummary(phone)` - Retorna resumo formatado do lead
- `getMetricsReport(days)` - Retorna metricas completas

### 3.4 languages.js (v1.0)
**Funcao:** Deteccao de idioma e mensagens multilíngue (sem alteracoes)

---

## 4. FLUXO DE CONVERSACAO v8.6

```
[Usuario envia mensagem]
        |
        +--> [Detecta urgencia?] --> SIM --> Marca urgente + Envia msg especial
        |
        +--> [Pergunta FAQ?] --> SIM --> Responde FAQ automaticamente
        |
        v
[NEW] -> Envia boas-vindas + pergunta nome
        |
        v
[ASKED_NAME] -> Valida nome (Smart Name Detection)
        |
        +--> Nome invalido? Envia MENSAGEM VARIADA pedindo nome
        |
        v
[ASKED_INTEREST] -> Pergunta interesse (1-5)
        |
        +--> Resposta invalida? Envia MENSAGEM VARIADA
        |
        v
[ASKED_EMAIL] -> Pergunta email (ou "pular")
        |
        +--> Email com typo? --> [ASKED_EMAIL_CONFIRM]
        |                              |
        |                              +--> "sim" -> Usa email corrigido
        |                              +--> novo email -> Valida novamente
        |
        v
[ASKED_CONSULTATION_TYPE] -> Pergunta tipo (1-gratuita, 2-paga)
        |
        +--> Resposta invalida? Envia MENSAGEM VARIADA
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

## 5. SISTEMA DE SCORE

### Score de Leads WhatsApp (0-100):
- Engajamento: 2 pontos por mensagem (max 20)
- Dados fornecidos: nome (5), email (5), telefone (10), profissao (5)
- Tipo de visto: alto valor (25), medio valor (15), outros (5)
- Urgencia: sim (15)
- Consulta: paga (15), paga pendente (10), gratuita (5)

### Status baseado no Score:
- `hot` - Score >= 70-90 (dependendo da fonte)
- `qualified` - Score >= 50-70
- `warm` - Score >= 30-50
- `cold` - Score < 30

---

## 6. COMANDOS DE MANUTENCAO

### Reiniciar bot:
```bash
cd /var/www/legacy.example/whatsapp-bot
pm2 restart whatsapp-bot
```

### Ver logs:
```bash
pm2 logs whatsapp-bot --lines 100
```

### Verificar versao:
```bash
head -10 /var/www/legacy.example/whatsapp-bot/bot-flow.js
```

### Acessar metricas:
- Dashboard: http://SEU_IP:3001/api/metrics/html
- JSON: http://SEU_IP:3001/api/metrics
- Lead especifico: http://SEU_IP:3001/api/lead/TELEFONE

---

## 7. ESTRUTURA DE ARQUIVOS

```
/var/www/legacy.example/whatsapp-bot/
├── server.js              # Servidor principal (v8.6)
├── bot-flow.js            # Logica de conversa (v8.6)
├── languages.js           # Mensagens multilíngue
├── database.js            # Persistencia MySQL (v8.6)
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
│   ├── DOCUMENTACAO-v8.5.md
│   └── DOCUMENTACAO-v8.6.md
├── backups/               # Backups por versao
│   ├── v8.5-20251222-*/
│   └── v8.6-20251222/
└── logs/                  # Logs locais
```

---

## 8. HISTORICO DE VERSOES

- **v8.6** (2024-12-22): Smart Features + API + Metrics
  - Validacao inteligente de email com sugestoes
  - Mensagens variadas (4 por tipo)
  - Deteccao de urgencia em qualquer momento
  - FAQ automatico (preco, localizacao, tempo, documentos)
  - API de metricas (/api/metrics, /api/metrics/html)
  - API de resumo de lead (/api/lead/:phone)

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

---

## 9. VARIAVEIS DE AMBIENTE (.env)

```
# WhatsApp
WHATSAPP_SESSION=immigrant-law

# Database
DB_HOST=localhost
DB_USER=immigrant_bot
DB_PASSWORD=[REDACTED - see .env]
DB_NAME=immigrant_whatsapp

# Integracoes
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

## 10. PROXIMAS MELHORIAS PLANEJADAS

1. ~~Validacao inteligente de email~~ ✅ v8.6
2. ~~Mensagens variadas~~ ✅ v8.6
3. ~~Deteccao de urgencia~~ ✅ v8.6
4. ~~FAQ automatico~~ ✅ v8.6
5. ~~API de metricas~~ ✅ v8.6
6. ~~Historico resumido para equipe~~ ✅ v8.6
7. Corrigir integracao Telegram (chat_id)
8. Dashboard web completo com graficos
