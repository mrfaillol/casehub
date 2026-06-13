# Brief — login.html

**Data:** 2026-04-14 · **Rota:** /casehub/login · **Prioridade:** P0

## Contrato preservado (passo 2)

- **Vars Jinja:** `product`, `org_name`, `org_logo`, `org_settings` (font_family, font_heading, accent_color, shader_color1-4), `org_slug`, `theme`, `lang`, `error`, `showcase`, `PREFIX`
- **Data-attrs usados:** `data-theme`, `data-product`, `data-org` (no `<html>`)
- **IDs/classes JS espera:**
  - `#organic-canvas` (three.js shader fundo)
  - `#skyCanvas` (sky shader overlay, apenas `product=="lite"`)
  - `.macos-titlebar` (drag script)
  - `.macos-window-login` (drag target)
  - `.traffic-dot` (ignorado pelo drag)
- **Form names:** `email`, `password`
- **Rotas:**
  - `POST {{ PREFIX }}/login` (ou `javascript:void(0)` em showcase)
  - `GET {{ PREFIX }}/set-language/pt|en`
  - `GET {{ PREFIX }}/forgot-password`
  - `GET {{ PREFIX }}/signup`

## Proposta visual

Refactor incremental do macOS window login existente. Mantém a identidade macOS (traffic-lights, window + titlebar draggable, split brand/form) mas migra de hex/px cru → tokens semânticos do design system (tokens.css + components/buttons,forms).

Titlebar ganha tratamento **liquid-glass tier B** inspirado em `codepen-references/liquid-glass-elements`: highlight inset top (1px branco 30%), gradient border radial sutil, inner-glow suave no hover. Casa com identidade macOS sem importar o CSS pesado (3679 linhas).

Form panel: `.os-input-group` → `.field`, `.os-input` → `.input`, `.os-btn-primary` → `.btn.btn--primary.btn--lg.btn--block`. Labels ganham weight/escala tokenizados.

Shader three.js do fundo preservado como identidade única (Victor autorizou budget memory ≤120MB nessa rota).

**Lei UX aplicada:** **Fitts** — botão primary `.btn--lg` (52px min-height) + inputs `.input` (44px min) atendem tap-target em mobile; links `login-links` mantêm área clicável ≥44px via padding implícito do gap.

## Referência codepen

- **Pasta:** `codepen-references/liquid-glass-elements/`
- **Tier:** B · **Security scan:** SAFE 2026-04-13
- **O que aproveitar:** técnica de composição (highlight inset top + gradient border + backdrop-filter moderado) na `.macos-titlebar`
- **O que NÃO copiar:** `liquid-glass.css` inteiro (3679 linhas, 60+ usos de backdrop-filter estoura budget GPU). Só inspiração da camada de highlight.

## Red flags

- Three.js shader = ~80-110MB heap. Budget relaxado 120MB conforme decisão.
- Múltiplos backdrop-filter (window + titlebar + form-panel) já existem — manter ≤3 camadas.
- `overflow: hidden` no body mobile foi removido no CSS original (override `!important` em mobile) — preservar.
- Icons FontAwesome via CDN → mantido (contrato visual existente).

## Variante immigrant

- Trechos já existem via `{% if product == "lite" %}` vs `else`. Tokens `--accent` herdados de `[data-org="immigrant"]` em tokens.css cobrem variante.
- Nenhuma mudança necessária nesse refactor.

## Critério de aceite

- [ ] pixel-diff desktop ≤1.5% (identidade mudou, refactor não é pixel-perfect)
- [ ] FPS p95 ≤16.67ms
- [ ] axe-core 0 serious/critical
- [ ] heap ≤120MB (budget login relaxado; three.js shader)
- [ ] 3 viewports (390×844, 820×1180, 1440×900) sem overflow
- [ ] Form POST `{{ PREFIX }}/login` funciona com `victor@vingren.me` / `dev123`
- [ ] Drag da titlebar funciona
- [ ] Links set-language / forgot-password / signup clicáveis


## Como era × Como ficou

### Antes
- Cores e medidas hex/px crus inline (`#1C2447`, `0.7rem`, `10px`).
- Classes `.os-input-group`, `.os-input`, `.os-btn-primary` próprias do template — sem reuso.
- `login-os.css` 270 linhas com hex/px direto.

### Depois
- Tokens semânticos (`var(--accent)`, `var(--space-5)`, `var(--radius-lg)`) — mudar 1 token muda 200 templates.
- Classes `.field`/`.input`/`.btn.btn--primary.btn--lg` do design system.
- Titlebar ganhou efeito **liquid-glass** (highlight inset top + gradient border) — inspiração do `codepen-references/liquid-glass-elements` tier B (security scan SAFE).
- `100dvh` em vez de `100vh` (corrige Safari mobile).

### Por quê melhorou
1. Identidade visual unificada com o resto do app.
2. Tap targets 52px no botão primary (lei de Fitts) — mais fácil clicar no mobile.
3. Animação `var(--dur-organic)` (220ms) em vez de `0.3s` mágico.
4. Three.js shader preservado (identidade da marca CaseHub Lite).
