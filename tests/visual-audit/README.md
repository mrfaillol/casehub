# Visual Regression — Fase 1

Sistema automatizado de regressão visual pra produção alpha (`casehub.legal`).
Substitui a validação manual descrita em
`memory/feedback_testing_automation.md`: bot Playwright loga, navega 10 rotas
em 3 viewports × 2 temas (60 PNGs), captura 5 interações chave, e gera diff
contra baseline versionado em git.

> **Fase 1 (este diretório):** runner local + baseline + relatório HTML.
> **Fase 2 (depois, NÃO incluso):** workflow GitHub Actions + email alerts.

## Estrutura

```
tests/
├── visual-audit/
│   ├── run.spec.js         # Playwright runner (login + 60 PNGs + interações)
│   ├── compare.js          # pixelmatch diff engine + report.json/html
│   ├── README.md           # este arquivo
│   ├── results/
│   │   ├── latest.txt      # ponteiro pra última run (ISO timestamp)
│   │   └── <ISO>/          # uma pasta por run
│   │       ├── *.png       # 60 screenshots + interações
│   │       ├── diff/*.png  # masks de diff (após compare.js)
│   │       ├── run-summary.json
│   │       ├── report.json
│   │       └── report.html
│   └── visual-baselines/   # ../visual-baselines, versionado em git
│       └── *.png
```

## Pré-requisitos

- Node 18+ (testado com Node 25).
- Playwright em `~/Projects/casehub/node_modules/` (chromium-1223 já instalado).
- pixelmatch + pngjs em `~/Projects/trabalho-workspace/node_modules/`.
- Credenciais alpha em env vars: `LOGIN_EMAIL_ALPHA` e `LOGIN_PASS_ALPHA`.

Override de caminhos (opcional):

```bash
export PLAYWRIGHT_NODE_MODULES=/path/to/playwright/node_modules
export TRABALHO_NODE_MODULES=/path/to/pixelmatch/node_modules
export CASEHUB_BASE_URL=https://casehub.legal
```

## Como rodar

### Capturar screenshots (run.spec.js)

```bash
cd ~/Projects/casehub-maestro-backend
LOGIN_EMAIL_ALPHA='SEU_EMAIL' LOGIN_PASS_ALPHA='SUA_SENHA' \
  node tests/visual-audit/run.spec.js
```

Tempo: ~3-4 min para 60 capturas + 5 interações.
Resultado vai pra `tests/visual-audit/results/<ISO-timestamp>/`.

Exit code:
- `0` — tudo OK.
- `1` — alguma rota falhou (timeout/erro). Screenshots parciais ainda salvos.
- `2` — env vars faltando.

### Comparar com baseline (compare.js)

```bash
# Compara a última run (lê results/latest.txt)
node tests/visual-audit/compare.js

# Ou aponta uma run específica
node tests/visual-audit/compare.js --run 2026-05-27T03-00-00-000Z
```

Gera:
- `results/<ISO>/diff/*.png` — masks de pixels diferentes (vermelho).
- `results/<ISO>/report.json` — resultado estruturado (CI-friendly).
- `results/<ISO>/report.html` — relatório visual side-by-side
  (baseline | current | diff).

Exit code:
- `0` — todas as comparações dentro da tolerância (ou apenas `new`).
- `1` — pelo menos 1 verdict `fail`.

## Como atualizar baseline

Quando uma mudança visual for **intencional** (refactor de UI aprovado), copie
os PNGs da última run pro diretório de baselines:

```bash
# pega a última run
RUN=$(cat tests/visual-audit/results/latest.txt)
cp tests/visual-audit/results/$RUN/*.png tests/visual-baselines/

# commit explícito
git add tests/visual-baselines/
git commit -m "chore(baselines): refresh after intentional UI change"
```

Recomendação: PR separado com label `intended-baseline-refresh`, link pra ruling/issue
explicando a mudança visual.

## Semantica de threshold

Tolerância é **fração de pixels diferentes** sobre o total, comparado por viewport:

| Viewport | Largura | Cap     | Racional                                                |
|----------|---------|---------|---------------------------------------------------------|
| desktop  | 1440px  | ≤0.5%   | Layout estável; qualquer diff > 7.2k pixels chama atenção. |
| tablet   | 768px   | ≤2%     | Tolerância maior por dropdowns/responsivo borderline.   |
| mobile   | 393px   | ≤5%     | Reflow agressivo de cards/sidebar exige mais folga.     |

`pixelmatch.threshold = 0.1` (sensibilidade per-pixel, ignora antialiasing).

Diff dimension mismatch (baseline 1440×900 vs current 1440×902) é resolvido
estendendo a menor imagem com transparência preta — diff fica gritante e o
campo `dim_mismatch: true` aparece no `report.json`.

## Verdicts

| Verdict | Significado |
|---------|-------------|
| `pass`  | Comparou com baseline, ratio ≤ tolerância. |
| `fail`  | Comparou com baseline, ratio > tolerância. |
| `new`   | Sem baseline (primeiro run ou rota nova). Vira `pass` depois do `cp` inicial. |

## Cobertura atual

**10 rotas** (alpha-critical):

1. `/casehub/dashboard`
2. `/casehub/tasks/kanban`
3. `/casehub/assistente`
4. `/casehub/whatsapp-chat`
5. `/casehub/casehub-md/poc`
6. `/casehub/controladoria`
7. `/casehub/cases`
8. `/casehub/clients`
9. `/casehub/files`
10. `/casehub/calendar/agenda`

**3 viewports:** desktop 1440×900, tablet 768×1024, mobile 393×852.
**2 temas:** light (default), dark (via `localStorage.casehub.theme`).
**Total:** 10 × 3 × 2 = **60 PNGs por run**.

**5 interações:**

| Nome | Rota | Viewport | Tema |
|---|---|---|---|
| `dashboard-cmdk-open` | dashboard | desktop | light |
| `dashboard-theme-toggle` | dashboard | desktop | light |
| `mobile-sidebar-open` | dashboard | mobile | light |
| `assistente-prompt-typed` | assistente | desktop | light |
| `whatsapp-chat-rendered` | whatsapp-chat | desktop | light |

Cada interação salva `interaction-<nome>.png` na pasta da run.

## Workflow recomendado

1. **Baseline inicial** (1x): rode `run.spec.js` → revise os PNGs visualmente →
   `cp results/<ISO>/*.png visual-baselines/` → commit.
2. **Após cada deploy** (manual hoje, GitHub Actions na Fase 2):
   - `node tests/visual-audit/run.spec.js`
   - `node tests/visual-audit/compare.js`
   - abrir `report.html` no browser
3. **Regressão detectada (`fail`):**
   - se intencional → atualizar baseline (PR separado).
   - se bug → rollback ou hotfix, re-rodar.

## Próximos passos (Fase 2 — NÃO faz parte desta entrega)

1. `.github/workflows/visual-regression.yml`: cron 06:00 BRT + após `deploy-alpha`.
2. GitHub Secrets `LOGIN_EMAIL_ALPHA` / `LOGIN_PASS_ALPHA`.
3. Email Victor via msmtp + iCloud (config já existe em `token-economy`).
4. Auto-create GitHub Issue por regressão crítica (label `visual-regression`).
5. Self-hosted Oracle runner quando voltar online (zera custo Actions minutes).

Convocar `/council` antes de mexer em `.github/workflows/` — workflow auth é
red line (ruling `2026-05-05-perpetual-sessions-and-automerge`).

## Troubleshooting

**"Login form not found at /casehub/login"** — verifique se a URL do login mudou.
Inspecione `results/<ISO>/run-summary.json` pra ver o último estado.

**"post-login URL unexpected"** — landing não foi pra `/casehub/...`. Pode ser
2FA, captcha ou conta bloqueada. Confirme login manual no browser primeiro.

**Pixel diff 100% em todas as rotas** — provavelmente o baseline foi capturado
em outra resolução. Re-gere baseline e commit.

**Erro `Cannot find module 'playwright'`** — ajuste `PLAYWRIGHT_NODE_MODULES` env
var pra apontar pro lugar correto.

**Erro `Cannot find module 'pixelmatch'`** — ajuste `TRABALHO_NODE_MODULES`.
Pixelmatch 7.x é ESM-only, `compare.js` usa `import()` dinâmico.

## Spec canônica

`memory/feedback_testing_automation.md` (proposta + arquitetura completa
incluindo Fases 2 e 3).
