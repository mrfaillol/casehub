"""Regression tests for leads_manager.notify_conversion_feedback — non-blocking.

notify_conversion_feedback POSTs a conversion event to the WhatsApp bot. The
call is fire-and-forget telemetry (result only logged), but it ran a blocking
httpx.post(timeout=5.0) inline. The function is reached from async route
handlers (update_lead_endpoint, mark-as-converted) via update_lead /
mark_as_converted, so the blocking POST stalled the event loop for up to 5s
per pipeline-stage change. The POST now runs on a detached daemon thread.

Run: pytest tests/test_leads_conversion_feedback.py
"""
import threading
import time

import httpx

from services import leads_manager


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "ok"


def test_notify_conversion_feedback_does_not_block_caller(monkeypatch):
    """The caller returns immediately; the blocking POST is detached to a
    background thread but still fires with the correct payload."""
    delay = 0.4
    posted = threading.Event()
    captured = {}

    def _slow_post(url, *args, **kwargs):
        time.sleep(delay)
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        posted.set()
        return _Resp(200)

    monkeypatch.setattr(leads_manager.httpx, "post", _slow_post)

    lead = {"id": "L1", "name": "Alice", "phone": "+5511999999999"}
    t0 = time.perf_counter()
    leads_manager.notify_conversion_feedback(lead, new_stage="CLOSING")
    elapsed = time.perf_counter() - t0

    # caller is not blocked by the up-to-5s POST
    assert elapsed < delay / 2, f"caller blocked for {elapsed:.2f}s"

    # the POST still happens, off-thread, with the mapped event
    assert posted.wait(timeout=3.0), "conversion POST never fired"
    assert captured["json"]["event"] == "payment_completed"   # CLOSING
    assert captured["json"]["lead_id"] == "L1"
    assert captured["url"].endswith("/api/conversion-feedback")


def test_notify_conversion_feedback_skips_unmapped_stage(monkeypatch):
    """A stage with no conversion event mapped -> no POST, no thread."""
    calls = []
    monkeypatch.setattr(leads_manager.httpx, "post",
                        lambda *a, **k: calls.append(1) or _Resp(200))

    leads_manager.notify_conversion_feedback({"id": "L1"}, new_stage="NOT_A_STAGE")

    assert calls == []


def test_notify_conversion_feedback_skips_same_event_transition(monkeypatch):
    """Moving between two stages that map to the same event -> no POST."""
    calls = []
    monkeypatch.setattr(leads_manager.httpx, "post",
                        lambda *a, **k: calls.append(1) or _Resp(200))

    # LEAD_QUALIFICATION and INTAKE_CALL both map to 'qualified'
    leads_manager.notify_conversion_feedback(
        {"id": "L1"}, new_stage="INTAKE_CALL", old_stage="LEAD_QUALIFICATION"
    )

    assert calls == []
