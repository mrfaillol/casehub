# Fatia 1 — POC TipTap standalone (markdown round-trip)

> **Objetivo:** provar TipTap dentro do CaseHub como rota isolada, com conversão markdown↔HTML funcionando bidirecional, sob o design system Basic (data-theme="neuromorphic"). Sem features, sem ruler/page Google Docs (Fatia 2), sem integração com módulos do CaseHub. POC = "vivo dentro do app, prova o pipeline".

## Critérios de pronto

1. Rota `GET /casehub-md/poc` retorna HTML autenticado.
2. Página carrega TipTap via ESM CDN (jsdelivr) sem build step novo.
3. Editor TipTap visível e editável.
4. Painel lateral mostra markdown atualizando em tempo real ao digitar (Doherty <500ms).
5. Botão "Carregar" injeta markdown editado de volta no editor.
6. Shell visual respeita design system: data-theme="neuromorphic", elevation tokens, sem hex/px cru.
7. Smoke test Playwright valida: rota carrega, editor monta, digitar reflete no mirror, round-trip reverso funciona.
8. Não toca nenhum template/rota alpha-crítica.
9. Branch dedicada (worktree): `session-2026-05-22-casehub-md-poc` em `casehub-worktrees/casehub-md-poc-20260522`. Diff <300 linhas.

## Escopo OUT (não fazer agora)

- "Folha" Google Docs com ruler SVG, sombra de página, margens 1in (Fatia 2)
- Tables, embeds, code blocks com syntax highlighting (Fatia 3)
- Export DOCX (Fatia 4)
- Drive sync (Fatia 5)
- OCR (Fatia 6)
- Maestro (Fatia 7)
- Collab (Fatia 8)
- Persistência (POC vive no DOM, sem DB)
- Build pipeline (Vite/Webpack) — fica pra avaliar quando precisar tree-shaking ou componentes Vue ricos

## Decisão técnica: ESM via CDN vs build pipeline

**Escolhido: ESM via CDN (cdn.jsdelivr.net)** para Fatia 1.

| Critério | ESM CDN | Vite build |
|---|---|---|
| Quebra alpha? | Não | Risco (novo pipeline, scripts npm) |
| Tempo até POC | minutos | ~1h setup |
| Bundle tree-shaken | não | sim |
| Manutenção longo-prazo | precisa migrar | já pronto |
| CSP atual permite | sim (cdn.jsdelivr.net já liberado) | sim (`'self'`) |

Para POC, **CDN é correto**. Quando passar de POC pra release, abrir issue/Council pra avaliar Vite. Vue 3 + componentes via SFC migram para esse caminho na Fatia 3+ se for necessário.

## Leis UX aplicadas (Fatia 1)

- **Fitts:** toolbar buttons ≥36×36 hit target; alvos primários (back, ↻ Carregar) no topo.
- **Miller:** toolbar agrupada em 3 chunks (inline, headings, blocks) — cada grupo 3-4 itens.
- **Doherty:** mirror reflete digitação em <500ms (sync onUpdate síncrono, sem debounce).

## Arquivos a criar (Fatia 1)

```
routes/casehub_md.py                 # APIRouter, rota /casehub-md/poc
templates/casehub_md/poc.html        # standalone, carrega tokens+neumorphic+poc.css
static/js/casehub-md/poc.js          # ESM module, TipTap init, marked+turndown
static/css/casehub-md/poc.css        # CSS via tokens semânticos (sem hex/px cru)
tests/smoke-casehub-md-poc.spec.js   # Playwright smoke
docs/casehub-md/README.md            # criado
docs/casehub-md/fatia-1-spec.md      # este arquivo
core/app_factory.py                  # 1 linha: "casehub_md" em CORE_ROUTERS
```

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec (este doc) | ✅ | `docs/casehub-md/{README,fatia-1-spec}.md` |
| 2. POC code (rota + template + JS) | ✅ | `routes/casehub_md.py`, `templates/casehub_md/poc.html`, `static/js/casehub-md/poc.js` |
| 3. Estética básica (neumórfico, tokens) | ✅ | `static/css/casehub-md/poc.css` (sem hex/px cru, leis citadas) |
| 4. Integração CaseHub backend (rota live em CORE_ROUTERS) | ✅ | `core/app_factory.py:357` `"casehub_md"` no CORE_ROUTERS |
| 5. Smoke test Playwright | ✅ criado | `tests/smoke-casehub-md-poc.spec.js`. Execução contra dev gated em `CASEHUB_SMOKE_BASE_URL` — pendente runtime dev live |
| 6. Commit pequeno | ⚠️ commit feito, diff 895 linhas (290 docs + 600 código) | `e2ddea7` em `session-2026-05-22-casehub-md-poc` |
| 7. Checkpoint (este registro) | ✅ | atualizado 2026-05-22 |

## Notas operacionais

- Sessão concorrente Codex/outro processo causou `git clean` no working tree principal `~/Projects/casehub` às 22:24. Arquivos não-commitados foram perdidos. Recuperação: novo worktree `casehub-md-poc-20260522` + commit imediato. Documentar para evitar repetir.
