# ADR — Vocabulário do funil de lead (3 fontes)

2026-05-31. Ratifica o split de vocabulário de estágio que o council notou (ruling `2026-05-31-wa-crm-fase2-decisions`).

## Contexto
Existem 3 vocabulários de "estágio de lead" no codebase:
1. **`wa_contacts.lead_stage`** (CRM WhatsApp, **fonte canônica**): `novo → triagem → reuniao → proposta → cliente / descartado` (intake jurídico).
2. **Bot Node** (`services/whatsapp-bot`, SQLite própria): `cold / warm / qualified / hot`.
3. **ILC `leads_manager`** (legado file-based JSON): `NEW_LEAD / LEAD_QUALIFICATION / ...`.

## Decisão
Os 3 são **silos conscientes**, não contaminação:
- `wa_contacts.lead_stage` é a fonte canônica do CRM (UI, funil, scoring, analytics, sugestão de estágio).
- `normalize_stage()` (`services/whatsapp_clone_service.py`) mapeia qualquer valor legado (cold/warm/qualified/hot) pro funil canônico **na leitura** — dados antigos sobrevivem sem data-migration.
- O bot Node e o ILC `leads_manager` **não escrevem** `lead_stage`; vivem em storage próprio. Não há ponte de escrita que contamine o canônico (`casehub-bridge.js` não toca `lead_stage`).

## Consequência
- Mexer no vocab canônico = editar `LEAD_STAGES` em `whatsapp_clone_service` (re-exportado por `whatsapp_crm`).
- Unificar com o bot Node exigiria migração de dados + ruling — **fora do escopo da Fase 2** (omissão deliberada).

## Pendência de polish (Fase 1.x) não fechada nesta sessão
- **pipeline-polish** (pixel/fps/a11y/mem/responsive nas 3 superfícies × 2 temas): **diferido** — o MCP de browser (Playwright/chrome-devtools) caiu durante a sessão. Rodar `scripts/pipeline-polish.sh` quando o browser tooling voltar.
- **FK constraint** de `wa_contacts.owner_user_id`: o ORM declara `ForeignKey(... SET NULL)` mas o boot-migration adiciona `INTEGER` puro (degrada gracioso: badge some se o user for deletado). Adicionar `ADD CONSTRAINT` guardado quando conveniente (within-table, não-red-line — git-custodian).
