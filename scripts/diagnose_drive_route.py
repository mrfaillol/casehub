#!/usr/bin/env python3
"""Sanitized diagnostics for the CaseHub Drive documents route.

The script is read-only: it checks DB/config/token presence and, when
``--probe`` is passed, runs a Drive ``files.list`` only if the token is already
valid. It does not refresh tokens and never prints token or client-secret data.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import settings
from models import Organization, SessionLocal
from routes.integrations import _google_drive_credentials_path
from services.per_org_credentials import DEFAULT_ORG_ID


def _token_path(org_id: int) -> Path:
    return Path(settings.BASE_DIR) / "credentials" / f"org_{org_id}" / "drive_token.json"


def _path_status(path: Path) -> dict[str, Any]:
    return {
        "exists": path.exists(),
        "filename": path.name,
    }


def _root_info(db, org_id: int) -> tuple[str, str]:
    try:
        org = db.query(Organization).filter(Organization.id == int(org_id)).first()
        root_id = getattr(org, "google_drive_root_id", None) if org else None
        if root_id:
            return str(root_id), "org"
    except Exception:
        pass
    if settings.GOOGLE_DRIVE_ROOT_ID:
        return settings.GOOGLE_DRIVE_ROOT_ID, "global"
    return "root", "root-fallback"


def _drive_probe(token_path: Path, folder_id: str, page_size: int) -> dict[str, Any]:
    if not token_path.exists():
        return {"ok": False, "reason": "token_missing"}

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return {"ok": False, "reason": "google_api_packages_missing"}

    try:
        creds = Credentials.from_authorized_user_file(str(token_path))
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__}

    if not creds.valid:
        reason = "token_expired" if getattr(creds, "expired", False) else "token_invalid"
        return {"ok": False, "reason": reason}

    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        payload = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            pageSize=max(1, min(int(page_size), 100)),
            fields="nextPageToken, files(mimeType)",
            orderBy="folder,name",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
    except Exception as exc:
        return {"ok": False, "reason": type(exc).__name__}

    files = payload.get("files") or []
    return {
        "ok": True,
        "count": len(files),
        "next_page_token_present": bool(payload.get("nextPageToken")),
        "mime_types": sorted({item.get("mimeType") or "unknown" for item in files}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", type=int, default=DEFAULT_ORG_ID)
    parser.add_argument("--folder-id", default="")
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Run a sanitized Drive files.list probe if the token is valid.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        root_id, root_source = _root_info(db, args.org_id)
    finally:
        db.close()

    credentials_path = _google_drive_credentials_path()
    token_path = _token_path(args.org_id)
    folder_id = args.folder_id or root_id or "root"
    report: dict[str, Any] = {
        "org_id": args.org_id,
        "root": {
            "configured": root_source != "root-fallback",
            "source": root_source,
            "uses_my_drive_fallback": root_source == "root-fallback",
        },
        "credentials": _path_status(credentials_path),
        "token": _path_status(token_path),
        "probe": {"ok": None, "reason": "not_requested"},
    }

    if args.probe:
        report["probe"] = _drive_probe(token_path, folder_id, args.page_size)

    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
