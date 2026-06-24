"""
Test CaseHub core models: Client, Case, Organization.
Covers creation, computed properties, PII encryption, and Brazilian-law fields.
"""
import pytest
from unittest.mock import patch

from conftest import TestSession, TEST_ENGINE
from models.client import Client
from models.case import Case
from models.tenant import Organization


# --- Helpers ---

def _make_client(db, **overrides):
    """Create a Client with sensible defaults, overridable by kwargs."""
    defaults = dict(
        first_name="PessoaDemo",
        last_name="Silva",
        email="pessoa_demo@test.com",
        phone="+55-32-99999-0000",
        client_number="CH-0001",
        status="active",
    )
    defaults.update(overrides)
    client = Client(**defaults)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _make_case(db, client_id, **overrides):
    """Create a Case with sensible defaults."""
    defaults = dict(
        client_id=client_id,
        case_number="CASE-001",
        case_name="Test Case",
        status="intake",
        priority="medium",
    )
    defaults.update(overrides)
    case = Case(**defaults)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


# ===================================================================
# Client Model Tests
# ===================================================================

class TestClientCreate:
    """Test basic Client creation and persistence."""

    def test_create_client(self, db):
        client = _make_client(db)
        assert client.id is not None
        assert client.first_name == "PessoaDemo"
        assert client.last_name == "Silva"

    def test_client_has_created_at(self, db):
        client = _make_client(db)
        assert client.created_at is not None

    def test_client_default_status(self, db):
        client = Client(first_name="A", last_name="B")
        db.add(client)
        db.commit()
        db.refresh(client)
        assert client.status == "active"

    def test_client_default_client_type(self, db):
        client = Client(first_name="A", last_name="B")
        db.add(client)
        db.commit()
        db.refresh(client)
        assert client.client_type == "individual"


class TestClientFullName:
    """Test full_name computed property."""

    def test_full_name_first_last(self, db):
        client = Client(first_name="John", last_name="Smith")
        assert client.full_name == "John Smith"

    def test_full_name_with_middle(self, db):
        client = Client(first_name="John", middle_name="Michael", last_name="Smith")
        assert client.full_name == "John Michael Smith"

    def test_full_name_no_middle(self, db):
        client = Client(first_name="Ana", middle_name=None, last_name="Costa")
        assert client.full_name == "Ana Costa"

    def test_full_name_empty_middle(self, db):
        client = Client(first_name="Ana", middle_name="", last_name="Costa")
        # Empty string is falsy, so should be skipped
        assert client.full_name == "Ana Costa"


class TestClientPIIEncryption:
    """Test encrypt_pii / decrypt_pii on immigration PII fields."""

    def test_encrypt_pii_changes_ssn(self, db):
        client = _make_client(db, ssn="123-45-6789")
        client.encrypt_pii()
        assert client.ssn != "123-45-6789"

    def test_encrypt_decrypt_roundtrip_ssn(self, db):
        client = _make_client(db, ssn="999-88-7777")
        client.encrypt_pii()
        db.commit()
        db.refresh(client)
        client.decrypt_pii()
        assert client.ssn == "999-88-7777"

    def test_encrypt_decrypt_roundtrip_alien_number(self, db):
        client = _make_client(db, alien_number="A111222333")
        client.encrypt_pii()
        db.commit()
        db.refresh(client)
        client.decrypt_pii()
        assert client.alien_number == "A111222333"

    def test_encrypt_decrypt_roundtrip_passport(self, db):
        client = _make_client(db, passport_number="X9876543")
        client.encrypt_pii()
        db.commit()
        db.refresh(client)
        client.decrypt_pii()
        assert client.passport_number == "X9876543"

    def test_encrypt_none_fields_unchanged(self, db):
        client = _make_client(db, ssn=None, alien_number=None, passport_number=None)
        client.encrypt_pii()
        assert client.ssn is None
        assert client.alien_number is None
        assert client.passport_number is None


class TestClientBrazilianFields:
    """Test Brazilian-law PII fields (cpf, rg, cnpj)."""

    def test_client_has_cpf_field(self, db):
        client = _make_client(db, cpf="123.456.789-00")
        assert client.cpf == "123.456.789-00"

    def test_client_has_rg_field(self, db):
        client = _make_client(db, rg="MG-12.345.678")
        assert client.rg == "MG-12.345.678"

    def test_client_has_cnpj_field(self, db):
        client = _make_client(db, cnpj="12.345.678/0001-99")
        assert client.cnpj == "12.345.678/0001-99"

    def test_encrypt_decrypt_cpf(self, db):
        client = _make_client(db, cpf="111.222.333-44")
        client.encrypt_pii()
        assert client.cpf != "111.222.333-44"
        client.decrypt_pii()
        assert client.cpf == "111.222.333-44"

    def test_encrypt_decrypt_rg(self, db):
        client = _make_client(db, rg="MG-99.888.777")
        client.encrypt_pii()
        assert client.rg != "MG-99.888.777"
        client.decrypt_pii()
        assert client.rg == "MG-99.888.777"

    def test_encrypt_decrypt_cnpj(self, db):
        client = _make_client(db, cnpj="99.888.777/0001-66")
        client.encrypt_pii()
        assert client.cnpj != "99.888.777/0001-66"
        client.decrypt_pii()
        assert client.cnpj == "99.888.777/0001-66"

    def test_encrypt_none_brazilian_fields(self, db):
        client = _make_client(db, cpf=None, rg=None, cnpj=None)
        client.encrypt_pii()
        assert client.cpf is None
        assert client.rg is None
        assert client.cnpj is None

    def test_client_oab_number(self, db):
        client = _make_client(db, oab_number="OAB/MG 123456")
        assert client.oab_number == "OAB/MG 123456"

    def test_client_nationality(self, db):
        client = _make_client(db, nationality="Brasileiro")
        assert client.nationality == "Brasileiro"


# ===================================================================
# Case Model Tests
# ===================================================================

class TestCaseCreate:
    """Test basic Case creation."""

    def test_create_case(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id)
        assert case.id is not None
        assert case.client_id == client.id
        assert case.status == "intake"

    def test_case_default_priority(self, db):
        client = _make_client(db)
        case = Case(client_id=client.id, case_number="CASE-DEF")
        db.add(case)
        db.commit()
        db.refresh(case)
        assert case.priority == "medium"

    def test_case_has_created_at(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id)
        assert case.created_at is not None


class TestCaseBrazilianFields:
    """Test Brazilian-law fields on the Case model."""

    def test_numero_processo(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id, numero_processo="0001234-56.2025.8.13.0145")
        assert case.numero_processo == "0001234-56.2025.8.13.0145"

    def test_tipo_acao(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id, tipo_acao="Acao Civil Publica")
        assert case.tipo_acao == "Acao Civil Publica"

    def test_vara(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id, vara="2a Vara Civel")
        assert case.vara == "2a Vara Civel"

    def test_comarca(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id, comarca="Juiz de Fora")
        assert case.comarca == "Juiz de Fora"

    def test_tribunal(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id, tribunal="TJMG")
        assert case.tribunal == "TJMG"

    def test_fase_processual(self, db):
        client = _make_client(db)
        case = _make_case(db, client.id, fase_processual="Instrucao")
        assert case.fase_processual == "Instrucao"

    def test_polo_ativo_passivo(self, db):
        client = _make_client(db)
        case = _make_case(
            db, client.id,
            polo_ativo="Joao da Silva",
            polo_passivo="Empresa XYZ Ltda",
        )
        assert case.polo_ativo == "Joao da Silva"
        assert case.polo_passivo == "Empresa XYZ Ltda"

    def test_all_brazilian_fields_together(self, db):
        """Verify all Brazilian fields can be set simultaneously."""
        client = _make_client(db)
        case = _make_case(
            db, client.id,
            numero_processo="0009999-88.2026.8.13.0145",
            tipo_acao="Mandado de Seguranca",
            vara="1a Vara da Fazenda Publica",
            comarca="Belo Horizonte",
            tribunal="TJMG",
            fase_processual="Recurso",
            polo_ativo="Estado de Minas Gerais",
            polo_passivo="Contribuinte ABC",
        )
        assert case.numero_processo == "0009999-88.2026.8.13.0145"
        assert case.tipo_acao == "Mandado de Seguranca"
        assert case.tribunal == "TJMG"


# ===================================================================
# Organization Model Tests
# ===================================================================

class TestOrganizationModel:
    """Test the Organization model."""

    def test_create_organization(self, db):
        org = Organization(
            uuid="test-uuid-1234",
            name="Test Firm",
            slug="test-firm",
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.id is not None
        assert org.name == "Test Firm"

    def test_has_feature_returns_true(self, db):
        """has_feature should return True when feature is in the dict."""
        org = Organization(
            uuid="feat-uuid-001",
            name="Featured Firm",
            slug="featured-firm",
            features={"sso": True, "ai_lor": True},
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.has_feature("sso") is True
        assert org.has_feature("ai_lor") is True

    def test_has_feature_returns_false(self, db):
        """has_feature should return False when feature is absent or False."""
        org = Organization(
            uuid="nofeat-uuid-001",
            name="Basic Firm",
            slug="basic-firm",
            features={"sso": False},
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.has_feature("sso") is False
        assert org.has_feature("nonexistent") is False

    def test_has_feature_empty_features(self, db):
        """has_feature should return False when features is empty/None."""
        org = Organization(
            uuid="empty-uuid-001",
            name="Empty Firm",
            slug="empty-firm",
            features={},
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.has_feature("anything") is False

    def test_has_feature_none_features(self, db):
        """has_feature should return False when features is None."""
        org = Organization(
            uuid="none-uuid-001",
            name="None Firm",
            slug="none-firm",
            features=None,
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.has_feature("anything") is False

    def test_default_plan(self, db):
        org = Organization(
            uuid="plan-uuid-001",
            name="Default Plan Firm",
            slug="default-plan",
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.plan == "office"

    def test_from_email_property(self, db):
        org = Organization(
            uuid="email-uuid-001",
            name="Email Firm",
            slug="email-firm",
            smtp_from_name="CaseHub Notify",
            smtp_user="notify@casehub.io",
        )
        db.add(org)
        db.commit()
        assert org.from_email == "CaseHub Notify <notify@casehub.io>"

    def test_from_email_fallback(self, db):
        org = Organization(
            uuid="fallback-uuid-001",
            name="Fallback Firm",
            slug="fallback-firm",
            email="info@example.com",
        )
        db.add(org)
        db.commit()
        assert "Fallback Firm" in org.from_email
        assert "info@example.com" in org.from_email

    def test_repr(self, db):
        org = Organization(
            uuid="repr-uuid-001",
            name="Repr Firm",
            slug="repr-firm",
        )
        result = repr(org)
        assert "repr-firm" in result
        assert "Repr Firm" in result
