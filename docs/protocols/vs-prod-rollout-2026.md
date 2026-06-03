# VS-prod rollout 2026 — playbook de deploy seguro

> **Banner docs-only.** Este documento é um **plano de deploy**, não um script executável. **Nenhum comando real foi rodado durante a redação.** Execução real exige (1) Council ruling autorizando o rollout, (2) Sentinela approval pós-revisão, (3) confirmação explícita `YES-DEPLOY-PROD-<SHA>` do Victor no terminal, (4) backup DB <24h e backup uploads conforme `scripts/deploy-casehub-prod.sh`. Red lines do `AGENTS.md` se aplicam.

**Snapshot baseline 2026-05-18:**
- `mrfaillol/casehub` `main` = `e36f414b2beea5417abbed7240ffe2ec81cef742` (`fix(login): remove Basic language switch (#498)`)
- VS-prod último `.deploy-sha` registrado: `38cf102788c2eec03d87a6aedaead427965bafef` (2026-05-14)
- Dev `https://app.example.com/casehub/healthz` = mesmo SHA do main, status healthy
- **Deploy gap aberto:** main avançou 5 PRs além de prod (#487, #494, #496, #497, #498)

---

## 1. Diff entre `38cf102` e `e36f414b`

PRs mergeados no intervalo (verificar via `gh pr list --state merged --search "merged:2026-05-14..2026-05-18"`):

| PR | Tema | Risco para prod |
|---|---|---|
| `#487` | Google Calendar consent/neutral mode | Médio — adiciona env vars `GOOGLE_CALENDAR_EVENT_DETAIL_MODE`/`_LANG`. Default-off para tenant prod sem secret OAuth. |
| `#494` | Detail page spacing | Baixo — CSS/template only |
| `#496` | Favicon leaf fallback | Baixo — assets only |
| `#497` | Mobile login + favicons | Baixo — UI mobile |
| `#498` | Remove Basic language switch | Baixo — UI Basic |

**Não há migrations DB neste intervalo** (validar via `git diff 38cf102..e36f414b -- migrations/` antes do rollout).

---

## 2. Pré-flight obrigatório (ordem rígida)

```
[ ] 1. Ruling Council autorizando deploy explicitamente
[ ] 2. Sentinela approval (security review do diff)
[ ] 3. Working tree casehub limpo + sincronizado com origin (scripts/deploy-casehub-prod.sh:pre-flight aborta se sujo)
[ ] 4. Backup DB < 24h (script abortar se mais antigo)
[ ] 5. Backup uploads < 24h
[ ] 6. Branch atual = main (script aborta se outra)
[ ] 7. SHA pushado para origin (script aborta se local diverge)
[ ] 8. Notificação para [parceiro] (sócio) — janela de deploy
[ ] 9. dev healthz green no SHA alvo
[ ] 10. Confirmação `YES-DEPLOY-PROD-<SHA>` digitada pelo Victor
```

Bypass de qualquer item exige ruling separado **antes** do deploy. Não há flag `SKIP_PROD_GIT_PREFLIGHT` em VS-prod (apenas em dev).

---

## 3. Janela operacional

| Critério | Recomendação |
|---|---|
| Dia | Terça/Quarta — evita seg (segunda o cliente), evita sex (rollback no fim de semana) |
| Horário | 14h00–16h00 BRT — fora de pico, com expediente VS ativo para feedback imediato |
| Não deploy | Véspera de feriado; primeira semana do mês (folha); durante incidente ativo em qualquer repo |
| Comunicação prévia | Aviso a [parceiro] com ≥2h de antecedência via Signal/Threema |

---

## 4. Smoke pós-deploy (mínimo)

Em ordem, dentro de 5min do deploy:

1. **Healthz:** `curl -fsS https://cliente.example.com/casehub/healthz` → `status=healthy, commit=<SHA alvo>, db=true, templates=true`.
2. **Login:** acessar `/casehub/login`, autenticar com conta de teste (sem dados VS reais — usar conta `qa-prod@example.com` ou similar).
3. **Dashboard:** carregar `/casehub/dashboard`, conferir métricas, ausência de erro no console.
4. **5 rotas FASE 1:**
   - `/casehub/controladoria/dashboard`
   - `/casehub/calendar`
   - `/casehub/tasks/kanban`
   - `/casehub/clients`
   - `/casehub/cases`
   Cada uma deve retornar 200 OK ou 302 (auth redirect esperado).
5. **Logs:** `docker compose logs --tail=200 casehub | grep -iE "ERROR|Traceback|500"` → zero hits relacionados ao deploy.

Se qualquer item falhar → rollback imediato (seção 6).

---

## 5. Smoke estendido (24h pós-deploy)

| Janela | Verificação |
|---|---|
| T+15min | Monitorar erro 5xx em `/var/log/nginx/access.log` (taxa <1%) |
| T+1h | Performance Guardian baseline comparison (sem regressão p95 >5%) |
| T+4h | Confirmar com o cliente ([parceiro] contata) — uso normal? |
| T+24h | Re-rodar smoke mínimo; checar disk usage container + DB |

---

## 6. Rollback path

**Critério para rollback:** qualquer item do smoke mínimo falha OU erro 5xx >5% em janela 5min OU report explícito do o cliente de quebra.

### 6.1. Rollback Docker (preferido)

```
# VS-prod:
# Confirmar no preflight. Preferir usuário/diretório dedicado; não assumir /root.
CASEHUB_DEPLOY_DIR="${CASEHUB_DEPLOY_DIR:-/opt/casehub}"
cd "$CASEHUB_DEPLOY_DIR"
# Reverter para SHA anterior gravado em .deploy-sha.backup (script grava antes de cada deploy)
PREV_SHA=$(cat .deploy-sha.backup)
git fetch --quiet
git checkout $PREV_SHA
docker compose -f docker-compose.yml up -d --build casehub
```

### 6.2. Rollback DB (se migration aplicada)

**Cenário não esperado neste diff** (sem migrations), mas documentado por completude:

```
# Restaurar backup pre-deploy:
pg_restore -d casehub -c /root/backups/casehub-pre-<SHA>.dump
```

Conferir com Victor antes de rodar restore — perda de dados criados pós-deploy.

### 6.3. Comunicação pós-rollback

- Comment em PR/issue master explicando o que falhou (SHA, sintoma, log relevante).
- Issue criada se a falha exigir fix em código (`bug` + `urgent` labels).
- Notificar [parceiro] — minimizar impacto VS.

---

## 7. Pós-deploy bem-sucedido

```
[ ] Atualizar tasks.md (issue `#347` PAO master gate ganha checkmark de "Prod gate")
[ ] Comment em `#347` com SHA + ambiente + smoke evidence
[ ] Atualizar `docs/deploy-log/prod/2026-MM-DD-<SHA>.md` (auto-gerado pelo script + complemento manual de notas)
[ ] Memory `decisions.md` registra o deploy
[ ] Performance Guardian baseline atualizada
[ ] Notificar [parceiro] do sucesso
```

---

## 8. O que este rollout **não** cobre

- Ativação Google OAuth prod (`#478`) — exige seu próprio runbook (`docs/integrations/google-calendar-activation.md`) e Sentinela review separado.
- Mudança em branch protection rules — não tocar.
- Mudança em runner topology — issue `#480` separada.
- Alteração de schema DB sem migration testada — proibido.
- Deploy de instância demo `casehub.legalopsco.work` — issue `#414` separada.

---

## 9. Pegadinhas conhecidas

1. **Container non-root chmod**: bind-mount `./credentials:/app/credentials` exige `chown 1000:1000` após scp (feedback memory `rsync_perms`). Verificar antes de declarar deploy completo se algum secret novo foi plantado.
2. **`.deploy-sha` vs `.deploy-sha.backup`**: o script já grava ambos. Não tocar manualmente.
3. **PR #487 traz env vars novos**: `GOOGLE_CALENDAR_EVENT_DETAIL_MODE` e `GOOGLE_CALENDAR_EVENT_LANG`. Sem secret OAuth plantado, são no-ops. Confirmar `.env` em VS-prod não contém valores reais — defaults aplicam.
4. **Static assets manifest**: se `static/assets/dashboard-manifest.json` mudou, container precisa rebuild (não só restart). Script já faz `--build`.
5. **HALT `#134`**: confirmar status não-conflito antes de deploy (HALT é sentinel; deploy normal não conflita, mas validar via `gh issue view 134`).

---

## 10. Refs

- `scripts/deploy-casehub-prod.sh` — script canônico (preflight + deploy + log).
- `docs/protocols/casehub-git-rsync-topology.md` — ruling 2026-04-24.
- `docs/vps-hostinger-playbook.md` — playbook operacional Hostinger.
- `agents/knowledge/council/principles.md` — quando convocar Council.
- `agents/sentinela.md` — gatilhos de security review.

— Plano drafted by Claude Opus 4.7 @mac, 2026-05-18, em sessão handoff `docs/handoff/claude-code-2026-05-18-alpha-closeout/90-vs-prod-rollout.md`. **Sem execução real durante a redação.**
