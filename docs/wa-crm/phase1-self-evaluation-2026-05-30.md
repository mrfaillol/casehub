# WhatsApp CRM — Fase 1: autoavaliação de engenharia

**Data:** 2026-05-30 → 31 · **Autor:** Claude Opus 4.8 (autônomo) · **Feature:** owner-tag + nome real + funil intake-jurídico
**Branches:** `feat/wa-crm-owner-funnel-2026-05-30` (#711, mergeado) + `chore/wa-crm-followups-2026-05-30` (Fase 1.1)

---

## 1. Veredito honesto

A Fase 1 entregou o caminho-feliz e foi provada por teste de unidade, mas **a primeira versão (#711) tinha 1 blocker e 4 bugs reais que meu self-review inline não pegou** — encontrados por uma revisão adversarial independente (5 agentes). Nota inicial honesta: **C+**. Após a Fase 1.1 (correções abaixo, com teste de regressão): **sólida**.

A lição: meu self-review inline cobriu backend/tenant/funil (onde eu estava certo), mas teve ponto cego em **resiliência do hot-path** e **DOM do frontend**. A revisão independente foi o que elevou a qualidade — registro isso como evidência de que revisão adversarial pré-deploy não é opcional.

## 2. O que foi entregue (Fase 1, #711)

1. **Nome real do contato** — `api_get_conversations` passou a usar `list_conversations` (resolve `Client.full_name` > `display_name` > phone) em vez do proxy do bot (nome vazio).
2. **Tag de dono colorida** — `wa_contacts.owner_user_id` (FK users) + cor de `users.color`/paleta; badge na lista + header; dropdown no painel; endpoints `POST /api/crm/owner` + `GET /api/crm/org-users`.
3. **Funil intake-jurídico** — `cold/warm/qualified/hot` → `Novo/Triagem/Reunião/Proposta/Cliente/Descartado`; vocab centralizado + `normalize_stage` (mapeia legado sem data-migration).

## 3. Bugs encontrados pela revisão independente → corrigidos (Fase 1.1)

| # | Sev | Bug | Fix |
|---|-----|-----|-----|
| A | 🔴 blocker | `list_conversations` virou fonte primária **sem try/except**; fallback só em lista vazia, não em exceção → erro de DB = 500 no chat (hot path) | `try/except → db.rollback() → []` deixa a cadeia de fallback seguir |
| B | 🟡 high | Badge do **header morto**: `#chatOwnerBadge` aninhado em `#chatName`; `textContent=name` apagava o span | `#chatName` virou `<span>` irmão do badge |
| C | 🟡 high | `from_bot` refletia `ai_generated` → resposta de humano marcava "precisa responder" falso | `from_bot` reflete `from_me` (direção da última msg) |
| D | 🟡 med | `POST /api/crm/owner` dava 500 em body não-JSON / phone inválido (fora do try) | guards de input → 400 |
| E | 🟡 low | Owner desabilitado mostrava badge mas sumia do dropdown | `.filter(User.enabled.is_(True))` nos paths de display |

## 4. Dívida consciente (documentada, não corrigida nesta fase)

- **Completeness do mirror**: `list_conversations` lê só `wa_*`. Medido na org 4: **9 wa_contacts = 9 phones legados (sem gap)** — risco "chat antigo some" não se aplica hoje, mas o split de fontes precisa de ADR/backfill antes de escalar.
- **FK só no ORM**: migração adiciona `owner_user_id INTEGER` sem `REFERENCES`; em DB existente o `SET NULL` nunca dispara (degrada gracioso: badge some). Alinhar via `ADD CONSTRAINT` quando conveniente.
- **3 vocabulários de funil**: `wa_contacts` (novo/triagem) vs bot Node (cold/warm, SQLite própria) vs `leads_manager` (NEW_LEAD). Silos conscientes, sem contaminação. Falta ADR.
- **`lead_score`**: coluna migrada + serializada mas write-never/read-never (scaffolding Fase 2). Comentário honesto no código.
- **Shape do owner** `{user_id}` (badge) vs `{id}` (dropdown) — funciona (consumidores distintos), padronizar depois.
- **Renderer original `chat.js:665`** é dead code (override em 3101 vence) — o badge ativo é o override (editado). Edição no original foi inócua.

## 5. Matriz de evidência

| Camada | Verificação | Status |
|---|---|---|
| Lógica backend (nome/owner/funil/tenant/from_bot/enabled) | **pytest 9/9** (`tests/test_wa_crm_owner_funnel.py`) em código real | 🟢 provado |
| Import/sintaxe (15 arquivos) | import real + `node --check` + jinja compile | 🟢 provado |
| Migration + endpoints live | colunas no DB Mumbai, endpoints 401, app sem erro | 🟢 provado |
| Resiliência sob erro de DB | fix por leitura; não reproduzi erro transitório real | 🟡 lógico |
| **Render visual no browser** | harness offline (próximo passo) | 🟡 em validação |
| pipeline-polish (pixel/fps/a11y/mem) | **não rodado** | 🔴 pendente |

## 6. Forças (confirmadas pela revisão)

- Isolamento de tenant sólido nos endpoints novos (owner valida membro enabled da org; `tenant_query`; sem leak cross-org — provado por teste).
- `normalize_stage` genuinamente robusto (legado renderiza no funil novo sem data-migration).
- Badge XSS-hardened (null-guard, cor validada por regex, `escapeHtml` no nome).
- Migração idempotente/defensiva (additive, nullable, `or 0`).
- Centralização limpa em `whatsapp_clone_service`; comentários honestos sobre intenção.

## 7. O que ainda depende do Victor / próximos passos

- **Confirmação visual no fluxo real** (login do alpha) — a regra do projeto. Mitiguei com harness offline + os fixes de DOM, mas o pixel final é seu.
- **pipeline-polish** nas 3 superfícies × 2 temas antes de declarar "produto pronto".
- **Fase 2**: scoring/follow-up/dedup portados do ILC (lógica, não JSON), notas por contato, CRUD de templates, slot de AI provider-agnostic (não-Gemini), analytics do funil.
