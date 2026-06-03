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
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


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

# F44 Fase 2 (FR-1 pré-[parceiro] 30/05): regex detecta citação de artigo/lei na
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

        if history:
            messages.extend(history[-10:])  # Last 10 messages

        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    # F44 Fase 1: temperature baixa reduz alucinação. Top_p estreito
                    # mantém respostas determinísticas. num_ctx 4096 cabe firm context.
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.2,
                            "top_p": 0.85,
                            "num_ctx": 4096,
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
                LEFT JOIN clients cl ON cl.id = c.client_id
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
            result = db.execute(text("""
                SELECT p.tipo,
                       p.data_vencimento,
                       p.status,
                       COALESCE(p.processo_override, c.case_number, 'sem processo') AS processo,
                       COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente
                FROM prazos_processuais p
                LEFT JOIN cases c ON c.id = p.case_id
                LEFT JOIN clients cl ON cl.id = c.client_id
                WHERE p.org_id = :oid AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'cancelado')
                ORDER BY p.data_vencimento ASC NULLS LAST
                LIMIT 20
            """), {"oid": org_id})
            prazos = list(result)
            if prazos:
                context_parts.append("Prazos pendentes (próximos 20):")
                for p in prazos:
                    cliente = f", cliente {p[4]}" if p[4].strip() else ""
                    context_parts.append(f"  - {p[0]}: vence {p[1]} (processo {p[3]}{cliente}, status {p[2]})")
        except Exception:
            pass

        # F44 Fase 1: bloco específico "Prazos vencendo em até N dias" — Jaime
        # testou na reunião com "prazos próximos 15 dias" e Maestro falhou.
        # Pré-computar window 7/15/30 dias dá ao modelo bloco facilmente citável.
        try:
            for janela in (7, 15, 30):
                result = db.execute(text("""
                    SELECT p.tipo,
                           p.data_vencimento,
                           COALESCE(p.processo_override, c.case_number, 'sem processo') AS processo,
                           COALESCE(cl.first_name || ' ' || cl.last_name, '') AS cliente
                    FROM prazos_processuais p
                    LEFT JOIN cases c ON c.id = p.case_id
                    LEFT JOIN clients cl ON cl.id = c.client_id
                    WHERE p.org_id = :oid
                      AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'cancelado')
                      AND p.data_vencimento IS NOT NULL
                      AND p.data_vencimento <= NOW() + (:dias || ' days')::interval
                      AND p.data_vencimento >= NOW() - INTERVAL '1 day'
                    ORDER BY p.data_vencimento ASC
                    LIMIT 30
                """), {"oid": org_id, "dias": janela})
                items = list(result)
                context_parts.append(f"Prazos vencendo em até {janela} dias ({len(items)} encontrado{'s' if len(items) != 1 else ''}):")
                if items:
                    for p in items:
                        cliente = f" — cliente {p[3]}" if p[3].strip() else ""
                        context_parts.append(f"  - {p[0]}: vence {p[1]} (proc. {p[2]}{cliente})")
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
