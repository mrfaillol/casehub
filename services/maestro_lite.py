"""
CaseHub Lite - Maestro Lite (AI Assistant)
Contextual AI that knows about the law firm's cases, clients, and deadlines.
Uses Ollama for local LLM inference.
"""
import httpx
import logging
import json
import re
from datetime import datetime

logger = logging.getLogger(__name__)

import os
from services.circuit_breaker import AsyncCircuitBreaker, CircuitOpenError

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "hermes3:8b")
# Hard ceiling for Ollama inference so a slow/CPU model can't pin a worker
# indefinitely (incident 2026-06-16 VS 504). Was hardcoded 180s/300s. Bounded +
# env-tunable; must stay < nginx proxy_read_timeout. Structural fix = bulkhead
# (limit concurrent LLM calls) + async/SSE (#852).
LLM_TIMEOUT_S = float(os.getenv("EXTERNAL_LLM_TIMEOUT_S", "90"))

# Shared breaker + bulkhead around the Ollama upstream (incident 2026-06-16):
# a CPU-bound model serialises generation, so without a bound every uvicorn
# worker piles up waiting on the same 300s call and the app saturates -> 504.
# max_concurrency caps how many workers can ever be parked on Ollama at once;
# the extra callers fail fast (CircuitOpenError) and return a degraded reply
# instead of hanging. Tunable via env without a redeploy of this module.
_OLLAMA_BREAKER = AsyncCircuitBreaker(
    "ollama",
    failure_threshold=int(os.getenv("OLLAMA_BREAKER_THRESHOLD", "3")),
    reset_timeout=float(os.getenv("OLLAMA_BREAKER_RESET_SECONDS", "30")),
    max_concurrency=int(os.getenv("OLLAMA_MAX_CONCURRENCY", "2")),
)


async def generate_text(prompt, *, temperature=0.4, max_tokens=400, num_ctx=8192, model=None):
    """Geração CRUA via Ollama local (/api/generate), SEM os short-circuits do
    MaestroLite.chat (jurisprudência/prazo/law-guard). Usada pelo bloco CRM do
    WhatsApp p/ resumir a conversa e sugerir próximas mensagens (Equipe CaseHub 10/06):
    local-first, zero transferência externa. Retorna str ou None.
    """
    import logging
    import httpx
    _log = logging.getLogger(__name__)
    mdl = model or DEFAULT_MODEL

    async def _do_generate():
        async with httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT_S, connect=10.0)) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": mdl,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {
                        "temperature": temperature,
                        "top_p": 0.9,
                        "num_ctx": num_ctx,
                        "num_predict": max_tokens,
                        "repeat_penalty": 1.1,
                    },
                },
            )
            resp.raise_for_status()
            return (resp.json().get("response") or "").strip()

    try:
        text = await _OLLAMA_BREAKER.call(_do_generate)
        return text or None
    except CircuitOpenError as e:
        # Upstream saturated/tripped — fail fast, do not park this worker.
        _log.warning("maestro_lite.generate_text breaker rejected (%s): %s", mdl, e)
        return None
    except Exception as e:  # noqa: BLE001
        _log.warning("maestro_lite.generate_text falhou (%s): %s", mdl, e)
        return None

ALLOWED_CHAT_HISTORY_ROLES = {"user", "assistant"}
MAX_CHAT_HISTORY_MESSAGES = 10
MAX_CHAT_HISTORY_CONTENT_CHARS = 2000


def sanitize_chat_history(history):
    """Keep user-supplied chat history from injecting system/tool messages."""
    if not isinstance(history, list):
        return []

    sanitized = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ALLOWED_CHAT_HISTORY_ROLES:
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        sanitized.append({
            "role": role,
            "content": content[:MAX_CHAT_HISTORY_CONTENT_CHARS],
        })
    return sanitized[-MAX_CHAT_HISTORY_MESSAGES:]


def repo_aware_enabled() -> bool:
    """Feature flag for the repo-aware (product knowledge) grounding.

    Default OFF — the grounding only activates when an index has been built AND
    the operator opts in via ``CASEHUB_MAESTRO_REPO_AWARE_ENABLED``. Keeping it
    flagged means a half-built index never changes assistant behaviour in prod.
    """
    raw = os.getenv("CASEHUB_MAESTRO_REPO_AWARE_ENABLED")
    if raw is None:
        try:
            from config import settings as _settings
            raw = getattr(_settings, "CASEHUB_MAESTRO_REPO_AWARE_ENABLED", "")
        except Exception:  # noqa: BLE001 — never break the chat on a config issue
            raw = ""
    return str(raw or "").lower() in {"1", "true", "yes", "on"}


# Heuristic: does the question look like it's about the PRODUCT / how to use
# CaseHub (vs. about the firm's own clients/cases/deadlines)? When it matches we
# attempt repo-index retrieval. Cheap keyword gate — retrieval itself is the real
# filter (a miss returns no context and the model says it didn't find it).
PRODUCT_QUESTION_RE = re.compile(
    r"(?ix)\b("
    r"casehub|sistema|plataforma|aplicativo|app|"
    r"como\s+(?:eu\s+)?(?:fa[çc]o|funciona|configuro|uso|cadastro|crio|ativo|habilito)|"
    r"onde\s+(?:eu\s+)?(?:configuro|encontro|acho|fica|vejo|clico)|"
    r"m[oó]dulo|funcionalidade|recurso|integra[çc][aã]o|webhook|"
    r"controladoria|agenda|kanban|tarefas|crm|maestro|whatsapp|"
    r"configura[çc][aã]o|ajuste|prefer[eê]ncia|tela|p[aá]gina|bot[aã]o|menu"
    r")\b"
)

# F44 Fase 2 (FR-1 pré-UsuarioDemo 30/05): regex detecta citação de artigo/lei na
# pergunta do usuário. Quando casa, prepend de bloco extra ANTI-ALUCINAÇÃO ao
# system prompt — modelo llama3.2:3b alucinou Art. 212 CPC na reunião QA
# (2026-05-27), retornando texto sobre jurisdição/competência. Pequenos modelos
# locais não confiam para citações textuais — força disclaimer obrigatório.
LAW_CITATION_RE = re.compile(
    r"\b(art(?:igo)?\.?\s*\d+|s[uú]mula\s*\d+|lei\s*\d+|"
    r"c[oó]digo\s+(?:civil|penal|tribut[aá]rio|processo|consumidor|trabalho)|"
    r"cpc|clt|c[fc]|cdc|ctn)\b",
    re.IGNORECASE,
)

# Jurisprudência (case law / precedentes) é distinta de citação de artigo de lei.
# Não há fonte de jurisprudência ativa (PDPJ em hold indefinido; nenhuma base de
# ementas/acórdãos validada — ver docs/maestro/pipeline-treinamento.md §3). Sem
# fonte, o Maestro RECUSA honestamente em vez de inventar julgados — alucinar
# jurisprudência é o pior caso para um produto jurídico.
JURISPRUDENCE_RE = re.compile(
    r"(?ix)\b("
    r"jurisprud[eê]ncia|ac[oó]rd[aã]o|ac[oó]rd[aã]os|ementa|"
    r"precedente|julgado|decis[aã]o\s+(?:do|da|no|na)\s+(?:stf|stj|tst|trf|tj|trt)|"
    r"entendimento\s+(?:do|dos|da)\s+(?:tribunal|stf|stj|tst)|"
    r"\bstf\b|\bstj\b|\btst\b|repetitivo|repercuss[aã]o\s+geral"
    r")\b"
)

# Resposta honesta de recusa para jurisprudência (sem fonte ativa). Determinística
# — não passa pelo modelo, então não há risco de alucinação.
# TODO(maestro-fase-N): quando houver fonte de jurisprudência validada (PDPJ
# destravado ou base de ementas/acórdãos curada — ver docs/maestro/pipeline-treinamento.md
# §3, gate aberto), trocar esta recusa por retrieval citável (mesmo padrão grounded
# do repo-aware). Até lá, recusar é o comportamento correto para um produto jurídico.
JURISPRUDENCE_REFUSAL = (
    "Ainda não tenho uma fonte de jurisprudência conectada (acórdãos, ementas e "
    "precedentes), então não posso citar ou resumir decisões de tribunais com "
    "segurança. Posso ajudar com os clientes, processos, prazos e tarefas "
    "cadastrados no CaseHub, ou com a descrição temática de um dispositivo de lei. "
    "Para jurisprudência, consulte as bases oficiais dos tribunais (ex: "
    "https://jurisprudencia.stf.jus.br ou https://scon.stj.jus.br)."
)

SYSTEM_PROMPT = """Você é o Maestro, assistente operacional do escritório {org_name} integrado ao CaseHub.
Você responde com base no contexto do CaseHub fornecido (clientes, processos, prazos, tarefas reais).
Você NÃO é um assistente genérico de IA — você é um assistente especializado nos dados reais do escritório.

REGRAS:

1. **Clientes/processos/prazos do escritório**: PRIMEIRO leia o "Contexto do escritório" abaixo. Se o nome ou termo da pergunta aparecer no contexto (mesmo que parcialmente — ex: "Costa" casa com "Costa Empreendimentos"), RESPONDA usando esses dados reais. Cite nome completo + status/processo/prazo conforme aparece.
   - Match flexível: aceitar substring case-insensitive (Costa = costa = Costa Empreendimentos).
   - Se o nome NÃO aparecer de forma alguma no contexto, responda EXATAMENTE: "Não encontrei isso no CaseHub. Verifique se está cadastrado em /clients ou /controladoria."
   - NÃO invente clientes, NÃO sugira nomes que não estão no contexto.

2. **Prazos "próximos N dias"**: o contexto tem blocos pré-computados ("Prazos vencendo em até 7/15/30 dias"). Use APENAS esses itens. Liste tipo + data + processo + cliente conforme aparece. Se o bloco N dias está vazio (ou diz "(nenhum)"), responda "Nenhum prazo vencendo nos próximos N dias."

3. **Resumo geral / resumo do dia / "o que tem hoje" / "status geral"**: NÃO descreva a história, o perfil ou o porte do escritório. Responda APENAS com dados operacionais do contexto:
   - Prazos vencendo nos próximos 7 dias (use o bloco "Prazos vencendo em até 7 dias")
   - Tarefas pendentes mais próximas (use o bloco "Tarefas pendentes")
   - Totais de clientes e processos por status
   Formato: bullet points concisos. Se algum bloco estiver vazio, informe "(nenhum)".

4. **Lei/jurisprudência** (CPC, CLT, CF, CDC, CTN, súmulas, artigos numerados): você NÃO é fonte primária. Responda apenas quando o backend fornecer o bloco "Conhecimento JURIDICO OFICIAL verificado". Sem esse bloco, recuse em vez de presumir norma, jurisprudência ou prazo legal.

5. Quando não souber e não for cliente/processo/prazo/lei: "Não tenho essa informação."

6. Sempre português brasileiro, profissional, direto. Sem floreios. Use a data atual fornecida no contexto — nunca invente ou presuma o ano.

Exemplos:
- Pergunta: "Me fala do cliente Costa" + contexto tem "Costa Empreendimentos Imobiliários S/A" → Resposta: "Costa Empreendimentos Imobiliários S/A — está cadastrado no escritório. [+ detalhes do contexto: e-mail, telefone, processos vinculados]."
- Pergunta: "Me fala do processo José da Silva" + José da Silva NÃO aparece → Resposta: "Não encontrei isso no CaseHub. Verifique se está cadastrado em /clients ou /controladoria."
- Pergunta: "Quais prazos vencem nos próximos 15 dias?" + bloco tem 2 itens → Liste os 2 itens com tipo, data, processo.
- Pergunta: "Quais prazos próximos 15 dias?" + bloco "(nenhum)" → Resposta: "Nenhum prazo vencendo nos próximos 15 dias."
- Pergunta: "O que diz o art. 212 do CPC?" sem bloco jurídico oficial → recuse. Com bloco jurídico oficial → responda apenas com base nele e cite a URL oficial.
- Pergunta: "Faça um resumo geral do escritório hoje" → Liste prazos 7 dias + tarefas pendentes + totais. NÃO descreva história do escritório.
"""

# Bloco INJETADO quando o backend recuperou fontes jurídicas oficiais. Reforça
# no contexto imediato que o modelo só pode responder com o material citável.
LEGAL_RAG_GUARD = """ATENÇÃO: A próxima pergunta menciona norma, jurisprudência, prazo legal ou fonte jurídica brasileira.
- Responda APENAS com base no bloco "Conhecimento JURIDICO OFICIAL verificado".
- CITE a autoridade e a URL oficial usadas.
- NÃO acrescente artigos, julgados, prazos, datas, teses ou requisitos que não apareçam nas fontes recuperadas.
- Se as fontes recuperadas forem insuficientes para a pergunta, diga que não encontrou fonte oficial suficiente.
"""

# Pergunta jurídica sem fonte oficial indexada deve recusar deterministicamente.
# Não deixar o Llama "descrever genericamente" norma brasileira: isso já causou
# alucinação de artigo na QA e é incompatível com o produto jurídico.
LEGAL_SOURCE_REQUIRED_REFUSAL = (
    "Ainda não encontrei uma fonte oficial indexada para responder essa questão "
    "jurídica com segurança. Para evitar inventar norma, prazo, súmula ou "
    "jurisprudência, não vou resumir nem citar esse ponto sem fonte verificável. "
    "Consulte a fonte oficial aplicável, como o Planalto, CNJ ou o tribunal "
    "competente, e me envie a referência para eu trabalhar em cima dela."
)

# Guard injetado quando há contexto do PRODUTO (repo-aware). Força grounding +
# citação + recusa de inventar. O modelo pequeno tende a "preencher lacunas" —
# este reforço imediato amarra a resposta às fontes recuperadas.
REPO_AWARE_GUARD = """ATENÇÃO: A próxima pergunta é sobre o PRODUTO CaseHub (como funciona / como usar).
- Responda APENAS com base no bloco "Conhecimento do PRODUTO CaseHub" fornecido acima.
- SEMPRE cite o arquivo-fonte entre parênteses (ex: "(fonte: routes/controladoria.py)").
- Se a resposta NÃO estiver no conhecimento do produto fornecido, responda EXATAMENTE: "Não encontrei essa informação na documentação indexada do CaseHub."
- NÃO invente caminhos de menu, nomes de botões, endpoints ou comportamentos que não estejam nas fontes.
"""

# Guard injetado quando a pergunta parece ser sobre o produto MAS nenhuma fonte
# foi recuperada (índice ausente, Ollama embed offline, ou nada relevante). Evita
# que o modelo alucine documentação inexistente.
REPO_AWARE_NO_CONTEXT_GUARD = """ATENÇÃO: A pergunta parece ser sobre o produto CaseHub, mas NÃO há fontes de produto disponíveis no contexto.
- NÃO invente como o produto funciona.
- Se for sobre clientes/processos/prazos do escritório, use o "Contexto do escritório".
- Caso contrário, responda: "Não encontrei essa informação na documentação indexada do CaseHub."
"""


class MaestroLite:
    def __init__(self, org_name="CaseHub", ollama_url=None, model=None):
        self.org_name = org_name
        self.ollama_url = ollama_url or OLLAMA_URL
        self.model = model or DEFAULT_MODEL
        self.system_prompt = SYSTEM_PROMPT.format(org_name=org_name)

    async def chat(self, message, context=None, history=None, repo_context=None,
                   legal_context=None):
        """Send message to Ollama with context.

        ``repo_context`` (optional) is the grounded PRODUCT-knowledge block
        produced by services.maestro_repo_index.retrieve_repo_context — already
        secret-redacted and citation-annotated. When present, the model is told
        to answer about the product ONLY from it and to cite the source file.
        """
        legal_context = (legal_context or "").strip()

        # Legal short-circuit: no active official source, so refuse honestly and
        # deterministically. This covers both jurisprudence and literal law
        # citation asks. With a legal_context, the source-backed guard below
        # takes over and the model may answer from retrieved sources only.
        if (
            JURISPRUDENCE_RE.search(message or "")
            and not LAW_CITATION_RE.search(message or "")
            and not legal_context
        ):
            logger.info("maestro_lite: jurisprudence asked, no source — honest refusal")
            return {
                "response": JURISPRUDENCE_REFUSAL,
                "model": self.model,
                "status": "ok",
                "refusal_code": "no_official_jurisprudence_source",
            }

        if LAW_CITATION_RE.search(message or "") and not legal_context:
            logger.info("maestro_lite: law citation asked, no official source — honest refusal")
            return {
                "response": LEGAL_SOURCE_REQUIRED_REFUSAL,
                "model": self.model,
                "status": "ok",
                "refusal_code": "no_official_legal_source",
            }

        # Calculadora determinística de prazos: se a mensagem identifica data + ato
        # processual, retorna resposta calculada sem chamar o LLM (rápido e exato).
        try:
            from services.prazo_intent import prazo_intent
            _prazo_resp = prazo_intent(message or "")
            if _prazo_resp:
                logger.info("maestro_lite: prazo_intent respondeu deterministicamente")
                return {"response": _prazo_resp, "model": "prazo_calculator", "status": "ok"}
        except Exception as _pi_err:  # noqa: BLE001
            logger.warning("maestro_lite: prazo_intent falhou (%s) -> LLM segue", _pi_err)

        messages = [{"role": "system", "content": self.system_prompt}]

        if context:
            messages.append({"role": "system", "content": f"Contexto do escritório:\n{context}"})

        # Repo-aware: inject the product-knowledge block as its own system turn so
        # the model treats it as authoritative grounding (distinct from firm data).
        if repo_context:
            messages.append({"role": "system", "content": repo_context})

        # Legal RAG grounding guard. This is separate from repo-aware product
        # grounding: official law/CNJ/tribunal sources are not tenant uploads and
        # must be cited by URL/hash.
        if legal_context:
            messages.append({"role": "system", "content": legal_context})
            messages.append({"role": "system", "content": LEGAL_RAG_GUARD})
            logger.info("maestro_lite: official legal context injected, grounding guard on")

        # Repo-aware grounding guards (injected right before the user turn so the
        # small model can't drift). Two cases: (1) we have product fonts → force
        # grounding + citation; (2) the question looks product-ish but we found
        # nothing → forbid inventing documentation.
        elif repo_context:
            messages.append({"role": "system", "content": REPO_AWARE_GUARD})
            logger.info("maestro_lite: repo context injected, grounding guard on")
        elif PRODUCT_QUESTION_RE.search(message or ""):
            messages.append({"role": "system", "content": REPO_AWARE_NO_CONTEXT_GUARD})
            logger.info("maestro_lite: product-ish question, no repo context — anti-invent guard on")

        clean_history = sanitize_chat_history(history)
        if clean_history:
            messages.extend(clean_history)

        messages.append({"role": "user", "content": message})

        # ── Provider externo (BYO-API, ex.: Gemini) tem prioridade quando
        # configurado (CASEHUB_AI_PROVIDER=gemini + GEMINI_API_KEY). É rápido e
        # raciocina de verdade; o Ollama local fica como FALLBACK. Sem chave, o
        # NullProvider devolve None e o fluxo cai direto no Ollama (inalterado).
        try:
            from services.ai_provider import get_ai_provider, NullProvider
            _provider = get_ai_provider()
            if not isinstance(_provider, NullProvider) and getattr(self, "_external_budget_ok", True):
                _tag = {"system": "INSTRUCOES", "assistant": "MAESTRO", "user": "USUARIO"}
                _prompt = "\n\n".join(
                    f"[{_tag.get(m.get('role'), 'USUARIO')}]\n{m.get('content','')}"
                    for m in messages
                ) + "\n\n[MAESTRO]\n"
                _ext = await _provider.generate(_prompt, temperature=0.2, max_tokens=800)
                if _ext:
                    try:
                        from services.maestro_budget import note_success
                        from services.maestro_redact import unredact
                        note_success()
                        _ext = unredact(_ext, getattr(self, "_egress_unmap", None))
                    except Exception:  # noqa: BLE001
                        pass
                    return {"response": _ext, "model": _provider.name, "status": "ok"}
                try:
                    from services.maestro_budget import note_failure
                    note_failure("no_response")
                except Exception:  # noqa: BLE001
                    pass
                logger.info("maestro_lite: provider %s sem resposta -> fallback Ollama", _provider.name)
        except Exception as _pe:
            try:
                from services.maestro_budget import note_failure
                note_failure(str(_pe))
            except Exception:  # noqa: BLE001
                pass
            logger.warning("maestro_lite: provider externo falhou (%s) -> fallback Ollama", _pe)

        try:
            # Timeout: llama3.2:3b on a CPU-only VPS (remote runtime alpha) needs ~37s of
            # prompt-eval alone for ~1.8K context tokens + ~1s per 12 generated
            # tokens (measured 2026-06-03). With firm context attached a real
            # answer lands at 50-90s; the old 120s ReadTimeout was being hit
            # silently and surfaced as "assistente offline" on EVERY grounded
            # firm question — the exact symptom UsuarioDemo reported (Maestro "não acha
            # os prazos / não responde"). Raise to 300s so the grounded answer
            # actually completes. num_predict caps the answer so generation can't
            # run away. keep_alive holds the model warm between turns (cold reload
            # costs another ~6s). Pair this with the context trimming in
            # get_firm_context below — both are needed.
            async def _do_chat():
                async with httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT_S, connect=10.0)) as client:
                    resp = await client.post(
                        f"{self.ollama_url}/api/chat",
                        # F44 Fase 1: temperature baixa reduz alucinação. Top_p estreito
                        # mantém respostas determinísticas.
                        # Fix 2026-06-09: num_ctx 4096 truncava o prompt (~4.7k tok com
                        # clientes+processos+prazos). 8192 acomoda o firm_context inteiro.
                        # 2026-06-17: reduzimos LIMIT de clientes/casos (30→10) e ficamos
                        # com 5120 — janela 37% menor que 8192, KV cache mais leve em CPU.
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "keep_alive": "30m",
                            "options": {
                                "temperature": 0.2,
                                "top_p": 0.85,
                                "num_ctx": 5120,
                                "num_predict": 300,
                                "repeat_penalty": 1.15,
                            },
                        }
                    )
                    # raise_for_status so a non-2xx counts as a breaker failure
                    # (a 5xx from Ollama is exactly the signal we want to trip on).
                    resp.raise_for_status()
                    return resp.json()

            data = await _OLLAMA_BREAKER.call(_do_chat)
            return {"response": data["message"]["content"], "model": self.model, "status": "ok"}
        except CircuitOpenError as ce:
            # Too many workers already parked on Ollama, or the breaker is
            # tripped — return immediately so this worker stays free.
            logger.warning("maestro_lite.chat: ollama breaker rejected: %s", ce)
            return {
                "response": "O assistente está com muitas solicitações no momento. "
                            "Aguarde alguns segundos e tente novamente.",
                "status": "busy",
            }
        except Exception as e:
            logger.error("Ollama error: %s", e)
            return {
                "response": "O assistente de IA não está disponível no momento. Verifique se o Ollama está rodando.",
                "status": "offline",
                "error": str(e)
            }

    def _build_messages(self, message, context=None, history=None,
                        repo_context=None, legal_context=None):
        """Assemble the messages list shared by chat() and chat_stream()."""
        messages = [{"role": "system", "content": self.system_prompt}]
        # Inject current date so the model never guesses the year from training data.
        _today = datetime.now().strftime("%d/%m/%Y")
        messages.append({"role": "system", "content": f"Data atual: {_today} (America/Sao_Paulo). Use esta data em todas as respostas."})
        if context:
            messages.append({"role": "system", "content": f"Contexto do escritório:\n{context}"})
        if repo_context:
            messages.append({"role": "system", "content": repo_context})
        if legal_context:
            messages.append({"role": "system", "content": legal_context})
            messages.append({"role": "system", "content": LEGAL_RAG_GUARD})
            logger.info("maestro_lite: official legal context injected, grounding guard on")
        elif repo_context:
            messages.append({"role": "system", "content": REPO_AWARE_GUARD})
            logger.info("maestro_lite: repo context injected, grounding guard on")
        elif PRODUCT_QUESTION_RE.search(message or ""):
            messages.append({"role": "system", "content": REPO_AWARE_NO_CONTEXT_GUARD})
            logger.info("maestro_lite: product-ish question, no repo context — anti-invent guard on")
        clean_history = sanitize_chat_history(history)
        if clean_history:
            messages.extend(clean_history)
        messages.append({"role": "user", "content": message})
        return messages

    async def chat_stream(self, message, context=None, history=None,
                          repo_context=None, legal_context=None):
        """Async generator that yields SSE-ready dicts for each token chunk.

        Fast-path responses (short-circuits, external providers) yield a single
        ``{"response": ..., "done": True}`` dict. Ollama streaming yields
        ``{"chunk": str}`` dicts followed by one final ``{"done": True, ...}``.
        The caller serialises each dict as ``data: <json>\\n\\n``.
        """
        legal_context = (legal_context or "").strip()

        # ── Short-circuit: jurisprudência sem fonte ────────────────────────
        if (
            JURISPRUDENCE_RE.search(message or "")
            and not LAW_CITATION_RE.search(message or "")
            and not legal_context
        ):
            logger.info("maestro_lite: stream jurisprudence refusal")
            yield {"response": JURISPRUDENCE_REFUSAL, "model": self.model,
                   "status": "ok", "done": True, "refusal_code": "no_official_jurisprudence_source"}
            return

        # ── Short-circuit: citação de lei sem fonte ────────────────────────
        if LAW_CITATION_RE.search(message or "") and not legal_context:
            logger.info("maestro_lite: stream law citation refusal")
            yield {"response": LEGAL_SOURCE_REQUIRED_REFUSAL, "model": self.model,
                   "status": "ok", "done": True, "refusal_code": "no_official_legal_source"}
            return

        # ── Short-circuit: calculadora determinística de prazos ────────────
        try:
            from services.prazo_intent import prazo_intent
            _prazo_resp = prazo_intent(message or "")
            if _prazo_resp:
                logger.info("maestro_lite: stream prazo_intent respondeu deterministicamente")
                yield {"response": _prazo_resp, "model": "prazo_calculator", "status": "ok", "done": True}
                return
        except Exception as _pi_err:  # noqa: BLE001
            logger.warning("maestro_lite: prazo_intent falhou (%s) -> LLM segue", _pi_err)

        messages = self._build_messages(message, context, history, repo_context, legal_context)

        # ── External provider (BYO-API) — primary streaming path ─────────────
        # When CASEHUB_AI_PROVIDER is explicit (NVIDIA etc.), do not fall back to
        # the legacy Ollama CPU stream after a provider timeout. That produced the
        # UsuarioDemo N4 symptom: HTTP 200 stays open, but no visible token arrives.
        try:
            from services.ai_provider import get_ai_provider, NullProvider
            _provider = get_ai_provider()
            if not isinstance(_provider, NullProvider):
                if not getattr(self, "_external_budget_ok", True):
                    yield {
                        "response": "O provedor de IA atingiu o limite temporário. Tente novamente em instantes.",
                        "model": _provider.name,
                        "status": "error",
                        "done": True,
                    }
                    return
                _tag = {"system": "INSTRUCOES", "assistant": "MAESTRO", "user": "USUARIO"}
                _prompt = "\n\n".join(
                    f"[{_tag.get(m.get('role'), 'USUARIO')}]\n{m.get('content','')}"
                    for m in messages
                ) + "\n\n[MAESTRO]\n"
                _full_text = ""
                async for _chunk in _provider.generate_stream(_prompt, temperature=0.2, max_tokens=800):
                    if not _chunk:
                        continue
                    _full_text += _chunk
                    try:
                        from services.maestro_redact import unredact
                        _safe_chunk = unredact(_chunk, getattr(self, "_egress_unmap", None))
                    except Exception:  # noqa: BLE001
                        _safe_chunk = _chunk
                    yield {"chunk": _safe_chunk, "model": _provider.name}
                if _full_text.strip():
                    try:
                        from services.maestro_budget import note_success
                        from services.maestro_redact import unredact
                        note_success()
                        _full_text = unredact(_full_text.strip(), getattr(self, "_egress_unmap", None))
                    except Exception:  # noqa: BLE001
                        pass
                    yield {"response": _full_text, "model": _provider.name, "status": "ok", "done": True}
                    return
                try:
                    from services.maestro_budget import note_failure
                    note_failure("no_response")
                except Exception:  # noqa: BLE001
                    pass
                logger.warning("maestro_lite: stream provider %s sem resposta", _provider.name)
                yield {
                    "response": "O provedor de IA não respondeu. Tente novamente em instantes.",
                    "model": _provider.name,
                    "status": "error",
                    "done": True,
                }
                return
        except Exception as _pe:  # noqa: BLE001
            try:
                from services.maestro_budget import note_failure
                note_failure(str(_pe))
            except Exception:  # noqa: BLE001
                pass
            logger.warning("maestro_lite: stream provider externo falhou (%s)", _pe)
            yield {
                "response": "O provedor de IA falhou. Tente novamente em instantes.",
                "status": "error",
                "done": True,
            }
            return

        # ── Ollama streaming ───────────────────────────────────────────────
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT_S, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "keep_alive": "30m",
                        "options": {
                            "temperature": 0.2,
                            "top_p": 0.85,
                            "num_ctx": 5120,
                            "num_predict": 300,
                            "repeat_penalty": 1.15,
                        },
                    },
                ) as resp:
                    if resp.status_code != 200:
                        yield {"response": "Erro ao comunicar com o modelo de IA.",
                               "status": "error", "done": True}
                        return
                    full_text = ""
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        chunk = (data.get("message") or {}).get("content", "")
                        if chunk:
                            full_text += chunk
                            yield {"chunk": chunk}
                        if data.get("done"):
                            yield {"response": full_text, "model": self.model,
                                   "status": "ok", "done": True}
                            return
                    # Exhausted without done flag
                    if full_text:
                        yield {"response": full_text, "model": self.model,
                               "status": "ok", "done": True}
        except Exception as e:  # noqa: BLE001
            logger.error("Ollama stream error: %s", e)
            yield {
                "response": "O assistente de IA não está disponível no momento. Verifique se o Ollama está rodando.",
                "status": "offline",
                "done": True,
            }

    async def get_status(self):
        """Check if Ollama is running and which models are available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    return {"status": "online", "models": [m["name"] for m in models]}
        except Exception:
            pass
        return {"status": "offline", "models": []}

    def get_firm_context(self, db, org_id):
        """Build context string from database.

        Inclui nomes reais de clientes/casos/prazos para que o modelo não alucine
        quando perguntado sobre entidades específicas ("me fala do processo
        José da Silva"). Limita por recência para caber no budget de tokens.
        """
        from sqlalchemy import text
        context_parts = []

        try:
            result = db.execute(text("SELECT COUNT(*) FROM clients WHERE org_id = :oid"), {"oid": org_id})
            count = result.scalar()
            context_parts.append(f"O escritório tem {count} clientes cadastrados.")
        except Exception:
            pass

        try:
            result = db.execute(text("SELECT COUNT(*), status FROM cases WHERE org_id = :oid GROUP BY status"), {"oid": org_id})
            for row in result:
                context_parts.append(f"Processos com status '{row[1]}': {row[0]}")
        except Exception:
            pass

        try:
            result = db.execute(text("""
                SELECT COALESCE(first_name || ' ' || last_name, email, phone, 'Cliente #' || id) AS nome,
                       email, phone
                FROM clients
                WHERE org_id = :oid
                ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
                LIMIT 10
            """), {"oid": org_id})
            clientes = list(result)
            if clientes:
                context_parts.append("Clientes cadastrados (mais recentes 10):")
                for c in clientes:
                    detalhes = []
                    if c[1]:
                        detalhes.append(f"email {c[1]}")
                    if c[2]:
                        detalhes.append(f"tel {c[2]}")
                    suffix = " — " + ", ".join(detalhes) if detalhes else ""
                    context_parts.append(f"  - {c[0]}{suffix}")
        except Exception:
            pass

        try:
            result = db.execute(text("""
                SELECT COALESCE(c.case_name, c.case_number, 'Processo #' || c.id) AS titulo,
                       COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente,
                       c.status,
                       c.case_number
                FROM cases c
                LEFT JOIN clients cl ON cl.id = c.client_id AND cl.org_id = :oid
                WHERE c.org_id = :oid
                ORDER BY COALESCE(c.updated_at, c.created_at) DESC NULLS LAST
                LIMIT 10
            """), {"oid": org_id})
            casos = list(result)
            if casos:
                context_parts.append("Processos cadastrados (mais recentes 10):")
                for ca in casos:
                    cliente = f" — cliente {ca[1]}" if ca[1].strip() else ""
                    numero = f" [{ca[3]}]" if ca[3] else ""
                    context_parts.append(f"  - {ca[0]}{numero} (status {ca[2] or 'pendente'}){cliente}")
        except Exception:
            pass

        try:
            # Apenas prazos ALÉM de 30 dias (ou sem data). Os prazos dentro de
            # 30 dias já entram nos blocos "Prazos vencendo em até 7/15/30 dias"
            # abaixo — listá-los duas vezes inflava o prompt em ~400 tokens (no
            # alpha VS são 22 prazos só em 7 dias), e o prompt-eval do llama3.2:3b
            # no VPS CPU-only custa ~37s para ~1.8K tokens (medido 2026-06-03),
            # estourando o timeout. Este bloco passa a cobrir só o que as janelas
            # NÃO cobrem, eliminando a duplicação sem perder cobertura.
            result = db.execute(text("""
                SELECT p.tipo,
                       p.data_vencimento,
                       p.status,
                       COALESCE(p.processo_override, c.case_number, 'sem processo') AS processo,
                       COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente,
                       COALESCE(p.source_provider, 'manual') AS source_provider,
                       COALESCE(p.source_status, 'manual') AS source_status,
                       COALESCE(p.calculation_engine_version, '') AS calculation_engine_version
                FROM prazos_processuais p
                LEFT JOIN cases c ON c.id = p.case_id AND c.org_id = :oid
                LEFT JOIN clients cl ON cl.id = c.client_id AND cl.org_id = :oid
                WHERE p.org_id = :oid AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'cancelado')
                  AND (p.data_vencimento IS NULL OR p.data_vencimento > NOW() + INTERVAL '30 days')
                ORDER BY p.data_vencimento ASC NULLS LAST
                LIMIT 15
            """), {"oid": org_id})
            prazos = list(result)
            if prazos:
                context_parts.append("Outros prazos pendentes (após 30 dias):")
                for p in prazos:
                    # tipo é NULL/vazio para a maioria dos prazos importados via
                    # planilha (PJe/processo_override sem case_id). Renderizar o
                    # Python None vira a string literal "None: vence ..." no prompt,
                    # que o modelo pequeno lê como tipo faltando/quebrado. Usar um
                    # rótulo genérico mantém a linha limpa e citável (2026-06-03).
                    tipo = (p[0] or "Prazo processual").strip() or "Prazo processual"
                    cliente = f", cliente {p[4]}" if (p[4] or "").strip() else ""
                    fonte = f", fonte {p[5]}:{p[6]}" if p[5] or p[6] else ""
                    motor = f", calculo {p[7]}" if p[7] else ""
                    context_parts.append(f"  - {tipo}: vence {p[1]} (processo {p[3]}{cliente}, status {p[2]}{fonte}{motor})")
        except Exception:
            pass

        # F44 Fase 1: blocos de prazo por janela temporal NÃO-SOBREPOSTOS.
        # Janelas cumulativas (≤7, ≤15, ≤30) triplicavam cada prazo no prompt —
        # ~400 tokens extras no alpha VS com 22 prazos. Agora cada prazo aparece
        # exatamente UMA VEZ na janela mais próxima. Modelo responde igual;
        # prompt encolhe ~60% neste bloco.
        try:
            # (inicio_excl, fim_incl, label)
            _janelas = [
                (0, 7,  "Prazos vencendo em até 7 dias"),
                (7, 15, "Prazos vencendo em 8–15 dias"),
                (15, 30, "Prazos vencendo em 16–30 dias"),
            ]
            for _min, _max, _label in _janelas:
                result = db.execute(text("""
                    SELECT p.tipo,
                           p.data_vencimento,
                           COALESCE(p.processo_override, c.case_number, 'sem processo') AS processo,
                           COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente,
                           COALESCE(p.source_provider, 'manual') AS source_provider,
                           COALESCE(p.source_status, 'manual') AS source_status,
                           COALESCE(p.calculation_engine_version, '') AS calculation_engine_version
                    FROM prazos_processuais p
                    LEFT JOIN cases c ON c.id = p.case_id AND c.org_id = :oid
                    LEFT JOIN clients cl ON cl.id = c.client_id AND cl.org_id = :oid
                    WHERE p.org_id = :oid
                      AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'cancelado')
                      AND p.data_vencimento IS NOT NULL
                      AND p.data_vencimento > NOW() + (:dmin || ' days')::interval
                      AND p.data_vencimento <= NOW() + (:dmax || ' days')::interval
                    ORDER BY p.data_vencimento ASC
                    LIMIT 20
                """), {"oid": org_id, "dmin": _min, "dmax": _max})
                items = list(result)
                context_parts.append(f"{_label} ({len(items)} encontrado{'s' if len(items) != 1 else ''}):")
                if items:
                    for p in items:
                        tipo = (p[0] or "Prazo processual").strip() or "Prazo processual"
                        cliente = f" — cliente {p[3]}" if (p[3] or "").strip() else ""
                        fonte = f", fonte {p[4]}:{p[5]}" if p[4] or p[5] else ""
                        motor = f", calculo {p[6]}" if p[6] else ""
                        context_parts.append(f"  - {tipo}: vence {p[1]} (proc. {p[2]}{cliente}{fonte}{motor})")
                else:
                    context_parts.append("  (nenhum)")
        except Exception:
            pass

        try:
            result = db.execute(text("""
                SELECT title, status, due_date FROM tasks
                WHERE org_id = :oid AND status != 'completed'
                ORDER BY due_date ASC NULLS LAST LIMIT 10
            """), {"oid": org_id})
            tasks = list(result)
            if tasks:
                context_parts.append("Tarefas pendentes (próximas 10):")
                for t in tasks:
                    due = f" (vence {t[2]})" if t[2] else ""
                    context_parts.append(f"  - {t[0]}: {t[1]}{due}")
        except Exception:
            pass

        firm_context = "\n".join(context_parts)
        self._egress_unmap = {}
        self._external_budget_ok = True
        # Egress redaction (ruling 2026-06-18-activate-nvidia-nim-maestro-egress):
        # com provider externo ativo (NVIDIA etc.) o firm context NAO sai cru -
        # pseudonimiza nomes/processos/PII. Ollama local (on-prem) recebe integro.
        try:
            from services.ai_provider import get_ai_provider, NullProvider
            _external = not isinstance(get_ai_provider(), NullProvider)
        except Exception:  # noqa: BLE001
            _external = False
        if _external:
            try:
                from services.maestro_redact import redact_firm_context
                firm_context, self._egress_unmap = redact_firm_context(firm_context, db, org_id)
                if not firm_context:
                    firm_context = "[contexto do escritorio omitido - redacao vazia]"
            except Exception:  # noqa: BLE001 - fail-closed: nunca vaza cru
                firm_context = "[contexto do escritorio omitido - falha na redacao]"
                self._egress_unmap = {}
            try:
                from services.maestro_budget import external_allowed
                self._external_budget_ok = external_allowed(db, org_id)
            except Exception:  # noqa: BLE001
                self._external_budget_ok = True
        return firm_context


# ---------------------------------------------------------------------------
# Contexto-360 de CLIENTE — bloco "CLIENTE EM FOCO"
# ---------------------------------------------------------------------------
# Quando a pergunta cita um cliente do escritório pelo nome, este bloco junta
# cadastro + processos + prazos + agenda + tarefas abertas do cliente num só
# lugar, para o modelo responder com dados reais sem caçar pelo contexto geral.
# Funções NOVAS e autocontidas: os chamadores (routes/assistente.py e
# routes/team_messages.py) anexam o retorno ao contexto existente com 1 linha.
# Falha graciosa: qualquer erro → '' (o chat segue sem o bloco, nunca quebra).

CLIENT_CONTEXT_MAX_CHARS = 2500


def client_context_enabled() -> bool:
    """Kill-switch do bloco CLIENTE EM FOCO (default ON).

    ``CASEHUB_MAESTRO_CLIENT_CONTEXT_ENABLED=0`` (ou false/no/off) desliga em
    runtime sem deploy — bloco some e o chat volta ao contexto anterior.
    """
    raw = os.getenv("CASEHUB_MAESTRO_CLIENT_CONTEXT_ENABLED", "1")
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _detect_client(db, org_id, message):
    """Acha o cliente da org citado na mensagem (match mais longo, >=4 chars).

    Candidatos por cliente: nome completo, "primeiro último" e cada parte do
    nome com >=4 chars. Match case-insensitive com fronteira de palavra (para
    "Ana" não casar dentro de "banana"). Empate → maior candidato vence.
    Org-scoped (red line). Retorna a row do cliente ou None.
    """
    from sqlalchemy import text
    msg = (message or "").strip().lower()
    if len(msg) < 4:
        return None
    rows = db.execute(text("""
        SELECT id, first_name, middle_name, last_name, email, phone, whatsapp,
               COALESCE(status, 'active') AS status
        FROM clients
        WHERE org_id = :oid
        ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
        LIMIT 2000
    """), {"oid": org_id}).fetchall()
    best, best_len = None, 0
    for r in rows:
        parts = [(p or "").strip() for p in (r.first_name, r.middle_name, r.last_name)]
        parts = [p for p in parts if p]
        if not parts:
            continue
        candidates = {" ".join(parts)}
        if len(parts) >= 2:
            candidates.add(f"{parts[0]} {parts[-1]}")
        candidates.update(parts)
        for cand in candidates:
            if len(cand) < 4 or len(cand) <= best_len:
                continue
            if re.search(r"(?<!\w)" + re.escape(cand.lower()) + r"(?!\w)", msg):
                best, best_len = r, len(cand)
    return best


def get_client_context(db, org_id, message) -> str:
    """Bloco "CLIENTE EM FOCO" quando a mensagem cita um cliente da org.

    Cadastro (nome/contato/status) + processos (cases) + prazos (reminders e
    prazos_processuais via processos do cliente) + agenda (appointments futuros
    e últimos 3 passados, com data/hora) + tarefas abertas do kanban — TUDO
    filtrado por org_id. Retorna '' se nenhum cliente citado, feature desligada
    ou falha. Saída com prefixo "\\n\\n" (pronta para ``contexto += ...``) e
    limitada a CLIENT_CONTEXT_MAX_CHARS.
    """
    try:
        if org_id is None or not client_context_enabled():
            return ""
        from sqlalchemy import text

        def _safe_rollback():
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass

        cli = _detect_client(db, org_id, message)
        if cli is None:
            return ""
        cid = cli.id
        full_name = " ".join(
            p.strip() for p in (cli.first_name, cli.middle_name, cli.last_name) if p and p.strip()
        )
        lines = [f"CLIENTE EM FOCO: {full_name}"]
        detalhes = []
        if cli.phone:
            detalhes.append(f"tel {cli.phone}")
        if cli.whatsapp and cli.whatsapp != cli.phone:
            detalhes.append(f"whatsapp {cli.whatsapp}")
        if cli.email:
            detalhes.append(f"email {cli.email}")
        detalhes.append(f"status {cli.status}")
        lines.append("Cadastro: " + ", ".join(detalhes))

        # Processos (cases) do cliente — número BR primeiro, fallback imigração.
        try:
            casos = db.execute(text("""
                SELECT COALESCE(numero_processo, case_number, 'Processo #' || id) AS numero,
                       COALESCE(tipo_acao, area_of_practice, visa_type, '') AS tipo,
                       COALESCE(status, 'pendente') AS status
                FROM cases
                WHERE org_id = :oid AND client_id = :cid
                ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST
                LIMIT 8
            """), {"oid": org_id, "cid": cid}).fetchall()
            if casos:
                lines.append(f"Processos do cliente ({len(casos)}):")
                for ca in casos:
                    tipo = f" — {ca.tipo}" if (ca.tipo or "").strip() else ""
                    lines.append(f"  - {ca.numero}{tipo} (status {ca.status})")
            else:
                lines.append("Processos do cliente: (nenhum)")
        except Exception:  # noqa: BLE001
            _safe_rollback()

        # Prazos do cliente: lembretes (reminders.client_id) + prazos
        # processuais vinculados via processos do cliente. Pendentes apenas.
        prazo_lines = []
        try:
            for r in db.execute(text("""
                SELECT title, due_date FROM reminders
                WHERE org_id = :oid AND client_id = :cid
                  AND COALESCE(is_completed, FALSE) = FALSE
                ORDER BY due_date ASC
                LIMIT 5
            """), {"oid": org_id, "cid": cid}).fetchall():
                prazo_lines.append(f"  - {r.title}: vence {r.due_date}")
        except Exception:  # noqa: BLE001
            _safe_rollback()
        try:
            for p in db.execute(text("""
                SELECT p.tipo, p.data_vencimento,
                       COALESCE(p.processo_override, c.numero_processo, c.case_number, 'sem processo') AS processo
                FROM prazos_processuais p
                JOIN cases c ON c.id = p.case_id AND c.org_id = :oid
                WHERE p.org_id = :oid AND c.client_id = :cid
                  AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'cancelado')
                ORDER BY p.data_vencimento ASC NULLS LAST
                LIMIT 5
            """), {"oid": org_id, "cid": cid}).fetchall():
                tipo = (p.tipo or "Prazo processual").strip() or "Prazo processual"
                prazo_lines.append(f"  - {tipo}: vence {p.data_vencimento} (proc. {p.processo})")
        except Exception:  # noqa: BLE001
            _safe_rollback()
        lines.append("Prazos do cliente:")
        lines.extend(prazo_lines or ["  (nenhum)"])

        # Agenda: appointments não tem client_id — vínculo via case_id de um
        # processo do cliente OU client_name (texto livre) contendo o nome.
        nm_first_last = f"{(cli.first_name or '').strip()} {(cli.last_name or '').strip()}".strip().lower()
        ag_params = {
            "oid": org_id,
            "cid": cid,
            "nm1": f"%{full_name.lower()}%",
            "nm2": f"%{nm_first_last}%" if len(nm_first_last) >= 4 else f"%{full_name.lower()}%",
        }
        ag_filter = """
                FROM appointments a
                LEFT JOIN cases c ON c.id = a.case_id AND c.org_id = :oid
                WHERE a.org_id = :oid
                  AND (c.client_id = :cid
                       OR LOWER(COALESCE(a.client_name, '')) LIKE :nm1
                       OR LOWER(COALESCE(a.client_name, '')) LIKE :nm2)
        """

        def _fmt_appt(a):
            hora = f" {str(a.time_start)[:5]}" if a.time_start is not None else ""
            tipo = f" ({a.type})" if (a.type or "").strip() else ""
            return f"  - {a.date}{hora} — {a.title}{tipo}"

        try:
            futuros = db.execute(text(
                "SELECT a.date, a.time_start, a.title, a.type" + ag_filter +
                " AND a.date >= CURRENT_DATE"
                " ORDER BY a.date ASC, a.time_start ASC NULLS LAST LIMIT 6"
            ), ag_params).fetchall()
            lines.append("Agenda — próximos compromissos:")
            lines.extend([_fmt_appt(a) for a in futuros] or ["  (nenhum)"])
            passados = db.execute(text(
                "SELECT a.date, a.time_start, a.title, a.type" + ag_filter +
                " AND a.date < CURRENT_DATE"
                " ORDER BY a.date DESC, a.time_start DESC NULLS LAST LIMIT 3"
            ), ag_params).fetchall()
            lines.append("Agenda — últimos 3 compromissos passados:")
            lines.extend([_fmt_appt(a) for a in passados] or ["  (nenhum)"])
        except Exception:  # noqa: BLE001
            _safe_rollback()

        # Tarefas abertas do kanban (tasks.client_id). Tarefas privadas ficam
        # fora do contexto (visibility='private' é só criador/responsável); em
        # DBs antigos sem a coluna, retry sem o filtro preserva o bloco.
        try:
            _tasks_sql = """
                SELECT title, COALESCE(status, 'pending') AS status, due_date
                FROM tasks
                WHERE org_id = :oid AND client_id = :cid
                  AND COALESCE(status, 'pending') != 'completed'
                  {vis}
                ORDER BY due_date ASC NULLS LAST
                LIMIT 8
            """
            try:
                tarefas = db.execute(
                    text(_tasks_sql.format(vis="AND COALESCE(visibility, 'org') != 'private'")),
                    {"oid": org_id, "cid": cid},
                ).fetchall()
            except Exception:  # noqa: BLE001
                _safe_rollback()
                tarefas = db.execute(
                    text(_tasks_sql.format(vis="")),
                    {"oid": org_id, "cid": cid},
                ).fetchall()
            lines.append("Tarefas abertas do cliente (kanban):")
            if tarefas:
                for t in tarefas:
                    due = f", vence {t.due_date}" if t.due_date else ""
                    lines.append(f"  - {t.title} (status {t.status}{due})")
            else:
                lines.append("  (nenhuma)")
        except Exception:  # noqa: BLE001
            _safe_rollback()

        block = "\n".join(lines)
        if len(block) > CLIENT_CONTEXT_MAX_CHARS:
            block = block[: CLIENT_CONTEXT_MAX_CHARS - 25]
            cut = block.rfind("\n")
            if cut > 0:
                block = block[:cut]
            block += "\n  (bloco truncado)"
        logger.info("maestro_lite: CLIENTE EM FOCO anexado (client_id=%s, %s chars)", cid, len(block))
        return "\n\n" + block
    except Exception as exc:  # noqa: BLE001 — nunca quebrar o chat por causa do bloco
        logger.warning("maestro_lite: get_client_context falhou (%s) — seguindo sem bloco", exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return ""
