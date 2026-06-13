"""Tenant-scoped Maestro provider/model policy.

This resolver is intentionally conservative: unsupported or missing policies
fall back to the local Ollama configuration, and provider credentials are never
returned to the caller. The credential store is prepared by migration for a
later encrypted admin UI, but runtime routing only needs non-secret policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


SUPPORTED_PROVIDERS = {"ollama"}


@dataclass(frozen=True)
class MaestroPolicy:
    provider: str
    model: str
    ollama_url: str
    source: str = "default"


def _default_policy() -> MaestroPolicy:
    return MaestroPolicy(
        provider="ollama",
        model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        ollama_url=os.getenv("OLLAMA_URL", "http://host.docker.internal:11434"),
    )


def resolve_maestro_policy(db: Optional[Session], org_id: Optional[int]) -> MaestroPolicy:
    """Resolve safe provider/model policy for one tenant.

    Unknown providers are ignored on purpose. This prevents a tenant setting
    from silently routing privileged firm context to an external API before the
    provider has an audited adapter and credential boundary.
    """
    default = _default_policy()
    if db is None or org_id is None:
        return default

    try:
        row = db.execute(
            text("""
                SELECT provider, model, endpoint_url, enabled
                FROM org_ai_policies
                WHERE org_id = :org_id AND feature = 'maestro'
                LIMIT 1
            """),
            {"org_id": org_id},
        ).fetchone()
    except Exception:
        return default

    if not row or not row.enabled:
        return default

    provider = (row.provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        return default

    return MaestroPolicy(
        provider=provider,
        model=(row.model or default.model).strip() or default.model,
        ollama_url=(row.endpoint_url or default.ollama_url).strip() or default.ollama_url,
        source="database",
    )
