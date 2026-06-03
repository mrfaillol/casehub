"""
CaseHub - Email Worker Status API
Endpoint para monitoramento do worker de emails
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from models import get_db
from auth import get_current_user
from datetime import datetime, timedelta
from config import settings

router = APIRouter()

@router.get("/api/email-worker/status")
async def email_worker_status(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    """Retorna status do email worker para monitoramento"""
    
    # Emails pendentes (não processados)
    _org_email = settings.ORG_EMAIL or settings.SMTP_USER or ""
    pending = db.execute(text("""
        SELECT COUNT(*) FROM email_messages
        WHERE notion_task_id IS NULL
        AND direction = 'inbound'
        AND sender NOT LIKE :org_email_pattern
        AND subject NOT LIKE '%Nova tarefa:%'
    """), {"org_email_pattern": f"%{_org_email}%"}).scalar() or 0
    
    # Última task criada
    last_task = db.execute(text("""
        SELECT notion_task_created_at FROM email_messages
        WHERE notion_task_id IS NOT NULL 
        AND notion_task_id != 'NO_PARALEGAL'
        ORDER BY notion_task_created_at DESC LIMIT 1
    """)).scalar()
    
    # Tasks criadas hoje
    tasks_today = db.execute(text("""
        SELECT COUNT(*) FROM email_messages
        WHERE notion_task_id IS NOT NULL 
        AND notion_task_id != 'NO_PARALEGAL'
        AND notion_task_created_at >= CURRENT_DATE
    """)).scalar() or 0
    
    # Emails recebidos hoje
    emails_today = db.execute(text("""
        SELECT COUNT(*) FROM email_messages
        WHERE direction = 'inbound'
        AND created_at >= CURRENT_DATE
    """)).scalar() or 0
    
    # Emails com LLM summary (últimas 24h)
    # Não temos campo específico, mas podemos inferir pelos que têm notion_task
    
    # Últimos 5 emails processados
    recent = db.execute(text("""
        SELECT id, LEFT(sender, 40) as sender, notion_task_id IS NOT NULL as has_task, 
               notion_task_created_at, created_at
        FROM email_messages
        WHERE direction = 'inbound'
        ORDER BY id DESC LIMIT 5
    """)).fetchall()
    
    recent_emails = [{
        "id": r[0],
        "sender": r[1],
        "has_task": r[2],
        "task_created": r[3].isoformat() if r[3] else None,
        "received": r[4].isoformat() if r[4] else None
    } for r in recent]
    
    # Determinar status geral
    if pending > 10:
        status = "warning"
    elif pending > 20:
        status = "critical"
    else:
        status = "healthy"
    
    return {
        "status": status,
        "pending_emails": pending,
        "tasks_today": tasks_today,
        "emails_today": emails_today,
        "last_task_created": last_task.isoformat() if last_task else None,
        "recent_emails": recent_emails,
        "worker_active": True,  # O worker está sempre ativo se o app está rodando
        "timestamp": datetime.utcnow().isoformat()
    }
