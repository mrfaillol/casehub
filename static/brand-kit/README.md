# CaseHub Brand Kit

Source of truth for the CaseHub Basic identity. This kit is separate from the
CaseHub legacy palette in `static/css/tokens.css` and should be consumed
through `--ch-*` variables.

## Assets

Default Basic signature:

- `logo/casehub-logo-full-green-blue.svg`
- `logo/casehub-logo-mark.svg` (cropped from the same approved vector)
- `favicon/favicon.svg` (cropped from the same approved vector)

Login Basic fallback:

- `logo/casehub-logo-login-blue.svg` (Victor-provided blue vector)
- `logo/casehub-logo-login-mark-blue.svg` (viewBox crop with the leaf/C visible,
  used as the mask when `org_logo` is absent)
- `favicon/casehub-favicon-degrade-1.svg` through
  `favicon/casehub-favicon-degrade-4.svg` (viewBox crops from Victor's
  `Degradês` vectors, used by the Login Basic organic variants and as the
  browser chrome fallback when `org_favicon` is absent)

Contextual variants:

- `logo/casehub-logo-full-darkgreen-blue.svg`
- `logo/casehub-logo-full-navy-blue.svg`
- `logo/casehub-logo-full-navy-green.svg`
- `logo/casehub-logo-mono-black.svg`
- `logo/casehub-logo-mono-white.svg`
- `logo/casehub-logo-mono-inv.svg`
- `logo/casehub-wordmark.svg`

Reference screenshots live in `reference/` as optimized JPGs. They are visual
references only; failed captures from the source package are bug evidence and
must not drive aesthetic decisions.

## Tokens

`tokens.css` defines the CaseHub brand palette, semantic roles, typography,
neumorphic surface values, motion, radius, and bridge variables for the Basic
shell. It is loaded by `templates/partials/head_css.html` with `asset_url()`.

Use these variables in product CSS:

- color: `--ch-brand-primary`, `--ch-brand-secondary`, `--ch-brand-accent`,
  `--ch-brand-ink`, `--ch-brand-paper`
- surface: `--ch-neu-bg`, `--ch-neu-surface`, `--ch-neu-surface-raised`,
  `--ch-neu-surface-sunken`
- typography: `--ch-font-body`, `--ch-font-display`, `--ch-font-mono`
- motion: `--ch-motion-fast`, `--ch-motion-base`, `--ch-ease-organic`

Do not hardcode brand hex values in templates or feature CSS. Add a token here
first, then consume the token.

## Source Package

Untracked design sources used for this import:

- `external/raw/CaseHub Brand Kit.zip`
  - SHA-256: `df21b0e675a33e969ea05175b799dceebd8c4b0bcce72416df4dae34d4f6164b`
- `external/raw/CaseHub.fig`
  - SHA-256: `838996617d73ee5bdfc967a28a251b7d077e38663e2e934fbc651e51db866b6d`

Curated vector sources and their tracked outputs are listed in
`manifest.json`. The default green+blue lockup, mark, and favicon are derived
from `external/victor-brand-green-blue-vector.svg`
with the green normalized to the canonical `#6FBE54` token.
The Login Basic mark is derived from Victor's blue login vector and keeps the
leaf/C visible; the screen fills that mark through a CSS mask using the same
organic color family as the background. Do not substitute the old hollow-H crop
on this screen.

The raw `.zip`, `.fig`, and full-size PNG exports are intentionally not tracked
because this repo does not have Git LFS configured. Tracked assets are SVGs,
tokens, docs, manifest metadata, and optimized JPG references.

## Rules

- Keep default Basic on the green+blue signature.
- Keep Login Basic on the blue cropped mark with the leaf/C visible.
- Respect `org_logo` and `org_favicon`; CaseHub assets are fallbacks only.
- Keep changes layered: tokens, shell, components, then templates.
- Do not extend OS-like desktop mode for Basic; it remains legacy VS.
- Validate visual changes with screenshots before calling the UI complete.
