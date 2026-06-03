"""
Global search endpoint — feeds the topbar palette (Cmd+K / "Buscar tudo…").

Returns a flat list of hits across clients, cases, prazos, and tasks. Hard cap
of 5 per kind to keep the palette fast and scannable (Hick's law). Each row
carries an href so the frontend just navigates on click.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import get_current_user
from core.template_config import PREFIX
from models import get_db


router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def global_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    q = (q or "").strip()
    if len(q) < 2:
        return JSONResponse({"results": []})

    org_id = request.state.org_id
    like = f"%{q}%"
    results: list[dict] = []

    # Clients
    try:
        rows = db.execute(
            text("""
                SELECT id,
                       COALESCE(first_name || ' ' || last_name, email, phone, 'Cliente #' || id) AS nome,
                       email
                FROM clients
                WHERE org_id = :org_id
                  AND (
                    (first_name ILIKE :q OR last_name ILIKE :q OR email ILIKE :q
                     OR client_number ILIKE :q OR phone ILIKE :q)
                  )
                ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
                LIMIT 5
            """),
            {"q": like, "org_id": org_id},
        ).fetchall()
        for r in rows:
            results.append({
                "kind": "Cliente",
                "title": r[1],
                "subtitle": r[2] or "",
                "href": f"{PREFIX}/clients/{r[0]}",
            })
    except Exception:
        pass

    # Cases
    try:
        rows = db.execute(
            text("""
                SELECT c.id,
                       COALESCE(c.case_name, c.case_number, 'Processo #' || c.id) AS titulo,
                       c.case_number,
                       COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente
                FROM cases c
                LEFT JOIN clients cl ON cl.id = c.client_id
                WHERE c.org_id = :org_id
                  AND (c.case_name ILIKE :q OR c.case_number ILIKE :q
                       OR cl.first_name ILIKE :q OR cl.last_name ILIKE :q)
                ORDER BY COALESCE(c.updated_at, c.created_at) DESC NULLS LAST
                LIMIT 5
            """),
            {"q": like, "org_id": org_id},
        ).fetchall()
        for r in rows:
            subtitle_parts = []
            if r[2]:
                subtitle_parts.append(r[2])
            if r[3] and r[3].strip():
                subtitle_parts.append(f"cliente {r[3]}")
            results.append({
                "kind": "Processo",
                "title": r[1],
                "subtitle": " · ".join(subtitle_parts),
                "href": f"{PREFIX}/cases/{r[0]}",
            })
    except Exception:
        pass

    # Prazos
    try:
        rows = db.execute(
            text("""
                SELECT p.id, p.tipo, p.data_vencimento,
                       COALESCE(p.processo_override, c.case_number, '') AS processo
                FROM prazos_processuais p
                LEFT JOIN cases c ON c.id = p.case_id
                WHERE p.org_id = :org_id
                  AND (p.tipo ILIKE :q OR p.processo_override ILIKE :q
                       OR c.case_number ILIKE :q OR p.observacao ILIKE :q)
                ORDER BY p.data_vencimento ASC NULLS LAST
                LIMIT 5
            """),
            {"q": like, "org_id": org_id},
        ).fetchall()
        for r in rows:
            subtitle = f"vence {r[2]}"
            if r[3]:
                subtitle += f" · processo {r[3]}"
            results.append({
                "kind": "Prazo",
                "title": r[1] or "Prazo",
                "subtitle": subtitle,
                "href": f"{PREFIX}/controladoria",
            })
    except Exception:
        pass

    # Tasks
    try:
        rows = db.execute(
            text("""
                SELECT id, title, status, due_date
                FROM tasks
                WHERE org_id = :org_id
                  AND title ILIKE :q
                ORDER BY due_date ASC NULLS LAST, updated_at DESC NULLS LAST
                LIMIT 5
            """),
            {"q": like, "org_id": org_id},
        ).fetchall()
        for r in rows:
            subtitle = r[2] or "pendente"
            if r[3]:
                subtitle += f" · {r[3]}"
            results.append({
                "kind": "Tarefa",
                "title": r[1],
                "subtitle": subtitle,
                "href": f"{PREFIX}/tasks/kanban",
            })
    except Exception:
        pass

    return JSONResponse({"results": results})
