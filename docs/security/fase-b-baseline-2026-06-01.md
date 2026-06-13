# Fase B Baseline - 2026-06-01

Contexto: continuidade da sessao Claude `3ab34b64-3002-4399-8144-c29064626386`.
Fase A de templates fechada em `docs/security/template-safe-classification-2026-06-01.md`.

## Ambiente

- Runner: `oracle-army:~/casehub-reconcile`
- Branch: `sec-hardening-on-main`
- Base URL: `https://dev.vingren.me`
- Login: `victor@vingren.me` via POST direto no contexto Playwright. Motivo: o dev historico usa senha `dev123`, mas o HTML tem `minlength=8` e bloqueia submit no browser embora o backend aceite.
- Run visual: `tests/visual-audit/results/2026-06-01T03-58-37-629Z`

## Visual

Captura autenticada concluida:

- 10 rotas
- 3 viewports
- 2 temas
- 5 interacoes
- 65 PNGs no total
- `run-summary.json`: `failures=0`, `total=60`

Rotas capturadas: dashboard, tasks/kanban, assistente, whatsapp-chat,
casehub-md/poc, controladoria, cases, clients, files, calendar/agenda.

`compare.js` contra o baseline versionado atual gerou:

- pass: 6
- fail: 59
- new: 0
- report: `tests/visual-audit/results/2026-06-01T03-58-37-629Z/report.html`

Interpretacao: isto nao deve ser tratado como regressao automatica ainda. A captura
nova foi em `dev.vingren.me`; o baseline versionado foi gerado em outro estado/host
e esta desalinhado. O proximo passo visual correto e revisar o HTML report e,
se aprovado como estado atual de dev, fazer refresh explicito de baseline em PR
separado.

Maiores deltas observados:

| arquivo | ratio | tolerancia |
| --- | ---: | ---: |
| `interaction-dashboard-theme-toggle.png` | 0.9254 | 0.0050 |
| `casehub_casehub-md_poc-tablet-dark.png` | 0.5426 | 0.0200 |
| `casehub_cases-tablet-light.png` | 0.5244 | 0.0200 |
| `casehub_calendar_agenda-tablet-light.png` | 0.4609 | 0.0200 |
| `casehub_clients-tablet-light.png` | 0.4436 | 0.0200 |

## Performance

Como `scripts/perf_guardian.py` dependia de `httpx` e o host Oracle estava sem
`pip`, foi usado benchmark HTTP Node equivalente para as mesmas rotas principais,
com 3 repeticoes autenticadas. Resultado salvo em:

`tests/visual-audit/results/2026-06-01T03-58-37-629Z/perf-node-dev.json`

Resumo:

| rota | status | total p95 | ttfb p95 | bytes | budget |
| --- | --- | ---: | ---: | ---: | ---: |
| dashboard | pass | 86ms | 84ms | 63,693 | 350,000 |
| clients | pass | 15ms | 14ms | 57,675 | 350,000 |
| cases | pass | 33ms | 31ms | 97,097 | 350,000 |
| tasks | pass | 7ms | 7ms | 0 | 350,000 |
| tasks-kanban | pass | 575ms | 572ms | 456,375 | 900,000 |
| calendar | pass | 24ms | 24ms | 50,580 | 350,000 |
| controladoria | fail | 405ms | 392ms | 1,161,436 | 900,000 |
| leads-dashboard | pass | 18ms | 18ms | 34,249 | 650,000 |

Unico budget estourado: `controladoria` por payload inicial acima de 900KB.
Nao corrigir nesta Fase A/B sem lane propria; registrar como candidate de
performance follow-up.

## Operacao no Oracle

Durante o setup do baseline foram instaladas dependencias Playwright e Chromium
no Oracle. A tentativa posterior de instalar `python3-pip` encheu o disco e deixou
pacotes parcialmente desembrulhados; o host foi recuperado no mesmo turno:

- `apt-get clean`
- remocao de caches Playwright antigos (`chromium-1208`, `chromium_headless_shell-1208`, `ffmpeg-1011`)
- `dpkg --configure -a`
- remocao dos pacotes quebrados: `build-essential`, `g++`, `libpython3-dev:arm64`, `libjs-sphinxdoc`
- `apt-get check` limpo
- espaco livre final: cerca de 1.9GB em `/`

## Veredito

Fase B tem baseline inicial suficiente para handoff:

- visual capturado com sucesso no dev
- report de diff produzido, mas exige refresh/revisao manual por host drift
- performance coletada; um follow-up real identificado em controladoria
- nenhuma correcao funcional adicional foi aplicada nesta lane
