# CaseHub — Matriz de Remediação de Segurança (Fase A)

> Track isolado (branch session-2026-05-30-security-hardening sobre main de hoje). Validação: portão A/B 358-rotas + pytest-diff + boot dev = 0 regressão por fix. Ruling: 2026-05-31-casehub-subsidiary-public-repo.

## ✅ CORRIGIDOS + VALIDADOS nesta Fase A (todos 0-regressão)
| Área | Fix | Commit |
|---|---|---|
| XSS email intake | html.escape(message, client_name) | `89b8462/21696d3` |
| XSS email compose | html_module.escape(body) x2 | `b6313d1/3dc64d5` |
| XSS dashboard | html.escape(str(name)) na saudação | `1e1394d` |
| XSS notificação staff | escape paralegal/client/subject/preview | `1e89208` |
| XSS notificação urgent | escape client/subject/body x2 blocos | `b790c7e` |
| XSS JSON-in-script | _json_script_safe() tasks_json/events_json (</script> breakout) | `db82f93` |
| XSS wiki article | escape render_rich_text + _safe_url (javascript:) | `1561f20` |
| XSS nota de caso | note.content | e antes do @mention (stored XSS) | `cceef0c` |
| Runtime bugs | import os em 7 módulos (NameError) | `e7529212` |
| IDOR org_id | case_archive (subquery) + versions (tenant_query) | `0c82df4c (reconciliado)` |
| Credencial vazada | jayme cred -> env em testes; senha admin fora do log | `72695eed` |

## ⚪ FALSO-POSITIVOS (verificados, sem ação)
- **~29 findings de template `{{var}}`**: Jinja autoescape LIGADO → já escapados.
- **chart_labels/chart_values, events_json (parcial), brief_html**: `|tojson|safe` ou JSON serializado / HTML git-controlled = padrão correto.
- **wa_logo_svg|safe**: SVG estático confiável.
- **IDOR documents.py, doc_templates.py, email_templates_v2 (cases)**: equipe já filtra org_id (Sentinela T3/T4) ou path-traversal já protegido (realpath).
- (auditoria: 222 falso-positivos descartados na verificação adversarial original.)

## 🔶 DEFERIDOS — mudaram de natureza (não safe-by-construction). Abertos restantes por categoria: {'IDOR/Tenant': 62, 'PII/Segredo': 129, 'Bug/Runtime': 5, 'Outro': 78, 'Injeção/Exec': 37, 'Web/XSS/CSRF': 59, 'Auth/Acesso': 11}

### A) Precisam de DESIGN
- **audit_log org_id backfill**: 200 linhas com org_id=NULL; não dá pra atribuir org cegamente. Filtro org_id foi REVERTIDO (quebrava /audit/api/recent). Requer estratégia de derivação de org por linha antes de re-aplicar.

### B) Precisam de VALIDAÇÃO COMPORTAMENTAL (DB/2-org ou teste de auth)
- **Endpoints sem auth** (ex: admin.js, intake-integration.js): adicionar decorator exige confirmar que não quebra fluxo.
- **IDOR em services com file-store/signature-change** (meeting_watchdog, document_watcher, document_classifier, email_processor, templates_service, triggers_service): exigem add org_id param + atualizar callers + validar com 2 orgs. Risco de quebrar caller (lição do deadline.py: caller sem org_id zera a query).

### C) PERIFÉRICOS (não no app principal — vps-monitor/orchestra/sentinela)
- coordinator.py load_activity NameError, smart_healer undefined var, monitor.js innerHTML: serviços de monitoramento, baixo valor pro produto/público.

### D) COLISÃO com sessões ativas (WhatsApp/maestro/marketing) — não tocar

### E) Council-gated (Fase C/D)
- Remoção de segredos do HEAD (já feito p/ test creds; demais via env) + untrack PII = pré-requisito do subsidiário, gated.

## Próximo: Fase B (quality gates)
Baselines pixel-perfect + benchmark de performance em sistema fraco (+ cleanup) + a11y — pedido explícito do Victor. Pré-requisito pro flip do subsidiário.
