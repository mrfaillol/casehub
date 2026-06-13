# CaseHub Basic Integrable Plan Implementation - 2026-05-04

This document is the implementation ledger for the CaseHub Basic plan that uses
the ILC legacy tree as a comparison source while keeping `mrfaillol/casehub-prod`
`main` as the product source of truth.

## Current GitHub State

Verified on 2026-05-04 before this branch was created and rechecked before
publication:

| Item | State |
| --- | --- |
| `mrfaillol/casehub-prod@main` | `b8d0ed4` - `Tighten CaseHub release notice on mobile` |
| `casehub#216` | merged; PDPJ/Google Calendar work is already on `main` |
| `casehub#223` | open draft; tracks Bootstrap modal backdrop error; `halt-guard` and `scope-guard` green; merge state blocked while draft |
| `trabalho-workspace#73` | open draft; MCP curation docs, `scope-guard` green, `claude-review` failing |

Implementation rule: start from a clean branch on `origin/main`; do not use the
dirty local `~/Projects/casehub` checkout for commits.

## Comparative Matrix

| Surface | Main current | ILC legacy reference | Decision |
| --- | --- | --- | --- |
| Product base | `CASEHUB_PRODUCT=lite` default for Basic | `CASEHUB_PRODUCT=immigration` default | Keep `main` as Basic; revive legacy only for audit/reference. |
| Routes | 107 route files | 107 route files | Compare behavior, not route count. |
| Templates | 301 templates | 299 templates | Main has newer Basic UI rescue and mobile shell work. |
| Services | 387 service files | 604 service files | Mine legacy for useful ILC/Google/WhatsApp flows; do not bulk copy. |
| Static assets | 252 files | 107 files | Preserve main assets because they contain Basic rescue/static fixes. |
| Google Calendar | Native OAuth service with read/write scopes | Legacy token import path exists | Keep native OAuth; allow legacy token import only for isolated audit. |
| Google Drive/Gmail | Settings/status surfaced in Basic integrations | Legacy ILC tools have deeper operational scripts | Promote only audited, tenant-safe pieces. |
| CNJ/PDPJ | PDPJ OAuth/client-credentials plus visible fallback chain | Older/current files available for comparison | Keep `ComunicaAPI/PDPJ -> DataJud -> Escavador -> JusBrasil`. |
| Escavador/JusBrasil | Env-gated services and UI status | Present in legacy too | Configure keys only in secure runtime, never Git. |
| MCP | No product runtime dependency yet | Not a legacy feature | Add default-off internal client facade; no CaseHub-as-server. |
| Visual QA | Basic audit script exists | Legacy can be revived as a visual benchmark | Add comparison audit script and pixel-perfect auditor profile. |

## Recovery Priorities

1. Keep Basic commercial flows first: dashboard, Controladoria, calendar, clients,
   tasks, documents/files, and integrations status.
2. Use ILC legacy as a controlled benchmark for working Google/Drive/WhatsApp and
   immigration-era workflow ergonomics.
3. Fix `casehub#207/#223` by validating whether production still serves an older
   unguarded Bootstrap modal initializer; current `main` already guards the
   feedback modal in `templates/base.html`.
4. Treat legal integrations as statusful systems: a failed provider must surface
   a clear reason and fallback status, never silent empty results.
5. Record credential work in `docs/integrations/credential-autonomy-ledger.md`
   without storing or emailing secret values.

## Acceptance Gates

- Existing `/casehub/api/v1` contract guard remains green.
- PDPJ/Controladoria fallback tests remain green.
- MCP facade tests prove default-off, admin-only policy blocking, allowlist
  blocking, private-network blocking, and redaction.
- Visual audit captures main and revived legacy with screenshots, metrics, and
  console/page/network error summaries.
- Production deploy remains blocked by HALT unless a narrow override is logged.

## Authenticated Audit Blocker

Rechecked in this implementation pass on 2026-05-04: the local execution
environment does not expose `CASEHUB_AUDIT_EMAIL`, `CASEHUB_AUDIT_PASSWORD`, or
`CASEHUB_AUDIT_STORAGE_STATE`. The same check found no runtime credential env
for Google Calendar, Google Drive, PDPJ/CNJ, Escavador, or JusBrasil.

Result: authenticated visual and provider validation remains blocked until a
secure audit session, storage-state file, or runtime secret store is available.
This branch must not use Victor's normal browser profile and must not commit or
publish tokens, cookies, OAuth secrets, app passwords, or API keys.

## Visual Smoke Evidence

Unauthenticated comparison audit re-executed on 2026-05-04 after the audit
script gained storage-state support and route-ready synchronization:

```bash
CASEHUB_AUDIT_SKIP_AUTH=1 \
CASEHUB_COMPARISON_BASE_URLS="main=https://dev.vingren.me,legacy=http://127.0.0.1:8017" \
npm run audit:basic-comparison
```

Local report:
`tmp/casehub-basic-comparison/2026-05-04T21-18-33-713Z/report.json`.

| Target | Routes/viewports | Page errors | Console errors | Failed requests | Bad responses | Horizontal overflow |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `main` / `https://dev.vingren.me` | 32 | 0 | 0 | 0 | 0 | 0 |
| `legacy` / `http://127.0.0.1:8017` | 32 | 0 | 4 | 0 | 4 | 0 |

Legacy bad responses were the expected missing current route
`/casehub/integrations` on the revived ILC reference. No real credentials were
used, so this is a render/error smoke, not an authenticated workflow audit.
