# WhatsApp CRM — Roadmap Fase 2 (+ polish backlog)

**Origem:** workflow de decomposição (4 agentes, 2026-05-31) sobre o estado pós Fase 1+1.1 (`b002de85`).
**Princípio:** portar a LÓGICA do legado ILC pro DB org-scoped (`wa_contacts`), NUNCA o storage JSON single-tenant (vazaria entre orgs). AI = provider-agnostic, **não-Gemini** default.

## Correção de premissa (importante)

O roadmap original marcou o **PR1 (foundation) como Council-required** por achar que precisava trocar o passo de migração do `deploy-alpha.yml`. **Isso é desnecessário:** `owner_user_id`/`lead_score` já existem fisicamente no DB Mumbai (verificado nesta sessão) porque o mecanismo real é `core/app_factory._run_pending_migrations()` (roda no boot/deploy, additive, app-code — **não** é deploy-topology). Colunas novas entram nessa lista; tabelas novas são criadas por `Base.metadata.create_all()` no boot. **Foundation = sem Council.**

## Gates reais

- **Sentinela** — PR9 (AI abstraction): toca convenção de env (`CASEHUB_AI_PROVIDER`) e leitura de chaves. Mitigado (sem secret novo, default não-Gemini). Rodar `/sentinela` antes de mergear; gate completo só quando uma 2ª chave real (ex. OPENAI_API_KEY) for adicionada.
- **Produto (Victor, não Council)** — PR6 (modelo de scoring VS): quais inputs de `wa_contacts` mapeiam Fit/Intent/Quality + tabela de valor por área. Dimensão Engagement é mecânica (sem decisão). **Aguarda sign-off do Victor.**
- **Produto (Victor)** — Deals/Forecast (revenue forecaster ponderado no estágio `proposta`): lógica ILC reusável, mas **fora do escopo declarado da Fase 2**. Omissão deliberada; precisa decisão própria.

## PRs sequenciados

| PR | Esf | Visível | Deps | Título | Gate |
|----|-----|---------|------|--------|------|
| 1 | M | · | — | Foundation: colunas (`follow_up_date/note`, `normalized_phone`) via `_run_pending_migrations` + tabelas novas via models | ~~Council~~ → **nenhum** (re-scoped) |
| 2 | S | 👁 | 1 | Owner shape `{user_id}` padronizado + badge **Processo** na sidebar (`case_number` no payload, batched, org-scoped) | nenhum |
| 3 | M | 👁 | — | **Notas por contato** (`wa_contact_notes` + painel) — maior valor diário | nenhum |
| 4 | M | 👁 | 1 | Templates CRUD (`wa_templates`, seed dos 22 hardcoded; global `org_id=NULL` + own-org) | nenhum |
| 5 | S | · | — | Captura de stage-history + score-history (`wa_contact_stage_history`) — pré-req de analytics | nenhum |
| 6 | L | 👁 | 1,5 | Lead scoring portado (Fit/Eng/Intent/Quality) | **Produto: Victor** |
| 7 | S | 👁 | 1,3 | Follow-up scheduling + overdue (datas, puro) | nenhum |
| 8 | S | 👁 | 1 | Detecção de duplicatas (sufixo 10 dígitos + email, **org-scoped**) | nenhum |
| 9 | M | · | — | Abstração de AI provider-agnostic (Gemini adapter + NullProvider default) | **Sentinela** |
| 10 | M | 👁 | 5 | Classificador de estágio determinístico (sem LLM, promote-only, never-touch-terminal) | nenhum |
| 11 | L | 👁 | 5,6,10 | Dashboard de analytics do funil (conversão/velocidade/aging/score-trends) | parcial (score-trends precisa PR6) |
| 12 | M | 👁 | 2,3,4,6,11 | Pipeline-polish sweep + FK constraint + cleanup (closeout) | nenhum (precisa browser tooling) |

## Tenant safety (red line transversal)

Toda query nova **WHERE org_id=:org**. Pontos críticos citados pelos agentes: dedup (PR8) — match global de sufixo vazaria clientes de outra firma; notas (PR3) — `org_id AND contact_id`; templates (PR4) — list = `org_id IS NULL OR org_id=:org`, mutações só own-org; Case lookup (PR2) — `tenant_query` no batch.

## Ordem de execução autônoma (sem gate)

Wave 1 (valor comercial imediato): **PR3 (notas) → PR2 (Processo) → PR4 (templates) → PR8 (dedup) → PR7 (follow-up) → PR5 (history)**.
Wave 2 (precisa decisão/review): PR9 (Sentinela), PR6 (Victor), PR10, PR11, PR12.

Cada PR: worktree → código → teste (pytest guard) → review adversarial → deploy-alpha → smoke → patch note in-app (org 4, leigo).
