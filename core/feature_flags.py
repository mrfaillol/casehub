"""Central feature-flag registry for CaseHub (default-OFF policy).

POLICY (issue #800)
-------------------
Any "[deploy gated]" code MUST be guarded by a default-OFF flag registered
here. The deploy gate lives in the FLAG, not in human deploy timing: merging
to main must always be deploy-safe, because every gated path is inert until
its flag is explicitly turned ON via environment variable.

How it works
------------
Each known flag has a registry entry with a ``default`` value (which MUST be
``False``/OFF) and a one-line description. At runtime a flag is enabled only
when the environment variable ``CASEHUB_FF_<NAME_UPPER>`` is set to a truthy
value ("1", "true", "on", "yes" — case-insensitive). Otherwise the registry
default (False) is returned. Unknown flag names are logged and treated as
OFF (the safe default) rather than raising, so a typo can never accidentally
enable gated code.

Convention note: the rest of CaseHub reads typed settings via ``config.py``
(pydantic ``Settings``). Feature flags are intentionally a separate, simpler
mechanism — a plain env-var lookup with an explicit OFF default — so that
adding a gated flag never requires touching the shared Settings schema and
the "default OFF" guarantee is enforced in one place.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Truthy values accepted for an ON flag (case-insensitive).
_TRUTHY = {"1", "true", "on", "yes"}

_ENV_PREFIX = "CASEHUB_FF_"


@dataclass(frozen=True)
class FeatureFlag:
    """A single registered feature flag.

    ``default`` MUST be ``False`` (OFF) per the #800 policy.
    """

    name: str
    default: bool
    description: str


# ── Registry ─────────────────────────────────────────────────────────────
# Every entry MUST have default=False. The activation of any "[deploy gated]"
# code path is keyed off one of these flags.
REGISTRY: dict[str, FeatureFlag] = {
    "secondary_calendar_sync": FeatureFlag(
        name="secondary_calendar_sync",
        default=False,
        description=(
            "T6 (#781) Google-Calendar multi-calendar sync: activate opt-in for "
            "secondary/non-primary calendars (two-way sync + write target). OFF "
            "= only the 'primary' calendar syncs, i.e. current prod behavior."
        ),
    ),
    "superadmin_2fa_enforcement": FeatureFlag(
        name="superadmin_2fa_enforcement",
        default=False,
        description=(
            "T10 (#805, CWE-308) Require TOTP 2FA on sensitive superadmin paths "
            "(impersonation, org toggle, plan change). ON: a superadmin who has "
            "NOT enrolled 2FA is redirected to /2fa/setup (enrollment grace, no "
            "hard lockout); an enrolled superadmin proceeds. OFF (default = "
            "current prod): superadmin paths behave exactly as today, no extra "
            "2FA requirement. Never blocks superadmin access while OFF."
        ),
    ),
    "dje_integration": FeatureFlag(
        name="dje_integration",
        default=False,
        description=(
            "(#809/#342) Domicílio Judicial Eletrônico (DJE) live integration. ON: "
            "routes that hit the PDPJ DJE gateway (gateway.cloud.pje.jus.br/"
            "domicilio-eletronico) are active — listing comunicações/intimações via "
            "client_credentials JWT + per-org tenantId. OFF (default = current prod): "
            "the DJE route returns 404 and no live API call is made. Validate against "
            "HML (DJE_ENV=hml) before enabling in prod."
        ),
    ),
}


def _env_var_name(name: str) -> str:
    return _ENV_PREFIX + name.strip().upper()


def is_enabled(name: str) -> bool:
    """Return True only if the flag is explicitly enabled via its env var.

    Resolution order:
      1. Unknown flag name -> log a warning and return False (safe default).
      2. Env var ``CASEHUB_FF_<NAME_UPPER>`` set to a truthy value -> True.
      3. Env var set to anything else -> False.
      4. Env var unset -> the registry default (always False).
    """
    flag = REGISTRY.get(name)
    if flag is None:
        logger.warning(
            "Unknown feature flag %r requested; treating as OFF (safe default).",
            name,
        )
        return False

    raw = os.getenv(_env_var_name(name))
    if raw is None:
        return flag.default
    return raw.strip().lower() in _TRUTHY
