# Prompt — Auditoria crítica + limpeza do repo CaseHub

> **Como usar:** abra uma sessão NOVA do Claude Code dentro do repo `mrfaillol/casehub`
> (ou aponte pra `/tmp/casehub-polish`) e cole o bloco abaixo. A sessão é READ-ONLY: ela
> só investiga e entrega um relatório acionável por PRs pequenos — não deleta nada.
> Gerado em 2026-05-29 a partir do workflow de design (`modular-squishing-moon` §5c).

---

```text
Voce e um auditor senior de codigo + seguranca trabalhando em modo READ-ONLY no repositorio privado CaseHub (mrfaillol/casehub, espelhado em /tmp/casehub-polish). NAO edite, crie, mova ou delete NENHUM arquivo. Voce so explora (find/grep/cat/git log) e produz um RELATORIO acionavel. Toda acao destrutiva e proposta para PRs pequenos, nunca executada por voce.

CONTEXTO DO PRODUTO (use para priorizar):
- App FastAPI multiproduto. O produto VIVO e o "lite/alpha" servido em *.casehub.legal. Existem tambem "immigration" e "whitelabel".
- Registry de routers em core/app_factory.py: CORE_ROUTERS (todos), LITE_ROUTERS, IMMIGRATION_ROUTERS, WHITELABEL_ROUTERS, PRODUCT_ROUTERS. Shell ativo de UI = templates/app/base.html (226 templates o estendem); templates/base.html e o shell LEGADO (217 dependentes, em deprecacao).
- Repo: ~40M, ~2.043 arquivos versionados.

SEUS DOIS OBJETIVOS:
(A) MANTER/MELHORAR O QUE ESTA VIVO: decidir, com base no codigo REAL, o que sustenta o produto lite/alpha e como melhora-lo. Priorize o caminho de request do lite (routers em CORE_ROUTERS+LITE_ROUTERS, templates/app/**, static/js/app/**, models/**, middleware/**, core/**).
(B) LIMPAR O REPO: identificar e classificar lixo — credenciais/segredos, PII, logos antigas, codigo morto, scripts orfaos, artefatos versionados, codigo de produtos NAO-lite.

CLASSIFIQUE CADA ARQUIVO RELEVANTE em uma categoria:
- MANTER (vivo no lite/alpha ou dependencia) — justifique com o caminho de uso.
- REFATORAR (vivo mas com divida: inseguro, duplicado) — diga o que muda.
- ARQUIVAR (historico/util fora do caminho ativo) — mover para fora do build, nao deletar.
- DELETAR (lixo claro: backups, duplicatas, one-off fixers, artefatos regeneraveis) — confirme com grep que nada vivo referencia antes de propor.

PISTAS CONCRETAS JA ENCONTRADAS (verifique e expanda):
1. PII/SEGREDO CRITICO VERSIONADO — services/ilc-tools/data/ (84K, tracked): users.json (password_hash bcrypt REAL + is_super_admin), sessions.json (27K, tokens+IPs+user-agents possivelmente vivos), login_attempts.json, email_threads.json, communications.json, communication_clients.json. → Tratar como INCIDENTE. NAO imprimir valores. Propor: untrack + .gitignore + MARCAR para Council decidir purga de historico git e rotacao/invalidacao de sessoes. Se chaves/sessoes ja abandonadas (repo privado), respeitar — so registrar.
2. ESTADO RUNTIME versionado (deveria ser gitignored): leads_crm.json (raiz), services/auto-healer/state.json, services/whatsapp-bot/bot-config.json, services/ilc-tools/data/watchdog_state.json.
3. SCRIPTS ORFAOS/DUPLICADOS em scripts/: compare_vps_drive_with_hash.py vs ..._FIXED.py; fix_calendly.py vs fix_calendly96.py; varios fix_*.py one-off. Determinar o canonico e propor deletar o resto.
4. CODIGO/TEMPLATES LEGADOS: templates/_archive/ (53 arquivos + _versions.json) → ARQUIVAR/DELETAR. templates/base.html (shell legado, 217 dependentes) → mapear quem depende e planejar migracao p/ templates/app/base.html; NAO remover de imediato.
5. WORKFLOWS MORTOS: .github/workflows/deploy.yml.disabled, test.yml.disabled.
6. DOCS pesados/duplicados (docs/, 1.6M, 175 arquivos): transcripts grandes, snapshots INPI duplicados em docs/legal/inpi/*.json, auditorias antigas. → ARQUIVAR.
7. LOGOS/marca: logo/ na raiz (logo.png, logo.svg) vs static/brand-kit/logo/ (18 SVGs casehub). Verificar duplicacao/marca antiga; confirmar referencias em templates/app/** e static/css/** antes de deletar. (FALSO POSITIVO: tools-simples-vs-presumido.css e ferramenta tributaria, NAO logo "VS".)
8. CODIGO DE PRODUTOS NAO-LITE: routers de immigration/whitelabel (uscis*, efiling, packets, shipments, ilc_tools, lor_maker, ps_maker...) — NAO sao lixo, mas NAO sao prioridade do alpha. MANTER-mas-fora-do-foco; sinalizar se carregam PII (item 1).
9. SEGREDOS HARDCODED: grep amplo por AIzaSy, sk-[A-Za-z0-9]{20,}, ghp_, github_pat_, AKIA, -----BEGIN .* PRIVATE KEY-----, e password|secret|token|api_key com valor literal. (No survey inicial NAO foram achadas chaves vivas em arquivos tracked — so exemplos em docs/API_KEY_ROTATION_GUIDE.md e blocklists; confirme e amplie.) demo/demo_config.env tem SECRET_KEY placeholder seguro.

TRATAMENTO DE SEGREDOS (regras rigidas):
- NUNCA cole valores de segredo/PII no relatorio. Refira por caminho + tipo.
- NUNCA proponha commitar segredo. Para credencial/sessao/PII versionada: propor untrack + .gitignore; purga de HISTORICO git e rotacao = Council.
- Respeitar a decisao do dono sobre chaves abandonadas (repo privado): registre, nao force rotacao.

RED LINES (NAO faca / escale ao Council):
- NAO quebrar o que esta no ar (lite/alpha). Antes de classificar DELETAR/REFATORAR, prove com grep que nenhum router ativo, templates/app/** ou static/js/app/** referencia.
- Deploy-topology, infra/cron, purga de historico git, rotacao de segredos → Council.
- NAO editar arquivos. So relatorio.

METODO (read-only):
1. Mapear o VIVO: ler core/app_factory.py (PRODUCT_ROUTERS, LITE_ROUTERS, CORE_ROUTERS); cruzar com templates/app/** e static/js/app/**.
2. Varrer por tipo de lixo (find *.json/*.bak/*.disabled, git ls-files do que nao devia, grep de segredos).
3. Para cada candidato, grep de referencias antes de classificar.
4. Produzir o relatorio.

FORMATO DO RELATORIO (responda em texto, NAO escreva arquivo):
- Resumo executivo (3-6 linhas): saude do repo, achados criticos (PII), tamanho do esforco.
- Tabela: caminho | categoria | motivo (1 linha) | refs (sim/nao) | risco.
- Secao SEGREDOS/PII: por caminho+tipo, acao proposta, flag Council.
- Plano de PRs PEQUENOS independentes (1 tema/PR): "PR1 untrack PII ilc-tools/data", "PR2 deletar scripts fix_* orfaos", "PR3 arquivar templates/_archive", "PR4 gitignore estado runtime"... cada um com arquivos + verificacao.
- RED LINES tocadas + o que vai ao Council.
- Itens incertos (precisam confirmacao do dono).
Priorize sempre o VIVO no lite/alpha. Comece pelo passo 1.
```
