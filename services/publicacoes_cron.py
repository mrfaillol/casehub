"""
CaseHub Lite — Daily Publication Scanner
Runs daily at 6:00 AM to check for new court publications.
Checks all monitored processos and notifies users of new movements.

Usage (standalone):
    python -m services.publicacoes_cron

Usage (from scheduler/cron):
    0 6 * * * cd /path/to/casehub && python -m services.publicacoes_cron

Usage (from app):
    from services.publicacoes_cron import scan_publicacoes
    await scan_publicacoes()
"""
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

from config import settings
from services.datajud import datajud_client
from services.escavador import escavador_client
from services.jusbrasil import jusbrasil_client

logger = logging.getLogger(__name__)


async def _get_monitored_processos() -> List[Dict[str, Any]]:
    """
    Retrieve all processos that should be scanned for new movements.
    Queries the database for cases with CNJ numbers attached.

    Returns:
        List of dicts with keys: case_id, numero_cnj, client_name, user_ids
    """
    try:
        from models import get_db_context, Case, Client
        from sqlalchemy import and_

        with get_db_context() as db:
            # Find cases with processo numbers
            cases = (
                db.query(Case)
                .filter(
                    Case.processo_numero.isnot(None),
                    Case.processo_numero != "",
                    Case.status.notin_(["closed", "archived", "cancelled"]),
                )
                .all()
            )

            processos = []
            for case in cases:
                client_name = ""
                if case.client:
                    client_name = f"{case.client.first_name or ''} {case.client.last_name or ''}".strip()

                # Collect user IDs who should be notified (assigned attorney + paralegals)
                user_ids = set()
                if case.assigned_to:
                    user_ids.add(case.assigned_to)
                if hasattr(case, "paralegal_id") and case.paralegal_id:
                    user_ids.add(case.paralegal_id)

                processos.append({
                    "case_id": case.id,
                    "numero_cnj": case.processo_numero,
                    "client_name": client_name,
                    "user_ids": list(user_ids),
                    "tribunal": getattr(case, "tribunal", None),
                })

            logger.info("Found %d monitored processos", len(processos))
            return processos

    except ImportError:
        logger.warning("Database models not available — cannot retrieve monitored processos")
        return []
    except Exception as e:
        logger.error("Error retrieving monitored processos: %s", e)
        return []


async def _check_processo_datajud(numero_cnj: str, tribunal: str = None) -> List[Dict]:
    """Check DataJud for new movements on a processo."""
    try:
        movimentacoes = await datajud_client.get_movimentacoes(numero_cnj, tribunal)
        return movimentacoes
    except Exception as e:
        logger.warning("DataJud check failed for %s: %s", numero_cnj, e)
        return []


async def _check_processo_escavador(numero_cnj: str) -> List[Dict]:
    """Check Escavador for new movements on a processo."""
    if not escavador_client.is_configured:
        return []
    try:
        resultado = await escavador_client.buscar_processo(numero_cnj)
        if resultado.get("mock"):
            return []
        data = resultado.get("data", resultado)
        processo_id = data.get("id")
        if processo_id:
            return await escavador_client.get_movimentacoes(processo_id)
        return []
    except Exception as e:
        logger.warning("Escavador check failed for %s: %s", numero_cnj, e)
        return []


async def _check_publicacoes_escavador(nome: str = None, oab: str = None) -> List[Dict]:
    """Check Escavador for new Diário publications."""
    if not escavador_client.is_configured:
        return []
    try:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        pubs = await escavador_client.buscar_publicacoes(
            nome=nome, oab=oab, data_inicio=yesterday
        )
        if pubs and not any(p.get("_mock") for p in pubs):
            return pubs
        return []
    except Exception as e:
        logger.warning("Escavador publicacoes check failed: %s", e)
        return []


async def _check_publicacoes_jusbrasil(termos: str) -> List[Dict]:
    """Check JusBrasil for new Diário publications."""
    if not jusbrasil_client.is_configured:
        return []
    try:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        pubs = await jusbrasil_client.buscar_diarios(termos, data=yesterday)
        if pubs and not any(p.get("_mock") for p in pubs):
            return pubs
        return []
    except Exception as e:
        logger.warning("JusBrasil publicacoes check failed: %s", e)
        return []


def _filter_new_movements(
    movimentacoes: List[Dict],
    since: datetime = None,
) -> List[Dict]:
    """
    Filter movements to only those after a given date.
    Defaults to yesterday if no date is provided.
    """
    if since is None:
        since = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())

    new_movs = []
    for mov in movimentacoes:
        # DataJud uses "dataHora", Escavador/JusBrasil use "data"
        mov_date_str = mov.get("dataHora") or mov.get("data") or ""
        if not mov_date_str:
            continue
        try:
            # Handle both "2024-12-01T10:30:00" and "2024-12-01" formats
            if "T" in mov_date_str:
                mov_date = datetime.fromisoformat(mov_date_str.replace("Z", "+00:00").split("+")[0])
            else:
                mov_date = datetime.strptime(mov_date_str[:10], "%Y-%m-%d")
            if mov_date >= since:
                new_movs.append(mov)
        except (ValueError, TypeError):
            continue

    return new_movs


async def notificar_novos_andamentos(
    case_id: int,
    numero_cnj: str,
    client_name: str,
    user_ids: List[int],
    new_movements: List[Dict],
) -> int:
    """
    Create in-app notifications for new movements on a processo.

    Args:
        case_id: CaseHub case ID.
        numero_cnj: CNJ process number.
        client_name: Name of the client for display.
        user_ids: List of user IDs to notify.
        new_movements: List of new movement dicts.

    Returns:
        Number of notifications created.
    """
    if not new_movements or not user_ids:
        return 0

    try:
        from models import get_db_context
        from services.notifications import create_notification
    except ImportError:
        logger.warning("Notification service not available — skipping notifications")
        return 0

    count = 0
    try:
        with get_db_context() as db:
            for mov in new_movements[:10]:  # Cap at 10 notifications per processo
                descricao = mov.get("descricao") or mov.get("complementosTabelados", [{}])[0].get("descricao", "Nova movimentação") if isinstance(mov.get("complementosTabelados"), list) and mov.get("complementosTabelados") else mov.get("descricao", "Nova movimentação")
                mov_date = mov.get("dataHora") or mov.get("data") or ""

                title = f"Nova movimentação — {numero_cnj}"
                if client_name:
                    title = f"Movimentação ({client_name}) — {numero_cnj}"

                message = f"{descricao}"
                if mov_date:
                    message = f"[{mov_date[:10]}] {descricao}"

                for user_id in user_ids:
                    try:
                        create_notification(
                            db=db,
                            user_id=user_id,
                            title=title[:255],
                            notification_type="tribunal_movimentacao",
                            message=message[:1000],
                            severity="info",
                            case_id=case_id,
                            action_url=f"{settings.PREFIX}/tribunal/processo/{numero_cnj}",
                        )
                        count += 1
                    except Exception as e:
                        logger.error("Failed to create notification for user %d: %s", user_id, e)

            db.commit()
    except Exception as e:
        logger.error("Error creating notifications: %s", e)

    logger.info(
        "Created %d notifications for processo %s (%d new movements)",
        count, numero_cnj, len(new_movements),
    )
    return count


async def scan_publicacoes() -> Dict[str, Any]:
    """
    Main scanner function. Queries APIs for all monitored processos
    and creates notifications for new movements.

    Returns:
        Summary dict with counts of processos checked, new movements found, notifications created.
    """
    logger.info("=== Daily Publication Scanner started at %s ===", datetime.now().isoformat())

    summary = {
        "started_at": datetime.now().isoformat(),
        "processos_checked": 0,
        "new_movements_total": 0,
        "notifications_created": 0,
        "errors": 0,
        "apis_available": [],
    }

    # Check which APIs are available
    summary["apis_available"].append("DataJud")
    if escavador_client.is_configured:
        summary["apis_available"].append("Escavador")
    if jusbrasil_client.is_configured:
        summary["apis_available"].append("JusBrasil")

    logger.info("APIs available: %s", summary["apis_available"])

    # Get monitored processos from database
    processos = await _get_monitored_processos()
    if not processos:
        logger.info("No monitored processos found — nothing to scan")
        summary["finished_at"] = datetime.now().isoformat()
        return summary

    for proc in processos:
        numero_cnj = proc["numero_cnj"]
        tribunal = proc.get("tribunal")
        summary["processos_checked"] += 1

        try:
            # Gather movements from all available sources
            all_movements = []

            # DataJud (always available, free)
            datajud_movs = await _check_processo_datajud(numero_cnj, tribunal)
            all_movements.extend(datajud_movs)

            # Escavador (if configured)
            escavador_movs = await _check_processo_escavador(numero_cnj)
            all_movements.extend(escavador_movs)

            # Filter to only new movements (since yesterday)
            new_movements = _filter_new_movements(all_movements)

            if new_movements:
                # Deduplicate by date + description
                seen = set()
                unique_movements = []
                for mov in new_movements:
                    key = (
                        (mov.get("dataHora") or mov.get("data", ""))[:10],
                        mov.get("descricao", "")[:100],
                    )
                    if key not in seen:
                        seen.add(key)
                        unique_movements.append(mov)

                summary["new_movements_total"] += len(unique_movements)

                # Create notifications
                notif_count = await notificar_novos_andamentos(
                    case_id=proc["case_id"],
                    numero_cnj=numero_cnj,
                    client_name=proc["client_name"],
                    user_ids=proc["user_ids"],
                    new_movements=unique_movements,
                )
                summary["notifications_created"] += notif_count

                logger.info(
                    "Processo %s: %d new movements, %d notifications",
                    numero_cnj, len(unique_movements), notif_count,
                )
            else:
                logger.debug("Processo %s: no new movements", numero_cnj)

        except Exception as e:
            summary["errors"] += 1
            logger.error("Error scanning processo %s: %s", numero_cnj, e, exc_info=True)

    summary["finished_at"] = datetime.now().isoformat()

    logger.info(
        "=== Daily Publication Scanner finished === "
        "Checked: %d | New movements: %d | Notifications: %d | Errors: %d",
        summary["processos_checked"],
        summary["new_movements_total"],
        summary["notifications_created"],
        summary["errors"],
    )

    return summary


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = asyncio.run(scan_publicacoes())
    print(f"\nScan complete: {result}")
