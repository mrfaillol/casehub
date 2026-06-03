"""
Test client CRUD and PII encryption for CaseHub.
Tests creation, PII field encryption/decryption, and search.
"""
import pytest
from unittest.mock import patch
import bcrypt
from sqlalchemy import text

from conftest import TestSession, TEST_ENGINE
from models.base import Base
from models.client import Client
from models.user import User
from routes.clients import _load_financial_summary


# --- Helpers ---

def _make_client(db, ssn="123-45-6789", alien="A123456789", passport="P9876543"):
    """Create a client with PII fields."""
    client = Client(
        first_name="Jane",
        last_name="Doe",
        email="jane@test.com",
        phone="+1-555-0100",
        ssn=ssn,
        alien_number=alien,
        passport_number=passport,
        client_number="CH-0001",
        status="active",
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# --- Tests ---

class TestClientCreation:
    """Test basic client CRUD."""

    def test_create_client(self, db):
        client = _make_client(db)
        assert client.id is not None
        assert client.first_name == "Jane"
        assert client.last_name == "Doe"
        assert client.status == "active"

    def test_client_full_name(self, db):
        client = Client(first_name="John", middle_name="M", last_name="Smith")
        assert client.full_name == "John M Smith"

    def test_client_full_name_no_middle(self, db):
        client = Client(first_name="John", last_name="Smith")
        assert client.full_name == "John Smith"

    def test_search_by_client_number(self, db):
        _make_client(db)
        found = db.query(Client).filter(Client.client_number == "CH-0001").first()
        assert found is not None
        assert found.email == "jane@test.com"

    def test_search_by_email(self, db):
        _make_client(db)
        found = db.query(Client).filter(Client.email == "jane@test.com").first()
        assert found is not None
        assert found.first_name == "Jane"

    def test_financial_summary_supports_legacy_invoice_schema(self, db):
        client = _make_client(db)
        db.execute(text("DROP TABLE IF EXISTS invoice_items"))
        db.execute(text("DROP TABLE IF EXISTS invoices"))
        db.execute(text("""
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                due_date DATE,
                total_amount NUMERIC DEFAULT 0,
                payment_status VARCHAR(50)
            )
        """))
        db.execute(text("""
            INSERT INTO invoices (client_id, due_date, total_amount, payment_status)
            VALUES (:client_id, CURRENT_DATE, 1000, 'pending')
        """), {"client_id": client.id})
        db.commit()

        summary = _load_financial_summary(db, client.id)

        assert summary["total_honorarios"] == 1000
        assert summary["total_pago"] == 0
        assert summary["saldo_devedor"] == 1000


class TestClientPIIEncryption:
    """Test that PII fields are encrypted before DB storage and decrypted on read."""

    def test_encrypt_pii_changes_ssn(self, db):
        """After encrypt_pii(), SSN should not be plaintext."""
        client = _make_client(db)
        original_ssn = client.ssn
        client.encrypt_pii()
        assert client.ssn != original_ssn
        assert client.ssn != "123-45-6789"

    def test_encrypt_decrypt_roundtrip(self, db):
        """encrypt then decrypt should return original value."""
        client = _make_client(db)
        client.encrypt_pii()
        db.commit()
        db.refresh(client)

        # SSN is now encrypted in DB
        encrypted_ssn = client.ssn
        assert encrypted_ssn != "123-45-6789"

        # Decrypt should restore original
        client.decrypt_pii()
        assert client.ssn == "123-45-6789"

    def test_encrypt_pii_all_three_fields(self, db):
        """All three PII fields should be encrypted."""
        client = _make_client(db)
        client.encrypt_pii()
        assert client.ssn != "123-45-6789"
        assert client.alien_number != "A123456789"
        assert client.passport_number != "P9876543"

    def test_encrypt_pii_empty_fields_unchanged(self, db):
        """Empty/None PII fields should remain empty/None."""
        client = Client(
            first_name="Empty",
            last_name="User",
            ssn=None,
            alien_number="",
            passport_number=None,
        )
        db.add(client)
        db.commit()
        client.encrypt_pii()
        assert client.ssn is None
        assert client.alien_number == ""
        assert client.passport_number is None

    def test_pii_not_plaintext_in_db(self, db):
        """After encryption + commit, querying raw DB should not show plaintext."""
        client = _make_client(db)
        client.encrypt_pii()
        db.commit()

        # Fetch fresh from DB (bypass Python caching)
        raw = db.query(Client).filter(Client.id == client.id).first()
        assert raw.ssn != "123-45-6789"
        assert "123-45-6789" not in (raw.ssn or "")
