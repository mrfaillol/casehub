# CaseHub Fase A/B — Classificacao de `|safe` / `autoescape false`

Data: 2026-06-01
Branch: `sec-hardening-on-main`
Base: `main` (`8f2c42b419c9`)
Contexto: continuacao da sessao Claude `3ab34b64-3002-4399-8144-c29064626386` via Bastao/Codex.

## Escopo

Inventario executado no Oracle em `~/casehub-reconcile`:

```bash
grep -RIn --include="*.html" --include="*.jinja" --include="*.j2" --include="*.py" \
  --exclude-dir=.git --exclude-dir=credentials --exclude-dir=node_modules \
  "|safe" .
grep -RIn --include="*.html" --include="*.jinja" --include="*.j2" --include="*.py" \
  --exclude-dir=.git --exclude-dir=credentials --exclude-dir=node_modules \
  "autoescape[[:space:]]*false" .
```

Resultado: 27 hits em 17 arquivos; nenhum `autoescape false` encontrado.

## Classificacao por categoria

### 1. JSON em `<script>` com serializacao segura ou fonte numerica

Status: OK / falso positivo de XSS. Manter `|safe` porque o valor ja chega como JSON literal, nao como HTML.

| Arquivo | Linhas | Valor | Classificacao | Evidencia |
|---|---:|---|---|---|
| `templates/dashboard.html` | 709, 712, 741, 744 | `visa_types`, `visa_counts`, `trend_months`, `trend_counts` com `tojson|safe` | OK | `services/dashboard_metrics.py` monta listas simples/numericas; `tojson` serializa e escapa para JS. |
| `templates/app/tasks/notion_list.html` | 563 | `tasks_json|safe` | OK | `routes/tasks.py:_json_script_safe()` usa `json.dumps(...).replace("<", "\\u003c")`; commit `db82f93` fechou `</script>` breakout. |
| `templates/tasks/notion_list.html` | 566 | `tasks_json|safe` | OK | Mesmo contrato do template `app/`. |
| `templates/app/tasks/calendar_view.html` | 134 | `events_json|safe` | OK | `routes/tasks.py:_json_script_safe(events)`. |
| `templates/tasks/calendar_view.html` | 84 | `events_json|safe` | OK | Mesmo contrato do template `app/`. |
| `templates/billing/dashboard.html` | 321, 322 | `chart_labels`, `chart_values` | OK | `routes/billing.py` usa `json.dumps(monthly_labels/monthly_values)`. Labels sao meses; values numericos. |
| `templates/app/billing/dashboard.html` | 315, 316 | `chart_labels`, `chart_values` | OK | Mesmo contrato do template legado. |
| `templates/letters/generate.html` | 10 | `template.variables|tojson|safe` | OK | Dados serializados via `tojson`; depois tratados como texto/lista. |
| `templates/app/triggers/list.html` | 118 | `cond|tojson|safe` | OK, mas desnecessario | So roda quando `condition_config` e string; o uso posterior espera dict. Nao ha XSS no render porque campos finais usam escape Jinja normal. |
| `templates/triggers/list.html` | 120 | `cond|tojson|safe` | OK, mas desnecessario | Mesmo contrato do template `app/`. |

### 2. HTML estatico ou gerado por renderer local que escapa texto

Status: OK / manter `|safe`.

| Arquivo | Linhas | Valor | Classificacao | Evidencia |
|---|---:|---|---|---|
| `templates/whatsapp/chat.html` | 14, 33, 90 | `wa_logo_svg|safe` | OK | SVG definido no proprio template (`{% set wa_logo_svg %}`), sem input de usuario. |
| `templates/refactor_review/compare.html` | 134 | `brief_html|safe` | OK condicionado a origem git-controlled | `routes/refactor_review.py:_markdown_basic()` escapa texto/codigo antes de inserir tags basicas. Brief vem de arquivo local/archive, nao de usuario final. Nota: links markdown permitem href textual; aceitavel porque origem e interna. |

### 3. Arquivos arquivados / fora do app vivo

Status: nao acionar fix de produto; manter fora do portao Fase A.

| Arquivo | Linhas | Valor | Classificacao |
|---|---:|---|---|
| `templates/_archive/billing-dashboard.html/theme-vs-classic-v1.html` | 156, 157 | `chart_labels`, `chart_values` | Arquivado. |
| `templates/_archive/billing-dashboard.html/2026-04-17-pre-pilot.html` | 257, 258 | `chart_labels`, `chart_values` | Arquivado. |
| `templates/_archive/billing-dashboard.html/theme-vs-classic-v2.html` | 156, 157 | `chart_labels`, `chart_values` | Arquivado. |

### 4. Bug funcional sem evidencia de XSS

Status: nao e achado XSS, mas vale issue/fix pequeno separado se essa rota ainda for usada.

| Arquivo | Linhas | Valor | Classificacao | Motivo |
|---|---:|---|---|---|
| `templates/processes/detail.html` | 147 | `process.visa_types|tojson|safe` em loop | Bug funcional provavel | `routes/processes.py` salva `visa_types` como JSON string. Aplicar `tojson` de novo tende a iterar caracteres da string, nao lista. O `{{ vt }}` ainda escapa normalmente, entao nao e XSS. |
| `templates/app/processes/detail.html` | 145 | `process.visa_types|tojson|safe` em loop | Bug funcional provavel | Mesmo problema do template legado. |

## Conclusao

- Nao ha `autoescape false` no inventario atual.
- Nenhum dos 27 hits exige remocao cega de `|safe`.
- Nenhum XSS real novo foi confirmado nesta classificacao.
- A classificacao reduz os achados de template para: 0 XSS confirmado, 2 bugs funcionais provaveis (`process.visa_types`), 6 hits arquivados, restante OK por JSON/HTML confiavel.

## Proximas acoes

1. Se for corrigir `process.visa_types`, fazer em PR/commit separado com teste da rota `/processes/{id}` e portao A/B, porque e bug funcional, nao hotfix XSS.
2. Iniciar Fase B: baselines pixel/a11y/perf nas rotas-chave do dev, conforme a matriz `docs/REMEDIATION-MATRIX.md`.
3. Manter `audit_log org_id backfill` e endpoints sem auth como SPEC/design, nao auto-aplicar.
