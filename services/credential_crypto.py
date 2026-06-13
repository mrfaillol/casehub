"""Credential encryption for stored e-mail account passwords.

Council ruling 2026-06-03-casehub-email-credential-encryption (approve 2/2,
sentinela + git-custodian): replaces the previous BASE64-only storage of
email_accounts.password_encrypted (CWE-312/CWE-261, plaintext-equivalent)
with real authenticated encryption (Fernet / AES-128-CBC + HMAC).

Key derivation: a Fernet key is derived from config.settings.SECRET_KEY via
HKDF-SHA256 (32 bytes -> urlsafe_b64encode), domain-separated with
info=b'casehub-email-credential-v1'. SECRET_KEY itself is NEVER used as the
Fernet key directly, and there is NO hardcoded key fallback. SECRET_KEY is
already fail-closed in config.py (FATAL on empty).

Storage format is versioned ('v1:' + Fernet token) so the scheme can be
rotated later. Legacy values without the prefix are read as the old base64
encoding (compat; email_accounts is empty in alpha) and re-encrypted on the
next save.
"""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import settings

logger = logging.getLogger(__name__)

_VERSION_PREFIX = "v1:"
_HKDF_INFO = b"casehub-email-credential-v1"

_fernet_cache = None


def _get_fernet() -> Fernet:
    """Build (and cache) the Fernet instance from the derived key.

    SECRET_KEY is fail-closed in config.py, so it is always non-empty here.
    """
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache

    secret = settings.SECRET_KEY
    if not secret:
        # Defensive: config.py already exits on empty SECRET_KEY. No fallback.
        raise RuntimeError("SECRET_KEY is not set; cannot derive credential key")

    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(secret.encode("utf-8"))

    fernet_key = base64.urlsafe_b64encode(derived)
    _fernet_cache = Fernet(fernet_key)
    return _fernet_cache


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential and return a versioned, storable string."""
    if plaintext is None:
        plaintext = ""
    token = _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return _VERSION_PREFIX + token


def decrypt_credential(stored: str) -> str:
    """Decrypt a stored credential.

    'v1:' prefix -> Fernet. Otherwise treat as legacy base64 (compat) so old
    rows still work; callers re-encrypt on next save.
    """
    if stored is None:
        return ""
    if stored.startswith(_VERSION_PREFIX):
        token = stored[len(_VERSION_PREFIX):].encode("utf-8")
        try:
            return _get_fernet().decrypt(token).decode("utf-8")
        except InvalidToken:
            # Never log token/key material.
            logger.error("Failed to decrypt v1 email credential (InvalidToken)")
            raise
    # Legacy base64 compatibility path (email_accounts empty in alpha).
    return base64.b64decode(stored).decode("utf-8")
