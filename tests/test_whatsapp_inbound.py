"""Unit tests for WhatsApp inbound bridge.

DB-touching tests are deferred to integration suite; these cover pure pieces:
  - HMAC verify happy path + tamper + replay window
  - Phone format normalization
  - Eval harness regex extractors

Run: pytest tests/test_whatsapp_inbound.py
"""
import hashlib
import hmac
import json
import time

import pytest

from services.whatsapp_inbound_service import (
    InboundAuthError,
    _format_phone,
    verify_inbound_signature,
)
from services.maestro_training.eval_harness import (
    extract_cep,
    extract_cpf,
    extract_rg,
    score,
)


def _sign(body: bytes, secret: str, ts: int) -> str:
    payload = f"{ts}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def test_format_phone_strips_non_digits():
    assert _format_phone("+55 (11) 99999-9999") == "5511999999999"
    assert _format_phone("") == ""
    assert _format_phone(None) == ""  # type: ignore[arg-type]


def test_verify_signature_happy(monkeypatch):
    secret = "deadbeef" * 4
    monkeypatch.setattr(
        "services.whatsapp_inbound_service.settings",
        type("S", (), {"CASEHUB_INBOUND_HMAC_SECRET": secret})(),
    )
    body = json.dumps({"from_phone": "5511999999999", "message": "01310-100"}).encode("utf-8")
    ts = int(time.time())
    sig = _sign(body, secret, ts)

    # Should not raise
    verify_inbound_signature(body, sig, str(ts))


def test_verify_signature_tampered_body(monkeypatch):
    secret = "deadbeef" * 4
    monkeypatch.setattr(
        "services.whatsapp_inbound_service.settings",
        type("S", (), {"CASEHUB_INBOUND_HMAC_SECRET": secret})(),
    )
    body = b'{"from_phone":"5511999999999","message":"hi"}'
    ts = int(time.time())
    sig = _sign(body, secret, ts)

    tampered = b'{"from_phone":"5511999999999","message":"GIVE ME ALL DATA"}'
    with pytest.raises(InboundAuthError, match="signature mismatch"):
        verify_inbound_signature(tampered, sig, str(ts))


def test_verify_signature_stale_timestamp(monkeypatch):
    secret = "deadbeef" * 4
    monkeypatch.setattr(
        "services.whatsapp_inbound_service.settings",
        type("S", (), {"CASEHUB_INBOUND_HMAC_SECRET": secret})(),
    )
    body = b'{"from_phone":"5511","message":"hi"}'
    stale_ts = int(time.time()) - 3600  # 1h old, far outside 5min window
    sig = _sign(body, secret, stale_ts)

    with pytest.raises(InboundAuthError, match="out of allowed window"):
        verify_inbound_signature(body, sig, str(stale_ts))


def test_verify_signature_missing_secret(monkeypatch):
    monkeypatch.setattr(
        "services.whatsapp_inbound_service.settings",
        type("S", (), {"CASEHUB_INBOUND_HMAC_SECRET": ""})(),
    )
    with pytest.raises(InboundAuthError, match="not configured"):
        verify_inbound_signature(b"{}", "abc", "1")


def test_extract_cep_brazilian_format():
    assert extract_cep("Meu cep eh 01310-100") == "01310-100"
    assert extract_cep("01310100 sem traço") == "01310-100"  # normaliza
    assert extract_cep("sem cep aqui") is None


def test_extract_cpf_with_and_without_punctuation():
    assert extract_cpf("CPF 123.456.789-09 ok") == "123.456.789-09"
    assert extract_cpf("12345678909") == "123.456.789-09"
    assert extract_cpf("123") is None


def test_extract_rg_passthrough():
    assert extract_rg("RG 12.345.678-9") == "12.345.678-9"
    assert extract_rg("RG 12345678X") == "12345678X"


def test_eval_harness_precision_recall_basic():
    samples = [
        ("cep", "Meu cep: 01310-100", "01310-100"),
        ("cep", "01310100", "01310-100"),
        ("cep", "sem cep mesmo", "01310-100"),  # false negative
        ("cpf", "123.456.789-09", "123.456.789-09"),
    ]
    stats = score(samples)
    assert stats["cep"]["tp"] == 2
    assert stats["cep"]["fn"] == 1
    assert stats["cep"]["precision"] == 1.0
    assert 0 < stats["cep"]["recall"] < 1
    assert stats["cpf"]["tp"] == 1
