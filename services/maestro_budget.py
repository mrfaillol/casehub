"""Cost bounds p/ o provider externo (pago) do Maestro NIM.

Ruling 2026-06-18-order-nvidia-maestro-activation-steps (token-economy):
- cap tokens/org/dia fail-closed (persistido via ai_chat_history.tokens_used);
- circuit-breaker em memoria (abre em 429/insufficient-credits/falhas repetidas).
Breaker e por-processo (uvicorn worker); cap e cross-processo via DB.
"""
import os
import time

from sqlalchemy import text as _sql_text

_BREAKER = {"open_until": 0.0, "fails": 0}
_THRESHOLD = 3
_COOLDOWN_S = 300.0


def _cap():
    try:
        return int(os.getenv("MAESTRO_DAILY_TOKEN_CAP", "200000"))
    except Exception:
        return 200000


def breaker_open():
    return time.monotonic() < _BREAKER["open_until"]


def note_failure(kind=""):
    _BREAKER["fails"] = _BREAKER["fails"] + 1
    k = (kind or "").lower()
    if _BREAKER["fails"] >= _THRESHOLD or "429" in k or "credit" in k or "quota" in k:
        _BREAKER["open_until"] = time.monotonic() + _COOLDOWN_S


def note_success():
    _BREAKER["fails"] = 0
    _BREAKER["open_until"] = 0.0


def external_allowed(db, org_id):
    """True se pode chamar o provider externo agora. Breaker aberto -> False;
    cap/dia excedido -> False (fail-closed); hiccup de query -> True (nao mata)."""
    if breaker_open():
        return False
    try:
        row = db.execute(_sql_text(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM ai_chat_history "
            "WHERE org_id = :oid AND created_at >= CURRENT_DATE"
        ), {"oid": org_id}).fetchone()
        used = int(row[0]) if row and row[0] is not None else 0
        return used < _cap()
    except Exception:
        return True
