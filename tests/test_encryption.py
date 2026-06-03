"""
Test encryption service for CaseHub.
Tests encrypt/decrypt roundtrip, plaintext fallback, and missing key behavior.
"""
import os
import pytest
from unittest.mock import patch


# --- Tests ---

class TestEncryptDecrypt:
    """Test core encrypt/decrypt functions."""

    def test_encrypt_returns_different_string(self):
        from services.encryption import encrypt_value
        encrypted = encrypt_value("hello world")
        assert encrypted != "hello world"
        assert len(encrypted) > 0

    def test_decrypt_reverses_encrypt(self):
        from services.encryption import encrypt_value, decrypt_value
        original = "SSN-123-45-6789"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)
        assert decrypted == original

    def test_encrypt_empty_returns_empty(self):
        from services.encryption import encrypt_value
        assert encrypt_value("") == ""
        assert encrypt_value(None) is None

    def test_decrypt_empty_returns_empty(self):
        from services.encryption import decrypt_value
        assert decrypt_value("") == ""
        assert decrypt_value(None) is None

    def test_encrypt_different_values_different_output(self):
        from services.encryption import encrypt_value
        e1 = encrypt_value("value1")
        e2 = encrypt_value("value2")
        assert e1 != e2

    def test_encrypt_same_value_different_tokens(self):
        """Fernet produces different ciphertext each time (IV-based)."""
        from services.encryption import encrypt_value
        e1 = encrypt_value("same")
        e2 = encrypt_value("same")
        # They decrypt to same value but encrypted form differs
        assert e1 != e2

    def test_decrypt_plaintext_returns_plaintext(self):
        """For migration compatibility: decrypting unencrypted data returns it as-is."""
        from services.encryption import decrypt_value
        result = decrypt_value("plain-text-ssn")
        assert result == "plain-text-ssn"

    def test_decrypt_unicode_plaintext(self):
        from services.encryption import decrypt_value
        result = decrypt_value("Jose da Silva")
        assert result == "Jose da Silva"


class TestEncryptionKeyValidation:
    """Test behavior when ENCRYPTION_KEY is missing or invalid."""

    def test_missing_key_raises_error(self):
        """If ENCRYPTION_KEY is not set, get_fernet should raise ValueError."""
        import services.encryption as enc
        # Reset the cached instance
        original_instance = enc._fernet_instance
        original_key = enc.ENCRYPTION_KEY
        try:
            enc._fernet_instance = None
            enc.ENCRYPTION_KEY = None
            with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
                enc.get_fernet()
        finally:
            enc._fernet_instance = original_instance
            enc.ENCRYPTION_KEY = original_key

    def test_invalid_key_raises_error(self):
        """A short/invalid key should raise ValueError."""
        import services.encryption as enc
        original_instance = enc._fernet_instance
        original_key = enc.ENCRYPTION_KEY
        try:
            enc._fernet_instance = None
            enc.ENCRYPTION_KEY = "too-short"
            with pytest.raises(ValueError, match="44-character"):
                enc.get_fernet()
        finally:
            enc._fernet_instance = original_instance
            enc.ENCRYPTION_KEY = original_key


class TestClientPIIEncryption:
    """Test encrypt_client_pii via the Client model."""

    def test_encrypt_client_pii_all_fields(self):
        from models.client import Client
        from services.encryption import decrypt_value

        client = Client(
            first_name="Test",
            last_name="User",
            ssn="111-22-3333",
            alien_number="A987654321",
            passport_number="X12345678",
        )
        client.encrypt_pii()

        # All three should be encrypted (not plaintext)
        assert client.ssn != "111-22-3333"
        assert client.alien_number != "A987654321"
        assert client.passport_number != "X12345678"

        # All three should decrypt back
        assert decrypt_value(client.ssn) == "111-22-3333"
        assert decrypt_value(client.alien_number) == "A987654321"
        assert decrypt_value(client.passport_number) == "X12345678"
