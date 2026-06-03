"""
CaseHub - LLM Thread Summarizer
Uses Gemini to create summaries of ENTIRE EMAIL THREADS (conversations)
"""
import os
import logging
from typing import List, Dict, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Initialize Gemini
_model = None

def _get_model():
    global _model
    if _model is None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            _model = genai.GenerativeModel('gemini-2.0-flash')
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            return None
    return _model


THREAD_SUMMARY_PROMPT = """Voce e assistente juridico.

Abaixo esta a THREAD COMPLETA de emails entre o escritorio e o cliente. Resuma a conversa inteira em PORTUGUES:

1. **Contexto:** Qual e o assunto/caso sendo discutido?
2. **Status Atual:** O que esta pendente ou foi resolvido?
3. **Proximos Passos:** O que o cliente precisa fazer ou espera do escritorio?
4. **Urgencia:** Ha prazo ou urgencia mencionada?

---
THREAD DE EMAILS (do mais antigo ao mais recente):
---
{thread_content}
---

RESUMO DA CONVERSA (2-4 frases):"""


def _get_base_subject(subject: str) -> str:
    """Remove Re:, Fwd:, etc. to get base subject"""
    if not subject:
        return ''
    base = subject
    prefixes = ['re:', 'fwd:', 'fw:', 'enc:', 'res:', 'rep.:']
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if base.lower().startswith(prefix):
                base = base[len(prefix):].strip()
                changed = True
    return base.strip()


def get_thread_emails(db: Session, sender_email: str, subject: str) -> List[Dict]:
    """Busca todos os emails da mesma thread (mesmo sender + subject base)"""
    base_subject = _get_base_subject(subject)
    
    if not base_subject:
        return []
    
    try:
        result = db.execute(text("""
            SELECT sender, body_text, received_at, direction
            FROM email_messages
            WHERE (
                sender ILIKE :sender_pattern
                OR sender ILIKE :org_email_pattern
            )
            AND (
                LOWER(subject) LIKE LOWER(:subject_pattern1)
                OR LOWER(subject) LIKE LOWER(:subject_pattern2)
                OR LOWER(subject) LIKE LOWER(:subject_pattern3)
            )
            ORDER BY received_at ASC
            LIMIT 15
        """), {
            "sender_pattern": f"%{sender_email}%",
            "subject_pattern1": f"%{base_subject}%",
            "subject_pattern2": f"Re: %{base_subject}%",
            "subject_pattern3": f"Re: Re: %{base_subject}%"
        })
        
        emails = [dict(row._mapping) for row in result.fetchall()]
        logger.info(f"Found {len(emails)} emails in thread for subject: {base_subject[:50]}")
        return emails
        
    except Exception as e:
        logger.error(f"Error fetching thread emails: {e}")
        return []


def format_thread_for_llm(emails: List[Dict]) -> str:
    """Formata a thread para o prompt do LLM"""
    thread_text = ""
    for i, email in enumerate(emails, 1):
        sender = email.get("sender", "Unknown")
        date = str(email.get("received_at", ""))[:19]
        direction = email.get("direction", "inbound")
        body = (email.get("body_text") or "")[:800]  # Limita cada email
        
        # Simplificar sender
        org_domain = os.getenv("ORG_DOMAIN", "")
        if org_domain and f"@{org_domain}" in sender.lower():
            sender_label = "Office"
        else:
            sender_label = "Cliente"
        
        thread_text += f"\n--- Email {i} ({date}) - {sender_label} ---\n"
        thread_text += f"{body}\n"
    
    return thread_text[:6000]  # Limite total para o LLM


def summarize_thread_sync(db: Session, sender_email: str, subject: str) -> str:
    """Busca toda a thread e gera resumo com LLM (versao sincrona)"""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not configured")
        return "(API nao configurada)"
    
    try:
        # 1. Buscar todos emails da thread
        thread_emails = get_thread_emails(db, sender_email, subject)
        
        if not thread_emails:
            return "(Thread com apenas 1 email)"
        
        if len(thread_emails) == 1:
            # Se so tem 1 email, resumir ele diretamente
            body = (thread_emails[0].get("body_text") or "")[:1500]
            return _summarize_single_email(body)
        
        # 2. Formatar para o LLM
        thread_content = format_thread_for_llm(thread_emails)
        
        # 3. Gerar resumo
        model = _get_model()
        if not model:
            return "(Erro ao inicializar LLM)"
        
        prompt = THREAD_SUMMARY_PROMPT.format(thread_content=thread_content)
        response = model.generate_content(prompt)
        
        summary = response.text.strip()
        logger.info(f"Generated thread summary: {summary[:100]}...")
        return summary
        
    except Exception as e:
        logger.error(f"Error summarizing thread: {e}")
        return f"(Erro ao resumir: {str(e)[:30]})"


def _summarize_single_email(body: str) -> str:
    """Resumo de um unico email"""
    try:
        model = _get_model()
        if not model:
            return "(Erro ao inicializar LLM)"
        
        prompt = f"""Resuma este email de cliente em 1-2 frases em portugues. 
O que o cliente quer ou precisa?

Email:
{body[:1500]}

Resumo:"""
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error summarizing single email: {e}")
        return "(Erro ao resumir)"


# Alias for backwards compatibility
async def summarize_thread(db: Session, sender_email: str, subject: str) -> str:
    """Async wrapper for summarize_thread_sync"""
    return summarize_thread_sync(db, sender_email, subject)
