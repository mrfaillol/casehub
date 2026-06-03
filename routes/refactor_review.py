"""
CaseHub — Refactor Review Panel
Painel pra Victor revisar templates refatorados: old × new lado a lado, feedback escrito,
explicação técnica simples. Lê de templates/_archive/ + docs/reestruturacao/briefs/.
"""
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from core.template_config import templates, PREFIX, mock_preview_context

router = APIRouter(prefix="/refactor-review", tags=["refactor-review"])

ARCHIVE_ROOT = os.path.join("templates", "_archive")
# Briefs ficam co-localizados com o archive (templates/ \u00e9 o \u00fanico dir montado no container dev)
BRIEFS_ROOT = ARCHIVE_ROOT
BRIEF_FILENAME = "_brief.md"

# Metadata por archive-key:
#   route           = rota live real no app (pra abrir em nova aba)
#   template_path   = caminho relativo em templates/ (pra render direto no preview)
#   auth_required   = True se rota live redireciona pra login sem sessão
#   requires_fixture= True se rota exige setup-ativo ou path param (token, id)
#   note            = string opcional exibida no compare.html
#
# Rotas reais conferidas em routes/onboarding.py, routes/password_reset.py.
ROUTE_META = {
    "login.html": {
        "route": "/login", "template_path": "login.html",
        "auth_required": False, "requires_fixture": False,
    },
    "forgot_password.html": {
        "route": "/forgot-password", "template_path": "forgot_password.html",
        "auth_required": False, "requires_fixture": False,
    },
    "reset_password.html": {
        "route": "/reset-password/preview-token", "template_path": "reset_password.html",
        "auth_required": False, "requires_fixture": True,
        "note": "rota real espera {token} — preview usa dummy",
    },
    "onboarding-signup.html": {
        "route": "/signup", "template_path": "onboarding/signup.html",
        "auth_required": False, "requires_fixture": False,
    },
    "onboarding-welcome.html": {
        "route": "/setup/welcome", "template_path": "onboarding/welcome.html",
        "auth_required": True, "requires_fixture": True,
        "note": "requer organização em estado de setup ativo",
    },
    "onboarding-complete.html": {
        "route": "/setup/complete", "template_path": "onboarding/complete.html",
        "auth_required": True, "requires_fixture": True,
        "note": "requer setup ativo + user autenticado",
    },
    "onboarding-branding.html": {
        "route": "/setup/branding", "template_path": "onboarding/branding.html",
        "auth_required": True, "requires_fixture": False,
    },
    "onboarding-drive.html": {
        "route": "/setup/drive", "template_path": "onboarding/drive.html",
        "auth_required": True, "requires_fixture": False,
    },
    "onboarding-team.html": {
        "route": "/setup/team", "template_path": "onboarding/team.html",
        "auth_required": True, "requires_fixture": False,
    },
    "onboarding-plan.html": {
        "route": "/setup/plan", "template_path": "onboarding/plan.html",
        "auth_required": True, "requires_fixture": False,
    },
}

# Mantido pra compat com código/template que ainda lê a URL crua
LIVE_ROUTE_BY_KEY = {k: m["route"] for k, m in ROUTE_META.items()}


def _safe_key(key: str) -> str:
    if "/" in key or ".." in key:
        raise HTTPException(status_code=400, detail="invalid key")
    return key


def _list_archived_templates():
    """Lista todos os archive-keys que têm _versions.json (ou seja, refatorados)."""
    out = []
    if not os.path.isdir(ARCHIVE_ROOT):
        return out
    for entry in sorted(os.listdir(ARCHIVE_ROOT)):
        if entry.startswith("_"):
            continue
        manifest = os.path.join(ARCHIVE_ROOT, entry, "_versions.json")
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
            versions = data.get("versions", [])
        except Exception:
            versions = []
        out.append({
            "key": entry,
            "versions": versions,
            "live_route": LIVE_ROUTE_BY_KEY.get(entry, ""),
            "has_brief": os.path.isfile(_brief_path(entry)),
        })
    return out


def _brief_path(key: str) -> str:
    # templates/_archive/<key>/_brief.md (co-localizado com _versions.json)
    return os.path.join(ARCHIVE_ROOT, key, BRIEF_FILENAME)


def _read_brief(key: str) -> Optional[str]:
    fname = _brief_path(key)
    if not os.path.isfile(fname):
        return None
    with open(fname, "r", encoding="utf-8") as f:
        return f.read()


def _feedback_path(key: str) -> str:
    return os.path.join(ARCHIVE_ROOT, key, "_feedback.json")


def _read_feedback(key: str):
    p = _feedback_path(key)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("messages", [])
    except Exception:
        return []


def _append_feedback(key: str, author: str, text: str):
    p = _feedback_path(key)
    msgs = _read_feedback(key)
    msgs.append({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "text": text,
    })
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"messages": msgs}, f, ensure_ascii=False, indent=2)


def _markdown_basic(md: str) -> str:
    """Renderização markdown leve (headings, bold, code, listas, links)."""
    if not md:
        return ""
    lines = md.split("\n")
    html = []
    in_list = False
    in_code = False
    for line in lines:
        if line.startswith("```"):
            if in_code:
                html.append("</code></pre>")
                in_code = False
            else:
                html.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            html.append(_escape(line))
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            n = len(m.group(1))
            html.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                html.append("<ul>")
                in_list = True
            stripped = re.sub(r'^\s*[-*]\s+', '', line)
            html.append(f"<li>{_inline(stripped)}</li>")
            continue
        if in_list and not line.strip():
            html.append("</ul>")
            in_list = False
        if not line.strip():
            html.append("")
        else:
            html.append(f"<p>{_inline(line)}</p>")
    if in_list:
        html.append("</ul>")
    if in_code:
        html.append("</code></pre>")
    return "\n".join(html)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    s = _escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    items = _list_archived_templates()
    # Esconde os _deprecated
    items = [i for i in items if not i["key"].startswith("_deprecated")]
    return templates.TemplateResponse("refactor_review/index.html", {
        "request": request,
        "PREFIX": PREFIX,
        "items": items,
    })


@router.get("/{key}", response_class=HTMLResponse)
async def compare(request: Request, key: str):
    key = _safe_key(key)
    manifest_path = os.path.join(ARCHIVE_ROOT, key, "_versions.json")
    if not os.path.isfile(manifest_path):
        raise HTTPException(status_code=404, detail=f"template '{key}' not in archive")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    versions = manifest.get("versions", [])
    latest_old = versions[0]["id"] if versions else None
    brief = _read_brief(key)
    feedback = _read_feedback(key)
    meta = ROUTE_META.get(key, {})
    live_route = meta.get("route", "")
    return templates.TemplateResponse("refactor_review/compare.html", {
        "request": request,
        "PREFIX": PREFIX,
        "key": key,
        "versions": versions,
        "latest_old": latest_old,
        "brief_html": _markdown_basic(brief) if brief else "",
        "brief_raw": brief or "",
        "feedback": feedback,
        "live_route": live_route,
        "live_auth_required": meta.get("auth_required", False),
        "live_requires_fixture": meta.get("requires_fixture", False),
        "live_note": meta.get("note", ""),
        "preview_available": bool(meta.get("template_path")),
    })


@router.get("/_preview/{key}", response_class=HTMLResponse)
async def preview_current(request: Request, key: str):
    """Renderiza o template LIVE com contexto mock — evita redirect de auth
    e 404s por path params. Iframe "depois" do compare.html aponta aqui."""
    key = _safe_key(key)
    meta = ROUTE_META.get(key)
    if not meta or not meta.get("template_path"):
        raise HTTPException(status_code=404, detail=f"no preview mapping for '{key}'")
    tpl_path = meta["template_path"]
    # checa existência pra falhar cedo (evita TemplateNotFound genérico)
    full = os.path.join("templates", tpl_path)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail=f"template not found: {tpl_path}")
    ctx = mock_preview_context(request)
    try:
        return templates.TemplateResponse(tpl_path, ctx)
    except Exception as exc:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        return HTMLResponse(
            f"<!-- live preview (raw, Jinja render falhou: {type(exc).__name__}: {exc}) -->\n"
            + raw,
            status_code=200,
        )


@router.post("/{key}/feedback")
async def post_feedback(key: str, request: Request, text: str = Form(...), author: str = Form("victor")):
    key = _safe_key(key)
    if not text.strip():
        return RedirectResponse(url=f"{PREFIX}/refactor-review/{key}", status_code=303)
    _append_feedback(key, author.strip()[:60], text.strip()[:4000])
    return RedirectResponse(url=f"{PREFIX}/refactor-review/{key}#feedback", status_code=303)


@router.get("/{key}/feedback", response_class=JSONResponse)
async def list_feedback(key: str):
    key = _safe_key(key)
    return {"key": key, "messages": _read_feedback(key)}


# ── Trilha H — ponte refactor-review ↔ gen-lab ──────────────────────────────
# H.1: GET /_api/briefs            — lista templates + brief + feedback recente
# H.2: POST /_api/{key}/candidate  — gen-lab empurra HTML gerado, vira versão arquivada
#
# Auth via header x-gen-lab-key (env GEN_LAB_KEY). Sem o header, 401.
# Sanitização: regex básico (strip <script>, on*= handlers). Bleach quando disponível.

GEN_LAB_KEY_ENV = "GEN_LAB_KEY"


def _check_gen_lab_key(request: Request) -> bool:
    expected = os.environ.get(GEN_LAB_KEY_ENV, "")
    if not expected:  # se env não setada, recusa por segurança
        return False
    return request.headers.get("x-gen-lab-key", "") == expected


def _sanitize_html(html: str) -> str:
    """Strip <script>, on* handlers, javascript: URIs. Best-effort, não substitui review humano."""
    if not isinstance(html, str):
        return ""
    # remove <script>...</script> (multiline)
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
    # remove on*= handlers (onclick, onerror, etc)
    html = re.sub(r"\s+on[a-z]+\s*=\s*\"[^\"]*\"", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\s+on[a-z]+\s*=\s*'[^']*'", "", html, flags=re.IGNORECASE)
    # neutraliza javascript: URIs
    html = re.sub(r"javascript\s*:", "blocked:", html, flags=re.IGNORECASE)
    return html


@router.get("/_api/briefs", response_class=JSONResponse)
async def api_list_briefs(needs_candidate: int = 0):
    """Expõe briefs + feedback recente pro gen-lab consumir.

    Query: ?needs_candidate=1 → filtra apenas templates sem candidate gerado nas últimas 24h
    (candidates têm prefixo 'lab-gen-' no _versions.json).
    """
    items = _list_archived_templates()
    items = [i for i in items if not i["key"].startswith("_deprecated")]
    out = []
    cutoff_ts = datetime.now(timezone.utc).timestamp() - 86400  # 24h atrás
    for it in items:
        key = it["key"]
        brief_md = _read_brief(key) or ""
        feedback = _read_feedback(key)[-5:]  # últimos 5
        recent_lab_gen = [
            v for v in it["versions"]
            if str(v.get("id", "")).startswith("lab-gen-")
            and v.get("created_at_ts", 0) >= cutoff_ts
        ]
        if needs_candidate and recent_lab_gen:
            continue
        meta = ROUTE_META.get(key, {})
        out.append({
            "key": key,
            "brief_md": brief_md,
            "feedback_recent": [{"text": m.get("text", ""), "ts": m.get("ts", "")} for m in feedback],
            "live_route": meta.get("route", ""),
            "template_path": meta.get("template_path", ""),
            "lab_gen_count_24h": len(recent_lab_gen),
        })
    return {"count": len(out), "items": out}


@router.post("/_api/{key}/candidate", response_class=JSONResponse)
async def api_post_candidate(key: str, request: Request):
    """Recebe HTML gerado pelo gen-lab. Salva como versão arquivada com prefixo lab-gen-<ts>.

    Headers: x-gen-lab-key obrigatório (env GEN_LAB_KEY).
    Body JSON: {html: str, reasoning: str, source: str}
    """
    if not _check_gen_lab_key(request):
        raise HTTPException(status_code=401, detail="invalid or missing x-gen-lab-key")
    key = _safe_key(key)
    if key not in ROUTE_META:
        raise HTTPException(status_code=404, detail=f"key '{key}' not in ROUTE_META")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="json inválido")
    html = (payload or {}).get("html", "")
    if not isinstance(html, str) or len(html) < 100:
        raise HTTPException(status_code=400, detail="html ausente ou < 100 chars")
    if len(html) > 524288:  # 512KB
        raise HTTPException(status_code=413, detail="html excede 512KB")
    reasoning = str((payload or {}).get("reasoning", ""))[:2000]
    source = str((payload or {}).get("source", "gen-lab"))[:60]
    law_applied = str((payload or {}).get("law_applied", ""))[:120]
    # refs_used: lista de slugs codepen (ou strings curtas); aceita list ou string
    refs_raw = (payload or {}).get("refs_used", [])
    if isinstance(refs_raw, str):
        refs_raw = [refs_raw]
    refs_used = [str(r)[:80] for r in (refs_raw or [])[:10]]  # max 10 refs

    # Rate limit: máx 1 candidate / 6h por template
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - 6 * 3600
    versions_path = os.path.join(ARCHIVE_ROOT, key, "_versions.json")
    if os.path.isfile(versions_path):
        with open(versions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        recent = [
            v for v in data.get("versions", [])
            if str(v.get("id", "")).startswith("lab-gen-")
            and v.get("created_at_ts", 0) >= cutoff
        ]
        if recent:
            raise HTTPException(status_code=429, detail=f"rate limit: candidate gerado nas últimas 6h ({recent[0]['id']})")
    else:
        data = {"versions": []}

    # Salva o HTML
    ts = int(now.timestamp())
    candidate_id = f"lab-gen-{ts}"
    sanitized = _sanitize_html(html)
    folder = os.path.join(ARCHIVE_ROOT, key)
    os.makedirs(folder, exist_ok=True)
    out_path = os.path.join(folder, f"{candidate_id}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(sanitized)

    # Atualiza _versions.json (insere no início, ordem reversa cronológica)
    new_entry = {
        "id": candidate_id,
        "label": f"lab-gen · {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "date": now.strftime("%Y-%m-%d"),
        "created_at_ts": ts,
        "source": source,
        "reasoning": reasoning,
    }
    if law_applied:
        new_entry["law_applied"] = law_applied
    if refs_used:
        new_entry["refs_used"] = refs_used
    data["versions"] = [new_entry] + data.get("versions", [])
    with open(versions_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "key": key,
        "candidate_id": candidate_id,
        "url": f"{PREFIX}/templates/_archive/{key}?v={candidate_id}",
        "size": len(sanitized),
    }
