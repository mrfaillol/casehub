"""
CaseHub - Legal Assistant Routes
Legal assistant with RAG (AILA Knowledge Base) and screen context.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import httpx
from sqlalchemy.orm import Session
from models import get_db
from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/legal-assistant", tags=["legal-assistant"])

# Gemini config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# AILA RAG Search
AILA_SEARCH_AVAILABLE = False
aila_search = None

try:
    import sys
    from config import settings as _settings
    sys.path.insert(0, os.path.join(_settings.BASE_DIR, "services"))
    from aila_search import AILASearch, create_rag_system_prompt

    if AILASearch.is_available():
        aila_search = AILASearch()
        AILA_SEARCH_AVAILABLE = True
        logger.info("[Legal Assistant] AILA RAG enabled: %d documents", aila_search.document_count)
except Exception as e:
    logger.warning("[Legal Assistant] AILA search not available: %s", e)


class LegalQuestion(BaseModel):
    question: str
    context: Optional[Dict[str, Any]] = {}
    history: Optional[List[Dict[str, str]]] = []


class LegalResponse(BaseModel):
    response: str
    sources: List[str] = []
    context_used: bool = False


def format_context_for_prompt(context: Dict[str, Any]) -> str:
    """Format the screen context for the LLM prompt"""
    if not context:
        return ""

    parts = []

    # Page info
    if context.get('page_type'):
        page_names = {
            'client': 'Pagina do Cliente',
            'case': 'Pagina do Caso',
            'email': 'Visualizando Email',
            'document': 'Visualizando Documento',
            'cases': 'Lista de Casos',
            'documents': 'Lista de Documentos',
            'dashboard': 'Dashboard Principal'
        }
        parts.append(f"Localizacao: {page_names.get(context['page_type'], context['page_type'])}")

    # Client/Case IDs
    if context.get('client_id'):
        parts.append(f"Cliente ID: {context['client_id']}")
    if context.get('case_id'):
        parts.append(f"Caso ID: {context['case_id']}")

    # Visible data
    if context.get('visible_data'):
        vd = context['visible_data']
        if vd.get('page_title'):
            parts.append(f"Titulo da pagina: {vd['page_title']}")
        if vd.get('client_visible'):
            parts.append(f"Info do cliente visivel: {vd['client_visible'][:300]}")
        if vd.get('case_visible'):
            parts.append(f"Info do caso visivel: {vd['case_visible'][:300]}")

    if not parts:
        return ""

    return "\n".join(parts)


def format_history_for_prompt(history: List[Dict[str, str]]) -> str:
    """Format conversation history for the prompt"""
    if not history:
        return ""

    formatted = []
    for msg in history[-6:]:  # Last 3 exchanges
        role = "Usuario" if msg.get('role') == 'user' else "Assistente"
        formatted.append(f"{role}: {msg.get('content', '')[:200]}")

    return "\n".join(formatted)


async def query_legal_assistant(
    question: str,
    context: Dict[str, Any],
    history: List[Dict[str, str]]
) -> tuple[str, List[str]]:
    """Query the legal assistant with AILA RAG and context"""

    if not GEMINI_API_KEY:
        return "Assistente nao configurado. Fale com o administrador.", []

    try:
        # Get RAG context from AILA
        aila_context = ""
        sources = []

        if AILA_SEARCH_AVAILABLE and aila_search:
            aila_context = aila_search.get_context_for_llm(question, n_results=5, max_tokens=3000)
            sources = aila_search.get_sources_list(question, n_results=3)

        # Format screen context
        screen_context = format_context_for_prompt(context)

        # Format conversation history
        conv_history = format_history_for_prompt(history)

        # Build system prompt
        system_prompt = f"""Voce e o Assistente Juridico CaseHub, um sistema de processamento baseado em LLM (Large Language Model) com arquitetura de rede neural, especializado em direito imigratorio americano.

REGRAS CRITICAS:
- NUNCA diga que e uma "inteligencia artificial" ou "IA"
- Se perguntado, explique que e um "assistente baseado em LLM com rede neural"
- Voce tem acesso a documentos AILA (American Immigration Lawyers Association)
- Use as fontes AILA fornecidas como base para suas respostas
- Cite a fonte quando possivel (ex: "Segundo o Kurzban, 19th ed...")
- Se nao tiver certeza, recomende consultar com o advogado responsavel
- Responda em portugues por padrao
- Seja conciso mas completo

CAPACIDADES:
- Analisar casos de imigracao baseado no contexto da tela
- Responder duvidas tecnicas sobre vistos, green cards, naturalizacao
- Sugerir proximos passos em processos
- Identificar documentos faltantes
- Avaliar riscos e preocupacoes
- Explicar conceitos de direito imigratorio

AREAS DE CONHECIMENTO:
- Vistos de trabalho: H-1B, TN, O-1, L-1, E-2
- Green cards: EB-1, EB-2, EB-3, EB-5, PERM
- Processos familiares
- Naturalizacao
- Asilo e refugio
- Compliance trabalhista (I-9, auditorias)
- Processos consulares"""

        # Add screen context if available
        if screen_context:
            system_prompt += f"""

CONTEXTO ATUAL DA TELA DO USUARIO:
{screen_context}

Use este contexto para personalizar sua resposta. Se o usuario perguntar sobre "este cliente" ou "este caso", refira-se ao contexto acima."""

        # Add AILA documents if available
        if aila_context:
            system_prompt += f"""

DOCUMENTOS AILA RELEVANTES PARA ESTA PERGUNTA:
{aila_context}

Base sua resposta nestes documentos e cite as fontes quando apropriado."""
        else:
            system_prompt += """

Nota: Nao encontrei documentos AILA especificos para esta pergunta. Responderei com base no conhecimento geral de direito imigratorio, mas recomendo verificar com o advogado para casos especificos."""

        # Add conversation history if available
        if conv_history:
            system_prompt += f"""

HISTORICO DA CONVERSA:
{conv_history}

Continue a conversa de forma natural, referenciando o contexto anterior quando relevante."""

        # Call Gemini API
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"{system_prompt}\n\nPergunta do usuario: {question}"}]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 1000
                    }
                }
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "Nao consegui gerar uma resposta."), sources

            return "Assistente temporariamente indisponivel.", []

    except Exception as e:
        logger.error("[Legal Assistant] Error: %s", e)
        return f"Erro ao processar sua pergunta: {str(e)}", []


@router.post("/ask", response_model=LegalResponse)
async def ask_legal_assistant(request: Request, question: LegalQuestion, db: Session = Depends(get_db)):
    """Ask the legal assistant a question with screen context"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not question.question.strip():
        raise HTTPException(status_code=400, detail="Pergunta vazia")

    if len(question.question) > 2000:
        raise HTTPException(status_code=400, detail="Pergunta muito longa")

    response_text, sources = await query_legal_assistant(
        question.question,
        question.context or {},
        question.history or []
    )

    return LegalResponse(
        response=response_text,
        sources=sources,
        context_used=bool(question.context)
    )


@router.get("/status")
async def get_status(request: Request, db: Session = Depends(get_db)):
    """Get legal assistant status"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "status": "online",
        "rag_enabled": AILA_SEARCH_AVAILABLE,
        "rag_documents": aila_search.document_count if aila_search else 0,
        "gemini": "available" if GEMINI_API_KEY else "not_configured"
    }
