"""Per-org credentials directory + token path helpers.

Centralizes the convention `credentials/org_{org_id}/` for all Google OAuth
integrations (Calendar, Drive, SSO future). Migrates legacy single-tenant
layout transparently when org_id == DEFAULT_ORG_ID.

Multi-tenant principle:
- Each org gets its own credentials/org_{id}/ subdirectory.
- Tokens are scoped by integration + account_name within that dir.
- Legacy single-tenant tokens (token_center.json, google_drive_token.pickle)
  inherit to the default org on first call.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_ORG_ID = int(os.getenv("CASEHUB_DEFAULT_ORG_ID", "2"))


def get_org_credentials_dir(org_id: int) -> Path:
    """Return `credentials/org_{org_id}/` path. Creates if missing."""
    if not org_id or org_id <= 0:
        raise ValueError(f"org_id required and positive, got {org_id!r}")
    base = Path(settings.BASE_DIR) / "credentials"
    org_dir = base / f"org_{org_id}"
    org_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(org_dir, 0o700)
    except OSError:
        pass
    return org_dir


def get_org_token_path(org_id: int, integration: str, account_name: str = "default") -> Path:
    """Return path for token file scoped to org + integration + account.

    Examples:
        get_org_token_path(2, "calendar", "center")
            → credentials/org_2/calendar_token_center.json
        get_org_token_path(4, "drive")
            → credentials/org_4/drive_token.json
    """
    org_dir = get_org_credentials_dir(org_id)
    safe_account = "".join(c for c in account_name if c.isalnum() or c in ("-", "_"))
    if not safe_account:
        safe_account = "default"
    return org_dir / f"{integration}_token_{safe_account}.json"


def get_org_user_credentials_dir(org_id: int, user_id: int) -> Path:
    """Return `credentials/org_{org_id}/users/{user_id}/` path. Creates if missing.

    Per-USER credential storage lives in a dedicated `users/` subtree so it can
    never collide with the org-account token namespace
    (`calendar_token_{account}.json`) used by the office (center/info) slots.
    Each user directory is 0700 (only the app process reads it).
    """
    if not user_id or int(user_id) <= 0:
        raise ValueError(f"user_id required and positive, got {user_id!r}")
    user_dir = get_org_credentials_dir(org_id) / "users" / str(int(user_id))
    user_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(user_dir, 0o700)
        os.chmod(user_dir.parent, 0o700)
    except OSError:
        pass
    return user_dir


def get_org_user_token_path(
    org_id: int, user_id: int, integration: str = "calendar"
) -> Path:
    """Return per-USER token path scoped to org + user + integration.

    Example:
        get_org_user_token_path(4, 12, "calendar")
            → credentials/org_4/users/12/calendar_token.json

    One token per integration per user (no account_name slot — the user only
    connects their own single Google account per integration).
    """
    safe_integration = "".join(
        c for c in (integration or "") if c.isalnum() or c in ("-", "_")
    ) or "calendar"
    return get_org_user_credentials_dir(org_id, user_id) / f"{safe_integration}_token.json"


def save_org_user_token(org_id: int, user_id: int, content: str, integration: str = "calendar") -> Path:
    """Write per-user token JSON with 0600 perms. Returns the path."""
    path = get_org_user_token_path(org_id, user_id, integration)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
    finally:
        if fd is not None:
            os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def delete_org_user_token(org_id: int, user_id: int, integration: str = "calendar") -> bool:
    """Remove the per-user token file. Returns True if a file was deleted."""
    path = get_org_user_token_path(org_id, user_id, integration)
    if path.exists():
        path.unlink(missing_ok=True)
        return True
    return False


def get_org_drive_token_path(org_id: int) -> Path:
    """Drive uses single token per org (no account_name slot in legacy code)."""
    return get_org_credentials_dir(org_id) / "drive_token.json"


def get_org_drive_legacy_pickle_path(org_id: int) -> Path:
    """Legacy pickle path inside org dir (for one-shot migration)."""
    return get_org_credentials_dir(org_id) / "drive_token.pickle"


def migrate_legacy_credentials_to_org(org_id: int) -> dict:
    """One-time migration: copy legacy single-tenant tokens to org_{DEFAULT_ORG_ID}/.

    Only runs when org_id == DEFAULT_ORG_ID. Safe to call multiple times —
    skips if dest exists.

    Returns dict with `migrated`, `skipped`, `missing` lists.
    """
    result = {"migrated": [], "skipped": [], "missing": [], "reason": ""}
    if org_id != DEFAULT_ORG_ID:
        result["reason"] = f"not_default_org (got {org_id}, default {DEFAULT_ORG_ID})"
        return result

    base = Path(settings.BASE_DIR) / "credentials"
    org_dir = get_org_credentials_dir(org_id)

    pairs = [
        (base / "token_center.json", org_dir / "calendar_token_center.json"),
        (base / "token_info.json", org_dir / "calendar_token_info.json"),
        (base / "google_calendar_credentials.json", org_dir / "calendar_token_legacy.json"),
        (base / "google_drive_token.pickle", org_dir / "drive_token.pickle"),
    ]

    for legacy, new in pairs:
        if not legacy.exists():
            result["missing"].append(legacy.name)
            continue
        if new.exists():
            result["skipped"].append(legacy.name)
            continue
        try:
            shutil.copy2(legacy, new)
            os.chmod(new, 0o600)
            result["migrated"].append(legacy.name)
            logger.info("Migrated %s → %s", legacy, new)
        except OSError as e:
            logger.warning("Migration failed %s → %s: %s", legacy, new, e)

    return result


def list_orgs_with_credentials() -> list[int]:
    """Return list of org_ids that have credentials/org_{id}/ subdirectories."""
    base = Path(settings.BASE_DIR) / "credentials"
    if not base.exists():
        return []
    org_ids = []
    for child in base.iterdir():
        if child.is_dir() and child.name.startswith("org_"):
            try:
                org_ids.append(int(child.name[4:]))
            except ValueError:
                pass
    return sorted(org_ids)
