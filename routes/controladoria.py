"""
CaseHub Lite — Controladoria Juridica
Modulo de controle de prazos processuais.
Substitui e melhora o app "Prazo Certo" (Lovable) da instancia legada.

Routes:
    GET  /controladoria              — Dashboard principal
    POST /controladoria/novo-prazo   — Criar novo prazo
    POST /controladoria/buscar-intimacoes — Buscar intimacoes via DataJud
    POST /controladoria/{id}/update   — Inline edit field (Asana-style)
    POST /controladoria/{id}/concluir — Marcar prazo como concluido
    POST /controladoria/{id}/excluir  — Excluir prazo
    GET  /controladoria/export/excel  — Exportar prazos para Excel
    GET  /controladoria/api/stats     — Estatisticas JSON para os cards
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import bindparam, text
from datetime import date, datetime, timedelta
from typing import Any, Optional
import logging
import io
import re

logger = logging.getLogger(__name__)

from core.template_config import templates, PREFIX, inject_org_context
from auth import get_current_user
from config import settings
from models import get_db, Case
from models.tenant import tenant_query
from services.prazos_cpc import (
    calcular_prazo,
    calcular_prazo_detalhado,
    prazos_comuns,
    proximo_dia_util,
)

router = APIRouter(prefix="/controladoria", tags=["controladoria"])

CONTROLADORIA_RENDER_LIMIT = 300
CONTROLADORIA_CASE_OPTION_LIMIT = 250

TRIBUNAL_PATTERNS = {
    "TRT3": "%.5.03.%",
    "TRT1": "%.5.01.%",
    "TRT2": "%.5.02.%",
    "TRF1": "%.4.01.%",
    "TRF2": "%.4.02.%",
    "TRF3": "%.4.03.%",
    "TRF4": "%.4.04.%",
    "TRF5": "%.4.05.%",
    "TRF6": "%.4.06.%",
    "TJMG": "%.8.13.%",
    "TJSP": "%.8.26.%",
    "TJRJ": "%.8.19.%",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _business_days_between(start: date, end: date) -> int:
    """Count business days (Mon-Fri) between start and end (signed).
    Positive = end is in the future, negative = end is in the past."""
    if start == end:
        return 0
    sign = 1 if end >= start else -1
    a, b = (start, end) if sign == 1 else (end, start)
    count = 0
    current = a
    while current < b:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            count += 1
    return count * sign


def _get_org_id(request: Request) -> int:
    """Extract org_id from request state (set by TenantMiddleware)."""
    return getattr(request.state, "org_id", 1)


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp for operator-facing diagnostics."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_api_error(value: Any) -> str:
    """Keep upstream diagnostics useful without risking token/secret leakage."""
    if not value:
        return ""
    text_value = str(value)
    replacements = [
        (r"(?i)(Bearer)\s+[^\s,;]+", r"\1 <redacted>"),
        (r"(?i)(access_token|refresh_token|client_secret)(\s*['\"]?\s*[:=]\s*['\"]?)([^\s'\",}&]+)", r"\1\2<redacted>"),
        (r"eyJ[A-Za-z0-9_\-]{20,}\.eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]+", "<redacted-jwt>"),
    ]
    for pattern, replacement in replacements:
        text_value = re.sub(pattern, replacement, text_value, flags=re.IGNORECASE)
    return text_value[:160]


def _provider_attempt(
    provider: str,
    status: str,
    reason: str,
    *,
    error: Any = "",
    count: int = 0,
) -> dict:
    return {
        "provider": provider,
        "status": status,
        "reason": reason,
        "error": _safe_api_error(error),
        "count": count,
        "attempted_at": _utc_now_iso(),
    }


def _default_tribunal_for_uf(uf: str) -> str:
    return {
        "AC": "TJAC",
        "AL": "TJAL",
        "AM": "TJAM",
        "AP": "TJAP",
        "BA": "TJBA",
        "CE": "TJCE",
        "DF": "TJDFT",
        "ES": "TJES",
        "GO": "TJGO",
        "MA": "TJMA",
        "MG": "TJMG",
        "MS": "TJMS",
        "MT": "TJMT",
        "PA": "TJPA",
        "PB": "TJPB",
        "PE": "TJPE",
        "PI": "TJPI",
        "PR": "TJPR",
        "RJ": "TJRJ",
        "RN": "TJRN",
        "RO": "TJRO",
        "RR": "TJRR",
        "RS": "TJRS",
        "SC": "TJSC",
        "SE": "TJSE",
        "SP": "TJSP",
        "TO": "TJTO",
    }.get(uf.upper(), "TJMG")


def _extract_nested_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("nome") or value.get("name") or ""
    return str(value or "")


def _date_only(value: Any) -> str:
    if not value:
        return ""
    return str(value)[:10]


def _normalize_process_fallback_item(item: dict, provider: str, tribunal: str) -> dict:
    numero = item.get("numeroProcesso") or item.get("numero_cnj") or item.get("numero_processo") or ""
    orgao = _extract_nested_name(item.get("orgaoJulgador")) or item.get("orgao") or ""
    data_ref = item.get("dataHoraUltimaAtualizacao") or item.get("dataAjuizamento") or item.get("ultima_atualizacao")
    return {
        "id": f"{provider.lower().replace(' ', '-')}-{numero or hash(str(item))}",
        "numero_processo": numero,
        "tribunal": item.get("tribunal") or item.get("siglaTribunal") or tribunal,
        "orgao": orgao,
        "tipo_comunicacao": "Processo localizado",
        "texto": (
            "Resultado subsidiario por processo/OAB. PDPJ/ComunicaAPI nao retornou "
            "intimacoes autenticadas; confira a fonte antes de importar prazo."
        ),
        "data_disponibilizacao": _date_only(data_ref),
        "source": provider,
        "importable": False,
    }


def _normalize_publication_item(item: dict, provider: str) -> dict:
    texto = item.get("texto") or item.get("conteudo") or item.get("descricao") or ""
    numero = item.get("numero_processo") or item.get("numeroProcesso") or item.get("processo") or ""
    data_ref = item.get("data_disponibilizacao") or item.get("data") or item.get("data_publicacao")
    return {
        "id": f"{provider.lower().replace(' ', '-')}-{item.get('id') or hash(str(item))}",
        "numero_processo": numero,
        "tribunal": item.get("tribunal") or item.get("diario") or "",
        "orgao": item.get("orgao") or item.get("caderno") or "",
        "tipo_comunicacao": item.get("tipo_comunicacao") or item.get("tipo") or "Publicacao",
        "texto": texto,
        "data_disponibilizacao": _date_only(data_ref),
        "source": provider,
        "importable": bool(texto and data_ref),
    }


def _comunicaapi_reason(error_code: str, source: str, message: str = "") -> str:
    if message:
        return message
    if error_code == "missing_credentials":
        return "PDPJ_CLIENT_ID/PDPJ_CLIENT_SECRET ausentes ou nao lidos pelo runtime."
    if error_code == "invalid_client":
        return "PDPJ rejeitou client_id/client_secret; conferir credencial CNJ e client profile."
    if error_code == "unauthorized_client":
        return "O client PDPJ nao esta autorizado para o grant type configurado."
    if error_code == "invalid_grant":
        return "Refresh token PDPJ expirou ou foi revogado; reconexao necessaria."
    if error_code == "no_access_token":
        return "PDPJ nao emitiu access_token; conferir client profile e credenciais no Keycloak."
    if error_code == "auth_failure":
        return "Falha de autenticacao PDPJ; consultar logs sanitizados do VPS."
    if error_code == "network":
        return "Erro de rede ao contactar PDPJ/ComunicaAPI."
    if error_code and error_code.startswith("http_"):
        return f"ComunicaAPI retornou {error_code.replace('_', ' ').upper()}."
    if "demo" in source.lower():
        return "DEMO_MODE ativo; dados mockados."
    return "ComunicaAPI respondeu sem itens para a OAB/periodo informado."


def _controladoria_api_card(
    name: str,
    status: str,
    reason: str,
    detail: str = "",
    badge_text: str = "",
) -> dict:
    return {
        "name": name,
        "status": status,
        "reason": reason,
        "detail": detail,
        "badge_text": badge_text,
    }


def _controladoria_api_status_cards() -> list[dict]:
    """Operator-facing integration truth for the Controladoria header."""
    cards: list[dict] = []

    try:
        from services.comunicaapi import pdpj_auth

        auth = pdpj_auth.public_status()
        if auth.get("token_cached"):
            cards.append(_controladoria_api_card(
                "PDPJ/CNJ",
                "ok",
                "Autenticacao PDPJ encontrada neste servidor.",
                "Fonte preferencial para intimacoes oficiais.",
                "Oficial PDPJ",
            ))
        elif auth.get("configured"):
            code = auth.get("last_error_code") or "auth_pending"
            if code == "auth_pending":
                reason = "Credenciais PDPJ existem, mas o token ainda nao foi validado neste servidor."
            else:
                reason = _comunicaapi_reason(code, "ComunicaAPI PJE/CNJ", auth.get("last_error_message") or "")
            cards.append(_controladoria_api_card(
                "PDPJ/CNJ",
                "down",
                reason,
                "Enquanto isso, use Novo Prazo e a busca subsidiaria.",
                "Oficial PDPJ",
            ))
        else:
            cards.append(_controladoria_api_card(
                "PDPJ/CNJ",
                "down",
                "Credenciais PDPJ/CNJ ausentes ou nao lidas pelo runtime.",
                "Sem autorizacao valida, o CNJ nao libera intimacoes por OAB.",
                "Oficial PDPJ",
            ))
    except Exception as exc:
        cards.append(_controladoria_api_card(
            "PDPJ/CNJ",
            "down",
            "Falha ao ler o status local da integracao PDPJ.",
            _safe_api_error(exc),
            "Oficial PDPJ",
        ))

    cards.append(_controladoria_api_card(
        "DataJud",
        "warn",
        "Fallback publico CNJ disponivel para consulta subsidiaria de processos.",
        "Nao substitui a importacao oficial de prazos/intimacoes do PDPJ.",
        "Fallback publico",
    ))

    cards.append(_controladoria_api_card(
        "Escavador",
        "ok" if settings.ESCAVADOR_API_KEY else "down",
        "Chave configurada para busca subsidiaria de publicacoes." if settings.ESCAVADOR_API_KEY else "ESCAVADOR_API_KEY ausente neste servidor.",
        "Usado como apoio quando PDPJ nao retorna intimacoes oficiais.",
        "Provider ativo" if settings.ESCAVADOR_API_KEY else "Chave ausente",
    ))

    cards.append(_controladoria_api_card(
        "JusBrasil",
        "ok" if settings.JUSBRASIL_API_KEY else "down",
        "Chave configurada para diarios e publicacoes." if settings.JUSBRASIL_API_KEY else "JUSBRASIL_API_KEY ausente neste servidor.",
        "Usado como apoio quando fontes oficiais nao retornam resultado.",
        "Provider ativo" if settings.JUSBRASIL_API_KEY else "Chave ausente",
    ))

    return cards


def _is_integration_failure(attempt: dict) -> bool:
    return attempt.get("status") in {"failed", "unavailable"} and bool(attempt.get("error"))


def _failed_status_code(code: str) -> int:
    if code == "missing_credentials":
        return 503
    if code == "unexpected":
        return 500
    return 502


async def _try_comunicaapi_provider(
    numero_oab: str,
    uf_oab: str,
    data_inicio: str,
    data_fim: str,
) -> dict:
    provider = "ComunicaAPI PJE/CNJ"
    try:
        from services.comunicaapi import comunicaapi_client, pdpj_auth
    except ImportError as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "unavailable", "Servico ComunicaAPI nao disponivel.", error=e),
            "auth_status": "unavailable",
            "grant_attempted": "none",
        }

    try:
        resultado = await comunicaapi_client.buscar_por_oab(
            numero_oab,
            uf_oab,
            data_inicio=data_inicio or None,
            data_fim=data_fim or None,
        )
    except Exception as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "failed", "Erro inesperado na ComunicaAPI.", error=e),
            "auth_status": "error",
            "grant_attempted": getattr(pdpj_auth, "_last_grant_type", None) or "client_credentials",
        }

    items = resultado.get("items", [])
    error_code = resultado.get("error", "")
    source = resultado.get("source", provider)
    status = "ok" if items else ("failed" if error_code else "empty")
    auth_status = "configured" if getattr(pdpj_auth, "is_configured", False) else "missing_credentials"
    grant_attempted = getattr(pdpj_auth, "_last_grant_type", None)
    if not grant_attempted:
        grant_attempted = "none" if auth_status == "missing_credentials" else "client_credentials"
    for item in items:
        item.setdefault("importable", True)
    return {
        "items": items,
        "attempt": _provider_attempt(
            provider,
            status,
            _comunicaapi_reason(error_code, source, resultado.get("message", "")),
            error=error_code,
            count=len(items),
        ),
        "auth_status": auth_status,
        "grant_attempted": grant_attempted,
        "source": source,
    }


async def _try_datajud_provider(numero_oab: str, uf_oab: str) -> dict:
    provider = "DataJud (CNJ)"
    tribunal = _default_tribunal_for_uf(uf_oab)
    try:
        from services.datajud import datajud_client
        resultados = await datajud_client.buscar_por_advogado(numero_oab, tribunal=tribunal)
    except Exception as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "failed", "DataJud falhou na busca por OAB.", error=e),
        }

    items = [_normalize_process_fallback_item(item, provider, tribunal) for item in resultados]
    return {
        "items": items,
        "attempt": _provider_attempt(
            provider,
            "ok" if items else "empty",
            (
                "Busca subsidiaria por processos da OAB; resultados nao substituem "
                "intimacoes autenticadas do PDPJ."
                if items else
                "DataJud nao retornou processos para a OAB informada."
            ),
            count=len(items),
        ),
    }


async def _try_escavador_provider(numero_oab: str, uf_oab: str, data_inicio: str) -> dict:
    provider = "Escavador"
    try:
        from services.escavador import escavador_client
    except ImportError as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "unavailable", "Servico Escavador nao disponivel.", error=e),
        }
    if not getattr(escavador_client, "is_configured", False):
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "skipped", "ESCAVADOR_API_KEY nao configurada."),
        }
    try:
        publicacoes = await escavador_client.buscar_publicacoes(
            oab=f"{uf_oab.upper()}{numero_oab}",
            data_inicio=data_inicio or None,
        )
    except Exception as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "failed", "Escavador falhou na busca de publicacoes.", error=e),
        }
    items = [_normalize_publication_item(item, provider) for item in publicacoes if not item.get("_mock")]
    return {
        "items": items,
        "attempt": _provider_attempt(
            provider,
            "ok" if items else "empty",
            "Busca subsidiaria em publicacoes do Escavador." if items else "Escavador nao retornou publicacoes reais.",
            count=len(items),
        ),
    }


async def _try_jusbrasil_provider(numero_oab: str, uf_oab: str, data_inicio: str) -> dict:
    provider = "JusBrasil"
    try:
        from services.jusbrasil import jusbrasil_client
    except ImportError as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "unavailable", "Servico JusBrasil nao disponivel.", error=e),
        }
    if not getattr(jusbrasil_client, "is_configured", False):
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "skipped", "JUSBRASIL_API_KEY nao configurada."),
        }
    tribunal = _default_tribunal_for_uf(uf_oab)
    try:
        diarios = await jusbrasil_client.buscar_diarios(
            f"OAB {uf_oab.upper()} {numero_oab}",
            data=data_inicio or None,
            tribunal=tribunal,
        )
    except Exception as e:
        return {
            "items": [],
            "attempt": _provider_attempt(provider, "failed", "JusBrasil falhou na busca de diarios.", error=e),
        }
    items = [_normalize_publication_item(item, provider) for item in diarios if not item.get("_mock")]
    return {
        "items": items,
        "attempt": _provider_attempt(
            provider,
            "ok" if items else "empty",
            "Busca subsidiaria em diarios do JusBrasil." if items else "JusBrasil nao retornou publicacoes reais.",
            count=len(items),
        ),
    }


async def _search_intimacoes_oab_chain(
    numero_oab: str,
    uf_oab: str,
    data_inicio: str,
    data_fim: str,
) -> dict:
    """Search intimation sources in a transparent, operator-visible order."""
    attempts = []
    auth_status = "unknown"
    grant_attempted = "none"

    comunica = await _try_comunicaapi_provider(numero_oab, uf_oab, data_inicio, data_fim)
    attempts.append(comunica["attempt"])
    auth_status = comunica.get("auth_status", auth_status)
    grant_attempted = comunica.get("grant_attempted", grant_attempted)
    if comunica["items"]:
        return {
            "items": comunica["items"],
            "provider": "ComunicaAPI PJE/CNJ",
            "provider_status": "ok",
            "reason": comunica["attempt"]["reason"],
            "last_error": comunica["attempt"]["error"],
            "fallback_active": False,
            "fallback_chain": attempts,
            "auth_status": auth_status,
            "grant_attempted": grant_attempted,
            "source": comunica.get("source", "ComunicaAPI PJE/CNJ"),
            "last_attempt_at": comunica["attempt"]["attempted_at"],
            "code": comunica["attempt"]["error"] or None,
        }

    primary_failed = _is_integration_failure(comunica["attempt"])
    fallback_process_results = None

    if not primary_failed:
        return {
            "items": [],
            "provider": "ComunicaAPI PJE/CNJ",
            "provider_status": "empty",
            "reason": "Consulta executada sem intimacoes no periodo selecionado.",
            "last_error": "",
            "fallback_active": False,
            "fallback_chain": attempts,
            "auth_status": auth_status,
            "grant_attempted": grant_attempted,
            "source": comunica.get("source", "ComunicaAPI PJE/CNJ"),
            "last_attempt_at": comunica["attempt"]["attempted_at"],
            "code": None,
        }

    datajud = await _try_datajud_provider(numero_oab, uf_oab)
    attempts.append(datajud["attempt"])
    if datajud["items"]:
        fallback_process_results = datajud

    escavador = await _try_escavador_provider(numero_oab, uf_oab, data_inicio)
    attempts.append(escavador["attempt"])
    if escavador["items"]:
        return {
            "items": escavador["items"],
            "provider": "Escavador",
            "provider_status": "fallback",
            "reason": "PDPJ/ComunicaAPI falhou; usando publicacoes do Escavador.",
            "last_error": comunica["attempt"]["error"],
            "fallback_active": True,
            "fallback_chain": attempts,
            "auth_status": auth_status,
            "grant_attempted": grant_attempted,
            "source": "Escavador",
            "last_attempt_at": escavador["attempt"]["attempted_at"],
            "code": comunica["attempt"]["error"] or "upstream_failed",
        }

    jusbrasil = await _try_jusbrasil_provider(numero_oab, uf_oab, data_inicio)
    attempts.append(jusbrasil["attempt"])
    if jusbrasil["items"]:
        return {
            "items": jusbrasil["items"],
            "provider": "JusBrasil",
            "provider_status": "fallback",
            "reason": "PDPJ/ComunicaAPI falhou; usando diarios do JusBrasil.",
            "last_error": comunica["attempt"]["error"],
            "fallback_active": True,
            "fallback_chain": attempts,
            "auth_status": auth_status,
            "grant_attempted": grant_attempted,
            "source": "JusBrasil",
            "last_attempt_at": jusbrasil["attempt"]["attempted_at"],
            "code": comunica["attempt"]["error"] or "upstream_failed",
        }

    if fallback_process_results:
        return {
            "items": fallback_process_results["items"],
            "provider": "DataJud (CNJ)",
            "provider_status": "fallback_limited",
            "reason": (
                "PDPJ/ComunicaAPI falhou; DataJud retornou processos da OAB, "
                "mas nao intimações prontas para importacao."
            ),
            "last_error": comunica["attempt"]["error"],
            "fallback_active": True,
            "fallback_chain": attempts,
            "auth_status": auth_status,
            "grant_attempted": grant_attempted,
            "source": "DataJud (CNJ)",
            "last_attempt_at": fallback_process_results["attempt"]["attempted_at"],
            "code": comunica["attempt"]["error"] or "upstream_failed",
        }

    return {
        "items": [],
        "provider": "Nenhuma API",
        "provider_status": "failed",
        "reason": "Nenhuma fonte retornou intimacoes ou resultados para a OAB/periodo informado.",
        "last_error": comunica["attempt"]["error"],
        "fallback_active": True,
        "fallback_chain": attempts,
        "auth_status": auth_status,
        "grant_attempted": grant_attempted,
        "source": None,
        "last_attempt_at": attempts[-1]["attempted_at"] if attempts else _utc_now_iso(),
        "code": comunica["attempt"]["error"] or "integration_failed",
    }


def _get_stats(db: Session, org_id: int) -> dict:
    """Compute stat card values."""
    hoje = date.today()
    proximos_limite = hoje + timedelta(days=7)

    base = "SELECT COUNT(*) FROM prazos_processuais WHERE org_id = :org_id"

    total = db.execute(text(base), {"org_id": org_id}).scalar() or 0

    fatais_hoje = db.execute(
        text(base + " AND data_vencimento = :hoje AND status NOT IN ('concluido')"),
        {"org_id": org_id, "hoje": hoje},
    ).scalar() or 0

    proximos = db.execute(
        text(
            base + " AND data_vencimento > :hoje AND data_vencimento <= :limite "
            "AND status NOT IN ('concluido')"
        ),
        {"org_id": org_id, "hoje": hoje, "limite": proximos_limite},
    ).scalar() or 0

    vencidos = db.execute(
        text(base + " AND data_vencimento < :hoje AND status NOT IN ('concluido', 'perdido')"),
        {"org_id": org_id, "hoje": hoje},
    ).scalar() or 0

    concluidos = db.execute(
        text(base + " AND status = 'concluido'"),
        {"org_id": org_id},
    ).scalar() or 0

    return {
        "total": total,
        "fatais_hoje": fatais_hoje,
        "vencidos": vencidos,
        "proximos": proximos,
        "concluidos": concluidos,
    }


def _append_prazos_filters(
    query: str,
    params: dict,
    *,
    search: str = "",
    status_filter: str = "",
    mes: str = "",
    tribunal: str = "",
) -> str:
    """Apply dashboard filters shared by list and derived counts."""
    if search:
        query += """
            AND (
                LOWER(COALESCE(c.case_number, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(c.numero_processo, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(p.processo_override, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(p.cliente_override, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(cl.first_name, '') || ' ' || COALESCE(cl.last_name, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(c.case_name, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(p.responsavel, '')) LIKE LOWER(:search)
                OR LOWER(COALESCE(p.tipo, '')) LIKE LOWER(:search)
            )
        """
        params["search"] = f"%{search}%"

    if status_filter and status_filter != "todos":
        query += " AND p.status = :status_filter"
        params["status_filter"] = status_filter
    elif not status_filter:
        query += " AND p.status NOT IN ('concluido')"

    if mes:
        try:
            ano, m = mes.split("-")
            query += " AND EXTRACT(YEAR FROM p.data_vencimento) = :ano AND EXTRACT(MONTH FROM p.data_vencimento) = :mes"
            params["ano"] = int(ano)
            params["mes"] = int(m)
        except (ValueError, AttributeError):
            pass

    # C1 fix: Filtro por tribunal — mapear codigo para pattern do no processo
    if tribunal:
        if tribunal in TRIBUNAL_PATTERNS:
            query += " AND COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE :trib_pat"
            params["trib_pat"] = TRIBUNAL_PATTERNS[tribunal]
        elif tribunal == "Outro":
            known_pats = " AND ".join(
                f"COALESCE(p.processo_override, c.numero_processo, c.case_number, '') NOT LIKE '{v}'"
                for v in TRIBUNAL_PATTERNS.values()
            )
            query += f" AND ({known_pats})"

    return query


def _get_prazos(
    db: Session,
    org_id: int,
    search: str = "",
    status_filter: str = "",
    mes: str = "",
    tribunal: str = "",
    limit: Optional[int] = None,
) -> list:
    """Fetch prazos with optional filters, joined with cases."""
    query = """
        SELECT
            p.id, p.case_id, p.tipo, p.data_intimacao, p.data_inicio,
            p.data_vencimento, p.dias_prazo, p.responsavel, p.status,
            p.descricao, p.uf, p.dobro, p.created_at, p.tipo_peticao,
            COALESCE(p.ordem, 0) AS ordem,
            COALESCE(p.processo_override, c.numero_processo, c.case_number) AS processo,
            COALESCE(p.cliente_override, TRIM(COALESCE(cl.first_name, '') || ' ' || COALESCE(cl.last_name, '')), c.case_name) AS cliente,
            c.case_name AS parte_contraria
        FROM prazos_processuais p
        LEFT JOIN cases c ON p.case_id = c.id
        LEFT JOIN clients cl ON c.client_id = cl.id
        WHERE p.org_id = :org_id
    """
    params = {"org_id": org_id}

    query = _append_prazos_filters(
        query,
        params,
        search=search,
        status_filter=status_filter,
        mes=mes,
        tribunal=tribunal,
    )

    query += (
        " ORDER BY COALESCE(p.ordem, 999999),"
        " CASE WHEN p.data_vencimento IS NULL THEN 1 ELSE 0 END ASC,"
        " p.data_vencimento ASC, p.id ASC"
    )
    if limit is not None:
        query += " LIMIT :limit"
        params["limit"] = limit

    rows = db.execute(text(query), params).fetchall()
    hoje = date.today()
    alerta_3dias = hoje + timedelta(days=3)

    alerta_7dias = hoje + timedelta(days=7)
    prazos = []
    for row in rows:
        venc = row.data_vencimento
        dias_restantes = None
        if isinstance(venc, date):
            dias_restantes = _business_days_between(hoje, venc)

        # Urgencia: TODA linha ativa recebe uma cor
        if row.status == "concluido":
            urgencia = "concluido"
        elif row.status == "perdido":
            urgencia = "vencido"  # perdido = vermelho
        elif not isinstance(venc, date):
            urgencia = "verde"  # sem data = assume ok
        elif venc < hoje:
            urgencia = "vencido"
        elif venc == hoje:
            urgencia = "fatal"
        elif venc <= alerta_7dias:
            urgencia = "amarelo"  # <=7 dias
        else:
            urgencia = "verde"  # >7 dias

        prazos.append({
            "id": row.id,
            "case_id": row.case_id,
            "processo": row.processo or "—",
            "cliente": row.cliente or "—",
            "parte_contraria": row.parte_contraria or "—",
            "tipo": row.tipo,
            "data_intimacao": row.data_intimacao,
            "data_inicio": row.data_inicio,
            "data_vencimento": venc,
            "dias_prazo": row.dias_prazo,
            "dias_restantes": dias_restantes,
            "responsavel": row.responsavel or "—",
            "status": row.status,
            "descricao": row.descricao or "",
            "uf": row.uf,
            "dobro": row.dobro,
            "urgencia": urgencia,
            "tipo_peticao": row.tipo_peticao or "",
            "ordem": row.ordem or 0,
        })

    return prazos


def _get_prazos_vencidos_total(
    db: Session,
    org_id: int,
    search: str = "",
    status_filter: str = "",
    mes: str = "",
    tribunal: str = "",
) -> int:
    """Count overdue deadlines using the same filters and predicate as the table."""
    query = """
        SELECT COUNT(*)
        FROM prazos_processuais p
        LEFT JOIN cases c ON p.case_id = c.id
        LEFT JOIN clients cl ON c.client_id = cl.id
        WHERE p.org_id = :org_id
    """
    params = {"org_id": org_id, "hoje": date.today()}
    query = _append_prazos_filters(
        query,
        params,
        search=search,
        status_filter=status_filter,
        mes=mes,
        tribunal=tribunal,
    )
    query += """
        AND (
            p.status = 'perdido'
            OR (p.data_vencimento < :hoje AND COALESCE(p.status, '') != 'concluido')
        )
    """
    return db.execute(text(query), params).scalar() or 0


def _get_responsaveis(db: Session, org_id: int) -> list:
    """List distinct responsaveis for filter dropdown."""
    rows = db.execute(
        text(
            "SELECT DISTINCT responsavel FROM prazos_processuais "
            "WHERE org_id = :org_id AND responsavel IS NOT NULL "
            "ORDER BY responsavel"
        ),
        {"org_id": org_id},
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def _get_produtividade_setores(db: Session, org_id: int) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT COALESCE(NULLIF(responsavel, ''), 'Sem responsável') AS setor,
                   COUNT(*) AS total,
                   SUM(CASE WHEN COALESCE(status, 'pendente') NOT IN ('concluido', 'perdido') THEN 1 ELSE 0 END) AS pendentes,
                   SUM(CASE WHEN status = 'concluido' THEN 1 ELSE 0 END) AS concluidos,
                   SUM(CASE WHEN data_vencimento < CURRENT_DATE AND COALESCE(status, 'pendente') NOT IN ('concluido', 'perdido') THEN 1 ELSE 0 END) AS vencidos,
                   SUM(CASE WHEN data_vencimento >= CURRENT_DATE
                             AND data_vencimento <= CURRENT_DATE + INTERVAL '7 days'
                             AND COALESCE(status, 'pendente') NOT IN ('concluido', 'perdido') THEN 1 ELSE 0 END) AS proximos
            FROM prazos_processuais
            WHERE org_id = :org_id
            GROUP BY COALESCE(NULLIF(responsavel, ''), 'Sem responsável')
            ORDER BY vencidos DESC, pendentes DESC, total DESC, setor ASC
            LIMIT 8
        """),
        {"org_id": org_id},
    ).fetchall()
    data = []
    for row in rows:
        total = int(row.total or 0)
        pendentes = int(row.pendentes or 0)
        concluidos = int(row.concluidos or 0)
        vencidos = int(row.vencidos or 0)
        proximos = int(row.proximos or 0)
        em_dia = max(total - vencidos, 0)
        data.append({
            "setor": row.setor,
            "total": total,
            "pendentes": pendentes,
            "concluidos": concluidos,
            "vencidos": vencidos,
            "proximos": proximos,
            "eficiencia": round((concluidos / total) * 100) if total else 0,
            "produtividade": em_dia,
            "em_dia": em_dia,
            "status_label": "Atenção" if vencidos else ("Semana crítica" if proximos else "Em dia"),
        })
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def controladoria_dashboard(
    request: Request,
    search: str = "",
    status: str = "",
    mes: str = "",
    tribunal: str = "",
    db: Session = Depends(get_db),
):
    """Dashboard principal da Controladoria."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = _get_org_id(request)
    stats = _get_stats(db, org_id)
    prazos_render = _get_prazos(
        db,
        org_id,
        search=search,
        status_filter=status,
        mes=mes,
        tribunal=tribunal,
        limit=CONTROLADORIA_RENDER_LIMIT + 1,
    )
    prazos_truncated = len(prazos_render) > CONTROLADORIA_RENDER_LIMIT
    prazos = prazos_render[:CONTROLADORIA_RENDER_LIMIT]

    # P9: Extrair tribunais disponíveis para o dropdown
    tribunal_rows = db.execute(
        text("""
            SELECT DISTINCT
                CASE
                    WHEN COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE '%.5.03.%' THEN 'TRT3'
                    WHEN COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE '%.5.01.%' THEN 'TRT1'
                    WHEN COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE '%.4.06.%' THEN 'TRF6'
                    WHEN COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE '%.4.02.%' THEN 'TRF2'
                    WHEN COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE '%.8.13.%' THEN 'TJMG'
                    WHEN COALESCE(p.processo_override, c.numero_processo, c.case_number, '') LIKE '%.8.26.%' THEN 'TJSP'
                    ELSE 'Outro'
                END AS tribunal
            FROM prazos_processuais p
            LEFT JOIN cases c ON p.case_id = c.id
            WHERE p.org_id = :org_id AND p.status NOT IN ('concluido')
            ORDER BY 1
        """),
        {"org_id": org_id},
    ).fetchall()
    tribunais_disponiveis = [r.tribunal for r in tribunal_rows if r.tribunal and r.tribunal != 'Outro']
    if any(r.tribunal == 'Outro' for r in tribunal_rows):
        tribunais_disponiveis.append('Outro')

    # Buscar casos para o modal de novo prazo
    cases_query = (
        tenant_query(db, Case, org_id)
        .order_by(Case.case_number.asc())
        .limit(CONTROLADORIA_CASE_OPTION_LIMIT + 1)
        .all()
    )
    cases_truncated = len(cases_query) > CONTROLADORIA_CASE_OPTION_LIMIT
    cases_query = cases_query[:CONTROLADORIA_CASE_OPTION_LIMIT]

    # Prazos vencidos para popup de alerta
    prazos_vencidos = [p for p in prazos if p["urgencia"] == "vencido"]
    if prazos_truncated:
        prazos_vencidos_total = max(
            _get_prazos_vencidos_total(
                db,
                org_id,
                search=search,
                status_filter=status,
                mes=mes,
                tribunal=tribunal,
            ),
            len(prazos_vencidos),
        )
    else:
        prazos_vencidos_total = len(prazos_vencidos)
    prazos_vencidos_remaining = max(prazos_vencidos_total - min(len(prazos_vencidos), 15), 0)

    # Users da org para dropdown de responsável
    org_users = db.execute(
        text("SELECT id, name, email, user_type FROM users WHERE org_id = :org_id AND enabled = TRUE ORDER BY name"),
        {"org_id": org_id},
    ).fetchall()
    users_list = [{"id": u.id, "name": u.name, "initials": "".join(w[0].upper() for w in u.name.split()[:2])} for u in org_users]

    # Opções pros dropdowns de inline-edit Cliente/Processo (29/05 Victor): clicar
    # a célula abre um <select> com os existentes (tenant-isolado) + "cadastrar novo".
    # cliente_override/processo_override guardam o texto escolhido.
    clientes_opc = [
        {"id": r.id, "name": (r.name or "").strip()}
        for r in db.execute(
            text(
                "SELECT id, TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS name "
                "FROM clients WHERE org_id = :org_id ORDER BY first_name, last_name LIMIT 500"
            ),
            {"org_id": org_id},
        ).fetchall()
        if (r.name or "").strip()
    ]
    processos_opc = [
        {"id": c.id, "label": (c.case_number or c.case_name or f"Processo {c.id}")}
        for c in cases_query
    ]

    comuns = prazos_comuns()
    org_ctx = inject_org_context(request)

    return templates.TemplateResponse(
        "app/controladoria/dashboard.html",
        {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            "stats": stats,
            "prazos": prazos,
            "prazos_truncated": prazos_truncated,
            "controladoria_render_limit": CONTROLADORIA_RENDER_LIMIT,
            "prazos_vencidos": prazos_vencidos,
            "prazos_vencidos_total": prazos_vencidos_total,
            "prazos_vencidos_remaining": prazos_vencidos_remaining,
            "cases": cases_query,
            "cases_truncated": cases_truncated,
            "controladoria_case_option_limit": CONTROLADORIA_CASE_OPTION_LIMIT,
            "prazos_comuns": comuns,
            "org_users": users_list,
            "clientes_opc": clientes_opc,
            "processos_opc": processos_opc,
            "produtividade_setores": _get_produtividade_setores(db, org_id),
            "api_status_cards": _controladoria_api_status_cards(),
            "search": search,
            "status_filter": status,
            "mes_filter": mes,
            "tribunal_filter": tribunal,
            "tribunais_disponiveis": tribunais_disponiveis,
            **org_ctx,
        },
    )


@router.get("/cases/search")
async def buscar_cases_controladoria(
    request: Request,
    q: str = Query("", max_length=80),
    db: Session = Depends(get_db),
):
    """Search tenant cases for the Novo Prazo selector without rendering all options."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    term = (q or "").strip()
    if len(term) < 2 and not term.isdigit():
        return {"items": []}

    org_id = _get_org_id(request)
    rows = db.execute(
        text("""
            SELECT
                c.id,
                c.case_number,
                c.numero_processo,
                c.case_name,
                COALESCE(cl.first_name, '') || ' ' || COALESCE(cl.last_name, '') AS cliente
            FROM cases c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.org_id = :org_id
              AND (
                CAST(c.id AS TEXT) = :id_term
                OR LOWER(COALESCE(c.case_number, '')) LIKE LOWER(:term)
                OR LOWER(COALESCE(c.numero_processo, '')) LIKE LOWER(:term)
                OR LOWER(COALESCE(c.case_name, '')) LIKE LOWER(:term)
                OR LOWER(COALESCE(cl.first_name, '') || ' ' || COALESCE(cl.last_name, '')) LIKE LOWER(:term)
              )
            ORDER BY
                CASE
                    WHEN COALESCE(c.case_number, c.numero_processo, '') = '' THEN 1
                    ELSE 0
                END ASC,
                COALESCE(c.case_number, c.numero_processo, '') ASC,
                c.id ASC
            LIMIT 20
        """),
        {"org_id": org_id, "id_term": term if term.isdigit() else "", "term": f"%{term}%"},
    ).fetchall()

    items = []
    for row in rows:
        numero = row.case_number or row.numero_processo or "Sem numero"
        nome = row.case_name or "Sem nome"
        cliente = (row.cliente or "").strip()
        label = f"{numero} - {nome}"
        if cliente:
            label = f"{label} ({cliente})"
        items.append({"id": row.id, "label": label})

    return {"items": items}


@router.post("/novo-prazo")
async def criar_prazo(request: Request, db: Session = Depends(get_db)):
    """Criar novo prazo processual."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    try:
        data = await request.json()
    except Exception:
        # Fallback: form data
        form = await request.form()
        data = dict(form)

    case_id = data.get("case_id")
    processo_manual = data.get("processo_manual", "").strip()
    cliente_manual = data.get("cliente_manual", "").strip()

    # Prazo avulso: o advogado pode informar apenas o número do processo,
    # sem obrigar cadastro completo em cases.
    processo_override = processo_manual or None
    if case_id == "__manual__":
        case_id = None

    tipo = data.get("tipo", "").strip()
    data_intimacao_str = data.get("data_intimacao", "")
    dias_prazo = data.get("dias_prazo")
    responsavel = data.get("responsavel", "").strip()
    uf = data.get("uf", "MG").upper()
    descricao = data.get("descricao", "").strip()
    dobro = data.get("dobro", False)

    if isinstance(dobro, str):
        dobro = dobro.lower() in ("true", "1", "on", "sim")

    if not tipo:
        return JSONResponse({"error": "Tipo de prazo e obrigatorio"}, status_code=400)
    if not data_intimacao_str:
        return JSONResponse({"error": "Data de intimacao e obrigatoria"}, status_code=400)

    try:
        data_intimacao = date.fromisoformat(data_intimacao_str)
    except ValueError:
        return JSONResponse({"error": "Data de intimacao invalida (use AAAA-MM-DD)"}, status_code=400)

    # Determinar dias do prazo
    if not dias_prazo:
        comuns = prazos_comuns()
        if tipo in comuns:
            dias_prazo = comuns[tipo]["dias"]
        else:
            dias_prazo = 15  # padrao
    else:
        try:
            dias_prazo = int(dias_prazo)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Dias do prazo deve ser um numero"}, status_code=400)

    # Calcular datas
    data_inicio = proximo_dia_util(data_intimacao + timedelta(days=1), uf)
    data_vencimento = calcular_prazo(data_intimacao, dias_prazo, uf, dobro)

    # Inserir no banco
    try:
        db.execute(
            text("""
                INSERT INTO prazos_processuais
                    (case_id, org_id, tipo, data_intimacao, data_inicio, data_vencimento,
                     dias_prazo, responsavel, status, descricao, uf, dobro, processo_override, cliente_override)
                VALUES
                    (:case_id, :org_id, :tipo, :data_intimacao, :data_inicio, :data_vencimento,
                     :dias_prazo, :responsavel, 'pendente', :descricao, :uf, :dobro, :processo_override, :cliente_override)
            """),
            {
                "case_id": int(case_id) if case_id else None,
                "org_id": org_id,
                "tipo": tipo,
                "data_intimacao": data_intimacao,
                "data_inicio": data_inicio,
                "data_vencimento": data_vencimento,
                "dias_prazo": dias_prazo,
                "responsavel": responsavel or None,
                "descricao": descricao or None,
                "uf": uf,
                "dobro": dobro,
                "processo_override": processo_override,
                "cliente_override": cliente_manual or None,
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Erro ao criar prazo: %s", e)
        return JSONResponse({"error": f"Erro ao salvar: {str(e)}"}, status_code=500)

    logger.info(
        "Prazo criado: tipo=%s, intimacao=%s, vencimento=%s, responsavel=%s",
        tipo, data_intimacao, data_vencimento, responsavel,
    )

    # Se veio de JSON, retorna JSON. Se form, redireciona.
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return JSONResponse({
            "success": True,
            "prazo": {
                "tipo": tipo,
                "data_intimacao": data_intimacao.isoformat(),
                "data_inicio": data_inicio.isoformat(),
                "data_vencimento": data_vencimento.isoformat(),
                "dias_prazo": dias_prazo,
                "responsavel": responsavel,
                "processo": processo_override,
                "cliente": cliente_manual,
            },
        })
    return RedirectResponse(url=f"{PREFIX}/controladoria", status_code=303)


@router.post("/buscar-intimacoes")
async def buscar_intimacoes(request: Request, db: Session = Depends(get_db)):
    """Buscar intimacoes via DataJud para os processos monitorados."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    try:
        data = await request.json()
    except Exception:
        data = {}

    data_inicio_str = data.get("data_inicio", "")
    data_fim_str = data.get("data_fim", "")

    # Buscar processos monitorados (cases com case_number preenchido)
    cases = tenant_query(db, Case, org_id).filter(
        Case.case_number.isnot(None),
        Case.case_number != "",
    ).all()

    if not cases:
        return JSONResponse({
            "success": True,
            "message": "Nenhum processo monitorado encontrado",
            "intimacoes": [],
        })

    # Tentar importar DataJud
    try:
        from services.datajud import datajud_client
    except ImportError:
        return JSONResponse({
            "error": "Servico DataJud nao disponivel",
        }, status_code=503)

    intimacoes = []
    erros = []

    for case in cases:
        numero = case.case_number
        if not numero or len(numero.replace("-", "").replace(".", "")) < 15:
            continue  # Pular numeros que nao parecem ser CNJ

        try:
            movimentacoes = await datajud_client.get_movimentacoes(numero)
            for mov in movimentacoes:
                nome_mov = mov.get("nome", "").lower()
                # Filtrar por intimacoes e citacoes
                if any(kw in nome_mov for kw in ["intimacao", "intimação", "citacao", "citação", "notificacao", "notificação"]):
                    data_hora = mov.get("dataHora", "")
                    # Filtrar por periodo se informado
                    if data_inicio_str and data_hora < data_inicio_str:
                        continue
                    if data_fim_str and data_hora > data_fim_str + "T23:59:59":
                        continue

                    intimacoes.append({
                        "processo": numero,
                        "case_id": case.id,
                        "case_name": case.case_name or "",
                        "tipo": mov.get("nome", ""),
                        "data": data_hora[:10] if data_hora else "",
                        "complemento": ", ".join(
                            c.get("descricao", "")
                            for c in mov.get("complementosTabelados", [])
                        ),
                    })
        except Exception as e:
            erros.append({"processo": numero, "erro": str(e)})
            logger.warning("Erro ao buscar intimacoes do processo %s: %s", numero, e)

    intimacoes.sort(key=lambda x: x.get("data", ""), reverse=True)

    return JSONResponse({
        "success": True,
        "total": len(intimacoes),
        "intimacoes": intimacoes,
        "erros": erros,
        "processos_consultados": len(cases),
    })


@router.post("/buscar-comunicaapi")
async def buscar_comunicaapi(request: Request, db: Session = Depends(get_db)):
    """Buscar intimacoes via ComunicaAPI PJE/CNJ por numero OAB.
    Mais eficiente que buscar processo a processo: uma unica chamada retorna tudo."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        data = {}

    numero_oab = data.get("numero_oab", "").strip()
    uf_oab = data.get("uf_oab", "MG").strip().upper()
    data_inicio = data.get("data_inicio", "")
    data_fim = data.get("data_fim", "")
    org_id = _get_org_id(request)

    if not numero_oab:
        return JSONResponse({"error": "Numero OAB obrigatorio"}, status_code=400)

    try:
        resultado = await _search_intimacoes_oab_chain(numero_oab, uf_oab, data_inicio, data_fim)
        intimacoes = resultado.get("items", [])
        failed = resultado.get("provider_status") == "failed"
        payload = {
            "success": not failed,
            "code": resultado.get("code"),
            "message": resultado.get("reason"),
            "error": resultado.get("reason") if failed else None,
            "total": len(intimacoes),
            "intimacoes": intimacoes,
            "source": resultado.get("source") or resultado.get("provider"),
            "provider": resultado.get("provider"),
            "provider_status": resultado.get("provider_status"),
            "reason": resultado.get("reason"),
            "last_error": resultado.get("last_error"),
            "last_attempt_at": resultado.get("last_attempt_at"),
            "fallback_active": resultado.get("fallback_active", False),
            "fallback_chain": resultado.get("fallback_chain", []),
            "auth_status": resultado.get("auth_status"),
            "grant_attempted": resultado.get("grant_attempted"),
        }
        if not failed:
            payload.pop("error", None)
        status_code = _failed_status_code(str(resultado.get("code") or "")) if failed else 200
        return JSONResponse(payload, status_code=status_code)
    except Exception as e:
        logger.error("ComunicaAPI search error: %s", e, exc_info=True)
        return JSONResponse({
            "success": False,
            "code": "unexpected",
            "message": "Falha interna ao executar a cadeia de APIs.",
            "error": "Falha interna ao executar a cadeia de APIs.",
            "total": 0,
            "intimacoes": [],
            "provider": "Controladoria",
            "provider_status": "failed",
            "reason": "Falha interna ao executar a cadeia de APIs.",
            "last_error": _safe_api_error(e),
            "fallback_active": False,
            "fallback_chain": [],
        }, status_code=500)


@router.post("/importar-intimacoes")
async def importar_intimacoes(request: Request, db: Session = Depends(get_db)):
    """Importar intimacoes selecionadas do ComunicaAPI como novos prazos processuais."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    intimacoes = data.get("intimacoes", [])
    if not intimacoes:
        return JSONResponse({"error": "Nenhuma intimacao enviada"}, status_code=400)

    imported = 0
    skipped = 0

    for item in intimacoes:
        numero_processo = item.get("numero_processo", "").strip()
        texto_raw = item.get("texto", "").strip()
        data_disponibilizacao = item.get("data_disponibilizacao", "")
        tribunal = item.get("tribunal", "")
        orgao = item.get("orgao", "")

        # C4: Limpar HTML/códigos da descrição
        texto = re.sub(r'<[^>]+>', '', texto_raw)  # remove HTML tags
        texto = re.sub(r'&[a-zA-Z]+;', ' ', texto)  # remove &nbsp; etc
        texto = re.sub(r'\s+', ' ', texto).strip()  # normalizar espaços

        # C2+C3: Extrair prazo da publicação via regex
        dias_extraido = None
        prazo_patterns = [
            r'prazo\s+de\s+(\d+)\s*dias?',
            r'em\s+(\d+)\s*dias?\s*[uú]teis',
            r'no\s+prazo\s+de\s+(\d+)',
            r'(\d+)\s*dias?\s*para\s+(?:responder|manifestar|contestar|cumprir)',
            r'intimad[oa]\s+.*?(\d+)\s*dias?',
        ]
        for pat in prazo_patterns:
            m = re.search(pat, texto, re.IGNORECASE)
            if m:
                dias_extraido = int(m.group(1))
                if 1 <= dias_extraido <= 365:  # sanity check
                    break
                else:
                    dias_extraido = None
        dias_prazo = dias_extraido or 15  # default 15 se não encontrou

        # Parse date
        try:
            dt_intimacao = date.fromisoformat(data_disponibilizacao)
        except (ValueError, TypeError):
            dt_intimacao = date.today()

        # Check for duplicates by (processo + data_intimacao) OR (descricao + data_intimacao)
        dup_count = db.execute(
            text(
                "SELECT COUNT(*) FROM prazos_processuais p "
                "LEFT JOIN cases c ON p.case_id = c.id "
                "WHERE p.org_id = :org_id AND p.data_intimacao = :data "
                "AND (p.descricao = :texto OR COALESCE(p.processo_override, c.numero_processo, c.case_number) = :proc)"
            ),
            {"org_id": org_id, "texto": texto, "data": dt_intimacao, "proc": numero_processo},
        ).scalar() or 0

        if dup_count > 0:
            skipped += 1
            continue

        # Try to match case by numero_processo
        case_id = None
        if numero_processo:
            case_row = db.execute(
                text(
                    "SELECT id FROM cases "
                    "WHERE org_id = :org_id AND (case_number = :case_number OR numero_processo = :case_number) LIMIT 1"
                ),
                {"org_id": org_id, "case_number": numero_processo},
            ).fetchone()
            if case_row:
                case_id = case_row.id

        # Calculate vencimento using extracted or default days
        try:
            dt_vencimento = calcular_prazo(dt_intimacao, dias_prazo, estado="MG")
        except Exception:
            dt_vencimento = dt_intimacao + timedelta(days=int(dias_prazo * 1.4))

        # Determine processo_override (only if no case match)
        processo_override = numero_processo if (numero_processo and not case_id) else None

        db.execute(
            text(
                "INSERT INTO prazos_processuais "
                "(org_id, case_id, tipo, data_intimacao, data_inicio, dias_prazo, "
                "data_vencimento, descricao, status, responsavel, uf, processo_override, created_at) "
                "VALUES (:org_id, :case_id, :tipo, :data_intimacao, :data_inicio, :dias_prazo, "
                ":data_vencimento, :descricao, :status, :responsavel, :uf, :processo_override, CURRENT_TIMESTAMP)"
            ),
            {
                "org_id": org_id,
                "case_id": case_id,
                "tipo": "Prazo Processual",
                "data_intimacao": dt_intimacao,
                "data_inicio": dt_intimacao,
                "dias_prazo": dias_prazo,
                "data_vencimento": dt_vencimento,
                "descricao": texto,
                "status": "pendente",
                "responsavel": None,
                "uf": "MG",
                "processo_override": processo_override,
            },
        )
        imported += 1

    db.commit()
    logger.info(
        "Importacao intimacoes: %d importados, %d ignorados (org_id=%d)",
        imported, skipped, org_id,
    )

    return JSONResponse({
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "total": imported + skipped,
    })


@router.post("/{prazo_id}/concluir")
async def concluir_prazo(prazo_id: int, request: Request, db: Session = Depends(get_db)):
    """Marcar prazo como concluido, com tipo de peticao e data de conclusao."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    # Extract tipo_peticao and data_conclusao from request body
    tipo_peticao = None
    data_conclusao = None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
            tipo_peticao = data.get("tipo_peticao")
            data_conclusao_str = data.get("data_conclusao")
            if data_conclusao_str:
                data_conclusao = date.fromisoformat(data_conclusao_str)
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            tipo_peticao = form.get("tipo_peticao")
            data_conclusao_str = form.get("data_conclusao")
            if data_conclusao_str:
                data_conclusao = date.fromisoformat(data_conclusao_str)
        except Exception:
            pass

    if not data_conclusao:
        data_conclusao = date.today()

    result = db.execute(
        text(
            "UPDATE prazos_processuais SET status = 'concluido', updated_at = CURRENT_TIMESTAMP, "
            "tipo_peticao = :tipo_peticao, data_conclusao = :data_conclusao "
            "WHERE id = :id AND org_id = :org_id"
        ),
        {
            "id": prazo_id,
            "org_id": org_id,
            "tipo_peticao": tipo_peticao,
            "data_conclusao": data_conclusao,
        },
    )
    db.commit()

    if result.rowcount == 0:
        return JSONResponse({"error": "Prazo nao encontrado"}, status_code=404)

    logger.info("Prazo %d marcado como concluido (tipo_peticao=%s)", prazo_id, tipo_peticao)

    if "application/json" in content_type:
        return JSONResponse({"success": True})
    return RedirectResponse(url=f"{PREFIX}/controladoria", status_code=303)


@router.get("/api/datajud")
async def api_datajud_busca(
    request: Request,
    tipo: str = Query("numero", description="numero | oab | nome"),
    q: str = Query("", description="Termo de busca"),
    tribunal: str = Query("TJMG", description="Codigo do tribunal (ex.: TJMG, TJSP)"),
    db: Session = Depends(get_db),
):
    """Busca publica no DataJud (CNJ) embutida na controladoria — por numero CNJ, OAB do
    advogado ou nome da parte. API publica do CNJ, NAO precisa de credencial/secret."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "error": "Nao autenticado"}, status_code=401)

    termo = (q or "").strip()
    if not termo:
        return JSONResponse({"ok": False, "error": "Informe um numero, OAB ou nome para buscar."}, status_code=400)
    tribunal_code = (tribunal or "TJMG").strip().upper()

    try:
        from services.datajud import datajud_client
        if tipo == "numero":
            raw = await datajud_client.consultar_processo(termo, tribunal=tribunal_code)
            records = [raw] if raw else []
        elif tipo == "oab":
            records = await datajud_client.buscar_por_advogado(termo, tribunal=tribunal_code)
        else:
            records = await datajud_client.buscar_por_parte(termo, tribunal=tribunal_code)
    except Exception as exc:
        logger.error("DataJud busca falhou (tipo=%s, tribunal=%s): %s", tipo, tribunal_code, exc)
        return JSONResponse(
            {"ok": False, "error": "Falha ao consultar o CNJ. Tente outro tribunal ou termo."},
            status_code=502,
        )

    def _fmt(rec):
        classe = rec.get("classe") or {}
        orgao = rec.get("orgaoJulgador") or {}
        assuntos = rec.get("assuntos") or []
        movs = rec.get("movimentos") or []
        ultimo = None
        if movs:
            try:
                ultimo = sorted(movs, key=lambda m: (m or {}).get("dataHora") or "", reverse=True)[0]
            except Exception:
                ultimo = movs[-1]
        return {
            "numero": rec.get("numeroProcesso") or "",
            "classe": (classe.get("nome") if isinstance(classe, dict) else "") or "",
            "tribunal": rec.get("tribunal") or tribunal_code,
            "orgao": (orgao.get("nome") if isinstance(orgao, dict) else "") or "",
            "assunto": (assuntos[0].get("nome") if assuntos and isinstance(assuntos[0], dict) else "") or "",
            "grau": rec.get("grau") or "",
            "data_ajuizamento": rec.get("dataAjuizamento") or "",
            "ultimo_movimento": (ultimo.get("nome") if isinstance(ultimo, dict) else "") or "",
            "ultimo_movimento_data": (ultimo.get("dataHora") if isinstance(ultimo, dict) else "") or "",
        }

    results = [_fmt(r) for r in records if r]
    return JSONResponse({"ok": True, "source": "DataJud (CNJ)", "count": len(results), "results": results})


@router.get("/api/produtividade")
async def api_produtividade(
    request: Request,
    mes: str = Query(None, description="Mes no formato YYYY-MM"),
    db: Session = Depends(get_db),
):
    """Retorna dados de produtividade por tipo de peticao para o pie chart."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    # Default to current month
    if not mes:
        mes = date.today().strftime("%Y-%m")

    try:
        ano, m = mes.split("-")
        ano = int(ano)
        m = int(m)
    except (ValueError, AttributeError):
        return JSONResponse({"error": "Formato de mes invalido. Use YYYY-MM"}, status_code=400)

    if m < 1 or m > 12:
        return JSONResponse({"error": "Formato de mes invalido. Use YYYY-MM"}, status_code=400)

    period_start = date(ano, m, 1)
    period_end = date(ano + 1, 1, 1) if m == 12 else date(ano, m + 1, 1)

    # C2 ([parceiro] 02/06): um prazo concluido conta na produtividade do mes quando a
    # DATA DE CONCLUSAO **ou** a DATA DE VENCIMENTO cai no mes. Antes so contava por
    # data_conclusao (com updated_at de fallback), entao prazos concluidos com
    # vencimento em maio/01-jun ficavam de fora da contagem mensal.
    rows = db.execute(
        text("""
            SELECT tipo_peticao, COUNT(*) as qtd
            FROM prazos_processuais
            WHERE org_id = :org_id
              AND status = 'concluido'
              AND tipo_peticao IS NOT NULL AND tipo_peticao != ''
              AND (
                  (data_conclusao IS NOT NULL AND data_conclusao >= :period_start AND data_conclusao < :period_end)
                  OR
                  (data_vencimento IS NOT NULL AND data_vencimento >= :period_start AND data_vencimento < :period_end)
                  OR
                  (data_conclusao IS NULL AND data_vencimento IS NULL AND updated_at >= :period_start AND updated_at < :period_end)
              )
            GROUP BY tipo_peticao
            ORDER BY qtd DESC
        """),
        {"org_id": org_id, "period_start": period_start, "period_end": period_end},
    ).fetchall()

    tipos = {}
    total = 0
    for row in rows:
        tipos[row.tipo_peticao] = row.qtd
        total += row.qtd

    META = 100  # meta mensal configuravel

    return JSONResponse({
        "total": total,
        "mes": mes,
        "tipos": tipos,
        "meta_batida": total >= META,
        "meta": META,
    })


@router.post("/reordenar")
async def reordenar_prazos(request: Request, db: Session = Depends(get_db)):
    """Persist manual row ordering from the Controladoria table."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)
    try:
        data = await request.json()
        ids = [int(value) for value in data.get("ids", []) if value]
    except (TypeError, ValueError):
        return JSONResponse({"error": "Lista de prazos invalida"}, status_code=400)

    if not ids:
        return JSONResponse({"error": "Nenhum prazo informado"}, status_code=400)

    try:
        for position, prazo_id in enumerate(ids, start=1):
            db.execute(
                text("""
                    UPDATE prazos_processuais
                    SET ordem = :ordem, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND org_id = :org_id
                """),
                {"ordem": position, "id": prazo_id, "org_id": org_id},
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Erro ao reordenar prazos: %s", exc)
        return JSONResponse({"error": "Erro ao salvar ordem dos prazos"}, status_code=500)

    return JSONResponse({"success": True, "count": len(ids)})


@router.post("/{prazo_id}/update")
async def update_prazo(prazo_id: int, request: Request, db: Session = Depends(get_db)):
    """Inline update a single field on a prazo (Asana-style editing)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    field = data.get("field")
    value = data.get("value")

    # Whitelist of editable fields
    allowed_fields = {
        "descricao": "descricao",
        "status": "status",
        "tipo": "tipo",
        "responsavel": "responsavel",
        "processo": "processo_override",
        "cliente": "cliente_override",
        "dias_prazo": "dias_prazo",
        "data_inicio": "data_inicio",
        "data_intimacao": "data_intimacao",
        "tipo_peticao": "tipo_peticao",
    }

    if field not in allowed_fields:
        return JSONResponse(
            {"error": f"Campo '{field}' nao editavel. Campos permitidos: {', '.join(allowed_fields.keys())}"},
            status_code=400,
        )

    # Validate status values
    if field == "status" and value not in ("pendente", "em_andamento", "concluido", "perdido"):
        return JSONResponse({"error": f"Status invalido: {value}"}, status_code=400)

    col = allowed_fields[field]

    # P8 fix: Ao editar dias_prazo, recalcular data_vencimento
    extra_updates = ""
    extra_params = {}
    if field == "dias_prazo":
        try:
            new_dias = int(value)
            # Buscar data_inicio e uf atuais do prazo
            prazo_row = db.execute(
                text("SELECT data_inicio, data_intimacao, uf, dobro FROM prazos_processuais WHERE id = :id AND org_id = :org_id"),
                {"id": prazo_id, "org_id": org_id},
            ).fetchone()
            if prazo_row and prazo_row.data_intimacao:
                uf = prazo_row.uf or "MG"
                dobro = prazo_row.dobro or False
                new_vencimento = calcular_prazo(prazo_row.data_intimacao, new_dias, uf, dobro)
                extra_updates = ", data_vencimento = :new_venc"
                extra_params["new_venc"] = new_vencimento
                value = new_dias
        except (TypeError, ValueError):
            pass

    try:
        result = db.execute(
            text(
                f"UPDATE prazos_processuais SET {col} = :value{extra_updates}, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id AND org_id = :org_id"
            ),
            {"value": value, "id": prazo_id, "org_id": org_id, **extra_params},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Erro ao atualizar prazo %d: %s", prazo_id, e)
        return JSONResponse({"error": f"Erro ao salvar: {str(e)}"}, status_code=500)

    if result.rowcount == 0:
        return JSONResponse({"error": "Prazo nao encontrado"}, status_code=404)

    resp = {"success": True, "field": field, "value": value}
    if extra_params.get("new_venc"):
        resp["new_vencimento"] = str(extra_params["new_venc"])

    logger.info("Prazo %d atualizado: %s = %s %s", prazo_id, field, value,
                f"(vencimento recalculado: {extra_params.get('new_venc')})" if extra_params.get("new_venc") else "")
    return JSONResponse(resp)


@router.post("/{prazo_id}/excluir")
async def excluir_prazo(prazo_id: int, request: Request, db: Session = Depends(get_db)):
    """Excluir prazo."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    result = db.execute(
        text(
            "DELETE FROM prazos_processuais WHERE id = :id AND org_id = :org_id"
        ),
        {"id": prazo_id, "org_id": org_id},
    )
    db.commit()

    if result.rowcount == 0:
        return JSONResponse({"error": "Prazo nao encontrado"}, status_code=404)

    logger.info("Prazo %d excluido", prazo_id)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return JSONResponse({"success": True})
    return RedirectResponse(url=f"{PREFIX}/controladoria", status_code=303)


@router.post("/bulk-concluir")
async def bulk_concluir(request: Request, db: Session = Depends(get_db)):
    """Concluir multiplos prazos de uma vez."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    ids = data.get("ids", [])
    if not ids:
        return JSONResponse({"error": "Nenhum prazo selecionado"}, status_code=400)

    tipo_peticao = data.get("tipo_peticao", "Pet. Simples")
    data_conclusao = date.today()

    result = db.execute(
        text(
            "UPDATE prazos_processuais SET status = 'concluido', "
            "tipo_peticao = :tipo_peticao, data_conclusao = :data_conclusao, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE id IN :ids AND org_id = :org_id AND status != 'concluido'"
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids, "org_id": org_id, "tipo_peticao": tipo_peticao, "data_conclusao": data_conclusao},
    )
    db.commit()
    return JSONResponse({"success": True, "updated": result.rowcount})


@router.post("/bulk-excluir")
async def bulk_excluir(request: Request, db: Session = Depends(get_db)):
    """Excluir multiplos prazos de uma vez."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    ids = data.get("ids", [])
    if not ids:
        return JSONResponse({"error": "Nenhum prazo selecionado"}, status_code=400)

    result = db.execute(
        text("DELETE FROM prazos_processuais WHERE id IN :ids AND org_id = :org_id")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": ids, "org_id": org_id},
    )
    db.commit()
    return JSONResponse({"success": True, "deleted": result.rowcount})


@router.post("/{prazo_id}/duplicar")
async def duplicar_prazo(prazo_id: int, request: Request, db: Session = Depends(get_db)):
    """Duplicar um prazo processual."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    row = db.execute(
        text(
            "SELECT case_id, tipo, data_intimacao, data_inicio, data_vencimento, "
            "dias_prazo, responsavel, descricao, uf, dobro "
            "FROM prazos_processuais WHERE id = :id AND org_id = :org_id"
        ),
        {"id": prazo_id, "org_id": org_id},
    ).fetchone()

    if not row:
        return JSONResponse({"error": "Prazo nao encontrado"}, status_code=404)

    result = db.execute(
        text(
            "INSERT INTO prazos_processuais "
            "(case_id, org_id, tipo, data_intimacao, data_inicio, data_vencimento, "
            "dias_prazo, responsavel, status, descricao, uf, dobro) "
            "VALUES (:case_id, :org_id, :tipo, :di, :ds, :dv, :dp, :resp, "
            "'pendente', :desc, :uf, :dobro) RETURNING id"
        ),
        {
            "case_id": row.case_id, "org_id": org_id, "tipo": row.tipo,
            "di": row.data_intimacao, "ds": row.data_inicio,
            "dv": row.data_vencimento, "dp": row.dias_prazo,
            "resp": row.responsavel, "desc": row.descricao,
            "uf": row.uf, "dobro": row.dobro,
        },
    )
    new_id = result.scalar()
    db.commit()
    return JSONResponse({"success": True, "new_id": new_id})


@router.get("/export/excel")
async def export_excel(request: Request, db: Session = Depends(get_db)):
    """Exportar prazos para planilha Excel (.xlsx)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = _get_org_id(request)
    prazos = _get_prazos(db, org_id)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return JSONResponse(
            {"error": "openpyxl nao instalado. Execute: pip install openpyxl"},
            status_code=500,
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Prazos Processuais"

    # Estilos
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="0EA5E9", end_color="0EA5E9", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Status fills
    status_fills = {
        "pendente": PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"),
        "em_andamento": PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid"),
        "concluido": PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid"),
        "perdido": PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"),
    }

    # Cabecalho
    headers = [
        "Processo", "Cliente", "Parte Contraria", "Tipo", "Intimacao",
        "Inicio", "Vencimento", "Dias", "Responsavel", "Status", "UF", "Descricao",
    ]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Dados
    for row_idx, p in enumerate(prazos, 2):
        values = [
            p["processo"],
            p["cliente"],
            p["parte_contraria"],
            p["tipo"],
            p["data_intimacao"].strftime("%d/%m/%Y") if isinstance(p["data_intimacao"], date) else str(p["data_intimacao"]),
            p["data_inicio"].strftime("%d/%m/%Y") if isinstance(p["data_inicio"], date) else str(p["data_inicio"]),
            p["data_vencimento"].strftime("%d/%m/%Y") if isinstance(p["data_vencimento"], date) else str(p["data_vencimento"]),
            p["dias_prazo"],
            p["responsavel"],
            p["status"],
            p["uf"],
            p["descricao"],
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            if col == 10:  # Status column
                fill = status_fills.get(p["status"])
                if fill:
                    cell.fill = fill

    # Ajustar larguras
    col_widths = [20, 25, 25, 20, 12, 12, 12, 6, 20, 14, 4, 40]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[chr(64 + col) if col <= 26 else "A"].width = width

    # Salvar em buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    hoje_str = date.today().strftime("%Y-%m-%d")
    filename = f"prazos_processuais_{hoje_str}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/stats")
async def api_stats(request: Request, db: Session = Depends(get_db)):
    """JSON stats para os cards do dashboard."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)
    stats = _get_stats(db, org_id)
    return JSONResponse(stats)


# ---------------------------------------------------------------------------
# Indices (Analytics Charts)
# ---------------------------------------------------------------------------

# Month names in Portuguese
_MONTH_NAMES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# Statuses considered as "won" for victory index
_WON_STATUSES = {
    "won", "approved", "granted", "deferido", "procedente", "ganho", "vitoria",
}
# Statuses considered as resolved (won or lost)
_RESOLVED_STATUSES = _WON_STATUSES | {
    "lost", "denied", "improcedente", "indeferido", "perdido", "derrota",
    "closed", "completed", "archived", "encerrado", "finalizado",
}


@router.get("/indices", response_class=HTMLResponse)
async def indices_page(request: Request, db: Session = Depends(get_db)):
    """Render the Indices analytics page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_ctx = inject_org_context(request)
    return templates.TemplateResponse(
        "controladoria/indices.html",
        {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            **org_ctx,
        },
    )


@router.get("/api/indices")
async def get_indices(
    request: Request,
    setor: str = None,
    tipo: str = None,
    periodo: str = None,
    db: Session = Depends(get_db),
):
    """Return analytics data for the 6 charts on the Indices page."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = _get_org_id(request)

    # Build date filter
    date_cutoff = None
    if periodo == "3m":
        date_cutoff = datetime.utcnow() - timedelta(days=90)
    elif periodo == "6m":
        date_cutoff = datetime.utcnow() - timedelta(days=180)
    elif periodo == "1y":
        date_cutoff = datetime.utcnow() - timedelta(days=365)

    # Build dynamic SQL with filters
    conditions = ["org_id = :org_id"]
    params: dict = {"org_id": org_id}

    if setor:
        conditions.append("area_of_practice = :setor")
        params["setor"] = setor
    if tipo:
        conditions.append("tipo_acao = :tipo")
        params["tipo"] = tipo
    if date_cutoff:
        conditions.append("created_at >= :date_cutoff")
        params["date_cutoff"] = date_cutoff

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT id, status, area_of_practice, tipo_acao,
               created_at, updated_at,
               EXTRACT(MONTH FROM created_at)::int AS month,
               EXTRACT(YEAR FROM created_at)::int AS year
        FROM cases
        WHERE {where_clause}
        ORDER BY created_at
    """)

    try:
        rows = db.execute(query, params).fetchall()
    except Exception as e:
        logger.error("Erro ao consultar indices: %s", e)
        rows = []

    # ── Helpers ──
    from collections import defaultdict

    # ── 1. Tempo Medio por Setor (months between created_at and updated_at) ──
    setor_times: dict = defaultdict(list)
    for r in rows:
        if r.area_of_practice and r.updated_at and r.created_at:
            if (r.status or "").lower() in _RESOLVED_STATUSES:
                delta = (r.updated_at - r.created_at).days / 30.0
                if delta >= 0:
                    setor_times[r.area_of_practice].append(delta)

    tempo_medio_setor = {
        "labels": list(setor_times.keys()),
        "data": [round(sum(v) / len(v), 1) if v else 0 for v in setor_times.values()],
    }

    # ── 2. Tempo Medio por Tipo ──
    tipo_times: dict = defaultdict(list)
    for r in rows:
        if r.tipo_acao and r.updated_at and r.created_at:
            if (r.status or "").lower() in _RESOLVED_STATUSES:
                delta = (r.updated_at - r.created_at).days / 30.0
                if delta >= 0:
                    tipo_times[r.tipo_acao].append(delta)

    tempo_medio_tipo = {
        "labels": list(tipo_times.keys()),
        "data": [round(sum(v) / len(v), 1) if v else 0 for v in tipo_times.values()],
    }

    # ── 3. Indice de Vitoria por Setor (%) ──
    setor_won: dict = defaultdict(int)
    setor_resolved: dict = defaultdict(int)
    for r in rows:
        if r.area_of_practice:
            sl = (r.status or "").lower()
            if sl in _RESOLVED_STATUSES:
                setor_resolved[r.area_of_practice] += 1
                if sl in _WON_STATUSES:
                    setor_won[r.area_of_practice] += 1

    vs_labels = list(setor_resolved.keys())
    vitoria_setor = {
        "labels": vs_labels,
        "data": [
            round(setor_won[s] / setor_resolved[s] * 100) if setor_resolved[s] else 0
            for s in vs_labels
        ],
    }

    # ── 4. Indice de Vitoria por Tipo (%) ──
    tipo_won: dict = defaultdict(int)
    tipo_resolved: dict = defaultdict(int)
    for r in rows:
        if r.tipo_acao:
            sl = (r.status or "").lower()
            if sl in _RESOLVED_STATUSES:
                tipo_resolved[r.tipo_acao] += 1
                if sl in _WON_STATUSES:
                    tipo_won[r.tipo_acao] += 1

    vt_labels = list(tipo_resolved.keys())
    vitoria_tipo = {
        "labels": vt_labels,
        "data": [
            round(tipo_won[t] / tipo_resolved[t] * 100) if tipo_resolved[t] else 0
            for t in vt_labels
        ],
    }

    # ── 5. Processos por Mes ──
    month_counts: dict = defaultdict(int)
    for r in rows:
        if r.year and r.month:
            month_counts[(int(r.year), int(r.month))] += 1

    sorted_months = sorted(month_counts.keys())
    processos_mes = {
        "labels": [
            f"{_MONTH_NAMES_PT.get(m, m)}/{str(y)[2:]}" for y, m in sorted_months
        ],
        "data": [month_counts[k] for k in sorted_months],
    }

    # ── 6. Distribuicao por Setor ao Longo do Tempo (%) ──
    all_setores: set = set()
    month_setor_counts: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r.area_of_practice and r.year and r.month:
            key = (int(r.year), int(r.month))
            month_setor_counts[key][r.area_of_practice] += 1
            all_setores.add(r.area_of_practice)

    all_setores_sorted = sorted(all_setores)
    dist_months = sorted(month_setor_counts.keys())
    dist_labels = [
        f"{_MONTH_NAMES_PT.get(m, m)}/{str(y)[2:]}" for y, m in dist_months
    ]

    dist_datasets = []
    for sname in all_setores_sorted:
        pct_data = []
        for mk in dist_months:
            total_in_month = sum(month_setor_counts[mk].values())
            if total_in_month > 0:
                pct_data.append(
                    round(month_setor_counts[mk][sname] / total_in_month * 100, 1)
                )
            else:
                pct_data.append(0)
        dist_datasets.append({"label": sname, "data": pct_data})

    distribuicao_setor = {
        "labels": dist_labels,
        "datasets": dist_datasets,
    }

    return JSONResponse({
        "tempo_medio_setor": tempo_medio_setor,
        "tempo_medio_tipo": tempo_medio_tipo,
        "vitoria_setor": vitoria_setor,
        "vitoria_tipo": vitoria_tipo,
        "processos_mes": processos_mes,
        "distribuicao_setor": distribuicao_setor,
    })
