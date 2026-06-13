# CaseHub Lite API Compatibility Audit - Manus Reference

Source reviewed: `/Users/beijaflor/Downloads/CaseHub Lite API Reference.md`.

## Scope

This audit treats the Manus Markdown as a compatibility reference for the May 4 performance HALT, not as an implementation spec for new public endpoints. The current cycle only adds guard tests around existing contracts and records gaps as follow-up work.

## Current Code Contract

- Current FastAPI router is `routes/api.py` with prefix `/api/v1`; `core/app_factory.py` mounts product routers under `settings.PREFIX`, so the app path is `/casehub/api/v1/...` in the Lite product.
- Existing authenticated dashboard endpoint is `GET /casehub/api/v1/dashboard/stats`.
- Existing cases list endpoint is `GET /casehub/api/v1/cases` with `skip`, `limit`, `search`, `status`, `client_id`, and `visa_type` query parameters.
- Current cases response shape is `{total, skip, limit, data}`. This differs from the Manus `{data, pagination}` envelope, so this PR keeps the current shape and covers it with regression tests.

## Manus Gaps Deferred

- Manus defines `GET /dashboard/metrics`; current code exposes `GET /dashboard/stats`.
- Manus defines `PATCH /cases/{id}`; current code exposes `PUT /cases/{case_id}`.
- Manus request/response fields use `title`, `case_type`, `due_date`, `cnj_process_number`, `metadata`, and string ids; current code uses SQL integer ids and existing `Case` fields such as `case_name`, `visa_type`, `numero_processo`, `expiration_date`, and `notes`.
- Manus describes rate-limit headers and a structured error envelope. Current app has middleware-level rate limiting and FastAPI default errors; response-header parity is not implemented in this cycle.
- Manus defines CNJ sync endpoints under `/integrations/cnj/sync`; current code has tribunal/DataJud-related modules but no matching public API contract.

## Guard Added In This PR

- `tests/test_api_contract_guard.py` checks that `GET /casehub/api/v1/dashboard/stats` keeps the existing `stats` and `charts` JSON shape.
- `tests/test_api_contract_guard.py` checks that `GET /casehub/api/v1/cases` remains tenant-scoped and returns the current `{total, skip, limit, data}` shape.

## Follow-Up Recommendation

Create a separate API-contract milestone after the performance HALT to decide whether Manus should become the public v1 contract, a v2 contract, or only external documentation. Do not mix that decision into the May 4 performance release.
