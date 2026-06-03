# CaseHub MCP Integrations Handoff

Date: 2026-05-03

This note is a sanitized handoff for evaluating MCP/connector usage around CaseHub integrations. It intentionally contains no tokens, secrets, raw e-mails, or client evidence.

## Current Context

PR `#216` (`fix/pdpj-gcal-controladoria`) is the active functional PR for:

- PDPJ/ComunicaAPI explicit failure states and admin diagnostics.
- Google Calendar read/write sync through the native Google Calendar API.
- `appointments.gcal_event_id` as the event reconciliation field.

## Recommended Boundary

MCP is viable for CaseHub, but it should be split into three different roles:

1. **Operational test bench**: use MCP connectors during engineering sessions to validate account access, event CRUD, files, e-mails, GitHub status, and other external systems.
2. **CaseHub-owned gateway**: if MCP-adjacent capabilities become a product layer, run a CaseHub-owned integration gateway with auth, audit logs, sanitization, idempotency, and tenant policy.
3. **Native app integration**: keep core recurring product flows on official provider APIs inside CaseHub, especially Google Calendar and PDPJ/ComunicaAPI.

The CaseHub runtime should not depend on a Codex operator MCP session.

## Google Calendar

Use OAuth, not app passwords. Google app passwords are not a viable Calendar API write mechanism.

The production UX should remain:

- Connect Google Calendar from the CaseHub settings screen.
- Request read and write event scopes.
- Prefer one default account (`center`, then `info` only as fallback if configured).
- Show clear states: connected, reconnect required, missing client secret, missing token, and real redirect URI.
- Keep local appointments as the source of truth.
- Treat Google sync as best-effort and show operation warnings without dropping the local appointment.

## Candidate MCP/Gateway Integrations

- Google Calendar: create/update/delete/read event validation and future sidecar gateway.
- Gmail: read operational threads only with explicit permission; never publish raw e-mails or secrets.
- Google Drive: export and attach generated documents and sanitized evidence bundles.
- Notion: publish sanitized handoffs, requirements, and decision records.
- GitHub: create issues from real bugs and update PRs with sanitized diagnostics.
- PDPJ/ComunicaAPI/DataJud/Escavador/JusBrasil: keep native integration first; consider gateway wrappers only after the current production path is stable.
- WhatsApp/intake: future candidate requiring LGPD, opt-in, and attachment controls.

## Future Gateway Shape

Proposed service name: `casehub-integrations-gateway`.

Current v0 foundation: `services/integrations_gateway/` and
`docs/integrations/casehub-integrations-gateway.md`. This foundation is
default-off and contains no live provider calls.

Expected responsibilities:

- Store provider credentials outside Git.
- Expose sanitized provider status.
- Enforce tenant/account policy.
- Implement idempotency keys for write operations.
- Keep audit logs without sensitive bodies.
- Support retries through an outbox/queue.
- Accept only authenticated calls from the CaseHub app.

Initial internal contracts could include:

- `GET /integrations/google-calendar/status`
- `POST /integrations/google-calendar/events`
- `PATCH /integrations/google-calendar/events/{id}`
- `DELETE /integrations/google-calendar/events/{id}`
- `POST /integrations/gmail/search`
- `POST /integrations/google-drive/export`
- `POST /integrations/notion/create-page`
- `GET /integrations/github/pr-status`

## Red Lines

- Do not commit or print real tokens, client secrets, raw e-mails, or client screenshots.
- Do not use a Codex MCP session as a production dependency.
- Do not silently convert integration failures into empty results.
- Do not invite clients to Google Calendar events automatically in this version.
- Do not deploy to production without backup and dev validation.
