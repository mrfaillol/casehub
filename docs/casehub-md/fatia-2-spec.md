# Fatia 2 — "Folha" Google Docs dentro do shell neumórfico

> **Objetivo:** transformar a "folha" (`.md-paper`) atualmente sunken-neutra numa página estilo Google Docs (serif, formato 8.5×11", margens 1in, sombra de página, ruler horizontal opcional). O **shell ao redor permanece neumórfico** — só a folha muda. Sem novas features de editor.

## Critérios de pronto

1. Folha tem largura visível ~8.5in (816px @96dpi) com margens 1in (96px) internas onde o texto fica.
2. Fundo da folha é "papel branco" — `--surface-base` ainda OK mas com sombra de página (não `--elevation-0` sunken; agora elevation forte simulando papel sobre mesa).
3. Família serif `Instrument Serif` (já carregado em Fatia 1) ou alternativa Lora/Merriweather no corpo do texto da folha — NÃO no shell.
4. Ruler horizontal SVG opcional no topo da folha (toggle via param `?ruler=1` por enquanto — feature flag simples).
5. Tipografia da folha: corpo serif, line-height generoso (≥1.75), font-size ≥16px, max-width respeitando margens (não 100% da folha).
6. Mobile (<60rem): folha vira full-width, ruler some, margens reduzidas.
7. Não toca arquivo Fatia 1 não-CSS — apenas `static/css/casehub-md/poc.css` + spec/checkpoint.
8. Diff <250 linhas (alvo cirúrgico desta vez).

## Escopo OUT (não fazer agora)

- Ruler interativo (drag para mudar margens) — Fatia 7+ se necessário.
- Page breaks visuais (múltiplas páginas) — depende de Fatia 4 export.
- Print stylesheet `@media print` — Fatia 4 (export) cobre.
- Page-number footer — Fatia 4.
- Margem comment (Notion-like) — Fatia 7 (Maestro).

## Decisões técnicas

### Fonte serif da folha

- **Escolhida:** `Instrument Serif` (já carregada em Fatia 1, presente nos tokens `--font-serif`).
- **Por quê:** já no design system canônico; carrega 1 arquivo via Google Fonts; estilo editorial sóbrio que o Victor já aprovou nos headings.
- Lora/Merriweather **rejeitadas**: adicionar nova família = bandwidth + sync com brand-kit. Quando o Victor pedir explicitamente "tem que ser Lora", trocamos via 1 token override em `casehub-md/poc.css` (`--font-serif-paper: 'Lora', ...`).

### Ruler horizontal

- **SVG inline** (não imagem) — escala sem perda, controlável via CSS variables.
- Posicionado **dentro do `.md-paper`** absolute top, antes do conteúdo.
- Toggle: `<body class="md-with-ruler">` quando `?ruler=1` no querystring. Default OFF na Fatia 2 (visual ainda em iteração).

### Sombra "papel sobre mesa"

- Não usar `--elevation-0` (sunken — sensação errada de "afundado").
- Usar `--elevation-3` ou nova variável `--elevation-paper` (definida localmente em `poc.css` consumindo tokens) — feel: papel suspenso sobre o card neumórfico.

### Largura responsiva

- Desktop ≥80rem: folha fixa em `min(816px, 100% - 2rem)`.
- Tablet 60–80rem: folha 100% do card menos padding.
- Mobile <60rem: folha edge-to-edge dentro do card, margens internas reduzidas a `--space-4`.

## Leis UX aplicadas (Fatia 2)

- **Hick:** evitar features competindo na folha (apenas typography editorial; ruler off por default).
- **Reading-ease (não é uma lei mas hábito):** line-height ≥1.75, max-width do parágrafo ~65ch para legibilidade longform.
- **Postel:** aceitar `?ruler=1`, `?ruler=true`, `?ruler=on` — todos ligam (futuro Fatia 6+).

## Arquivos a editar (Fatia 2)

```
static/css/casehub-md/poc.css           # estilos da .md-paper + .md-paper > .md-editor
templates/casehub_md/poc.html           # adicionar SVG ruler inline + class toggle via querystring
routes/casehub_md.py                    # ler ?ruler= e passar ao template
docs/casehub-md/fatia-2-spec.md         # este arquivo
```

**Não toca:** `static/js/casehub-md/poc.js`, `tests/smoke-casehub-md-poc.spec.js` (smoke continua válido — folha é cosmética, mount/round-trip não muda).

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec (este doc) | ✅ | `docs/casehub-md/fatia-2-spec.md` |
| 2. Folha CSS (page 8.5×11, sombra, serif) | ✅ | `.md-paper-sheet` em `static/css/casehub-md/poc.css` (width `min(51rem, 100% - var(--space-4))`, padding 6rem = 1in, sombra papel + serif `var(--font-serif)` body) |
| 3. Ruler SVG inline + toggle CSS | ✅ | template `poc.html` (`<div class="md-ruler"><svg viewBox="0 0 816 20">…</svg></div>` opt-in via `body.md-with-ruler`) |
| 4. Integração rota (`?ruler=`) | ✅ | `routes/casehub_md.py` — `_ruler_on()` Postel-friendly (`1/true/on/yes/sim`) |
| 5. Smoke continua válido | ✅ | seletores `#poc-editor`, `data-tiptap-ready`, `.ProseMirror` preservados; folha apenas envelopa |
| 6. Commit pequeno | ✅ alvo respeitado | diff 117/+ 12/- (alvo <250) |
| 7. Checkpoint | ✅ | atualizado 2026-05-22 |

## Próximos refinos (deferidos, não bloqueantes)

- Ruler com tick interativo (drag muda margens) — só faz sentido após Fatia 4 (export) decidir page geometry definitiva.
- Fonte Lora/Merriweather: trocar via `--font-serif-paper` override local; deferido até Victor pedir explicitamente.
- Print stylesheet — Fatia 4 (export DOCX) cobre essa camada via Pandoc/template OAB.
