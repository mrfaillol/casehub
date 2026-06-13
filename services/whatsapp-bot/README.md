# CaseHub WhatsApp Bot — Multi-session per-tenant

> **Status:** v4.0 (2026-05-27, F29). Cada tenant CaseHub tem uma sessão
> whatsapp-web.js isolada, com QR e número próprios. O bot dispatcha por
> `X-Org-Id` em cada request.

## Por que existe esta camada

O CaseHub roda multi-tenant: cada escritório tem seu próprio subdomínio
(`sampletenant.casehub.legal`, `outroescritorio.casehub.legal`). Cada um
quer **sua** linha WhatsApp e **suas** conversas — não a da org default.

A biblioteca [`whatsapp-web.js`](https://github.com/pedroslopez/whatsapp-web.js)
não é multi-tenant nativamente: cada `Client` é uma sessão. Para suportar
N tenants no mesmo processo, esta camada introduz um `WhatsAppManager`
(Map `orgId -> Client`) e `LocalAuth` com `clientId = "org-<N>"` para
isolar profiles do Chromium.

## Arquitetura

```
Browser (sampletenant.casehub.legal/casehub/whatsapp-chat)
  └ nginx → FastAPI (casehub:8001)
       └ TenantMiddleware resolve org_id=4 via Host header
       └ routes/whatsapp_chat.py + routes/whatsapp_proxy.py
            └ forward com header X-Org-Id: 4
                 └ bot Node.js (porta 3001) — server-lite.js
                      └ resolveOrgId(req) → 4
                      └ WhatsAppManager.ensureInitialized(4)
                           └ new Client({
                               authStrategy: new LocalAuth({
                                 clientId: "org-4",
                                 dataPath: "./.wwebjs_auth"
                               })
                             })
                           → Puppeteer/Chromium em
                             ./.wwebjs_auth/session-org-4/

Inbound (WhatsApp → CaseHub):
  Client da org-4 emite "message"
  └ WhatsAppManager re-emite com {orgId: 4}
       └ server-lite.js → forwardInbound(data, {orgId: 4})
            └ casehub-bridge.js POST /casehub/whatsapp/inbound
                 + X-Org-Id: 4 + HMAC(body)
            └ FastAPI valida HMAC + lê X-Org-Id
                 └ services/whatsapp_inbound_service.py
                    process_inbound(..., requested_org_id=4)
                    → grava wa_messages.org_id = 4 (sem heurística)
```

## Contrato de requests

Todo endpoint do bot aceita (e o FastAPI sempre envia) o header
`X-Org-Id`. Fallbacks aceitos em ordem de prioridade:

1. `X-Org-Id: <N>` (header)
2. `?org_id=N` (query)
3. `body.org_id` (POST)
4. `CASEHUB_DEFAULT_ORG_ID` (env, default `1`)

| Endpoint                       | Método | Descrição                                  |
| ------------------------------ | ------ | ------------------------------------------ |
| `/api/status`                  | GET    | Status da sessão da org                    |
| `/api/qr`                      | GET    | QR code da sessão da org                   |
| `/qr`                          | GET    | Página HTML do QR (debug)                  |
| `/api/conversations`           | GET    | Lista conversas vivas da sessão            |
| `/api/messages/:phone`         | GET    | Mensagens da conversa                      |
| `/api/send-message`            | POST   | Envia texto `{ phone, message }`           |
| `/api/send-media`              | POST   | Envia mídia multipart                      |
| `/api/disconnect`              | POST   | Limpa sessão e reinicia (novo QR)          |
| `/api/pairing-code`            | POST   | Fallback pareamento por código             |
| `/api/bot-control`             | POST   | Toggle bot por conversa (per-tenant state) |
| `/api/followup/{mark,unmark,check}` | POST/GET | Estado de follow-up (per-tenant)       |
| `/api/sessions`                | GET    | **Admin:** snapshot multi-tenant           |
| `/api/sessions/:orgId/init`    | POST   | **Admin:** pré-aquece sessão               |
| `/health`                      | GET    | Health check agregado                      |

## Sessions: storage layout

```
/app/.wwebjs_auth/                 # volume Docker (whatsapp_session)
├── session-org-1/                 # org default
│   ├── Default/                   # profile Chromium
│   └── ...
├── session-org-4/                 # sampletenant
│   ├── Default/
│   └── ...
└── session-org-N/                 # cada tenant ganha o seu
```

Cada `clientId="org-<N>"` faz o LocalAuth criar `session-org-<N>/` no
mesmo `dataPath`. Vantagem operacional: um único volume Docker
(`whatsapp_session`) cobre todas as orgs; `docker compose down -v` não
zera apenas uma — é tudo ou nada.

## Variáveis de ambiente

| Env                                | Default                                        | Descrição                                                                  |
| ---------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------- |
| `PORT`                             | `3001`                                         | Porta HTTP do bot                                                          |
| `CASEHUB_API_URL`                  | `http://localhost:8001`                        | Base do FastAPI (forward inbound/ack)                                      |
| `CASEHUB_INBOUND_HMAC_SECRET`      | (obrigatório)                                  | Segredo HMAC compartilhado com o backend                                   |
| `PUPPETEER_EXECUTABLE_PATH`        | `/usr/bin/chromium` (Docker)                   | Chromium do sistema                                                        |
| `CASEHUB_DEFAULT_ORG_ID`           | `1`                                            | Org assumida quando `X-Org-Id` está ausente (compat single-tenant)         |
| `CASEHUB_AUTOSTART_ORGS`           | `<DEFAULT_ORG_ID>` (e.g. `"1"`)                | CSV de orgs pra inicializar no boot. Alpha: `"1,4"` (default + sampletenant) |
| `CASEHUB_BRIDGE_ENABLED`           | `true`                                         | Set `false` pra desabilitar forward (debug)                                |

## Considerações de performance

- **Cold start de Puppeteer/Chromium** é ~3-8s por sessão. Use
  `CASEHUB_AUTOSTART_ORGS` para pré-aquecer as orgs ativas no boot,
  evitando o atraso na primeira mensagem.
- **Memória**: cada Chromium ocupa ~150-250 MB de RSS. Para 5-10 tenants
  no mesmo container, monitore o RSS via `/health` e considere migrar
  para uma topologia 1 bot container per N tenants quando passar de ~15
  sessões ativas.
- **CPU**: WhatsApp Web é leve; o gargalo é a sincronização inicial de
  histórico do contato (geralmente <30s na primeira conexão).

## Segurança

- **HMAC obrigatório**: `CASEHUB_INBOUND_HMAC_SECRET` valida todo forward
  bot→backend. Sem ele o bot loga `[skipping forward]` e nada é gravado.
- **X-Org-Id outside HMAC body**: o header carrega o tenant mas a
  assinatura cobre o body. Replay cross-tenant ainda exige assinatura
  válida.
- **FastAPI valida X-Org-Id**: `_resolve_inbound_org` confirma que a org
  existe antes de atribuir o inbound — header falsificado para org
  inexistente cai na heurística legada.
- **TenantMiddleware autoritativo**: o `whatsapp_proxy.py` sempre
  *sobrescreve* `X-Org-Id` com o valor de `request.state.org_id` (do
  Host header). O browser não pode injetar.

## Testes

```bash
# Unit tests (Node, sem Puppeteer/network)
cd services/whatsapp-bot
npm test
# 17 testes ao total (manager + bridge)

# Python tests (precisa venv com sqlalchemy)
pytest tests/test_whatsapp_multi_tenant.py
```

## Migração de single-org → multi-session

Volume existente (`./.wwebjs_auth/` sem subdiretórios `session-org-*`):

1. Container antigo (singleton) usava `dataPath: "./.wwebjs_auth"` direto.
2. Após o upgrade, o LocalAuth com `clientId="org-1"` cria
   `./.wwebjs_auth/session-org-1/` — **vazio** (a sessão antiga ficou na
   raiz e foi ignorada).
3. **Solução**: a primeira inicialização vai gerar um novo QR. Escaneie
   pelo número do alpha (`+55 ...`) e a sessão fica em `session-org-1/`.
4. **Limpeza**: depois de validar que a nova sessão funciona, remova os
   arquivos legados da raiz do volume (`Default/`, `IndexedDB/`, etc.
   FORA dos `session-org-*/`). Comando seguro:
   ```bash
   docker exec casehub-whatsapp-bot \
     find /app/.wwebjs_auth -maxdepth 1 -type d -name 'Default' -exec rm -rf {} +
   ```

## Troubleshooting

| Sintoma                                     | Diagnóstico                                                        | Ação                                                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Front mostra QR mas escanear não conecta    | `getStatus().status === "awaiting_scan"` mas `change_state` nunca emite | Checar `CASEHUB_AUTOSTART_ORGS` — se a org não está na lista, `ensureInitialized` só roda no primeiro request (cold start ~5s)                                    |
| Tenant A vê conversas do tenant B           | `X-Org-Id` não está chegando no bot                                | Verificar header com `curl -i http://localhost:3001/api/conversations -H 'X-Org-Id: 4'`. Se OK, o bug está no `whatsapp_proxy.py` (TenantMiddleware não setou org) |
| "WhatsApp nao conectado (org=N)"            | `manager.ensureInitialized(N)` ainda não rodou ou falhou           | `POST /api/sessions/N/init` pra forçar boot; checar logs `[boot] falha ao inicializar org-N`                                                                      |
| Inbound vai pra org errada                  | FastAPI fallback pra `slug='default'` quando phone match miss      | Conferir que o bot está mandando `X-Org-Id` (logs `[bridge][org-N] forwarded`). Se sim, conferir `process_inbound` no FastAPI                                    |
| 2 sessões consomem muita memória            | 2 Chromium = 300-500MB                                             | Esperado para alpha. Long-term: container pool ou Chromium shared profile não-isolado (sacrifica privacy) — não fazer sem ruling                                  |

## Limitações conhecidas

- **Não testado com 5+ orgs simultâneas em prod**. Alpha tem 2 (default +
  sampletenant). Validação de escala faz parte do roadmap pós-alpha.
- **Sem migração on-the-fly de sessão entre profiles**. Se uma org troca
  de número WhatsApp, deve `/api/disconnect` + escanear novo QR.
- **`/qr` HTML usa a org default**. O fluxo correto pra um tenant
  específico passa pelo FastAPI (`/casehub/whatsapp-chat` → proxy →
  `/api/qr` com `X-Org-Id`).

## Histórico

| Versão | Data       | Mudança                                                                  |
| ------ | ---------- | ------------------------------------------------------------------------ |
| v4.0   | 2026-05-27 | **Multi-session per-tenant** (F29). `WhatsAppManager`, `X-Org-Id` header |
| v3.2   | 2026-05-21 | Fix QR auth loop + webpack-exodus compat                                 |
| v2.0   | 2026-05-19 | `server-lite.js` stateless pro alpha CaseHub                             |

Ver `CHANGELOG.md` para o histórico completo.
