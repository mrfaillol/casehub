# CaseHub Integrations Gateway

Status: v0 foundation, default-off. This is a CaseHub-owned boundary for future
Google Workspace and MCP-adjacent integrations. It is not a production
activation runbook.

## Direction

CaseHub should not depend on a Codex operator session or local MCP runtime for
product behavior. The product path is:

1. Keep core recurring flows on native provider APIs where they already exist.
2. Use MCP/connectors as engineering test bench and discovery.
3. Promote stable integration capabilities into a CaseHub-owned gateway with
   tenant policy, audit-safe status, idempotency, and runtime credential refs.

The implemented slice lives in `services/integrations_gateway/` plus the
admin-only status route `routes/integrations_gateway.py`. It has a synthetic
execution path and an env-backed credential-ref resolver, but no provider SDK
and no live provider call. Activation (a real credential, an enabled provider,
a live call) is a separate, Council-gated slice.

## Providers

The v0 registry declares these disabled providers:

| Provider | Planned read operations | Planned mutating operations |
|---|---|---|
| `google-calendar` | `status.read`, `events.read` | `events.create`, `events.update`, `events.delete` |
| `gmail` | `threads.search`, `threads.read` | none |
| `google-drive` | `files.search`, `files.read` | `evidence.export` |

Google Calendar production activation remains blocked on #289. The gateway must
not replace the existing native OAuth service until runtime credentials and
tenant policy are provisioned outside Git.

## Safety Contract

- Providers are disabled by default.
- Enabled providers remain admin-only unless explicitly changed.
- Every operation must be allowlisted.
- Mutating operations require an idempotency key.
- Provider status hides credential refs and redacts sensitive error payloads.
- No raw provider response should be stored in GitHub issues, docs, or logs.

## Shipped (gateway v0.1, 2026-05-21)

- Admin-only sanitized status route: `GET {PREFIX}/integrations/gateway/status`
  (`routes/integrations_gateway.py`). Reports disabled providers; never returns
  credential refs or secret values; writes a body-free audit row
  (`gateway.status.read`).
- Runtime credential-ref resolver (`credentials.py`): `<backend>:<name>` refs,
  with env-backed and null backends — secrets stay out of Git. A richer backend
  (OS keychain, file mount, external secret manager) changes secret topology
  and is Council-gated.
- Synthetic adapters (`adapters/`) for test-bench fixtures — zero network/DB.
- `GatewayService` (`service.py`) ties policy -> credential -> adapter -> audit
  summary; defaults keep the gateway inert.
- Feature flag `CASEHUB_INTEGRATIONS_GATEWAY_ENABLED` (default `False`).
- Tests: `tests/test_integrations_gateway.py` (policy/credentials/adapters/
  service) and `tests/test_integrations_gateway_route.py` (admin gate + route).

## Next Slices

- Add outbox/retry semantics before enabling mutating operations.
- Keep Gmail read-only until there is an explicit legal/compliance decision for
  message publishing or attachment handling.
- Council before any of: provisioning a real credential, enabling a provider,
  or the first live provider call (red line: auth/secrets + deploy topology).
