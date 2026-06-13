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
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "hermes3:8b")


async def generate_text(prompt, *, temperature=0.4, max_tokens=400, num_ctx=8192, model=None):
    """Geração CRUA via Ollama local (/api/generate), SEM os short-circuits do
    MaestroLite.chat (jurisprudência/prazo/law-guard). Usada pelo bloco CRM do
    WhatsApp p/ resumir a conversa e sugerir próximas mensagens (Victor 10/06):
    local-first, zero transferência externa. Retorna str ou None.
    """
    import logging
    import httpx
    _log = logging.getLogger(__name__)
    mdl = model or DEFAULT_MODEL
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
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
            text = (resp.json().get("response") or "").strip()
            return text or None
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

# F44 Fase 2 (FR-1 pré-Example User 30/05): regex detecta citação de artigo/lei na
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

SYSTEM_PROMPT = """Você é o Maestro, assistente jurídico inteligente do escritório {org_name}.
Você responde com base no contexto do CaseHub fornecido (clientes, processos, prazos, tarefas reais).

REGRAS:

1. **Clientes/processos/prazos do escritório**: PRIMEIRO leia o "Contexto do escritório" abaixo. Se o nome ou termo da pergunta aparecer no contexto (mesmo que parcialmente — ex: "Costa" casa com "Costa Empreendimentos"), RESPONDA usando esses dados reais. Cite nome completo + status/processo/prazo conforme aparece.
   - Match flexível: aceitar substring case-insensitive (Costa = costa = Costa Empreendimentos).
   - Se o nome NÃO aparecer de forma alguma no contexto, responda EXATAMENTE: "Não encontrei isso no CaseHub. Verifique se está cadastrado em /clients ou /controladoria."
   - NÃO invente clientes, NÃO sugira nomes que não estão no contexto.

2. **Prazos "próximos N dias"**: o contexto tem blocos pré-computados ("Prazos vencendo em até 7/15/30 dias"). Use APENAS esses itens. Liste tipo + data + processo + cliente conforme aparece. Se o bloco N dias está vazio (ou diz "(nenhum)"), responda "Nenhum prazo vencendo nos próximos N dias."

3. **Lei/jurisprudência** (CPC, CLT, CF, CDC, CTN, súmulas, artigos numerados): você NÃO é fonte primária. Modelo pequeno alucina citações. SEMPRE:
   a) Comece com: "Não tenho certeza absoluta sobre o texto literal deste dispositivo."
   b) Forneça DESCRIÇÃO TEMÁTICA breve (sobre o que trata genericamente), NUNCA texto literal entre aspas.
   c) Termine com: "Confirme a redação atualizada em https://www.planalto.gov.br"
   d) Se nem o tema souber: "Não tenho certeza sobre este dispositivo específico. Consulte https://www.planalto.gov.br"

4. Quando não souber e não for cliente/processo/prazo/lei: "Não tenho essa informação."

5. Sempre português brasileiro, profissional, direto. Sem floreios.

Exemplos:
- Pergunta: "Me fala do cliente Costa" + contexto tem "Costa Empreendimentos Imobiliários S/A" → Resposta: "Costa Empreendimentos Imobiliários S/A — está cadastrado no escritório. [+ detalhes do contexto: e-mail, telefone, processos vinculados]."
- Pergunta: "Me fala do processo José da Silva" + José da Silva NÃO aparece → Resposta: "Não encontrei isso no CaseHub. Verifique se está cadastrado em /clients ou /controladoria."
- Pergunta: "Quais prazos vencem nos próximos 15 dias?" + bloco tem 2 itens → Liste os 2 itens com tipo, data, processo.
- Pergunta: "Quais prazos próximos 15 dias?" + bloco "(nenhum)" → Resposta: "Nenhum prazo vencendo nos próximos 15 dias."
- Pergunta: "O que diz o art. 212 do CPC?" → "Não tenho certeza absoluta sobre o texto literal deste dispositivo. O Art. 212 do CPC trata da prática de atos processuais. Confirme a redação atualizada em https://www.planalto.gov.br"
"""

# Bloco INJETADO antes da mensagem do usuário quando regex casa. Reforça regra 3
# no contexto imediato — modelo pequeno tende a ignorar regra distante do prompt.
LAW_CITATION_GUARD = """ATENÇÃO: A próxima pergunta menciona artigo, lei ou súmula. Aplique a Regra 3 ESTRITAMENTE:
- NÃO cite texto literal entre aspas.
- Comece com "Não tenho certeza absoluta sobre o texto literal deste dispositivo."
- Forneça apenas descrição temática breve.
- Termine sempre com "Confirme a redação atualizada em https://www.planalto.gov.br"
"""

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

    async def chat(self, message, context=None, history=None, repo_context=None):
        """Send message to Ollama with context.

        ``repo_context`` (optional) is the grounded PRODUCT-knowledge block
        produced by services.maestro_repo_index.retrieve_repo_context — already
        secret-redacted and citation-annotated. When present, the model is told
        to answer about the product ONLY from it and to cite the source file.
        """
        # Jurisprudence short-circuit: no active case-law source, so refuse
        # honestly and deterministically (never let the small model invent
        # acórdãos/ementas). A bare law-article citation (Rule 3) is NOT caught
        # here — only genuine jurisprudence/precedent asks.
        if JURISPRUDENCE_RE.search(message or "") and not LAW_CITATION_RE.search(message or ""):
            logger.info("maestro_lite: jurisprudence asked, no source — honest refusal")
            return {"response": JURISPRUDENCE_REFUSAL, "model": self.model, "status": "ok"}

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

        # F44 Fase 2 (FR-1): se a pergunta cita artigo/lei/súmula, injeta guard
        # adicional logo antes da mensagem. Modelo pequeno (3B params) ignora
        # regra distante; reforço imediato força disclaimer.
        if LAW_CITATION_RE.search(message or ""):
            messages.append({"role": "system", "content": LAW_CITATION_GUARD})
            logger.info("maestro_lite: law citation detected, injecting guard")

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
            if not isinstance(_provider, NullProvider):
                _tag = {"system": "INSTRUCOES", "assistant": "MAESTRO", "user": "USUARIO"}
                _prompt = "\n\n".join(
                    f"[{_tag.get(m.get('role'), 'USUARIO')}]\n{m.get('content','')}"
                    for m in messages
                ) + "\n\n[MAESTRO]\n"
                _ext = await _provider.generate(_prompt, temperature=0.2, max_tokens=800)
                if _ext:
                    return {"response": _ext, "model": _provider.name, "status": "ok"}
                logger.info("maestro_lite: provider %s sem resposta -> fallback Ollama", _provider.name)
        except Exception as _pe:
            logger.warning("maestro_lite: provider externo falhou (%s) -> fallback Ollama", _pe)

        try:
            # Timeout: llama3.2:3b on a CPU-only VPS (Mumbai alpha) needs ~37s of
            # prompt-eval alone for ~1.8K context tokens + ~1s per 12 generated
            # tokens (measured 2026-06-03). With firm context attached a real
            # answer lands at 50-90s; the old 120s ReadTimeout was being hit
            # silently and surfaced as "assistente offline" on EVERY grounded
            # firm question — the exact symptom Example User reported (Maestro "não acha
            # os prazos / não responde"). Raise to 300s so the grounded answer
            # actually completes. num_predict caps the answer so generation can't
            # run away. keep_alive holds the model warm between turns (cold reload
            # costs another ~6s). Pair this with the context trimming in
            # get_firm_context below — both are needed.
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    # F44 Fase 1: temperature baixa reduz alucinação. Top_p estreito
                    # mantém respostas determinísticas.
                    # Fix 2026-06-09: num_ctx 4096 truncava o prompt (~4.7k tok com
                    # clientes+processos+prazos) e os blocos de PRAZO caíam fora da
                    # janela -> o modelo respondia "não encontrei" mesmo com prazos
                    # no sistema. 8192 acomoda o firm_context inteiro com folga.
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "keep_alive": "30m",
                        "options": {
                            "temperature": 0.2,
                            "top_p": 0.85,
                            "num_ctx": 8192,
                            "num_predict": 600,
                            "repeat_penalty": 1.15,
                        },
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"response": data["message"]["content"], "model": self.model, "status": "ok"}
                else:
                    return {"response": "Erro ao comunicar com o modelo de IA.", "status": "error"}
        except Exception as e:
            logger.error("Ollama error: %s", e)
            return {
                "response": "O assistente de IA não está disponível no momento. Verifique se o Ollama está rodando.",
                "status": "offline",
                "error": str(e)
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
                LIMIT 30
            """), {"oid": org_id})
            clientes = list(result)
            if clientes:
                context_parts.append("Clientes cadastrados (mais recentes 30):")
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
                LIMIT 30
            """), {"oid": org_id})
            casos = list(result)
            if casos:
                context_parts.append("Processos cadastrados (mais recentes 30):")
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
                       COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente
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
                    context_parts.append(f"  - {tipo}: vence {p[1]} (processo {p[3]}{cliente}, status {p[2]})")
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
                           COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente
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
                        context_parts.append(f"  - {tipo}: vence {p[1]} (proc. {p[2]}{cliente})")
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

        return "\n".join(context_parts)


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
