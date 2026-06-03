"""
CaseHub — Artist Board (J.7)
Dashboard público que Victor acompanha produção cron (gen-lab + mutator + artist).

Fontes:
- Oracle /generative-lab/_digest.json (via proxy HTTP)
- app.example.com templates/_archive/*/lab-gen-*.html (local filesystem)
- memory/design-library/audits/ + fixes/ (tracked no workspace repo)
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from core.template_config import templates, PREFIX

try:
    import httpx
except ImportError:
    httpx = None

router = APIRouter(prefix="/artist-board", tags=["artist-board"])

GEN_LAB_DIGEST_URL = "https://app.example.com/lab/_digest.json"
ARCHIVE_ROOT = os.path.join("templates", "_archive")


async def _fetch_gen_lab_digest() -> dict:
    """Busca _digest.json do gen-lab Oracle via proxy HTTP."""
    if httpx is None:
        return {"error": "httpx not installed"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(GEN_LAB_DIGEST_URL)
            if r.status_code == 200:
                return r.json()
            return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def _list_lab_gen_candidates(limit: int = 50) -> list:
    """Lista candidates lab-gen-*.html do archive, mais recentes primeiro."""
    out = []
    if not os.path.isdir(ARCHIVE_ROOT):
        return out
    for template_key in os.listdir(ARCHIVE_ROOT):
        if template_key.startswith("_"):
            continue
        tdir = os.path.join(ARCHIVE_ROOT, template_key)
        if not os.path.isdir(tdir):
            continue
        for fname in os.listdir(tdir):
            if fname.startswith("lab-gen-") and fname.endswith(".html"):
                full = os.path.join(tdir, fname)
                try:
                    st = os.stat(full)
                    ts_ms = int(st.st_mtime * 1000)
                except OSError:
                    continue
                out.append({
                    "template_key": template_key,
                    "candidate_id": fname[:-5],
                    "ts_ms": ts_ms,
                    "date": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
                    "size": st.st_size,
                    "url": f"{PREFIX}/templates/_archive/{template_key}?v={fname[:-5]}",
                    "compare_url": f"{PREFIX}/refactor-review/{template_key}",
                })
    out.sort(key=lambda x: -x["ts_ms"])
    return out[:limit]


@router.get("/api/feed", response_class=JSONResponse)
async def api_feed(request: Request):
    """JSON feed consumido pela UI e por RSS futuro."""
    digest = await _fetch_gen_lab_digest()
    candidates = _list_lab_gen_candidates(50)
    return {
        "now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gen_lab": digest,
        "candidates_local": candidates,
        "candidates_count": len(candidates),
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Dashboard Artist Board."""
    digest = await _fetch_gen_lab_digest()
    candidates = _list_lab_gen_candidates(30)
    return templates.TemplateResponse("artist_board/index.html", {
        "request": request,
        "PREFIX": PREFIX,
        "digest": digest,
        "candidates": candidates,
        "candidates_count": len(candidates),
    })
