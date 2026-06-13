# Sentinela audit: Three.js SRI/vendor pinning

Date: 2026-05-14
Runtime: codex-cli-5x-pro assuming the Sentinela role per the workspace agent portability rule
Issue: https://github.com/mrfaillol/casehub-prod/issues/418
Base SHA: 73a8def

## Scope

Review and approve the supply-chain remediation for `three@0.160.0` imports
introduced around the CaseHub login organic background.

## Finding

- Category: supply-chain hardening
- Severity: medium
- Evidence before patch:
  - `static/js/casehub-login-organic.js:1` imported `three@0.160.0` from jsdelivr.
  - `static/js/desktop/wallpaper-sky-shader.js:5` imported the same version from jsdelivr.
- Risk: CSP allowlisting jsdelivr does not pin asset bytes. A compromised CDN asset
  or unexpected bytes at the pinned URL would execute in authenticated CaseHub pages.

## Approved Fix

Vendor `three@0.160.0` locally under `static/vendor/three/0.160.0/`, preserve the
MIT license, document source URLs, and point both same-version imports to the local
minified ES module:

- `static/js/casehub-login-organic.js:1`
- `static/js/desktop/wallpaper-sky-shader.js:5`

This avoids adding new runtime network dependencies and does not require changing
the current CSP because other existing pages still use jsdelivr for unrelated
libraries.

## Verification Required

- Confirm no runtime import remains for `cdn.jsdelivr.net/npm/three@0.160.0`.
- Regenerate `static/js/casehub-login-organic.min.js` and
  `static/assets/dashboard-manifest.json`.
- Run a browser smoke of `/casehub/login` and confirm the organic background loads
  without console errors.

Sentinela verdict: approved for PR review, with the out-of-scope note that other
non-0.160.0 CDN imports should be tracked separately rather than folded into this
issue.
