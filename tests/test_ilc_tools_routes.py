"""Regression tests for routes/ilc_tools — non-blocking HTTP to the tools service.

Four ilc_tools handlers (tools_dashboard, generate_lor, generate_ps,
tools_status) make blocking `requests` calls to the tools service — two of
them with timeout=60. They were declared `async def`, so the blocking call ran
directly on the event loop and stalled the whole server for the call's
duration (up to 60s for a LOR/PS generation).

They are now plain `def` handlers: they await nothing, and FastAPI runs sync
path operations in a threadpool, so the blocking I/O no longer touches the
event loop. This suite locks that in (structurally) and measures that
concurrent requests overlap instead of serializing.

Run: pytest tests/test_ilc_tools_routes.py
"""
import concurrent.futures
import inspect
import time

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.ilc_tools as ilc_tools
from models import get_db

_BLOCKING_HANDLERS = [
    ilc_tools.tools_dashboard,
    ilc_tools.generate_lor,
    ilc_tools.generate_ps,
    ilc_tools.tools_status,
]


@pytest.mark.parametrize("handler", _BLOCKING_HANDLERS, ids=lambda h: h.__name__)
def test_blocking_http_handlers_are_sync(handler):
    """Handlers that make blocking `requests` calls must be plain `def` so
    FastAPI threadpools them — never `async def` (that runs the blocking call
    on the event loop)."""
    assert not inspect.iscoroutinefunction(handler), (
        f"{handler.__name__} is async def but makes a blocking requests call; "
        f"it must be a sync def so FastAPI runs it off the event loop"
    )


def _build_app():
    app = FastAPI()
    app.include_router(ilc_tools.router)

    def _override_get_db():
        yield None

    app.dependency_overrides[get_db] = _override_get_db
    return app


def test_tools_status_requests_do_not_serialize(monkeypatch):
    """N concurrent GET /ilc-tools/api/status calls, each behind a 0.3s blocking
    tools-service request, must overlap (~0.3s) — not serialize (~N*0.3s) as
    they did while the handler was async def on the event loop."""
    delay, n = 0.3, 4

    class _Resp:
        status_code = 200

        def json(self):
            return {"version": "test"}

    def _slow_get(url, *args, **kwargs):
        time.sleep(delay)
        return _Resp()

    monkeypatch.setattr(ilc_tools, "get_current_user", lambda request, db: object())
    monkeypatch.setattr(requests, "get", _slow_get)

    app = _build_app()
    with TestClient(app) as client:
        def _one(_):
            r = client.get("/ilc-tools/api/status")
            return r.status_code, r.json()

        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            results = list(ex.map(_one, range(n)))
        elapsed = time.perf_counter() - t0

    serialized = n * delay
    assert elapsed < serialized / 2, (
        f"{elapsed:.2f}s for {n} concurrent calls — expected overlap near "
        f"{delay}s, not serialized {serialized:.2f}s (event loop blocked)"
    )
    assert all(status == 200 for status, _ in results)
    assert all(body == {"online": True, "version": "test"} for _, body in results)
