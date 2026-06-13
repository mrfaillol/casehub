# Fatia 9 — Integração frontend, acessibilidade, mobile, load on mount

> **Objetivo:** levar CaseHub.md de "POC isolada" para "aba nativa do produto". Pedido explícito do Victor (2026-05-23): entrada no frontend, mobile, acessibilidade, tudo funcionando perfeitamente.

## Critérios de pronto

1. **Entrada nas 3 navs do CaseHub:**
   - `sidebar_lite.html` (sidebar tradicional Lite + desktop view) — fontawesome `fa-pen-to-square` + label "CaseHub.md".
   - `browser_basic_rail.html` (rail browser-basic) — ícone SVG inline novo "editor" (pen + linhas).
   - `browser_basic_tabs.html` (tabs estilo Chrome) — mesmo ícone "editor".
2. **Fatia 5.1 — Load on mount:** rota lê `?doc=`, `?doc_id=`, `?d=` (Postel); template expõe via `data-initial-doc-id`; JS faz `GET /casehub-md/drive/{doc_id}` no mount; 404 vira "doc novo" silencioso.
3. **Botão "📂 Abrir":** dialog nativa lista os 100 docs recentes do Drive; click navega para `?doc=<id>` (URL shareable + reload limpo).
4. **A11y:**
   - Skip link "Pular para o editor" — focus visible, off-screen até `:focus`.
   - `<dialog>` nativos (focus trap automático + ESC fecha).
   - `role="status"` + `aria-live="polite"` no sync status.
   - `role="textbox"` `aria-multiline="true"` `aria-label` no editor; `tabindex="0"`.
   - `aria-expanded` no botão mobile toggle.
   - `aria-label` adicionado a botões com glyph apenas.
   - `role="option"` + keyboard (`Enter`, `Space`) nos itens da lista de docs.
5. **Mobile (≤60rem):**
   - Toolbar wrap em múltiplas linhas; botões ≥44×44px (Fitts mobile / Apple HIG).
   - Mirror card vira drawer slide-up (`position: fixed; bottom: 0; transform: translateY(100%)`).
   - Botão `⇆` no header com `aria-expanded` abre/fecha o drawer.
   - Folha edge-to-edge; padding reduzido.
   - Modais full-width.
   - Footer empilhado vertical.
6. **Keyboard shortcuts:** `Cmd/Ctrl + S` salva no Drive.
7. **Robust PREFIX:** body `data-prefix="{{ PREFIX }}"` substitui parsing do back link.
8. **Smoke ampliado:** 4 steps novos (skip link, data-prefix, mobile toggle transform, botão Abrir).

## Files modified

```
templates/partials/sidebar_lite.html         # +1 entry (3 linhas)
templates/partials/browser_basic_rail.html   # +1 entry + ícone SVG "editor" (7 linhas)
templates/partials/browser_basic_tabs.html   # +1 entry + ícone SVG "editor" (7 linhas)
routes/casehub_md.py                          # +initial_doc_id from ?doc= (11 linhas)
templates/casehub_md/poc.html                 # +skip-link, +modal open, +mobile toggle, ARIA refinements (62 linhas)
static/js/casehub-md/poc.js                   # +load on mount, +openDocDialog, +mobile toggle, +Cmd+S, +switchToDoc (232 linhas)
static/css/casehub-md/poc.css                 # +skip-link, +doc-list, +mobile drawer, +touch targets (152 linhas)
tests/smoke-casehub-md-poc.spec.js            # +4 steps (22 linhas)
docs/casehub-md/fatia-9-spec.md               # este arquivo
```

## Leis UX aplicadas

- **Fitts mobile:** ≥44×44px hit targets em viewport <60rem (Apple HIG; WCAG 2.5.5 Target Size AAA).
- **Postel:** `?doc=`, `?doc_id=`, `?d=` aceitos; doc_id sanitizado server-side.
- **Norman:** botão "📂 Abrir" tem glyph + label; aria-label adicional para SR.
- **Hick:** modal "Abrir" exibe apenas listagem + Fechar (sem rename/delete agora).
- **Doherty:** Cmd/Ctrl+S responde imediatamente (toolbar btn disabled + status busy <100ms).

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec | ✅ | este arquivo |
| 2. Nav entry (3 partials) | ✅ | sidebar_lite/basic_rail/basic_tabs |
| 3. Fatia 5.1 (load on mount) | ✅ | routes/casehub_md.py + JS loadDocOnMount() |
| 4. Modal Abrir + lista Drive | ✅ | `<dialog id="poc-open-dialog">` + openDocDialog() |
| 5. A11y completa | ✅ | skip-link, ARIA, role/aria-live, focus visible |
| 6. Mobile drawer + touch ≥44px | ✅ | @media ≤60rem + mobile-toggle handler |
| 7. Cmd/Ctrl+S shortcut | ✅ | document keydown listener |
| 8. Robust PREFIX via data-prefix | ✅ | body[data-prefix] |
| 9. Smoke ampliado | ✅ | steps 11-14 |
| 10. Commit + push | em curso | |
| 11. Checkpoint | em curso | |

## Decisões de não-implementar (defer explícito)

- **Login form mobile do CaseHub:** fora do escopo deste módulo.
- **Auto-refresh da lista do Drive:** lista é pull on-demand (click "📂 Abrir"); poll automático fica para quando colab Fatia 8 entrar.
- **Excluir/renomear doc na lista:** deferido — não toca o caminho feliz e mantém escopo enxuto.
- **Lighthouse/axe-core score:** smoke valida estrutura ARIA + skip link; auditoria Lighthouse end-to-end fica pra quando dev VPS rodar live.
