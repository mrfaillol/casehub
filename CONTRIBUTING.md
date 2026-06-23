# Contributing

## Scope

This repository is the public alpha snapshot of CaseHub. Contributions should be
small, reviewable, and safe to publish.

## Public Seed And Demo Data

Any seed, fixture, screenshot, demo page, test or documentation example must use
fabricated data only.

- Use reserved domains such as `example.com` for fixture email addresses.
- Do not use real client, prospect, company, personal, phone, document, address,
  OAB, CPF/CNPJ, process number, WhatsApp, Google account or case data.
- If realistic-looking data is needed for demos, keep it clearly fictional and
  document it as such in the seed file or PR.

## Before Opening A PR

Run the smallest relevant test set plus public-safety scans:

```bash
gitleaks detect --no-git --source . --redact --no-banner
git diff --check
python -m compileall core routes services
```

For UI changes, include screenshots for desktop, tablet and mobile. Do not use
real production screenshots unless every visible datum is manually sanitized.

## AI Integrations

Provider examples must be configuration-driven. Do not hardcode a model vendor,
API key, tenant policy, customer data flow or production router endpoint in code
or docs.

## Runtime Artifacts

Do not commit:

- `.env` or generated config;
- credentials, OAuth tokens or session files;
- `.wwebjs_auth`, browser profiles or WhatsApp QR/session material;
- logs, uploads, backups, database dumps or exported client packages;
- deploy-only scripts that reveal private infrastructure.
