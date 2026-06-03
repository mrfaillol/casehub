import re
from collections.abc import Mapping, Sequence, Set
from typing import Any


SENSITIVE_KEY_RE = re.compile(
    r"(authorization|cookie|client[_-]?secret|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|api[_-]?key|password|secret|jwt|private[_-]?key)",
    re.IGNORECASE,
)

TOKEN_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(Basic|Token|ApiKey|Digest)\s+[A-Za-z0-9._~+/=:-]+", re.IGNORECASE),
    re.compile(r"(client_secret|access_token|refresh_token|id_token|api_key)=([^&\s]+)", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
    re.compile(r"\bOAB[/-]?[A-Z]{2}\s*\d+\b", re.IGNORECASE),
]


def redact_text(value: str) -> str:
    redacted = value
    for pattern in TOKEN_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


def _redact_match(match: re.Match[str]) -> str:
    if "=" in match.group(0) and match.re.groups > 0:
        return match.group(1) + "=<redacted>"
    return "<redacted>"


def redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            key: ("<redacted>" if SENSITIVE_KEY_RE.search(str(key)) else redact_payload(item))
            for key, item in value.items()
        }
    if isinstance(value, Set):
        items = {redact_payload(item) for item in value}
        return frozenset(items) if isinstance(value, frozenset) else items
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [redact_payload(item) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    return value
