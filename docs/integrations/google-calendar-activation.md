# Google Calendar — Production Activation Runbook

**Status:** runbook (não auto-executável). Não plantar segredos por PR.
**Authority:** PR #215/#216 já mergearam o serviço nativo OAuth (`services/google_calendar_*`); #487 mergeou consent/neutral mode (2026-05-18); #478 acompanha Google Auth Platform, verification e smoke prod.
**Pré-requisito:** PR de consentimento/neutral mode mergeado e validado em dev antes de qualquer secret/smoke prod.

## Status atual (snapshot 2026-05-18)

- ✅ Backend OAuth nativo: `services/google_calendar.py` + `routes/google_calendar.py`
- ✅ Schema field `appointments.gcal_event_id` reservado
- ✅ Consent/neutral mode flags (`GOOGLE_CALENDAR_EVENT_DETAIL_MODE`, `_LANG`) em produção via #487 (default-off)
- ✅ Dev smoke pós-#487: `/casehub/google-calendar/status` → `connected=true, write_ready=true` em conta `center` (dev `da83b5fd`)
- ⏸ Aguarda Victor: Google Cloud Console publishing path + secret planting VS-prod
- ⏸ Aguarda Sentinela: review de OAuth scopes / refresh-token storage / consent path antes de PR público dos secrets
- ⚠ VS-prod `/app/credentials/google_client_secret.json` ausente (verificação read-only 2026-05-15)
- ⚠ HALT `#134` mantém #311-#320 fora da FASE 1 — não conflita com este runbook mas validar

## Pré-checks Sentinela (obrigatório antes de qualquer PR público com diff em secrets/OAuth)

- [ ] `gitleaks detect --config agents/knowledge/sentinela/gitleaks-custom.toml` retorna zero hits no diff.
- [ ] Nenhum `client_id`/`client_secret`/`refresh_token` real em texto plain — placeholders devem ser `<paste-id-here>`, não strings parecidas com credencial.
- [ ] Scopes pedidos = scopes usados pelo código (least privilege auditado contra `calendarList`, `events.*`).
- [ ] Redirect URIs apenas em domínios CaseHub controlados (dev/prod), sem wildcard.
- [ ] Refresh token storage path documentado e protegido (file 0600, owner appuser).
- [ ] Revocation flow funcional (`/disconnect/{account_name}` chama Google revoke endpoint).
- [ ] Logs do app **não** logam token / client_secret (grep no código).

## Por que este doc existe

`appointments.gcal_event_id` já está reservado no schema; OAuth scaffold + read/write pronto. O bloqueio não é só segredo operacional: enquanto o app estiver em **Testing**, o Google limita autorização a test users e refresh tokens podem expirar; para venda com contas Google arbitrárias, o app precisa estar **In production** e, por usar escopos Google Calendar, pode exigir verification. Este runbook formaliza os passos para Victor (ou operador autorizado com Google Cloud Console) executar sem reinvestigar.

## Passos (Victor)

### 1. Revogar o app OAuth ILC antigo

O CaseHub Immigration (ILC) já consumiu um OAuth app no projeto Google Cloud. Para evitar confusão de scopes/owner, **revogar primeiro**:

1. Login em https://console.cloud.google.com com a conta `casehub` (não a pessoal Victor)
2. APIs & Services → OAuth consent screen → buscar app `casehub-immigration` (ou similar)
3. **DELETE** ou **REMOVE OAUTH CLIENT** (não só desativar — deletar previne confusão)

### 2. Criar/ajustar o app `CaseHub Basic`

1. APIs & Services → Library → habilitar:
   - **Google Calendar API**
2. APIs & Services → OAuth consent screen → CREATE
   - User type: **External** (salvo se virar app interno de um Google Workspace controlado)
   - App name: `CaseHub Basic`
   - User support email e developer contact: contas Google reais e monitoradas pelo operador
   - Scopes: adicionar
     - `https://www.googleapis.com/auth/calendar.events`
     - `https://www.googleapis.com/auth/calendar.readonly`
   - Test users: enquanto em modo Testing, adicionar apenas contas Google reais usadas para smoke/piloto
3. Credentials → CREATE CREDENTIALS → OAuth client ID
   - Application type: **Web application**
   - Name: `casehub-basic-web`
   - Authorized redirect URIs (rota real montada em `routes/google_calendar.py` é `/google-calendar/callback` sob `${PREFIX}`, que é `/casehub` por default):
     - `https://app.example.com/casehub/google-calendar/callback` (Oracle dev)
     - `https://cliente.example.com/casehub/google-calendar/callback` (prod VS)
     - domínio comercial futuro somente depois de DNS/ambiente decididos
4. Clicar **DOWNLOAD JSON** — esse é o `client_secret_<long-id>.json`. **NÃO** copiar Client ID/Secret manualmente — a service `services/google_calendar.py` lê o arquivo JSON inteiro.

### 2.1. Transição Testing → In production

Decisão estratégica antes de qualquer plant prod:

| Modo | Implicações | Quando usar |
|---|---|---|
| **Testing** | Limite test users; refresh tokens expiram em 7 dias; sem verification Google | Piloto fechado, o cliente + ≤100 contas explicitamente adicionadas |
| **In production** (sem verification) | Sem verification: scopes "sensitive" mostram unverified warning Google; usuário precisa "Advanced → Go to (app)" | Não usar — UX ruim, conversão baixa em pitches |
| **In production + verification approved** | Conexão limpa para qualquer conta Google; sem warning | Venda aberta (FASE 2+); requer Sensitive Scope Verification process (~4-8 semanas Google) |

**Sequência recomendada FASE 1:**
1. Manter Testing enquanto o cliente + escritórios piloto ≤100 contas.
2. Quando [parceiro]/Victor sinalizarem "primeira venda externa", **submeter verification** (não publicar antes da verification aprovada).
3. Verification aprovada → publicar In production → conexão limpa para qualquer conta.

### 2.2. Preparar publishing/verification para venda

Fontes oficiais Google:

- Google Calendar API scopes: https://developers.google.com/workspace/calendar/api/auth
- OAuth app audience / Testing vs In production: https://support.google.com/cloud/answer/15549945
- Sensitive scope verification: https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification

Checklist antes de vender como integração aberta:

1. Confirmar least privilege dos escopos usados pelo código (`calendar.events` + `calendar.readonly`) contra as chamadas reais (`calendarList`, `events.list`, `events.insert`, `events.patch`, `events.delete`).
2. Deixar App home page, privacy policy e support contact públicos e coerentes com o nome `CaseHub Basic`.
3. Declarar no consent screen que eventos podem receber título, cliente, tipo e notas; se o tenant exigir minimização, documentar `GOOGLE_CALENDAR_EVENT_DETAIL_MODE=neutral`.
4. Preparar justificativa por escopo e vídeo de demonstração do fluxo: conectar conta Google, consentir, criar compromisso fictício e verificar evento criado.
5. Publicar o app como **In production** e submeter verification se o Console marcar os escopos Calendar como sensitive/restricted.
6. Até a verification estar aprovada, tratar pilotos como Testing/test-user ou Workspace-admin trusted app; não prometer conexão livre para qualquer conta Google.

### 3. Plantar o `client_secret.json` nos hosts

A `GoogleCalendarService.__init__` (linhas 60-67) lê:

```python
client_file = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH") or settings.GOOGLE_CALENDAR_CREDENTIALS_PATH
# fallback: <BASE_DIR>/credentials/google_client_secret.json
```

Não há `GOOGLE_OAUTH_CLIENT_ID/SECRET` — o segredo é o JSON file inteiro. Duas opções de planting:

**Opção A — montar via volume (recomendado para Docker):**

```bash
# Hostinger (prod VS): scripts/vps-deploy.sh:50 fixa DEPLOY_DIR=/app
# (não ~casehub/casehub). docker compose -f .../docker-compose.yml up -d --build
# casehub roda DESSA pasta, então o mount ./credentials:/app/credentials
# resolve para /app/credentials/. Plantar fora desse path deixa o
# container sem o JSON após restart automático do deploy.
ssh root@REDACTED-HOST  # (ou via deploy@ + sudo, conforme política Hostinger)
cd /app
mkdir -p ./credentials
# (do Mac local) scp ~/Downloads/client_secret_*.json \
#   root@REDACTED-HOST:/app/credentials/google_client_secret.json
# Both Dockerfile e Dockerfile.lite (linhas 38/31) criam appuser UID 1000
# e dropam pra ele via USER appuser. Bind-mount `./credentials` é lido com a
# UID do container — 0600 root:root deixa o arquivo ilegível pro appuser.
# chown 1000:1000 alinha ownership; chmod 600 mantém o segredo restrito.
chown 1000:1000 credentials/google_client_secret.json
chmod 600 credentials/google_client_secret.json
# Confirmar mount no compose:
grep -n "credentials:/app/credentials" docker-compose.yml
# Restart só do app (workflow deploy-prod.yml usará rebuild; uma rotação
# manual aqui é só para smoke imediato sem disparar workflow):
docker compose -f /app/docker-compose.yml restart casehub
```

**Opção B — variável de path explícita:**

```bash
# Se o JSON estiver em outro lugar (e.g., /etc/casehub/secrets/):
echo "GOOGLE_CALENDAR_CREDENTIALS_PATH=/app/secrets/google_client_secret.json" >> /app/.env
# E mountar /etc/casehub/secrets:/app/secrets:ro adicionalmente no compose
# (edit dedicado, fora do escopo deste runbook).
docker compose -f /app/docker-compose.yml restart casehub
```

**Oracle (dev):** scripts/vps-deploy-oracle*.sh usa `~ubuntu/casehub-dev` —
plantar em `/app/credentials/google_client_secret.json`,
`chown 1000:1000` + `chmod 600`, restart com `docker compose -f docker-compose.dev.yml restart casehub`.

> **Não** usar `gh secret set` pra plantar este JSON — workflows de deploy não usam o JSON em si (o app o lê em runtime do filesystem). Se quiser distribuir via Action, criar workflow que `scp` o secret base64-decoded para os hosts; padrão atual é provisionar manualmente uma vez por host.

### 4. Adicionar test users (somente enquanto Testing)

OAuth consent screen → Test users → ADD USERS. Por usuário:

- Email Google real (mesma conta que vai conectar no CaseHub).
- Máximo 100 (limite Google em apps Testing).
- Listar somente contas controladas: Victor, [parceiro], equipes o cliente autorizadas, piloto escritórios convidados.
- Documentar lista atualizada em `docs/integrations/google-calendar-test-users.md` (criar; chmod 600 no diff revisor — não comitar nomes/emails reais sem mascara).

Test user inválido → callback falha com `access_denied`. Smoke após cada add.

### 5. Smoke end-to-end

Routes reais em `routes/google_calendar.py`:

| Route | Método | Função |
|---|---|---|
| `${PREFIX}/google-calendar/settings` | GET (HTML) | Tela de Settings → Integrations |
| `${PREFIX}/google-calendar/connect/{account_name}` | GET | Inicia OAuth flow |
| `${PREFIX}/google-calendar/callback` | GET | Recebe code do Google |
| `${PREFIX}/google-calendar/status` | GET | Status JSON de cada conta (`center`/`info`) |
| `${PREFIX}/google-calendar/disconnect/{account_name}` | POST | Tenta revogar refresh token no Google e remove token local |

```bash
# 1. UI: navegar até https://app.example.com/casehub/google-calendar/settings
#    → clicar "Conectar center" → consent screen Google → callback → status "Conectado"

# 2. Backend smoke. /status usa get_current_user (auth.py:74-94), que lê APENAS
#    o cookie casehub_token (não Authorization: Bearer header). Após login na UI,
#    extraia o cookie do navegador e passe via -b. Resposta tem shape top-level
#    {connected, write_ready, accounts: [...], redirect_uri, sync_options} —
#    NÃO `.center` (a info por conta vive em accounts[].slug == "center").
#
COOKIE='casehub_token=<colar valor do cookie do browser logado>'
curl -fsS -b "$COOKIE" \
  https://app.example.com/casehub/google-calendar/status \
  | jq '{connected, write_ready, center: (.accounts[] | select(.slug == "center") | {connected, can_write, display_email})}'

# 3. Criar appointment via UI (Calendar → +) ou API existente; depois checar gcal sync:
#    O modelo Appointment grava gcal_event_id quando o sync best-effort sucede.
#    Conferir no DB:
docker compose exec postgres psql -U casehub -d casehub_dev -c \
  "SELECT id, title, gcal_event_id FROM appointments ORDER BY created_at DESC LIMIT 5;"

# 4. Verificar no Google Calendar UI: evento deve aparecer no calendário center@
```

Política de conteúdo outbound: por decisão operacional dos controladores/tratadores de dados, eventos criados no Google Calendar incluem o título do compromisso, cliente, tipo e notas visíveis. Esses campos ficam sob controle do CaseHub, da LegalOps Co. e do cliente que conectou a conta Google. O evento também carrega identificadores privados mínimos em `extendedProperties.private`.

Se o tenant exigir minimização estrita, configurar `GOOGLE_CALENDAR_EVENT_DETAIL_MODE=neutral`. Nesse modo o Google Calendar recebe apenas horário, título/descrição neutros e identificador privado do CaseHub; título, cliente, tipo e notas permanecem no CaseHub.

### 6. Rollback

Se algo quebrar:

```bash
# Desconectar via UI: Settings → Integrations → "Desconectar"
# OU desabilitar via filesystem (mantém DB):
mv credentials/google_client_secret.json credentials/google_client_secret.json.disabled
docker compose restart casehub
# Appointments locais continuam funcionando; só sync GCal pausa.
```

Em caso de leak de secret: revogar imediatamente no Cloud Console (Credentials → DELETE OAuth client), apagar `credentials/google_client_secret.json`, repetir passos 2–5 com novo client.

## Estados esperados na UI

Per `docs/integrations/2026-05-03-mcp-casehub-handoff.md` §Google Calendar UX:

| Estado | UI |
|---|---|
| Não conectado | Botão "Conectar Google Calendar" |
| Conectado | Email da conta + "Desconectar" |
| Reconnect required (token expirado) | Banner amarelo "Reconectar Google Calendar" |
| Missing client secret (env não setado) | Banner cinza "Integração indisponível — peça ao admin" |
| Invalid redirect URI | Erro inline com hint do passo 2.3 acima |

Local appointments **sempre são source of truth** — falha de sync GCal exibe warning mas não derruba a operação local.

## Bloqueios / dependências

- ✅ Backend OAuth pronto: `services/google_calendar.py` + `routes/google_calendar.py`
- ✅ Schema field `appointments.gcal_event_id` existente
- ✅ Consent/neutral mode em produção via #487 (2026-05-18)
- ⏸ Aguarda Victor: passos 1–4 deste doc (Cloud Console + JSON plant em VS-prod)
- ⏸ Aguarda Sentinela: review do diff pré-PR público (pré-checks do topo deste doc)
- ⚠ HALT #188 já foi lifted; manter watch em #134

## Próximos gates antes de fechar #478

1. **Sentinela approve** dos pré-checks (gitleaks zero, scopes auditados, redirect canônicos).
2. **Decisão Victor** sobre Testing vs Production+verification (seção 2.1).
3. **Plant secret** em VS-prod via Opção A ou B (seção 3), com `chown 1000:1000` + `chmod 600`.
4. **Smoke prod** com conta Google de teste autorizada (Victor ou conta dummy `qa-prod@`).
5. **Comment em #478** com SHA + ambiente + smoke evidence + screenshot do `/google-calendar/status` `connected=true`.

Sem esses 5 itens, #478 fica OPEN.

## Refs

- PR #215 (closed) — diagnóstico inicial
- PR #216 (merged) — `fix/pdpj-gcal-controladoria` (OAuth nativo)
- PR #487 (merged 2026-05-18) — consent/neutral mode
- `services/google_calendar.py` (linhas 60-67 — leitura do client_secret JSON)
- `routes/google_calendar.py` (linha 78-86 — construção do redirect_uri canônico)
- `models/appointment.py` (campo `gcal_event_id`)
- `agents/knowledge/sentinela/gitleaks-custom.toml` — leak detector custom rules
- Trilha handoff: `docs/handoff/claude-code-2026-05-18-alpha-closeout/20-google-calendar-478-343.md`

— Sections "Status atual", "Pré-checks Sentinela", "2.1 Transição Testing→Production", "4. Test users", "Próximos gates" added by Claude Opus 4.7 @mac, 2026-05-18, em sessão alpha-closeout.
