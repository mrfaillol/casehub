"""
CaseHub - PII Encryption Service
Encrypts/decrypts sensitive fields (SSN, alien_number, passport_number) using Fernet symmetric encryption.
"""
from cryptography.fernet import Fernet, InvalidToken
import os
import logging

logger = logging.getLogger(__name__)

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

_fernet_instance = None


def get_fernet():
    """Get or create a Fernet instance from the ENCRYPTION_KEY env var."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    if not ENCRYPTION_KEY:
        raise ValueError(
            "ENCRYPTION_KEY environment variable is required. "
            "Generate with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    key = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY

    # Validate it's a proper Fernet key (44 bytes base64-encoded)
    if len(key) != 44:
        raise ValueError(
            f"ENCRYPTION_KEY must be a 44-character base64-encoded Fernet key, got {len(key)} chars. "
            "Generate with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_value(value: str) -> str:
    """Encrypt a plaintext string. Returns the encrypted token as a string.
    Returns None/empty as-is."""
    if not value:
        return value
    f = get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """Decrypt an encrypted string. Returns plaintext.
    If the value is not encrypted (e.g., pre-migration plaintext), returns it as-is
    for backwards compatibility."""
    if not value:
        return value
    try:
        f = get_fernet()
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        # Value is not encrypted (plaintext from before migration) -- return as-is
        return value


# PII field names that should be encrypted
PII_FIELDS = ("ssn", "alien_number", "passport_number")


def encrypt_client_pii(data: dict) -> dict:
    """Encrypt PII fields in a dict before saving to DB.
    Modifies and returns the same dict."""
    for field in PII_FIELDS:
        if field in data and data[field]:
            data[field] = encrypt_value(data[field])
    return data


def decrypt_client_pii(data: dict) -> dict:
    """Decrypt PII fields in a dict after reading from DB.
    Modifies and returns the same dict."""
    for field in PII_FIELDS:
        if field in data and data[field]:
            data[field] = decrypt_value(data[field])
    return data
