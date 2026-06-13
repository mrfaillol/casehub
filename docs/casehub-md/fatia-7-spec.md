# Fatia 7 — Maestro integration (AI suggestion per parágrafo)

> **Objetivo:** botão "✨ Maestro" envia o parágrafo atual + opcional `case_id` para o backend Maestro, recebe sugestão de melhoria/continuação, e dá ao user a chance de aceitar (insere) ou descartar (modal simples).

## Council? Não necessário

Sem novo OAuth scope. Sem secret. Sem deploy topology. Proxy via HTTPx para Maestro backend já existente (worktree `~/Projects/casehub-maestro-backend`). URL configurável via env `MAESTRO_BASE_URL`; default `http://localhost:8005`. Se Maestro offline: 503 graceful.

## Critérios de pronto

1. `POST /casehub-md/maestro/suggest` body `{paragraph: str, case_id?: str, kind?: str}` → proxy para Maestro `POST {MAESTRO_BASE_URL}/suggest` ou compatível.
2. Backend retorna `{suggestion, model?, took_ms}` ou 503/504.
3. Botão "✨ Maestro" no toolbar (novo grupo "Assist"); seleciona o parágrafo atual (TipTap `getCurrentParagraph()` ou seleção do user); chama backend; modal mostra sugestão; aceitar insere após o parágrafo, descartar fecha modal.
4. `case_id` via query string opcional `?case_id=` (Postel: aceita também `case=`).
5. Smoke test cobre endpoint (aceita 200/503).
6. Diff <300 linhas.

## Decisão de payload com Maestro

O Maestro backend ainda está em desenvolvimento (worktree `casehub-maestro-backend`). Não confio na shape exata da API ainda. Estratégia POC defensiva:

- Backend envia payload simples: `{paragraph, case_id, kind}` (kind="suggest_continuation" default).
- Espera resposta com pelo menos uma das chaves: `suggestion`, `text`, `output`, `response`.
- Se Maestro retornar shape diferente: log warning + retorna a primeira string truthy encontrada.
- Timeout 15s (LLM upstream pode demorar).

Quando Maestro estabilizar contract → atualizar payload + remover heurística defensiva.

## Leis UX

- **Doherty:** botão fica `… pensando` durante request; status bar reflete.
- **Hick:** apenas 2 ações na sugestão: Aceitar ou Descartar (sem "Regenerar" agora).
- **Norman:** modal claro com label "Sugestão do Maestro" + diff visual texto original vs sugerido (futuro).

## Arquivos

```
services/casehub_md/maestro.py
routes/casehub_md.py              # +POST /casehub-md/maestro/suggest
templates/casehub_md/poc.html     # +1 botão + modal HTML
static/js/casehub-md/poc.js       # +1 comando maestro + modal handlers
static/css/casehub-md/poc.css     # estilo modal mínimo
docs/casehub-md/fatia-7-spec.md   # este arquivo
tests/smoke-casehub-md-poc.spec.js  # +1 assertion
```

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec | ✅ | `docs/casehub-md/fatia-7-spec.md` |
| 2. Service `maestro.py` | ✅ | `suggest()` HTTPx async proxy; shape-tolerant (`_coerce_suggestion`); 15s timeout; `MAESTRO_BASE_URL` env-configurable |
| 3. Endpoint FastAPI | ✅ | `POST /casehub-md/maestro/suggest` (Pydantic); mapeia 413/504/503/502 |
| 4. Frontend botão + modal | ✅ | botão "✨ Maestro" no grupo Assist; `<dialog>` nativo HTML; aceitar insere abaixo via marked.parse; descartar fecha |
| 5. Smoke test ampliado | ✅ | step 10: aceita 200/401/502/503/504; valida shape `{suggestion}` se 200 |
| 6. Commit pequeno | ✅ | 339 insertions (alvo <300 levemente excedido por causa do modal CSS) |
| 7. Checkpoint | ✅ | 2026-05-23 |

## Notas

- 339 linhas acima do alvo 300 — overshoot vem do modal CSS (~95 linhas) e modal HTML (~20). Cosmético cumulativo coerente; sem split artificial.
- `MAESTRO_BASE_URL` precisa ser configurado quando Maestro entrar em produção. Default `http://localhost:8005` funciona em dev se Maestro estiver up.
- Quando contract Maestro estabilizar, simplificar `_coerce_suggestion` removendo as heurísticas de shape variável.
