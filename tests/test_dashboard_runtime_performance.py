from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.templating import Jinja2Templates


def test_jinja_runtime_development_keeps_reload(tmp_path):
    from core.jinja_runtime import configure_jinja_templates

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    templates = Jinja2Templates(directory=str(templates_dir))

    configure_jinja_templates(templates, production=False)

    assert templates.env.auto_reload is True
    assert templates.env.bytecode_cache is None


def test_jinja_runtime_production_enables_bytecode_cache(tmp_path):
    from core.jinja_runtime import configure_jinja_templates

    templates_dir = tmp_path / "templates"
    cache_dir = tmp_path / "jinja-cache"
    templates_dir.mkdir()
    (templates_dir / "example.html").write_text("Hello {{ name }}", encoding="utf-8")
    templates = Jinja2Templates(directory=str(templates_dir))

    configure_jinja_templates(templates, production=True, cache_dir=str(cache_dir))
    html = templates.env.get_template("example.html").render(name="CaseHub")

    assert html == "Hello CaseHub"
    assert templates.env.auto_reload is False
    assert templates.env.bytecode_cache is not None
    assert cache_dir.exists()
    assert list(cache_dir.glob("__jinja2_*.cache"))


def test_jinja_runtime_debug_false_acts_as_production(tmp_path, monkeypatch):
    from config import settings
    from core.jinja_runtime import configure_jinja_templates, is_production_env

    templates_dir = tmp_path / "templates"
    cache_dir = tmp_path / "jinja-cache"
    templates_dir.mkdir()
    (templates_dir / "example.html").write_text("Cached", encoding="utf-8")
    templates = Jinja2Templates(directory=str(templates_dir))

    monkeypatch.setattr(settings, "CASEHUB_ENV", "development")
    monkeypatch.setattr(settings, "DEBUG", False)

    configure_jinja_templates(templates, cache_dir=str(cache_dir))
    html = templates.env.get_template("example.html").render()

    assert is_production_env() is True
    assert html == "Cached"
    assert templates.env.auto_reload is False
    assert templates.env.bytecode_cache is not None
    assert list(cache_dir.glob("__jinja2_*.cache"))


def test_get_context_reuses_explicit_user_without_second_lookup():
    from core.app_factory import get_context

    request = SimpleNamespace(
        cookies={},
        app=SimpleNamespace(state=SimpleNamespace(product="lite")),
        state=SimpleNamespace(org=None),
    )
    user = SimpleNamespace(id=7, ui_theme="glass")

    with patch("core.app_factory.get_current_user", side_effect=AssertionError("duplicate lookup")):
        ctx = get_context(request, db=object(), user=user)

    assert ctx["user"] is user
    assert ctx["ui_theme"] == "glass"


def test_get_current_user_caches_user_on_request_state(db, mock_request, monkeypatch):
    from auth import create_access_token, get_current_user
    from models import User

    user = User(
        email="cache@test.com",
        name="Cache Test",
        password_hash="not-used",
        org_id=1,
    )
    db.add(user)
    db.commit()

    mock_request.state = SimpleNamespace()
    mock_request.cookies = {"casehub_token": create_access_token({"sub": user.email})}

    first = get_current_user(mock_request, db)
    assert first.email == user.email

    monkeypatch.setattr(db, "query", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate query")))
    second = get_current_user(mock_request, db)
    assert second is first


def test_widget_html_cache_keys_by_org_user_and_widget(monkeypatch):
    from config import settings
    from services.dashboard_metrics import cached_widget_html, clear_dashboard_cache

    clear_dashboard_cache()
    monkeypatch.setattr(settings, "REDIS_URL", "")
    calls = {"count": 0}

    def render():
        calls["count"] += 1
        return f"<div>{calls['count']}</div>"

    assert cached_widget_html("process-status", 1, 10, render) == "<div>1</div>"
    assert cached_widget_html("process-status", 1, 10, render) == "<div>1</div>"
    assert cached_widget_html("process-status", 1, 11, render) == "<div>2</div>"
    assert calls["count"] == 2


def test_basic_dashboard_html_cache_keys_by_user_day_and_variant(monkeypatch):
    from services import dashboard_metrics

    class FakeRedis:
        def __init__(self):
            self.store = {}
            self.ttls = {}

        def get(self, key):
            return self.store.get(key)

        def setex(self, key, ttl, value):
            self.ttls[key] = ttl
            self.store[key] = value

    fake_redis = FakeRedis()
    today = date(2026, 5, 7)
    calls = {"count": 0}

    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(dashboard_metrics, "_redis", lambda: fake_redis)

    def render():
        calls["count"] += 1
        return f"<html>{calls['count']}</html>"

    assert dashboard_metrics.cached_basic_dashboard_html(42, 7, today, "lang=pt|theme=glass", render) == "<html>1</html>"
    dashboard_metrics.clear_dashboard_cache()
    assert dashboard_metrics.cached_basic_dashboard_html(42, 7, today, "lang=pt|theme=glass", render) == "<html>1</html>"
    assert dashboard_metrics.cached_basic_dashboard_html(42, 8, today, "lang=pt|theme=glass", render) == "<html>2</html>"
    assert dashboard_metrics.cached_basic_dashboard_html(42, 7, today, "lang=pt|theme=desktop", render) == "<html>3</html>"

    assert calls["count"] == 3
    assert set(fake_redis.ttls.values()) == {60}


def test_basic_dashboard_context_caches_json_context_in_redis(db, monkeypatch):
    from services import dashboard_metrics

    class FakeRedis:
        def __init__(self):
            self.store = {}
            self.ttls = {}

        def get(self, key):
            return self.store.get(key)

        def setex(self, key, ttl, value):
            self.ttls[key] = ttl
            self.store[key] = value

    fake_redis = FakeRedis()
    today = date(2026, 5, 5)
    user = SimpleNamespace(id=7, name="Ana Maria")

    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(dashboard_metrics, "_redis", lambda: fake_redis)

    first = dashboard_metrics.get_basic_dashboard_context(db, 42, user.id, today, user=user)
    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(db, "query", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cache miss")))

    second = dashboard_metrics.get_basic_dashboard_context(db, 42, user.id, today, user=user)

    assert second == first
    assert second["basic_dashboard"]["user_first_name"] == "Ana"
    assert list(fake_redis.ttls.values()) == [60]


def test_widget_prazos_uses_is_completed_flag(db):
    from models import Reminder
    from routes.dashboard_api import _widget_prazos

    today = date.today()
    reminder = Reminder(
        org_id=42,
        title="Prazo de contestacao",
        due_date=datetime.combine(today + timedelta(days=2), time(hour=10)),
        is_completed=False,
    )
    db.add(reminder)
    db.commit()

    html = _widget_prazos(db, 42, SimpleNamespace(id=1), today)

    assert "Prazo de contestacao" in html
    assert "2d" in html


def test_widget_revenue_scopes_billing_items_by_org(db):
    from models import BillingItem, Case, Client
    from routes.dashboard_api import _widget_revenue

    today = date(2026, 5, 13)
    visible_client = Client(first_name="Ana", last_name="Tenant", org_id=42)
    hidden_client = Client(first_name="Bob", last_name="Other", org_id=99)
    db.add_all([visible_client, hidden_client])
    db.flush()

    visible_case = Case(
        client_id=visible_client.id,
        org_id=42,
        case_number="REV-42",
        case_name="Visible billing",
    )
    hidden_case = Case(
        client_id=hidden_client.id,
        org_id=99,
        case_number="REV-99",
        case_name="Hidden billing",
    )
    db.add_all([visible_case, hidden_case])
    db.flush()

    db.add_all(
        [
            BillingItem(
                org_id=42,
                case_id=visible_case.id,
                description="Paid visible",
                amount=100,
                status="paid",
                paid_date=today,
            ),
            BillingItem(
                org_id=42,
                case_id=visible_case.id,
                description="Pending visible",
                amount=25,
                status="pending",
            ),
            BillingItem(
                org_id=99,
                case_id=hidden_case.id,
                description="Paid hidden",
                amount=9000,
                status="paid",
                paid_date=today,
            ),
            BillingItem(
                org_id=99,
                case_id=hidden_case.id,
                description="Pending hidden",
                amount=8000,
                status="pending",
            ),
        ]
    )
    db.commit()

    html = _widget_revenue(db, 42, SimpleNamespace(id=1), today)

    assert "R$ 100.00" in html
    assert "R$ 25.00" in html
    assert "R$ 9,000.00" not in html
    assert "R$ 8,000.00" not in html
