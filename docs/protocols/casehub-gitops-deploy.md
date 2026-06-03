# CaseHub GitOps Deploy Protocol

**Status:** Proposto via ruling `2026-04-24-casehub-gitops-deploy` (APPROVED_WITH_CONDITIONS, 3/3 vetos + 1 voice; zero vetos).
**Versão:** 0.1 (Fase 0 — implementação manual antes do soft-launch do army).
**Supersedes:** N/A — complementa (não substitui) `docs/protocols/casehub-git-rsync-topology.md` (workspace).
**Revisão obrigatória:** 2026-06-24 (60 dias após primeiro deploy estável — sunset do escape-hatch rsync).

> **HALT ativo desde 2026-05-02:** `docs/security/deploy-halt.json` bloqueia deploys de producao enquanto `active=true`. Issue canonica: https://github.com/mrfaillol/casehub/issues/188. Overrides exigem link dessa issue e motivo auditavel.

---

## Objetivo

Substituir deploy manual Mac→VPS (rsync via `scripts/deploy-casehub-prod.sh` em trabalho-workspace) por GitOps: merge em `main` triggera GitHub Actions → SSH ao VPS → `git pull --ff-only` + `docker compose restart` + health check + rollback automático.

**Não objetivo:** substituir `rsync` como transporte de arquivos em geral. Só o fluxo de deploy de código versionado. Secrets (`.env`), credenciais SSH, dumps DB continuam fora do git.

---

## Arquitetura

```
Victor                     GitHub                              Hostinger VPS
------                     ------                              ------------
git push      ─────▶  branch protection
PR review                  │
mergeia main  ─────▶  push:main trigger
                           │
                           ▼
                    Actions workflow
                      1. preflight:
                         - oxlint
                         - gitleaks (diff)
                         - trivy (image HIGH)
                         - SSH → backup check (<24h)
                      2. deploy:
                         - SSH deploy@vps "vps-deploy <sha>"
                             │
                             ▼
                           authorized_keys command=
                           → vps-deploy-wrapper.sh
                           → scripts/vps-deploy.sh <sha>
                             1. lock file
                             2. working tree limpa?
                             3. .previous-sha ← HEAD
                             4. git pull --ff-only
                             5. .deploy-sha ← target
                             6. docker compose restart
                             7. health (TLS + 200 + TTFB<2s + content marker) × 3
                             8. rollback se fail + blocklist check
                      3. notify:
                         - success: :notice:
                         - failure: SMTP → victor@example.com
```

---

## Arquivos desta implementação

### No repo `mrfaillol/casehub`

| Path | Função |
|---|---|
| [docs/templates/deploy-prod.yml.template](../templates/deploy-prod.yml.template) | Orquestra preflight → deploy → notify. Pin SHAs. **Nota:** vive em `docs/templates/` ao invés de `.github/workflows/` até Victor gerar PAT com `workflow` scope; então copiar para `.github/workflows/deploy-prod.yml` em PR separado. |
| [scripts/vps-deploy.sh](../scripts/vps-deploy.sh) | Executado no VPS (como `deploy`) para cada push. Rollback automático. |
| [scripts/vps-bootstrap.sh](../scripts/vps-bootstrap.sh) | Setup único no VPS: user `deploy` + sudoers + audit log. |
| [docs/protocols/casehub-gitops-deploy.md](casehub-gitops-deploy.md) | Este protocolo. |
| [docs/security/deploy-halt.json](../security/deploy-halt.json) | Flag versionada de HALT de producao/performance; `active=true` bloqueia deploy prod sem override. |
| [docs/security/sha-blocklist.txt](../security/sha-blocklist.txt) | Lista de SHAs com CVE conhecido; aborta rollback. Append-only. |
| `docs/deploy-log/prod/YYYY-MM-DD-<sha>.md` | Log por deploy (≤200 linhas T1, rotação 90d). |

### No repo `mrfaillol/trabalho-workspace` (separado — PR distinto)

| Path | Mudança |
|---|---|
| `scripts/deploy-casehub-prod.sh` | Header warn: use GitHub merge; só invocar com `DEPLOY_ESCAPE_REASON=`. |
| `docs/protocols/casehub-git-rsync-topology.md` | Matriz de 4 working trees atualizada (J4). |

---

## Threat model — 28 conditions cobertas

### Security (sentinela — 12 conditions)

| # | Condition | Implementação |
|---|---|---|
| S1 | Pin actions por SHA + Dependabot | `deploy-prod.yml` usa `@<40-char-sha>` em todas. Dependabot habilitar manual em Settings. |
| S2 | Allowlist de marketplace fechada | Manual: Settings > Actions > "Allow owner + select non-owner". Lista permitida: actions/checkout, actions/setup-node, gitleaks/gitleaks-action, aquasecurity/trivy-action, dawidd6/action-send-mail. |
| S3 | Deploy key ed25519 dedicada | Gerada offline por Victor. Registrada como deploy-key read-only em Settings > Deploy keys. Private key em GitHub Secret `HOSTINGER_DEPLOY_SSH_KEY`. Rotação 90d (doc renovation ruling em 2026-07-23). |
| S4 | User `deploy` + sudoers literal | `vps-bootstrap.sh` cria user, escreve `/etc/sudoers.d/casehub-deploy` sem wildcards, authorized_keys com `command=` forçando wrapper. |
| S5 | Workflow permissions + masking + pipefail | `permissions: contents: read`; `set -euo pipefail` em todos steps bash; nunca `set -x` em step com secret. |
| S6 | Branch protection main | Manual: required PR review ≥1, required status checks (preflight job), dismiss stale, signed commits, linear history. |
| S7 | Rollback blocklist | `docs/security/sha-blocklist.txt`; `vps-deploy.sh` consulta antes de revert; exit 2 + page se SHA em blocklist. |
| S8 | Preflight: trivy + backup + gitleaks | Job `preflight` no workflow antes de deploy. |
| S9 | Audit log append-only no VPS + logrotate | `vps-bootstrap.sh` cria `/var/log/casehub-deploy.log` com `chattr +a`. Logrotate mensal × 3 ciclos. |
| S10 | Health check TLS + 200 + content marker | `vps-deploy.sh` usa `curl -sS --max-time 5` + `grep CONTENT_MARKER` + TLS via https (cert validado por curl). |
| S11 | Escape-hatch rsync requer `DEPLOY_ESCAPE_REASON=` | Header warn em `deploy-casehub-prod.sh` (workspace PR). Remoção em 2026-06-24. |
| S12 | Dry-run em staging antes de habilitar trigger em main | Primeiro deploy será `workflow_dispatch` apontando para branch staging. Só depois habilitar `push:branches:[main]`. |

### Hygiene (workspace-janitor — 7 conditions)

| # | Condition | Implementação |
|---|---|---|
| J1 | Nenhum path absoluto hardcoded em YAML | `env:` do workflow + `vars.VPS_HOST`, `secrets.*`. |
| J2 | Preflight: working tree limpa no VPS | `vps-deploy.sh` step 1: `git status --porcelain` → abort se dirty. |
| J3 | deploy-casehub-prod.sh não órfão | Header warn + referência em AGENTS.md (a atualizar em workspace PR). |
| J4 | Atualizar matriz 4 working trees em `casehub-git-rsync-topology.md` | Workspace PR. |
| J5 | Artefatos auditoria `.deploy-sha` + `.deploy-timestamp` + `.deploy-actor` | `vps-deploy.sh` step 4. |
| J6 | Rollback via `git checkout`, não `reset --hard` | `vps-deploy.sh` step 7. |
| J7 | `.repos/casehub/` não usado por deploy | Comentário em `work-on.sh` / `push-repo.sh` (workspace PR). |

### Token economy (4 conditions)

| # | Condition | Implementação |
|---|---|---|
| T1 | Deploy log ≤200 linhas + rotação 90d | Workflow deploy step usa `tail -200`; arquivo `docs/deploy-log/prod/_archive/` gerado por script mensal (a criar). |
| T2 | Decisão só em decisions.md + csv + protocolo | Commit do ruling + este protocolo. Sem entrada nova em MEMORY.md. |
| T3 | Health check output truncado | `tail -200` no step de deploy; stderr completo em artifact, não commit. |
| T4 | Fase 2 com Claude CLI exige ruling separado | Registrado como Fase 2 do plano no ruling. |

### Science (5 conditions, voice)

| # | Condition | Implementação |
|---|---|---|
| E1 | Baseline 10 runs restart antes de enable | `docs/deploy-log/prod/baseline-restart-<sha>.md` com p50/p95. Gerado por script `scripts/baseline-restart.sh` (a criar). |
| E2 | Health em `/casehub/healthz` com TTFB<2s | `vps-deploy.sh` valida `$ttfb < 2.0` via awk. Rota `/casehub/healthz` a implementar em Flask (PR separado em routes/). |
| E3 | SLO 20s p99 por deploy (worst case 2× restart) | Documentado em `docs/deploy-log/prod/SLO.md` (a criar). |
| E4 | Issue auto se p95 > baseline +50% por 3 deploys | Script `scripts/check-deploy-drift.sh` (a criar, Fase 2). |
| E5 | Assets estáticos continuam gate pipeline-polish | Workflow NÃO toca `static/**/*.{css,js}` diretamente — PRs que mudam estáticos precisam do gate separado. |

---

## Fluxo operacional (runbook)

### Primeiro deploy (dry-run staging)

1. Victor: gerar ed25519 offline (`ssh-keygen -t ed25519 -C "casehub-prod-deploy-2026-04-24" -f ~/tmp/casehub-deploy.key`).
2. Victor: adicionar public key como Deploy Key (read-only) em `Settings > Deploy keys` do repo.
3. Victor: adicionar private key como Secret `HOSTINGER_DEPLOY_SSH_KEY`.
4. Victor: adicionar Variable `VPS_HOST` (ex: `REDACTED-HOST`).
5. Victor: configurar `Environments > production` com required reviewer = victor@example.com.
6. Victor: provisionar staging replica (pode ser subdomain `staging-app.example.com` em Oracle free-tier).
7. SSH root@staging: `curl -sS <url-bootstrap> | sudo bash` ou rodar `vps-bootstrap.sh` manual.
8. Colar public key em `/home/deploy/.ssh/authorized_keys` com `command="/app/scripts/vps-deploy-wrapper.sh"`.
9. Testar SSH: `ssh -i <privkey> deploy@staging "vps-deploy $(git rev-parse HEAD)"` — valida wrapper + sudoers + deploy full chain.
10. Baseline: rodar `scripts/baseline-restart.sh` 10×, commitar output em `docs/deploy-log/prod/baseline-restart-<sha>.md`.
11. Workflow dispatch apontando para staging; validar todos os steps.
12. Só após sucesso em staging: repetir (1)-(10) em VS-prod + habilitar trigger `push:main`.

### Deploy rotineiro (pós Fase 0 estável)

1. Feature em branch `feat/*` — oxlint local (`npm run lint`).
2. PR para `main`.
3. Required checks passam (preflight job).
4. Review ≥1 approver.
5. Merge → workflow dispara automaticamente.
6. Victor recebe notification se falhar.

### Rollback manual (se blocklist bloqueou rollback auto)

```bash
ssh root@REDACTED-HOST
cd /app
git log --oneline -5                          # identificar SHA seguro
git checkout <sha-seguro>
docker compose -f docker-compose.yml restart
curl -sS https://cliente.example.com/casehub/healthz
echo "manual-rollback $(date -u +%FT%TZ) by $(whoami)" >> /var/log/casehub-deploy.log
```

Documentar incidente em `journals/archive/YYYY-MM-DD-rollback-<sha>.md` + abrir ruling `/council` post-facto em 48h.

---

## Limitações conhecidas (Fase 0)

1. **Single VPS** — sem blue/green nem canary. Downtime 3-8s por restart é aceitável para volume atual (1 cliente, baixo tráfego). Revisar se adicionar 3º+ cliente.
2. **Sem rate limit no health check** — atacante pode DoS via request a `/casehub/healthz`. Mitigar com nginx `limit_req` em PR separado.
3. **GitHub IP allowlist manual** — condition S4 exige `from=` em authorized_keys; lista muda dinamicamente. Script `sync-github-ips.sh` (1×/dia) a criar na Fase 1.
4. **Escape-hatch rsync ainda existe** — sunset 2026-06-24 (60d após Fase 0 estável).
5. **Blocklist SHA vazia inicialmente** — popula com SHAs que o sentinela flagar ao longo do tempo. Processo: finding sentinela → PR adicionando SHA → merge → commit visível no histórico.

---

## Fases subsequentes (ver ruling)

- **Fase 1 (10-24/Mai):** GitOps estável + army em soft-launch de template-refactor. Army não toca deploy.
- **Fase 2 (pós-24/Mai, condicional):** ruling `expand-army-scope-to-ops` — army vira operador de emergency-revert.
- **Fase 3 (pós-24/Jun):** army como primary operator; humano só aprova PR merge.

---

## Revisão

- **Deadline:** 2026-06-24 (60 dias após primeiro deploy estável).
- **Trigger automático:** script `scripts/check-reviews.sh` do workspace deve marcar este protocolo como REVIEW DUE em 2026-06-24 via entrada em `memory/decisions.csv`.
- **Escopo da revisão:** (a) escape-hatch rsync sunset?, (b) blocklist tem entries?, (c) baseline restart estável?, (d) Fase 2 army pronta?
