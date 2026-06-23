from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from services.maestro_lite import get_client_context
from services.mcp_client import (
    MCPClient,
    MCPInvocationRequest,
    MCPInvocationResult,
    MCPServerConfig,
    redact_payload,
)

logger = logging.getLogger(__name__)

MAX_ENTRY_BYTES_FOR_CHAT_CTX = 4 * 1024
MAX_ENTRIES_FOR_CHAT_CTX = 20
SOURCES_CHAR_BUDGET = 8000
CASEHUB_MCP_SERVER_NAME = "casehub-self"
CASEHUB_MCP_ALLOWED_TOOLS = (
    "search_cases",
    "get_case",
    "list_clients",
    "validate_documento",
    "get_system_status",
    "list_templates",
)


try:
    from models import MaestroLearningEntry as _MaestroLearningEntry  # noqa: WPS433
except ImportError:
    _MaestroLearningEntry = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MaestroContextBlock:
    kind: str
    title: str
    content: str
    citations: tuple[str, ...] = field(default_factory=tuple)
    sensitivity: str = "tenant"


@dataclass(frozen=True)
class MaestroContextBundle:
    blocks: tuple[MaestroContextBlock, ...] = field(default_factory=tuple)
    repo_context: str | None = None

    @property
    def prompt_context(self) -> str:
        return "\n\n".join(
            block.content.strip() for block in self.blocks if (block.content or "").strip()
        )

    @property
    def audit_context(self) -> dict[str, Any]:
        return {
            "blocks": [
                {
                    "kind": block.kind,
                    "title": block.title,
                    "sensitivity": block.sensitivity,
                    "chars": len(block.content or ""),
                    "content_sha256": _sha256_text(block.content),
                    "redacted_preview": _redacted_preview(block.content),
                    "citations": list(block.citations),
                }
                for block in self.blocks
            ],
            "repo_context": {
                "present": bool(self.repo_context),
                "chars": len(self.repo_context or ""),
                "content_sha256": _sha256_text(self.repo_context or ""),
                "redacted_preview": _redacted_preview(self.repo_context or ""),
            },
        }


def maestro_learning_enabled() -> bool:
    raw = os.getenv("CASEHUB_MAESTRO_LEARNING_ENABLED")
    if raw is None:
        try:
            from config import settings as _settings
            raw = getattr(_settings, "CASEHUB_MAESTRO_LEARNING_ENABLED", "")
        except Exception:  # noqa: BLE001 - chat must survive config failures
            raw = ""
    return str(raw or "").lower() in {"1", "true", "yes", "on"}


def mcp_client_enabled() -> bool:
    raw = os.getenv("CASEHUB_MCP_CLIENT_ENABLED")
    if raw is None:
        try:
            from config import settings as _settings
            raw = getattr(_settings, "CASEHUB_MCP_CLIENT_ENABLED", "")
        except Exception:  # noqa: BLE001 - chat must survive config failures
            raw = ""
    return str(raw or "").lower() in {"1", "true", "yes", "on"}


def get_user_learning_context(db, org_id, user, *, model_class=None) -> str:
    """Assemble the user's enabled Maestro learning corpus for chat context."""
    if not maestro_learning_enabled():
        return ""
    entry_model = model_class or _MaestroLearningEntry
    if entry_model is None:
        return ""
    user_id = getattr(user, "id", None)
    if not user_id:
        return ""

    try:
        entries = (
            db.query(entry_model)
            .filter(
                entry_model.user_id == user_id,
                entry_model.org_id == org_id,
                entry_model.enabled.is_(True),
            )
            .order_by(entry_model.updated_at.desc())
            .limit(MAX_ENTRIES_FOR_CHAT_CTX)
            .all()
        )
    except Exception as exc:  # noqa: BLE001 - degrade silently
        logger.warning(
            "[MAESTRO LEARN CTX] failed to load entries for user_id=%s: %s",
            user_id,
            type(exc).__name__,
        )
        _safe_rollback(db)
        return ""

    if not entries:
        return ""

    formatted_blocks = []
    for entry in entries:
        title = (entry.title or "Sem título").strip()
        content = (entry.content or "")[:MAX_ENTRY_BYTES_FOR_CHAT_CTX]
        tags = ", ".join(entry.tags or []) if entry.tags else ""
        header = f"### {title}"
        if tags:
            header += f"  _(tags: {tags})_"
        formatted_blocks.append(f"{header}\n{content}")

    body = "\n\n".join(formatted_blocks)
    return (
        "\n\nAnotações do usuário (Maestro learning — fonte autoral, "
        "use como preferência mas valide contra o contexto do "
        "escritório quando houver conflito):\n" + body
    )


def get_custom_context(db, org_id) -> str:
    try:
        result = db.execute(
            text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_context'"),
            {"oid": org_id},
        )
        row = result.fetchone()
        if row:
            return row[0] or ""
    except Exception:
        return ""
    return ""


def build_sources_context(db, org_id) -> str:
    try:
        result = db.execute(
            text(
                "SELECT content FROM ai_knowledge_sources "
                "WHERE org_id = :oid AND content IS NOT NULL "
                "ORDER BY id DESC LIMIT 5"
            ),
            {"oid": org_id},
        )
        source_texts = [row[0] for row in result if row[0]]
    except Exception as exc:  # noqa: BLE001 - non-fatal source failure
        logger.warning("Error loading knowledge sources: %s", type(exc).__name__)
        return ""

    if not source_texts:
        return ""

    truncated = []
    remaining = SOURCES_CHAR_BUDGET
    for source_text in source_texts:
        if remaining <= 0:
            break
        chunk = source_text[: min(2000, remaining)]
        truncated.append(chunk)
        remaining -= len(chunk)
    return "\n\nFontes de conhecimento:\n" + "\n---\n".join(truncated)


def build_repo_context(message: str) -> str | None:
    try:
        from services.maestro_lite import repo_aware_enabled
        if repo_aware_enabled():
            from services.maestro_repo_index import retrieve_repo_context
            return retrieve_repo_context(message)
    except Exception as exc:  # noqa: BLE001 - grounding is best-effort
        logger.warning("repo-aware retrieval failed (non-fatal): %s", type(exc).__name__)
    return None


def default_casehub_mcp_config() -> MCPServerConfig:
    return MCPServerConfig(
        name=CASEHUB_MCP_SERVER_NAME,
        url="https://casehub.legal/mcp",
        enabled=True,
        allowed_tools=CASEHUB_MCP_ALLOWED_TOOLS,
        approval_required=False,
        admin_only=False,
    )


def build_mcp_context_block(
    *,
    db=None,
    org_id,
    user,
    mcp_client: MCPClient | None = None,
    mcp_config: MCPServerConfig | None = None,
) -> MaestroContextBlock | None:
    if not mcp_client_enabled() and mcp_client is None and mcp_config is None:
        return None

    config = mcp_config or default_casehub_mcp_config()
    client = mcp_client or MCPClient(adapter=_CaseHubSelfStatusAdapter(db))
    user_id = getattr(user, "id", None) or 0
    requester_is_admin = getattr(user, "user_type", None) == "admin"
    request = MCPInvocationRequest(
        org_id=org_id,
        user_id=user_id,
        server_name=config.name,
        capability_kind="tool",
        capability_name="get_system_status",
        arguments={},
        requester_is_admin=requester_is_admin,
    )

    result: MCPInvocationResult
    try:
        result = client.invoke(config, request)
    except Exception as exc:  # noqa: BLE001 - tool unavailability cannot break chat
        logger.warning("MCP context invocation crashed (non-fatal): %s", type(exc).__name__)
        return None

    if not result.ok or not result.content:
        return None

    return MaestroContextBlock(
        kind="mcp",
        title="MCP CaseHub",
        content="\n\nContexto MCP CaseHub (tenant-scoped, read-only):\n" + str(result.content),
        citations=(f"mcp:{result.audit_id}",) if result.audit_id else tuple(),
        sensitivity="tenant-redacted",
    )


def build_maestro_context(
    db,
    org_id,
    user,
    message: str,
    *,
    maestro=None,
    personality_context: str = "",
    mcp_client: MCPClient | None = None,
    mcp_config: MCPServerConfig | None = None,
) -> MaestroContextBundle:
    blocks: list[MaestroContextBlock] = []

    firm_context = ""
    if maestro is not None:
        try:
            firm_context = maestro.get_firm_context(db, org_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("firm context failed (non-fatal): %s", type(exc).__name__)
    _append_block(blocks, "firm_data", "Dados do escritório", firm_context)

    custom_context = get_custom_context(db, org_id)
    _append_block(
        blocks,
        "custom_context",
        "Informações adicionais do escritório",
        f"\n\nInformações adicionais do escritório:\n{custom_context}" if custom_context else "",
    )
    _append_block(blocks, "style", "Preferências de estilo", personality_context, "tenant-style")
    _append_block(blocks, "sources", "Fontes", build_sources_context(db, org_id))
    _append_block(
        blocks,
        "learning",
        "Learning do usuário",
        get_user_learning_context(db, org_id, user),
        "user-authored",
    )

    # Work-intelligence context shipped in #772. It lives under the SAME symbol
    # name (build_maestro_context) in services.work_intelligence, so import it
    # aliased to avoid colliding with THIS function. Re-introduced here so the
    # MCP-context refactor does not silently drop the work-intelligence block.
    try:
        from services.work_intelligence import (
            build_maestro_context as build_work_intelligence_context,
        )
        work_intelligence_context = build_work_intelligence_context(db, org_id=org_id, user=user)
    except Exception as exc:  # noqa: BLE001 - work-intelligence is best-effort
        logger.warning("work-intelligence context failed (non-fatal): %s", type(exc).__name__)
        work_intelligence_context = ""
    _append_block(
        blocks,
        "work_intelligence",
        "Inteligência de trabalho",
        work_intelligence_context,
    )

    try:
        client_context = get_client_context(db, org_id, message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("client focus context failed (non-fatal): %s", type(exc).__name__)
        client_context = ""
    _append_block(blocks, "client_focus", "Cliente em foco", client_context)

    mcp_block = build_mcp_context_block(
        db=db,
        org_id=org_id,
        user=user,
        mcp_client=mcp_client,
        mcp_config=mcp_config,
    )
    if mcp_block is not None:
        blocks.append(mcp_block)

    return MaestroContextBundle(
        blocks=tuple(blocks),
        repo_context=build_repo_context(message),
    )


def _append_block(
    blocks: list[MaestroContextBlock],
    kind: str,
    title: str,
    content: str | None,
    sensitivity: str = "tenant",
) -> None:
    if content and content.strip():
        blocks.append(
            MaestroContextBlock(
                kind=kind,
                title=title,
                content=content,
                sensitivity=sensitivity,
            )
        )


class _CaseHubSelfStatusAdapter:
    """CaseHub-owned read-only facade for the default Maestro MCP probe."""

    def __init__(self, db) -> None:
        self.db = db

    def call(self, request: MCPInvocationRequest) -> dict[str, Any]:
        if request.capability_name != "get_system_status":
            raise ValueError("unsupported_casehub_self_tool")

        payload: dict[str, Any] = {
            "status": "available",
            "mode": "casehub-owned-facade",
            "org_id": request.org_id,
            "allowed_tools": CASEHUB_MCP_ALLOWED_TOOLS,
        }
        if self.db is None:
            return payload

        try:
            payload["client_count"] = self.db.execute(
                text("SELECT COUNT(*) FROM clients WHERE org_id = :oid"),
                {"oid": request.org_id},
            ).scalar() or 0
            payload["case_count"] = self.db.execute(
                text("SELECT COUNT(*) FROM cases WHERE org_id = :oid"),
                {"oid": request.org_id},
            ).scalar() or 0
        except Exception as exc:  # noqa: BLE001 - status enrichment is optional
            logger.debug("MCP self status counts skipped: %s", type(exc).__name__)
            _safe_rollback(self.db)
        return payload


def _safe_rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _sha256_text(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()


def _redacted_preview(value: str | None, *, max_chars: int = 240) -> str:
    redacted = redact_payload(value or "")
    rendered = redacted if isinstance(redacted, str) else json.dumps(redacted, ensure_ascii=False)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 14] + "...[truncated]"
