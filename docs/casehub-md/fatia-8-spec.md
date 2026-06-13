# Fatia 8 — Colab Hocuspocus + Yjs (DEFERRED v2)

> **Status:** **deferida** com decisão explícita 2026-05-23. Não implementada nesta sessão.

## Por que deferir

1. **Goal explicita como "opcional v2":** "Fatia 8 (opcional v2) — Collab Hocuspocus + Yjs."
2. **Red line tocada:** adicionar Hocuspocus = novo processo Node WebSocket separado do FastAPI; requer:
   - novo container/serviço no `docker-compose.yml`
   - WebSocket proxy / SSL via nginx
   - Possivelmente porta nova exposta no VPS
   - **Mudança de deploy topology** → **Council obrigatório** (AGENTS.md "Quando convocar obrigatoriamente").
3. **Sem peer real, sem valor:** Yjs awareness só agrega quando há ≥2 usuários no mesmo doc. Sem multi-tenant edição ativa primeiro (Fatia 5.2 multi-user OAuth + carregar `?doc=` na URL), Yjs é overhead puro.
4. **POC atual cobre uso single-user:** Fatias 1-7 entregam editor WYSIWYG completo, com Drive autosave persistindo o conteúdo. Single-user já é fluxo end-to-end.

## Plano de implementação futura

Quando Victor priorizar colab:

### Pré-requisitos

1. Fatia 5.1 implementada (`?doc=<id>` carrega doc do Drive on-mount).
2. Multi-user OAuth (token por user, não org-wide) — Fatia 5.2 ou separado.
3. Ruling Council para deploy topology (novo serviço Hocuspocus no docker-compose).

### Stack

| Camada | Tecnologia | Licença | Notas |
|---|---|---|---|
| CRDT | Yjs | MIT | https://github.com/yjs/yjs |
| WebSocket server | Hocuspocus | MIT | https://tiptap.dev/docs/hocuspocus |
| Persistence | `@hocuspocus/extension-database` + Postgres `casehub_md_docs` table | MIT | Snapshot Yjs doc por save |
| Auth | Hocuspocus `onAuthenticate` lê cookie JWT do CaseHub | — | Reusa session |
| TipTap | `@tiptap/extension-collaboration` + `@tiptap/extension-collaboration-cursor` | MIT | Plug-and-play |

### Arquitetura

```
                ┌────────────────┐
   user (TipTap)│ y-websocket    │  ws://casehub.../md-collab
                └────────┬───────┘
                         │
                ┌────────▼────────┐
                │ Hocuspocus Node │  Port 1234 (internal)
                │  - onAuth (JWT) │
                │  - onChange     │
                │  - onLoad       │
                └────────┬────────┘
                         │
                ┌────────▼────────┐
                │ Postgres        │  casehub_md_docs(doc_id, yjs_state, snapshot_md, owner_user_id, updated_at)
                └─────────────────┘
                         │ (cron 60s)
                ┌────────▼────────┐
                │ FastAPI worker  │  serializa yjs_state → markdown → Drive sync
                └─────────────────┘
```

### Endpoints novos

- `POST /casehub-md/collab/token` — issued JWT short-lived para o Yjs connect.
- WebSocket externo `wss://.../md-collab/<doc_id>` (proxy nginx → Hocuspocus port 1234).

### Arquivos a criar

```
collab-server/                    # novo subprojeto Node
    package.json
    src/server.ts                 # Hocuspocus + extensions
    src/db.ts                     # pg client
docker-compose.yml                # +1 serviço hocuspocus
deploy/nginx/casehub.conf         # /md-collab/ WS upgrade
services/casehub_md/collab.py     # FastAPI side helpers (Yjs→markdown serialização)
routes/casehub_md.py              # POST /collab/token
static/js/casehub-md/poc.js       # Collaboration + CollaborationCursor extensions
templates/casehub_md/poc.html     # importmap + collab UI (avatars users online)
```

### Riscos / decisões abertas

- **Conflito Drive vs Postgres:** quem é fonte canônica do markdown? Proposta: **Postgres é runtime, Drive é backup** (worker serializa a cada 60s). Council deve ratificar.
- **Custo bandwidth:** Yjs awareness com 5+ users em doc longo é não-trivial. Profilar antes de release.
- **Mobile:** y-websocket reconecta automaticamente, mas conexões intermitentes (4G) merecem teste real.

## Estimativa

- Backend Hocuspocus + integração FastAPI: ~3-4 dias.
- Frontend collab extensions + UI awareness: ~1-2 dias.
- Council ruling + topology approval: 1 dia.
- Total: ~1 semana de trabalho focado, após pré-requisitos.

## Loop checkpoint

| Passo | Status |
|---|---|
| 1. Spec (este doc — defer rationale + plano futuro) | ✅ |
| 2-7 | DEFERRED |
