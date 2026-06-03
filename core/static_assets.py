"""Versioned static asset helpers."""
import json
import os
from functools import lru_cache

from config import settings


MANIFEST_PATH = os.path.join(settings.BASE_DIR, "static", "assets", "dashboard-manifest.json")
BRAND_KIT_MANIFEST_PATH = os.path.join(settings.BASE_DIR, "static", "brand-kit", "manifest.json")
DEFAULT_BRAND_KIT_FALLBACK_FAVICON = "favicon/casehub-favicon-degrade-4.svg"


@lru_cache(maxsize=1)
def _dashboard_manifest() -> dict:
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("assets", {}) if isinstance(data, dict) else {}


def asset_url(path: str) -> str:
    """
    Return a cache-versioned /static URL when the build manifest has an entry.

    The function accepts either "css/app.css" or "/static/css/app.css".
    Missing manifest entries fall back to the original unversioned asset.
    """
    normalized = (path or "").lstrip("/")
    if normalized.startswith("static/"):
        normalized = normalized[len("static/"):]

    entry = _dashboard_manifest().get(normalized)
    if entry:
        file_path = entry.get("file", normalized)
        version = entry.get("hash")
        if version:
            return f"/static/{file_path}?v={version}"
        return f"/static/{file_path}"
    return f"/static/{normalized}"


@lru_cache(maxsize=1)
def _brand_kit_manifest() -> dict:
    try:
        with open(BRAND_KIT_MANIFEST_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def brand_kit_fallback_favicon_url() -> str:
    """Return the browser fallback favicon from static/brand-kit/manifest.json."""
    manifest = _brand_kit_manifest()
    fallback = manifest.get("fallback_favicon")
    if not isinstance(fallback, str) or not fallback:
        fallback = DEFAULT_BRAND_KIT_FALLBACK_FAVICON

    normalized = fallback.replace("\\", "/").lstrip("/")
    if normalized.startswith("../") or "/../" in normalized:
        normalized = DEFAULT_BRAND_KIT_FALLBACK_FAVICON

    version = ""
    favicons = manifest.get("favicons")
    if isinstance(favicons, dict):
        digest = favicons.get(normalized)
        if isinstance(digest, str) and digest:
            version = digest

    url = f"/static/brand-kit/{normalized}"
    return f"{url}?v={version}" if version else url
