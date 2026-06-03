# Credential Autonomy Ledger

This ledger records credential work without storing secret values. It exists so
autonomous setup can be audited and safely summarized by e-mail.

## Rules

- Never commit or e-mail raw tokens, client secrets, refresh tokens, JWTs,
  cookies, private keys, app passwords, or API keys.
- Record only provider, environment, credential name, scope, secure storage
  location, validation result, and blocker state.
- If a provider requires payment, a contract, CNJ approval, or unavailable 2FA,
  stop and record the blocker instead of improvising.
- Google Calendar uses OAuth scopes. Gmail app passwords are only for SMTP/IMAP,
  not Calendar API event writes.

## Providers

| Provider | Required for Basic | Secret name / storage ref | Validation proof | Current state |
| --- | --- | --- | --- | --- |
| Google Calendar | read/write agenda sync | `GOOGLE_CALENDAR_CREDENTIALS_PATH`, token files under secure runtime credentials dir | list calendars, create/update/delete test event with `sendUpdates=none` | pending runtime validation |
| Google Drive | document export/files | `GOOGLE_DRIVE_CREDENTIALS_PATH`, `GOOGLE_DRIVE_TOKEN_PATH`, `GOOGLE_DRIVE_ROOT_ID` | create/read test folder or list root folder | pending runtime validation |
| Gmail SMTP/IMAP | e-mail send/read where authorized | `SMTP_PASS` or `GMAIL_CENTER_APP_PASSWORD` in runtime secret store | SMTP test send or IMAP readonly search | pending runtime validation |
| PDPJ/CNJ | official communications/deadlines | `PDPJ_CLIENT_ID`, `PDPJ_CLIENT_SECRET`, optional org refresh token | token probe and Controladoria OAB search | blocked if CNJ returns `invalid_client` |
| DataJud | fallback CNJ process lookup | optional `DATAJUD_API_KEY` | process/OAB fallback query | available as fallback, not official import |
| Escavador | publications/process support | `ESCAVADOR_API_KEY` | non-sensitive search probe | pending account/key |
| JusBrasil | publications/process support | `JUSBRASIL_API_KEY` | non-sensitive search probe | pending account/key |
| MCP gateway/client | future admin tooling | secret refs only, no raw values | fake server discovery/invocation tests | default-off prototype only |

## Current Blocker - 2026-05-04

Local PR maturation pass found no safe audit/provider credentials in the
environment: `CASEHUB_AUDIT_EMAIL`, `CASEHUB_AUDIT_PASSWORD`,
`CASEHUB_AUDIT_STORAGE_STATE`, `GOOGLE_CALENDAR_CREDENTIALS_PATH`,
`GOOGLE_DRIVE_CREDENTIALS_PATH`, `PDPJ_CLIENT_ID`, `PDPJ_CLIENT_SECRET`,
`ESCAVADOR_API_KEY`, and `JUSBRASIL_API_KEY` were all unavailable.

Authenticated visual audit and provider setup should resume only after a secure
runtime session or secret reference is available. If a provider requires 2FA,
CNJ portal approval, contract activation, or payment, stop at a checklist and do
not improvise with personal browser profiles or raw secrets.

## Entry Template

```text
date:
operator:
provider:
environment:
credential ref:
scope:
where stored:
validation command:
validation result:
blockers:
email-safe summary:
```
