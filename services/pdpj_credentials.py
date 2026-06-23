"""Tenant-scoped PDPJ client credential storage.

Raw PDPJ secrets must never be stored in Git, logs, chat transcripts, or API
responses. This module stores the tenant client secret encrypted in
organizations.settings and returns raw values only to the PDPJ token exchange
path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import logging
import os
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models.tenant import Organization
from services.credential_crypto import decrypt_credential, encrypt_credential

logger = logging.getLogger(__name__)

_CLIENT_ID_KEY = "pdpj_client_id"
_CLIENT_SECRET_KEY = "pdpj_client_secret_encrypted"
_CLIENT_ID_FINGERPRINT_KEY = "pdpj_client_id_fingerprint"
_CLIENT_SECRET_FINGERPRINT_KEY = "pdpj_client_secret_fingerprint"
_CONFIGURED_AT_KEY = "pdpj_client_configured_at"
_CONFIGURED_BY_KEY = "pdpj_client_configured_by"


@dataclass(frozen=True)
class PDPJClientCredentials:
    """Resolved PDPJ credentials for one tenant.

    ``client_secret`` is excluded from repr so accidental logs of the object do
    not print the secret.
    """

    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    source: str = "none"
    error: str = ""
    client_id_fingerprint: str = ""
    client_secret_fingerprint: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and not self.error)


def _fingerprint(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_settings(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _credentials_from_settings(settings: dict) -> Optional[PDPJClientCredentials]:
    has_client_id = _CLIENT_ID_KEY in settings
    has_secret = _CLIENT_SECRET_KEY in settings
    if not has_client_id and not has_secret:
        return None

    client_id = str(settings.get(_CLIENT_ID_KEY) or "").strip()
    encrypted_secret = str(settings.get(_CLIENT_SECRET_KEY) or "").strip()
    if not client_id or not encrypted_secret:
        return PDPJClientCredentials(
            client_id=client_id,
            source="database",
            error="tenant_credentials_incomplete",
            client_id_fingerprint=_fingerprint(client_id),
        )

    try:
        client_secret = decrypt_credential(encrypted_secret)
    except Exception:
        logger.error("PDPJ tenant credential decrypt failed; refusing env fallback")
        return PDPJClientCredentials(
            client_id=client_id,
            source="database",
            error="tenant_credentials_decrypt_failed",
            client_id_fingerprint=_fingerprint(client_id),
        )

    return PDPJClientCredentials(
        client_id=client_id,
        client_secret=client_secret,
        source="database",
        client_id_fingerprint=_fingerprint(client_id),
        client_secret_fingerprint=_fingerprint(client_secret),
    )


def _credentials_from_env(
    *,
    env_client_id: Optional[str] = None,
    env_client_secret: Optional[str] = None,
) -> PDPJClientCredentials:
    client_id = (env_client_id if env_client_id is not None else os.getenv("PDPJ_CLIENT_ID", "")).strip()
    client_secret = (
        env_client_secret if env_client_secret is not None else os.getenv("PDPJ_CLIENT_SECRET", "")
    ).strip()
    source = "env" if client_id or client_secret else "none"
    error = "missing_credentials" if source == "env" and not (client_id and client_secret) else ""
    return PDPJClientCredentials(
        client_id=client_id,
        client_secret=client_secret,
        source=source,
        error=error,
        client_id_fingerprint=_fingerprint(client_id),
        client_secret_fingerprint=_fingerprint(client_secret),
    )


def _load_org_settings(db: Session, org_id: Optional[int]) -> Optional[dict]:
    if db is None or org_id is None:
        return None
    try:
        org = db.query(Organization).filter(Organization.id == int(org_id)).first()
    except Exception as exc:
        logger.debug("PDPJ tenant credential lookup skipped: %s", exc)
        return None
    if not org:
        return None
    return _as_settings(org.settings)


def resolve_pdpj_client_credentials(
    db: Optional[Session],
    org_id: Optional[int],
    *,
    env_client_id: Optional[str] = None,
    env_client_secret: Optional[str] = None,
) -> PDPJClientCredentials:
    """Resolve tenant PDPJ credentials, then fall back to env only if absent.

    If tenant settings contain a partial/corrupt PDPJ credential, we fail closed
    and do not use the global env credential. That prevents cross-tenant
    credential bleed when one tenant is explicitly configured but broken.
    """

    tenant_settings = _load_org_settings(db, org_id)
    if tenant_settings is not None:
        tenant_credentials = _credentials_from_settings(tenant_settings)
        if tenant_credentials is not None:
            return tenant_credentials

    return _credentials_from_env(env_client_id=env_client_id, env_client_secret=env_client_secret)


def resolve_pdpj_client_credentials_from_runtime(
    org_id: Optional[int],
    *,
    env_client_id: Optional[str] = None,
    env_client_secret: Optional[str] = None,
) -> PDPJClientCredentials:
    """Resolve credentials from a short-lived DB session for runtime clients."""

    db = None
    try:
        from models.base import SessionLocal

        db = SessionLocal()
        return resolve_pdpj_client_credentials(
            db,
            org_id,
            env_client_id=env_client_id,
            env_client_secret=env_client_secret,
        )
    except Exception as exc:
        logger.debug("PDPJ runtime credential lookup fell back to env: %s", exc)
        return _credentials_from_env(env_client_id=env_client_id, env_client_secret=env_client_secret)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def public_pdpj_credential_status(
    db: Optional[Session],
    org_id: Optional[int],
    *,
    env_client_id: Optional[str] = None,
    env_client_secret: Optional[str] = None,
) -> dict:
    """Return redacted credential status for UI/admin diagnostics."""

    credentials = resolve_pdpj_client_credentials(
        db,
        org_id,
        env_client_id=env_client_id,
        env_client_secret=env_client_secret,
    )
    return {
        "configured": credentials.configured,
        "source": credentials.source,
        "error": credentials.error,
        "has_client_id": bool(credentials.client_id),
        "has_client_secret": bool(credentials.client_secret),
        "client_id_fingerprint": credentials.client_id_fingerprint,
        "client_secret_fingerprint": credentials.client_secret_fingerprint,
    }


def store_tenant_pdpj_client_credentials(
    db: Session,
    org_id: int,
    *,
    client_id: str,
    client_secret: str,
    user_id: Optional[int] = None,
) -> dict:
    """Store encrypted tenant PDPJ client credentials.

    Returns only redacted status. The caller owns commit/rollback.
    """

    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValueError("client_id_and_secret_required")

    org = db.query(Organization).filter(Organization.id == int(org_id)).first()
    if not org:
        raise ValueError("organization_not_found")

    settings = _as_settings(org.settings)
    settings[_CLIENT_ID_KEY] = client_id
    settings[_CLIENT_SECRET_KEY] = encrypt_credential(client_secret)
    settings[_CLIENT_ID_FINGERPRINT_KEY] = _fingerprint(client_id)
    settings[_CLIENT_SECRET_FINGERPRINT_KEY] = _fingerprint(client_secret)
    settings[_CONFIGURED_AT_KEY] = _utcnow_iso()
    if user_id is not None:
        settings[_CONFIGURED_BY_KEY] = int(user_id)

    org.settings = settings
    flag_modified(org, "settings")
    db.flush()

    return public_pdpj_credential_status(
        db,
        org_id,
        env_client_id="",
        env_client_secret="",
    )
