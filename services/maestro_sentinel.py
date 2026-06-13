"""
CaseHub — Maestro Sentinel
Notificações proativas no #equipe: prazos em ≤3 dias, tarefas atrasadas,
compromissos de amanhã. Roda diariamente via cron ou HTTP trigger.
Posta como MAESTRO_UID (-1) para não criar usuário virtual no banco.
Dedup por dia: não posta novamente se já há mensagem [sentinel] hoje.
"""
import logging
from datetime import date, timedelta
from sqlalchemy import text
from models.base import SessionLocal

logger = logging.getLogger(__name__)

MAESTRO_UID = -1
SENTINEL_TAG = "[sentinel]"
MAX_BODY = 2000


def _get_equipe_channel_id(db, org_id: int) -> int:
    """Retorna o channel_id do canal #equipe (kind='channel') da org, ou 0."""
    try:
        row = db.execute(
            text("SELECT id FROM team_channels WHERE org_id = :o AND kind = 'channel' ORDER BY id LIMIT 1"),
            {"o": org_id},
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception as e:
        logger.warning("sentinel: team_channels indisponível org=%s: %s", org_id, e)
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def _already_posted_today(db, org_id: int, cid: int) -> bool:
    """True se o sentinel já postou mensagem [sentinel] hoje neste canal."""
    try:
        row = db.execute(
            text("""
                SELECT 1 FROM team_messages
                WHERE org_id = :o AND channel_id = :c AND user_id = :u
                  AND body LIKE :tag AND created_at >= CURRENT_DATE
                LIMIT 1
            """),
            {"o": org_id, "c": cid, "u": MAESTRO_UID, "tag": f"{SENTINEL_TAG}%"},
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _post_as_maestro(db, org_id: int, cid: int, body: str) -> int:
    """Posta body no canal cid como MAESTRO_UID. Retorna msg_id ou 0."""
    try:
        body = str(body or "").strip()[:MAX_BODY]
        if not body:
            return 0
        db.execute(
            text("INSERT INTO team_messages (org_id, channel_id, user_id, body) VALUES (:o, :c, :u, :b)"),
            {"o": org_id, "c": cid, "u": MAESTRO_UID, "b": body},
        )
        db.commit()
        return int(db.execute(
            text("SELECT MAX(id) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
            {"o": org_id, "c": cid},
        ).scalar() or 0)
    except Exception as e:
        logger.error("sentinel: falha ao postar org=%s canal=%s: %s", org_id, cid, e)
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def _build_alert_message(db, org_id: int) -> str:
    """Constrói o resumo diário para a org. Retorna '' se não há alertas."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    in_3 = today + timedelta(days=3)

    lines = [f"{SENTINEL_TAG} 📋 **Resumo do dia — {today.strftime('%d/%m/%Y')}**"]
    has_alerts = False

    # 1. Prazos vencendo em até 3 dias (inclui hoje)
    try:
        rows = db.execute(text("""
            SELECT p.tipo, p.data_vencimento,
                   COALESCE(p.processo_override, c.case_number, 'sem processo') AS proc,
                   COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente
            FROM prazos_processuais p
            LEFT JOIN cases c ON c.id = p.case_id
            LEFT JOIN clients cl ON cl.id = c.client_id
            WHERE p.org_id = :oid
              AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'cancelado')
              AND p.data_vencimento IS NOT NULL
              AND p.data_vencimento BETWEEN :today AND :in3
            ORDER BY p.data_vencimento ASC
            LIMIT 10
        """), {"oid": org_id, "today": today, "in3": in_3}).fetchall()
        if rows:
            has_alerts = True
            lines.append("\n⏰ **Prazos nos próximos 3 dias:**")
            for r in rows:
                tipo = (r[0] or "Prazo processual").strip() or "Prazo processual"
                vence = r[1].strftime("%d/%m") if r[1] else "?"
                diff = (r[1] - today).days if r[1] else 0
                badge = "🔴 HOJE" if diff == 0 else ("🟡 amanhã" if diff == 1 else f"🟠 {diff}d")
                cliente = f" — {r[3]}" if (r[3] or "").strip() else ""
                lines.append(f"  • {badge}: {tipo} ({r[2]}{cliente}, {vence})")
    except Exception as e:
        logger.warning("sentinel: erro prazos org=%s: %s", org_id, e)
        try:
            db.rollback()
        except Exception:
            pass

    # 2. Tarefas atrasadas (due_date < hoje, não concluídas/canceladas)
    try:
        rows = db.execute(text("""
            SELECT t.title, t.due_date, COALESCE(u.name, u.email, '') AS resp
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to AND u.org_id = t.org_id
            WHERE t.org_id = :oid
              AND COALESCE(t.status, 'pending') NOT IN ('completed', 'cancelled')
              AND t.due_date IS NOT NULL AND t.due_date < :today
            ORDER BY t.due_date ASC
            LIMIT 8
        """), {"oid": org_id, "today": today}).fetchall()
        if rows:
            has_alerts = True
            lines.append("\n🔴 **Tarefas atrasadas:**")
            for r in rows:
                venceu = r[1].strftime("%d/%m") if r[1] else "?"
                resp = f" ({r[2]})" if (r[2] or "").strip() else ""
                lines.append(f"  • {r[0]}{resp} — venceu {venceu}")
    except Exception as e:
        logger.warning("sentinel: erro tarefas org=%s: %s", org_id, e)
        try:
            db.rollback()
        except Exception:
            pass

    # 3. Compromissos de amanhã
    try:
        rows = db.execute(text("""
            SELECT title, time_start, type, COALESCE(client_name, '') AS cliente
            FROM appointments
            WHERE org_id = :oid AND date = :tomorrow
            ORDER BY time_start ASC NULLS LAST
            LIMIT 8
        """), {"oid": org_id, "tomorrow": tomorrow}).fetchall()
        if rows:
            has_alerts = True
            lines.append(f"\n📅 **Compromissos de amanhã ({tomorrow.strftime('%d/%m')}):**")
            for r in rows:
                hora = str(r[1])[:5] if r[1] else "—"
                tipo = f" ({r[2]})" if (r[2] or "").strip() else ""
                cliente = f" — {r[3]}" if (r[3] or "").strip() else ""
                lines.append(f"  • {hora}: {r[0]}{tipo}{cliente}")
    except Exception as e:
        logger.warning("sentinel: erro agenda org=%s: %s", org_id, e)
        try:
            db.rollback()
        except Exception:
            pass

    if not has_alerts:
        return ""

    lines.append("\n_Mensagem automática. Responda aqui para interagir com o Maestro._")
    return "\n".join(lines)


def run_sentinel_for_org(org_id: int) -> bool:
    """Roda o sentinel para uma org. Retorna True se postou mensagem."""
    db = SessionLocal()
    try:
        cid = _get_equipe_channel_id(db, org_id)
        if not cid:
            logger.info("sentinel: org=%s sem canal #equipe ainda — pulando", org_id)
            return False
        if _already_posted_today(db, org_id, cid):
            logger.info("sentinel: org=%s canal=%s já postado hoje", org_id, cid)
            return False
        msg = _build_alert_message(db, org_id)
        if not msg:
            logger.info("sentinel: org=%s sem alertas hoje", org_id)
            return False
        mid = _post_as_maestro(db, org_id, cid, msg)
        if mid:
            logger.info("sentinel: msg #%s postada org=%s canal=%s", mid, org_id, cid)
        return bool(mid)
    finally:
        db.close()


def run_sentinel_all_orgs() -> dict:
    """Roda o sentinel em todas as orgs ativas."""
    db = SessionLocal()
    try:
        try:
            orgs = db.execute(text(
                "SELECT id FROM organizations WHERE COALESCE(enabled, TRUE) = TRUE"
            )).fetchall()
        except Exception:
            db.rollback()
            orgs = db.execute(text("SELECT id FROM organizations")).fetchall()
        org_ids = [r[0] for r in orgs]
    finally:
        db.close()

    posted, skipped = 0, 0
    for oid in org_ids:
        try:
            if run_sentinel_for_org(oid):
                posted += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("sentinel: erro org=%s: %s", oid, e)
            skipped += 1

    result = {"orgs_checked": len(org_ids), "posted": posted, "skipped": skipped}
    logger.info("sentinel: concluído %s", result)
    return result


if __name__ == "__main__":
    import logging as _log
    _log.basicConfig(level=_log.INFO)
    print(run_sentinel_all_orgs())
