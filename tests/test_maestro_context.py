from types import SimpleNamespace

from services.maestro_context import (
    MaestroContextBlock,
    MaestroContextBundle,
    build_maestro_context,
    build_mcp_context_block,
)
from services.mcp_client import MCPInvocationResult, MCPServerConfig


class FakeDb:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("no db in unit test")

    def rollback(self):
        pass


class FakeMaestro:
    def get_firm_context(self, db, org_id):
        assert org_id == 41
        return "O escritório tem 3 clientes cadastrados."


def test_build_maestro_context_degrades_without_mcp(monkeypatch):
    monkeypatch.setenv("CASEHUB_MCP_CLIENT_ENABLED", "")
    bundle = build_maestro_context(
        FakeDb(),
        41,
        SimpleNamespace(id=7, user_type="admin"),
        "Resumo do escritório",
        maestro=FakeMaestro(),
    )

    assert "3 clientes" in bundle.prompt_context
    assert all(block.kind != "mcp" for block in bundle.blocks)


def test_build_maestro_context_uses_casehub_owned_mcp_facade_when_enabled(monkeypatch):
    monkeypatch.setenv("CASEHUB_MCP_CLIENT_ENABLED", "true")
    bundle = build_maestro_context(
        FakeDb(),
        41,
        SimpleNamespace(id=7, user_type="regular"),
        "Status do tenant",
        maestro=FakeMaestro(),
        mcp_config=MCPServerConfig(
            name="casehub-self",
            url="https://integrations.example.invalid/mcp",
            enabled=True,
            allowed_tools=("get_system_status",),
            admin_only=False,
            approval_required=False,
        ),
    )

    assert any(block.kind == "mcp" for block in bundle.blocks)
    assert "casehub-owned-facade" in bundle.prompt_context


def test_mcp_context_block_passes_current_tenant_scope():
    class FakeMCPClient:
        def invoke(self, config, request):
            assert request.org_id == 41
            assert request.user_id == 7
            assert request.capability_name == "get_system_status"
            return MCPInvocationResult(
                ok=True,
                content='{"status": "online"}',
                audit_id="audit-123",
            )

    block = build_mcp_context_block(
        org_id=41,
        user=SimpleNamespace(id=7, user_type="regular"),
        mcp_client=FakeMCPClient(),
        mcp_config=MCPServerConfig(
            name="casehub-self",
            url="https://casehub.legal/mcp",
            enabled=True,
            allowed_tools=("get_system_status",),
            admin_only=False,
            approval_required=False,
        ),
    )

    assert block is not None
    assert block.kind == "mcp"
    assert "online" in block.content
    assert block.citations == ("mcp:audit-123",)


def test_context_audit_keeps_hash_and_redacted_preview_not_full_prompt():
    long_secret = "CPF 123.456.789-10 " + ("conteudo " * 80)
    bundle = MaestroContextBundle(
        blocks=(
            MaestroContextBlock(
                kind="firm_data",
                title="Dados do escritório",
                content=long_secret,
            ),
        )
    )

    audit = bundle.audit_context
    rendered = str(audit)

    assert "content_sha256" in audit["blocks"][0]
    assert "123.456.789-10" not in rendered
    assert len(audit["blocks"][0]["redacted_preview"]) < len(long_secret)
