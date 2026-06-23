"""
Regression test for the 2026-06-14 remote runtime (tenanta.casehub.legal) 502.

Root cause: the FastAPI ``startup`` lifespan handler bootstraps the default
admin via an UNGUARDED ``db = next(get_db())`` / ``db.query(User)``. When the
database is unreachable or rejects our credentials at boot — e.g. right after a
deploy's ``docker compose up -d --force-recreate`` while Postgres is still
settling, or during a brief credential window — that line raises. An unhandled
exception in a lifespan startup handler aborts uvicorn, the container exits,
``restart: unless-stopped`` relaunches it, and prod crash-loops into a 502 for
minutes.

``depends_on: condition: service_healthy`` (already configured) only gates
*connectivity* ordering (pg_isready); it does NOT cover an auth failure or a DB
blip, so the app must defend itself: boot degraded instead of crashing. The
deep ``/healthz`` route already returns 503 while the DB is unreachable. A
background retry re-runs the DB bootstrap once the DB is back, instead of
requiring a manual restart.
"""
import asyncio
from unittest.mock import patch


class _FailingSession:
    """Stand-in for a SQLAlchemy Session whose first query hits a DB/auth error."""

    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def query(self, *_args, **_kwargs):
        raise RuntimeError('FATAL:  password authentication failed for user "casehub"')

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _session_boom():
    return _FailingSession()


def test_startup_handler_survives_db_unavailable_and_schedules_retry(monkeypatch):
    import core.app_factory as af
    from core.app_factory import create_app

    with patch("core.app_factory.StaticFiles"), patch("core.app_factory.Jinja2Templates"):
        app = create_app("lite")

    # Isolate the path under test: init_db / migrations are already tolerant;
    # the regression is the admin-bootstrap DB access.
    monkeypatch.setattr(af, "SessionLocal", _session_boom)
    monkeypatch.setattr(af, "init_db", lambda: None)
    monkeypatch.setattr(af, "_run_pending_migrations", lambda: None)
    monkeypatch.setenv("MAESTRO_SENTINEL_ENABLED", "0")

    created_coroutines = []

    def _capture_create_task(coro):
        created_coroutines.append(coro)

        class _Task:
            def cancel(self):
                return None

        return _Task()

    monkeypatch.setattr(af.asyncio, "create_task", _capture_create_task)
    # Keep the background surveillance task from doing real work in the test.
    monkeypatch.setattr(
        "services.lead_surveillance.surveillance_loop", lambda: asyncio.sleep(0)
    )

    async def _run():
        for handler in list(app.router.on_startup):
            await handler()  # MUST NOT raise even though the DB session fails

    # Before the fix: RuntimeError propagates -> uvicorn boot aborts -> 502.
    asyncio.run(_run())

    try:
        assert any(
            getattr(coro, "cr_code", None) is not None
            and coro.cr_code.co_name == "_retry_startup_db_bootstrap"
            for coro in created_coroutines
        )
    finally:
        for coro in created_coroutines:
            coro.close()


def test_startup_db_bootstrap_retry_runs_until_db_recovers(monkeypatch):
    import core.app_factory as af

    calls = []
    sleeps = []

    def _bootstrap_once():
        calls.append("bootstrap")
        return len(calls) >= 2

    async def _sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(af, "_run_startup_db_bootstrap", _bootstrap_once)
    monkeypatch.setattr(af, "STARTUP_DB_BOOTSTRAP_RETRY_SECONDS", 0)
    monkeypatch.setattr(af, "STARTUP_DB_BOOTSTRAP_MAX_RETRY_SECONDS", 0)
    monkeypatch.setattr(af.asyncio, "sleep", _sleep)

    asyncio.run(af._retry_startup_db_bootstrap())

    assert calls == ["bootstrap", "bootstrap"]
    assert sleeps == [0, 0]
