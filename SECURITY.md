# Security Policy

## Reporting

Please do not open public issues with vulnerabilities, secrets, tenant names,
client data, screenshots of real matters, logs, tokens, or exploit details.

Send security reports to:

- `casehub@legalopsco.work`

Include a short description, affected version or commit, reproduction steps,
impact, and any suggested fix. Redact all personal data before sending.

## Public Repository Rules

This repository must not contain:

- `.env` files or production configuration;
- API keys, OAuth tokens, cookies, SSH keys, passphrases or webhook secrets;
- database dumps, backups, logs, uploads, generated reports or cache folders;
- WhatsApp session state, including `.wwebjs_auth`;
- Google credential or token files;
- screenshots with real client, firm, person, phone, address, case or process data;
- VPS topology, IP addresses, private hostnames or deploy-only runbooks.

Demo and test data must be fabricated and clearly non-real.

## AI And Data Egress

CaseHub supports provider-configurable AI surfaces. Real tenant data should only
be sent to an external model when the tenant has explicitly configured and
approved that provider and data policy.

Public examples should use synthetic data only.

## Maintainer Checklist

Before publishing a public PR:

```bash
gitleaks detect --no-git --source . --redact --no-banner
rg -n -i "private key|passphrase|api[_-]?key\\s*=|secret\\s*=|token\\s*=|bearer " .
rg -n -i "real-client-marker|private-host-marker|known-tenant-marker" .
```

Adapt the marker search to the current cleanup target. Treat any real match as
blocking until it is removed or documented as a false positive.
