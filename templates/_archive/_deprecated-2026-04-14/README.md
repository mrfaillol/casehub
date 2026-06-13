# Arquivados em 2026-04-14

Triagem automática (workspace-janitor) + validação por grep (zero refs).

- **portal-templates/** — 11 arquivos, fóssil do split `services/client-intake/` em 30/Mar/2026. `routes/portal.py` é admin API staff-facing; portal cliente roda em outro serviço.
- **misc/test_template.html** — teste manual, sem rota.
- **misc/index.html** — landing legacy pré-dashboard.
- **investigar/portal_access_link.html** — email transacional sem sender; considerar re-integrar em `routes/portal.py:50-96` que tem HTML inline.
- **investigar/first_login.html** — WIP onboarding, mtime 09/Abr/2026, nenhuma rota referencia.
- **investigar/whatsapp/embedded.html** — widget embed possivelmente planejado.

**Restaurar:** `git mv _archive/_deprecated-2026-04-14/<path> <original-path>` + restart container.

**Origem da triagem:** `/Users/beijaflor/Projects/casehub/docs/reestruturacao/orfaos-triagem.md`
