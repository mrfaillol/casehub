"""
CaseHub - Team Chat Routes (RAG-Enhanced)
Internal chat with @whatsapp, @assistente (RAG), and inter-user messaging.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json
import os
import httpx
import sys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# In-memory storage (para MVP - pode migrar para DB depois)
CHAT_MESSAGES = []
from config import settings as _settings
CHAT_FILE = os.path.join(_settings.BASE_DIR, "data", "team_chat.json")
MAX_MESSAGES = 200
ONLINE_USERS = {}

# Gemini config for @assistente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# AILA RAG Search
AILA_SEARCH_AVAILABLE = False
aila_search = None

try:
    # Try to import AILA search
    sys.path.insert(0, os.path.join(_settings.BASE_DIR, "services"))
    from aila_search import AILASearch, create_rag_system_prompt

    if AILASearch.is_available():
        aila_search = AILASearch()
        AILA_SEARCH_AVAILABLE = True
        logger.info("[Team Chat] AILA RAG enabled: %d documents", aila_search.document_count)
    else:
        logger.info("[Team Chat] AILA vectors not found, using standard assistant")
except Exception as e:
    logger.warning("[Team Chat] AILA search not available: %s", e)


class ChatMessage(BaseModel):
    text: str


class MessageResponse(BaseModel):
    id: int
    user_id: int
    sender: str
    text: str
    time: str
    is_bot: bool = False
    is_assistant: bool = False


def load_messages():
    """Load messages from file"""
    global CHAT_MESSAGES
    try:
        if os.path.exists(CHAT_FILE):
            with open(CHAT_FILE, 'r') as f:
                CHAT_MESSAGES = json.load(f)
        else:
            os.makedirs(os.path.dirname(CHAT_FILE), exist_ok=True)
            CHAT_MESSAGES = []
    except Exception as e:
        logger.error("Error loading chat: %s", e)
        CHAT_MESSAGES = []


def save_messages():
    """Save messages to file"""
    try:
        os.makedirs(os.path.dirname(CHAT_FILE), exist_ok=True)
        with open(CHAT_FILE, 'w') as f:
            json.dump(CHAT_MESSAGES[-MAX_MESSAGES:], f)
    except Exception as e:
        logger.error("Error saving chat: %s", e)


def get_current_user(request: Request):
    """Get current user from session"""
    user = getattr(request.state, 'user', None)
    if not user:
        try:
            # Try to get from session scope (requires SessionMiddleware)
            session = request.scope.get('session', {})
            user_id = session.get('user_id')
            if user_id:
                return {"id": user_id, "name": session.get('user_name', 'User')}
        except Exception:
            pass
        # Fallback: return default user for now
        return {"id": 1, "name": "Team"}
    return user


def add_message(user_id: int, sender: str, text: str, is_bot: bool = False, is_assistant: bool = False):
    """Add a message to chat"""
    msg = {
        "id": len(CHAT_MESSAGES) + 1,
        "user_id": user_id,
        "sender": sender,
        "text": text,
        "time": datetime.now().strftime("%H:%M"),
        "timestamp": datetime.now().isoformat(),
        "is_bot": is_bot,
        "is_assistant": is_assistant
    }
    CHAT_MESSAGES.append(msg)
    save_messages()
    return msg


async def call_whatsapp_bot(message: str, user_name: str) -> str:
    """Call WhatsApp bot to process a message"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_settings.WHATSAPP_BOT_URL}/api/chat/internal",
                json={
                    "message": message,
                    "from": user_name,
                    "source": "casehub_chat"
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "Desculpe, nao consegui processar sua mensagem.")
            return "WhatsApp Bot esta temporariamente indisponivel."
    except Exception as e:
        logger.error("WhatsApp bot error: %s", e)
        return "Nao foi possivel conectar ao WhatsApp Bot no momento."


async def call_assistant(message: str, user_name: str) -> str:
    """Call Gemini API for assistant responses with RAG if available"""
    if not GEMINI_API_KEY:
        return "Assistente nao configurado. Fale com o administrador."

    try:
        # Get RAG context if available
        context = ""
        sources = []

        if AILA_SEARCH_AVAILABLE and aila_search:
            context = aila_search.get_context_for_llm(message, n_results=5, max_tokens=3000)
            sources = aila_search.get_sources_list(message, n_results=3)

            if context:
                logger.debug("[Assistant] Found %d relevant sources for query", len(sources))

        # Create system prompt (RAG-enhanced if context available)
        if context:
            system_prompt = create_rag_system_prompt(message, context)
        else:
            # Fallback to standard prompt
            system_prompt = f"""Voce e o Assistente CaseHub, um sistema de processamento de linguagem baseado em LLM (Large Language Model) com arquitetura de rede neural.

REGRAS IMPORTANTES:
- NUNCA diga que e uma "inteligencia artificial" ou "IA"
- Se perguntado, explique que e um "assistente baseado em LLM com rede neural"
- Voce auxilia a equipe do {_settings.ORG_NAME}
- Responda de forma profissional e concisa
- Para perguntas tecnicas de imigracao, recomende consultar os documentos AILA ou o advogado

Voce ajuda a equipe do {_settings.ORG_NAME} com:
- Informacoes sobre casos e clientes
- Duvidas sobre processos de imigracao
- Suporte ao uso do CaseHub
- Respostas rapidas sobre procedimentos"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"{system_prompt}\n\nMensagem de {user_name}: {message}"}]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 800
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
                        response_text = parts[0].get("text", "Nao consegui gerar uma resposta.")

                        # Add sources if using RAG
                        if sources and AILA_SEARCH_AVAILABLE:
                            sources_text = "\n\n_Fontes: " + ", ".join(sources[:3]) + "_"
                            response_text += sources_text

                        return response_text

            return "Assistente temporariamente indisponivel."
    except Exception as e:
        logger.error("Gemini error: %s", e)
        return "Erro ao processar sua pergunta. Tente novamente."


@router.get("/messages")
async def get_messages(request: Request, since: int = 0):
    """Get chat messages"""
    load_messages()

    user = get_current_user(request)
    if user:
        ONLINE_USERS[user.get('id', 0)] = datetime.now()

    # Clean old online users (inactive > 1 min)
    cutoff = datetime.now().timestamp() - 60
    active = {k: v for k, v in ONLINE_USERS.items() if v.timestamp() > cutoff}
    ONLINE_USERS.clear()
    ONLINE_USERS.update(active)

    # Filter messages since ID
    if since > 0:
        messages = [m for m in CHAT_MESSAGES if m.get('id', 0) > since]
    else:
        messages = CHAT_MESSAGES[-50:]

    return {
        "messages": messages,
        "online": max(1, len(ONLINE_USERS)),
        "rag_enabled": AILA_SEARCH_AVAILABLE,
        "rag_documents": aila_search.document_count if aila_search else 0
    }


@router.get("/unread")
async def get_unread(request: Request):
    """Get unread message count"""
    return {"count": 0}


@router.get("/status")
async def get_status():
    """Get chat service status including RAG availability"""
    return {
        "status": "online",
        "rag_enabled": AILA_SEARCH_AVAILABLE,
        "rag_documents": aila_search.document_count if aila_search else 0,
        "whatsapp_bot": "available",
        "gemini": "available" if GEMINI_API_KEY else "not_configured"
    }


@router.post("/send")
async def send_message(request: Request, msg: ChatMessage):
    """Send a chat message"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Nao autenticado")

    user_id = user.get('id', 0)
    user_name = user.get('name', 'Usuario')
    text = msg.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Mensagem vazia")

    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Mensagem muito longa")

    load_messages()

    # Add user message
    user_msg = add_message(user_id, user_name, text)

    # Check for mentions
    text_lower = text.lower()

    # Handle @whatsapp mention
    if "@whatsapp" in text_lower:
        clean_text = text.replace("@whatsapp", "").replace("@Whatsapp", "").strip()
        bot_response = await call_whatsapp_bot(clean_text, user_name)
        add_message(0, "WhatsApp Bot", bot_response, is_bot=True)

    # Handle @assistente mention
    if "@assistente" in text_lower:
        clean_text = text.replace("@assistente", "").replace("@Assistente", "").strip()
        assistant_response = await call_assistant(clean_text, user_name)
        add_message(0, "Assistente CaseHub", assistant_response, is_assistant=True)

    return {"success": True, "message": user_msg}
