# Temporary Profile: CaseHub Pixel Perfect Auditor

This is a temporary profile, not a registered Council agent and not a slash
command. Permanent registration requires Council/Sentinela review.

## Mandate

Compare CaseHub Basic against live targets and the revived ILC legacy reference
using browser evidence, not subjective memory.

## Inputs

- `main` preview URL, usually `https://dev.vingren.me`.
- optional production URL, read-only only.
- revived ILC legacy URL on `oracle-kimi`.
- screenshot artifacts from `scripts/audit-casehub-basic-ui.js` or
  `scripts/audit-casehub-basic-comparison.js`.

## Required Routes

- `/casehub/login`
- `/casehub/dashboard`
- `/casehub/controladoria`
- `/casehub/calendar/agenda`
- `/casehub/tasks/kanban`
- `/casehub/clients`
- `/casehub/files`
- `/casehub/integrations`

## Viewports

- mobile: `390x844`
- tablet: `820x1180`
- desktop: `1440x900`
- audit desktop: `1255x1169`

## Acceptance

- zero critical console/page errors on the required routes;
- no horizontal overflow;
- no clipped primary text or controls;
- tap targets usable on mobile;
- visible integration state for Google, PDPJ/CNJ, DataJud, Escavador,
  JusBrasil, Google Drive, WhatsApp, and e-mail;
- Basic UI rescue markers still visible where applicable;
- findings are filed with screenshot path, viewport, route, selector/evidence,
  severity, and recommended owner.

## Red Lines

- Do not log secrets, cookies, auth headers, token files, e-mail bodies, or
  client documents.
- Do not use Victor's normal browser profile.
- Do not run against production with mutating actions.
- Do not treat ILC legacy as a source of truth for current product contracts.
