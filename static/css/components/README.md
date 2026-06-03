# CaseHub — Design System (foundation)

Arquivos canônicos da Trilha A. Tudo que segue (Trilha D em diante) consome estes tokens.

## Arquivos

```
static/css/
├── tokens.css                 # design tokens (cores, fonts, spacing, radius, shadow, motion, z-index)
├── reset.css                  # modern reset (substitui Bootstrap 5.3)
└── components/
    ├── README.md              # este arquivo
    ├── buttons.css            # .btn + variants (primary/secondary/ghost/danger/success) + sizes + .btn--icon
    ├── cards.css              # .card + .card--glass/interactive + partes (__header/body/footer)
    └── forms.css              # .field .input .textarea .select .checkbox .radio .fieldset
```

## Ordem de carga (obrigatória)

Carregar **nesta sequência** no `<head>` — a cascata depende disso:

```html
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/reset.css">
<link rel="stylesheet" href="/static/css/components/buttons.css">
<link rel="stylesheet" href="/static/css/components/cards.css">
<link rel="stylesheet" href="/static/css/components/forms.css">
<!-- em seguida: overrides específicos de view (liquid-glass.css, casehub-theme.css, etc) -->
```

Jinja (recomendado, em `templates/partials/head_css.html`):

```jinja
{% set ds_css = [
  'css/tokens.css',
  'css/reset.css',
  'css/components/buttons.css',
  'css/components/cards.css',
  'css/components/forms.css',
] %}
{% for f in ds_css %}
<link rel="stylesheet" href="/static/{{ f }}">
{% endfor %}
```

## Regras invioláveis

1. **Nunca** hex cru em componente — sempre via token (`var(--accent)`).
2. **Nunca** `!important` (exceção semântica documentada: `[hidden]` no reset).
3. **Nunca** valores mágicos de spacing (`13px`) — usar escala `--space-*`.
4. Tap target mobile `≥ 44px` (token `--tap-target-min`) — lei de Fitts.
5. Inputs `font-size: var(--fs-base)` (16px) — evita zoom iOS.
6. Se precisar de token novo, **adicionar em `tokens.css`**, não inline.

## Temas

- `<html data-theme="light">` (default, explícito)
- `<html data-theme="dark">`
- Auto: se `data-theme` ausente, segue `prefers-color-scheme`.

## Org override (ILC/immigrant)

```html
<body data-org="immigrant" data-theme="light">
```

Redefine apenas `--accent` e correlatos (sky-blue ILC). Estrutura permanece.

## Referências UX citadas no código

- **Fitts** — tap targets ≥ 44px (buttons.css, forms.css).
- **Hick** — variantes de botão limitadas a 5 (evitar paralisia).
- **Miller** — grouping via `.fieldset`, `.card` (cards.css, forms.css).
- **Doherty** — `dur-snappy=150ms`, loading spinner em botões.
- **Postel** — validação permissiva + normalização em JS (contract de forms.css).

Digest: `agents/knowledge/ui-ux/articles-digest.md`.

## Liquid Glass budget

`.card--glass` usa **1 camada** `backdrop-filter: blur(16px) saturate(1.4)`. Respeita budget de ≤20px blur e ≤3 layers simultâneos definido em `agents/knowledge/liquid-glass-principles.md`.

Fallback sólido via `@supports not (backdrop-filter)` já embutido.

## Próximos passos (Trilha D)

Consumir em:
- `templates/partials/head_css.html` — injetar ordem de carga acima antes de `liquid-glass.css`.
- `templates/auth/login.html` — migrar para `.btn.btn--primary`, `.input`, `.field`.
- `templates/base.html` — `.card` para widgets do dashboard modular.
- `casehub-theme.css` / `liquid-glass.css` — começar a deletar regras que agora vivem nos tokens (buscar `#1C2447`, `#C9A208`, `cubic-bezier(.22`).
