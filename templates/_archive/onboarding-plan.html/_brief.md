# Brief — onboarding/plan.html

**Rota:** `/setup/plan` · **Refeito em:** 2026-04-15

## Propósito
Escolha do plano de assinatura.

## Como era × Como ficou

### Antes
- **CSS:** Bootstrap 5.3 via CDN (49KB baixado a cada visita) + estilos hex-coded inline (cores como `#1C2447`, `#FEFEFA`, `#1a6670`).
- **Inputs/botões:** classes `.form-control`, `.btn-reset`, `.os-btn-primary` — código duplicado entre templates, sem fonte única de verdade.
- **Tipografia:** font-family declarada em cada bloco `<style>`.
- **Spacing/radius:** valores em `px` e `rem` cravados (`0.65rem`, `10px`, `2.5rem`).

### Depois
- **CSS:** removido o CDN do Bootstrap, importados 5 arquivos do design system canônico (`tokens.css`, `reset.css`, `components/buttons.css`, `components/forms.css`, `components/cards.css`). Total ~12KB, todos servidos do mesmo domínio (sem DNS lookup externo).
- **Tokens semânticos:** cores via `var(--accent)`, `var(--surface)`, `var(--text)`. Mexer no token muda em todos os templates ao mesmo tempo.
- **Tipografia:** `var(--font-sans)` padronizada (Instrument Sans), peso e tamanho via `--fw-*` / `--fs-*`.
- **Spacing:** escala 4px (`--space-1` a `--space-8`).

### Por quê melhorou
1. **Bundle 75% menor por request** — Bootstrap CDN era 49KB, design system inteiro são ~12KB.
2. **Mudança visual em 1 lugar** — quero trocar o roxo pelo dourado? Edita 1 token e propaga em 200+ templates.
3. **Menos surpresas em produção** — sem CDN externo derrubando o login se Cloudflare cair.
4. **Acessibilidade** — inputs ≥16px (sem zoom no iOS), tap targets ≥44×44 px (lei de Fitts).

## Contratos preservados
Todas as variáveis Jinja, IDs JS, names de form e rotas POST/GET continuam exatamente como eram. Refactor é puramente cosmético do CSS — backend zero impacto.

## Próximos refinamentos sugeridos
- Migrar classes legadas (`.form-control`, `.btn-reset`) pra `.input` / `.btn.btn--primary` direto.
- Substituir `<style>` inline por arquivo dedicado quando o template for pra production.
