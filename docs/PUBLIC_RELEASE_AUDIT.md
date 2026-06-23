# Public Release Audit - 0.9.12-alpha

Date: 2026-06-23

## Source

This public branch was prepared from the sanitized production cleanup line and
then curated for `mrfaillol/casehub`. Private production repository names,
runtime paths and deployment-only artifacts are intentionally excluded.

## Included

- Application code for the CaseHub alpha product.
- Generic migrations and tests.
- Public brand kit assets without real tenant screenshots.
- WhatsApp chat/bot code with tenant-isolated sessions.
- Maestro/provider-agnostic AI code paths.
- Public docs, README, SECURITY and CONTRIBUTING.
- Sanitized SVG mock screenshots.

## Excluded

- Runtime data: uploads, logs, cache, sessions, browser profiles.
- WhatsApp session state and QR material.
- `.env` files and production configuration.
- Backups, database dumps and exported client packages.
- Private deploy scripts, VPS monitors and runbooks.
- Handoffs, internal audits, worktree notes and agent journals.
- Tenant-specific screenshots and branding.
- Files containing real client, firm, person, phone, address or case data.

## Verification Completed

Completed on 2026-06-23 in the public release worktree:

```bash
gitleaks detect --source . --no-git --redact --report-format json --report-path /tmp/casehub-public-gitleaks-workingtree.json
git diff --check
python3 -m json.tool static/brand-kit/manifest.json
python3 -m json.tool package-lock.json
python3 -m compileall core routes services models middleware
node --check services/whatsapp-bot/agent-templates.js
node --check services/whatsapp-bot/llm-chatbot-v3.js
node --check services/whatsapp-bot/maestro-knowledge.js
node --check static/js/landing.js
node --check static/js/marketing.js
python3 -m pytest tests/test_app_factory.py tests/test_subdomain_validation.py tests/test_whatsapp_lite_routes.py tests/test_ai_provider.py tests/test_mcp_client_facade.py tests/test_legal_pages.py tests/test_whatsapp_followup_send.py tests/test_ilc_tools_routes.py tests/test_improvement_tasks.py
npm test  # from services/whatsapp-bot
```

Results:

- `gitleaks`: no leaks found.
- Python compile: passed.
- JS syntax checks: passed.
- Focused Python tests: 123 passed, 3 warnings from local Python 3.9 EOL.
- WhatsApp-bot Node tests: 72 passed.

## Residual Scanner Notes

The repository still contains synthetic placeholders and fixtures that match
generic phone, CPF, CNPJ and API-key regexes. These are examples or tests only:

- Brazilian document validators and redaction tests use fake CPF/CNPJ values.
- WhatsApp clone/unit tests use repeated synthetic E.164 numbers such as
  `+5511999999999`.
- UI placeholders show example phone/document formats.
- Stripe/OpenAI-style strings in docs/templates are shape examples such as
  `sk_live_xxxxx`, not real keys.
