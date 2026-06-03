# API Key Rotation Guide - CaseHub Lite

> **Objetivo:** Rotacionar todas as API keys para desacoplar CaseHub da infraestrutura ILC.
> Cada serviço abaixo lista: onde gerar, formato esperado, variável `.env`, e comportamento se ausente.

---

## Prioridade ALTA

### 1. Stripe (Pagamentos)

| Campo | Valor |
|-------|-------|
| **Ação** | Criar novas keys de produção na sua conta Stripe pessoal |
| **URL** | https://dashboard.stripe.com/apikeys |
| **Variáveis `.env`** | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| **Formato** | `sk_live_...` (secret), `pk_live_...` (publishable), `whsec_...` (webhook) |
| **Se ausente** | Degradação graceful -- rotas de billing/subscription retornam erro mas app funciona. Planos ficam inacessíveis. |

**Passo a passo:**
1. Acesse https://dashboard.stripe.com/apikeys
2. Clique "Create restricted key" ou use as Standard keys
3. Copie a Secret key (`sk_live_...`) para `STRIPE_SECRET_KEY`
4. Copie a Publishable key (`pk_live_...`) para `STRIPE_PUBLISHABLE_KEY`
5. Em Developers > Webhooks, crie um endpoint apontando para `{BASE_URL}/webhooks/stripe`
6. Copie o signing secret (`whsec_...`) para `STRIPE_WEBHOOK_SECRET`
7. Opcionalmente configure Price IDs: `STRIPE_PRICE_PROFESSIONAL`, `STRIPE_PRICE_ENTERPRISE`

---

### 2. Resend (Email Transacional)

| Campo | Valor |
|-------|-------|
| **Ação** | Gerar nova API key |
| **URL** | https://resend.com/api-keys |
| **Variável `.env`** | `RESEND_API_KEY` |
| **Formato** | `re_...` (ex: `re_123abc456def`) |
| **Se ausente** | Degradação graceful -- emails transacionais (confirmação, reset senha) falham silenciosamente. App funciona via SMTP se configurado. |

**Passo a passo:**
1. Crie conta em https://resend.com (plano gratuito: 3k emails/mês)
2. Vá em API Keys > Create API Key
3. Nomeie como "CaseHub Lite Production"
4. Copie a key `re_...` para `RESEND_API_KEY`
5. Configure e verifique seu domínio em Domains (necessário para envio em produção)

---

### 3. Google OAuth (Autenticação + Drive)

| Campo | Valor |
|-------|-------|
| **Ação** | Revogar credenciais ILC, criar projeto novo no Google Cloud |
| **URL** | https://console.cloud.google.com/apis/credentials |
| **Variáveis `.env`** | `GOOGLE_DRIVE_CREDENTIALS_PATH`, `GOOGLE_DRIVE_TOKEN_PATH`, `GOOGLE_DRIVE_ROOT_ID`, `GOOGLE_DRIVE_TASKS_ID` |
| **Formato** | Arquivo JSON (`credentials.json`) + token pickle gerado automaticamente |
| **Se ausente** | Degradação graceful -- sincronização Google Drive desabilitada. Upload/download de documentos funciona local. |

**Passo a passo:**
1. Acesse https://console.cloud.google.com
2. Crie um novo projeto "CaseHub Lite"
3. Ative as APIs: Google Drive API, Google Calendar API
4. Em Credentials > Create Credentials > OAuth 2.0 Client ID
5. Tipo: **Desktop App** (importante! "Web" não funciona para CLI)
6. Baixe o JSON e salve em `./credentials/google_drive_credentials.json`
7. Atualize `GOOGLE_DRIVE_CREDENTIALS_PATH=./credentials/google_drive_credentials.json`
8. Na primeira execução, o app abrirá o navegador para autorizar -- isso gera o token pickle
9. Configure `GOOGLE_DRIVE_ROOT_ID` com o ID da pasta raiz no Drive
10. Configure `GOOGLE_DRIVE_TASKS_ID` com o ID da pasta de tasks

**Revogar ILC:**
- No projeto ILC no Google Cloud Console, vá em Credentials e delete as OAuth keys antigas

---

## Prioridade MEDIA

### 4. DataJud / CNJ (Consulta Processual)

| Campo | Valor |
|-------|-------|
| **Ação** | Solicitar key gratuita no portal CNJ |
| **URL** | https://datajud-wiki.cnj.jus.br/api-publica/acesso/ |
| **Variável `.env`** | `DATAJUD_API_KEY` |
| **Formato** | String alfanumérica (ex: `cDZHYzlZa0JadVREZDM...`) |
| **Se ausente** | Degradação graceful -- consulta DataJud desabilitada. Monitoramento de processos via CNJ indisponível, mas busca via Escavador ainda funciona se configurado. |

**Passo a passo:**
1. Acesse https://datajud-wiki.cnj.jus.br/api-publica/acesso/
2. Preencha o formulário com seus dados (CPF, OAB)
3. Aguarde email de confirmação com a API key
4. Cole em `DATAJUD_API_KEY`

---

### 5. Escavador (Busca Jurídica)

| Campo | Valor |
|-------|-------|
| **Ação** | Criar conta e contratar plano |
| **URL** | https://www.escavador.com/precos |
| **Variável `.env`** | `ESCAVADOR_API_KEY` |
| **Formato** | String alfanumérica longa |
| **Se ausente** | Degradação graceful -- busca de processos via Escavador desabilitada. Funcionalidade de monitoramento de processos parcialmente indisponível. |

**Passo a passo:**
1. Acesse https://www.escavador.com/precos
2. Escolha o plano (API começa no plano Pro)
3. Após cadastro, acesse Configurações > API
4. Gere uma API key e copie para `ESCAVADOR_API_KEY`

---

## Prioridade BAIXA

### 6. Moskit CRM

| Campo | Valor |
|-------|-------|
| **Ação** | Revogar key ILC (não recriar -- CaseHub Lite usa CRM interno) |
| **URL** | Painel Moskit > Configurações > Integrações > API |
| **Variáveis `.env`** | `MOSKIT_API_KEY`, `MOSKIT_RESPONSIBLE_ID`, `MOSKIT_PIPELINE_ID` |
| **Formato** | UUID (ex: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`) |
| **Se ausente** | Degradação graceful -- sync CRM desabilitado. Leads ficam apenas no CaseHub. |

**Passo a passo:**
1. Acesse o painel Moskit da ILC
2. Vá em Configurações > API > Revogar key atual
3. Para CaseHub Lite: deixe as 3 variáveis em branco (CRM nativo é suficiente)

---

### 7. Twilio (SMS/WhatsApp)

| Campo | Valor |
|-------|-------|
| **Ação** | Revogar credenciais ILC |
| **URL** | https://console.twilio.com |
| **Variáveis `.env`** | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_WHATSAPP_FROM` |
| **Formato** | `AC...` (SID), string hex 32 chars (auth token), `+1XXXXXXXXXX` (numbers) |
| **Se ausente** | Degradação graceful -- SMS e WhatsApp via Twilio desabilitados. Notificações caem para email-only. |

**Passo a passo:**
1. Acesse https://console.twilio.com
2. Vá em Account > API Keys > Revoque keys da ILC
3. Para CaseHub Lite BR: pode deixar em branco (usar WhatsApp Bot nativo em vez de Twilio)

---

### 8. CallHippo (Telefonia)

| Campo | Valor |
|-------|-------|
| **Ação** | Revogar credenciais ILC |
| **URL** | Painel CallHippo > Settings > API |
| **Variáveis `.env`** | `CALLHIPPO_API_KEY`, `CALLHIPPO_FROM`, `CALLHIPPO_EMAIL` |
| **Formato** | String alfanumérica, `+1XXXXXXXXXX`, email |
| **Se ausente** | Degradação graceful -- integração CallHippo desabilitada. Click-to-call não funciona. |

**Passo a passo:**
1. Acesse o painel CallHippo da ILC
2. Vá em Settings > API > Revogue a key
3. Para CaseHub Lite BR: deixar em branco (telefonia US não se aplica)

---

### 9. Perplexity AI (Pesquisa Jurídica)

| Campo | Valor |
|-------|-------|
| **Ação** | Gerar nova API key pessoal |
| **URL** | https://docs.perplexity.ai |
| **Variável `.env`** | `PERPLEXITY_API_KEY` |
| **Formato** | `pplx-...` (ex: `pplx-abcdef1234567890`) |
| **Se ausente** | Degradação graceful -- assistente de pesquisa jurídica AI desabilitado. Não afeta operação core. |

**Passo a passo:**
1. Acesse https://www.perplexity.ai/settings/api
2. Crie uma API key
3. Cole em `PERPLEXITY_API_KEY`

---

### 10. Gemini (Geração de Documentos)

| Campo | Valor |
|-------|-------|
| **Ação** | Gerar nova API key pessoal |
| **URL** | https://aistudio.google.com/apikey |
| **Variável `.env`** | `GEMINI_API_KEY` |
| **Formato** | `AIza...` (ex: `AIzaSyD-abcdef1234567890`) |
| **Se ausente** | Degradação graceful -- geração de documentos AI desabilitada. Templates manuais continuam funcionando. |

**Passo a passo:**
1. Acesse https://aistudio.google.com/apikey
2. Clique "Create API Key"
3. Selecione o projeto Google Cloud (ou crie um novo)
4. Cole a key em `GEMINI_API_KEY`

---

### 11. Notion (Knowledge Base)

| Campo | Valor |
|-------|-------|
| **Ação** | Revogar integração ILC |
| **URL** | https://www.notion.so/my-integrations |
| **Variáveis `.env`** | `NOTION_TOKEN`, `NOTION_AILA_WIKI_DB`, `NOTION_TICKET_DATABASE_ID` |
| **Formato** | `secret_...` (token), UUIDs de 32 chars (database IDs) |
| **Se ausente** | Degradação graceful -- AILA Wiki e ticketing via Notion desabilitados. Não afeta operação core. |

**Passo a passo:**
1. Acesse https://www.notion.so/my-integrations
2. Encontre a integração "CaseHub" da ILC e delete
3. Para CaseHub Lite: criar nova integração se necessário, ou deixar em branco

---

## Checklist de Verificacao

Apos rotacionar, valide cada servico:

- [ ] **Stripe:** Acesse `/billing` e tente criar uma subscription de teste
- [ ] **Resend:** Envie um email de teste via `/settings/email-test`
- [ ] **Google OAuth:** Execute sync do Drive e verifique se arquivos aparecem
- [ ] **DataJud:** Busque um processo pelo numero e confirme retorno
- [ ] **Escavador:** Busque um advogado por OAB e confirme retorno
- [ ] **Moskit:** Confirme que variavel esta vazia e sync CRM esta desabilitado
- [ ] **Twilio:** Confirme que variavel esta vazia e SMS esta desabilitado
- [ ] **CallHippo:** Confirme que variavel esta vazia
- [ ] **Perplexity:** Teste pesquisa juridica no assistente AI
- [ ] **Gemini:** Teste geracao de documento via template AI
- [ ] **Notion:** Confirme que variavel esta vazia ou teste AILA Wiki

---

## Servicos que NAO precisam de key externa

Estes servicos usam credenciais locais/infra, nao API keys rotacionaveis:

| Servico | Variavel | Nota |
|---------|----------|------|
| PostgreSQL | `DATABASE_URL` | Senha do banco local, mude na instalacao |
| JWT Auth | `SECRET_KEY` | Gere com `python -c "import secrets; print(secrets.token_hex(32))"` |
| PII Encryption | `ENCRYPTION_KEY` | Gere com `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| SMTP | `SMTP_USER`, `SMTP_PASS` | App Password do Gmail do cliente |
| IMAP | `GMAIL_CENTER_EMAIL`, `GMAIL_CENTER_APP_PASSWORD` | App Password do Gmail do cliente |
| WhatsApp Bot | `WHATSAPP_BOT_URL` | URL do servico local (default: `http://localhost:3001`) |
