from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.templating import Jinja2Templates
from sqlalchemy import text


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
    user = SimpleNamespace(id=7, name="Ana PessoaDemo")

    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(dashboard_metrics, "_redis", lambda: fake_redis)

    first = dashboard_metrics.get_basic_dashboard_context(db, 42, user.id, today, user=user)
    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(db, "query", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cache miss")))

    second = dashboard_metrics.get_basic_dashboard_context(db, 42, user.id, today, user=user)

    assert second == first
    assert second["basic_dashboard"]["user_first_name"] == "Ana"
    assert list(fake_redis.ttls.values()) == [60]


def _create_dashboard_appointment_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY,
            org_id INTEGER,
            title VARCHAR(255) NOT NULL,
            type VARCHAR(50) NOT NULL DEFAULT 'atendimento',
            assigned_to INTEGER,
            created_by INTEGER,
            client_name VARCHAR(255),
            case_id INTEGER,
            date DATE NOT NULL,
            time_start TIME,
            time_end TIME,
            outcome VARCHAR(50)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS appointment_assignees (
            appointment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (appointment_id, user_id)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_assignees (
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (task_id, user_id)
        )
    """))
    db.commit()


def _metric_map(dashboard):
    return {metric["label"]: metric for metric in dashboard["metrics"]}


def test_basic_dashboard_scopes_tasks_appointments_and_hearings_by_user(db, monkeypatch):
    from models import Case, Client, Reminder, Task, User
    from services import dashboard_metrics

    _create_dashboard_appointment_tables(db)
    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(dashboard_metrics, "_redis", lambda: None)
    today = date(2026, 6, 15)
    admin = User(email="admin-scope@test.com", name="Admin Scope", password_hash="x", org_id=42, user_type="admin")
    ana = User(email="ana-scope@test.com", name="Ana Scope", password_hash="x", org_id=42, user_type="attorney")
    bruno = User(email="bruno-scope@test.com", name="Bruno Scope", password_hash="x", org_id=42, user_type="attorney")
    db.add_all([admin, ana, bruno])
    db.flush()

    # Volume do escritório (casos) é org-wide para TODOS, inclusive não-admin
    # (decisão de produto Equipe CaseHub 2026-06-15): só tarefas/compromissos/audiências filtram.
    cliente = Client(first_name="Cliente", last_name="Escritório", org_id=42)
    db.add(cliente)
    db.flush()
    db.add(Case(org_id=42, client_id=cliente.id, case_name="Caso Escritório", status="intake"))
    db.flush()

    ana_task = Task(org_id=42, title="Ana direta", status="pending", assigned_to=ana.id, due_date=today - timedelta(days=1))
    bruno_task = Task(org_id=42, title="Bruno direta", status="pending", assigned_to=bruno.id, due_date=today)
    ana_junction_task = Task(org_id=42, title="Ana junction", status="pending", assigned_to=None, due_date=today)
    db.add_all([ana_task, bruno_task, ana_junction_task])
    db.flush()
    db.execute(
        text("INSERT INTO task_assignees (task_id, user_id) VALUES (:task_id, :user_id)"),
        {"task_id": ana_junction_task.id, "user_id": ana.id},
    )
    db.execute(
        text("""
            INSERT INTO appointments (id, org_id, title, type, assigned_to, date, time_start)
            VALUES
              (1, 42, 'Ana compromisso', 'atendimento', :ana_id, :today, '09:00'),
              (2, 42, 'Bruno compromisso', 'atendimento', :bruno_id, :today, '10:00'),
              (3, 42, 'Ana audiencia junction', 'audiencia', NULL, :tomorrow, '11:00'),
              (4, 42, 'Bruno audiencia', 'audiencia', :bruno_id, :tomorrow, '13:00')
        """),
        {"ana_id": ana.id, "bruno_id": bruno.id, "today": today, "tomorrow": today + timedelta(days=1)},
    )
    db.execute(
        text("INSERT INTO appointment_assignees (appointment_id, user_id) VALUES (3, :ana_id)"),
        {"ana_id": ana.id},
    )
    db.add(Reminder(
        org_id=42,
        title="Prazo geral",
        due_date=datetime.combine(today + timedelta(days=2), time(hour=10)),
        is_completed=False,
    ))
    db.commit()

    personal = dashboard_metrics.get_basic_dashboard_context(db, 42, ana.id, today, user=ana)["basic_dashboard"]
    personal_metrics = _metric_map(personal)

    assert personal["scope_is_personal"] is True
    assert personal["scope_label"] == "Minha visão"
    assert personal_metrics["Tarefas em aberto"]["value"] == 2
    assert personal_metrics["Tarefas em aberto"]["delta"]["label"] == "1 atrasadas"
    assert personal_metrics["Compromissos (hoje)"]["value"] == 1
    assert personal_metrics["Compromissos (hoje)"]["delta"]["label"] == "2 na semana"
    assert personal_metrics["Audiências (semana)"]["value"] == 1
    assert personal_metrics["Prazos (7 dias)"]["value"] == 1
    # KPIs de volume da org permanecem visíveis e org-wide para não-admin.
    assert "Novos casos (14d)" in personal_metrics
    assert personal_metrics["Novos casos (14d)"]["value"] == 1
    assert [task["title"] for task in personal["tasks_today"]] == ["Ana direta", "Ana junction"]
    assert [hearing["title"] for hearing in personal["hearings_week"]] == ["Ana audiencia junction"]
    # Lista de processos recentes também é org-wide (não filtra por dono).
    assert [case["title"] for case in personal["recent_cases"]] == ["Caso Escritório"]

    dashboard_metrics.clear_dashboard_cache()
    bruno_dashboard = dashboard_metrics.get_basic_dashboard_context(db, 42, bruno.id, today, user=bruno)["basic_dashboard"]
    bruno_metrics = _metric_map(bruno_dashboard)

    assert bruno_dashboard["scope_is_personal"] is True
    assert bruno_metrics["Tarefas em aberto"]["value"] == 1
    assert bruno_metrics["Compromissos (hoje)"]["value"] == 1
    assert bruno_metrics["Audiências (semana)"]["value"] == 1
    assert [task["title"] for task in bruno_dashboard["tasks_today"]] == ["Bruno direta"]
    assert [hearing["title"] for hearing in bruno_dashboard["hearings_week"]] == ["Bruno audiencia"]

    dashboard_metrics.clear_dashboard_cache()
    admin_dashboard = dashboard_metrics.get_basic_dashboard_context(db, 42, admin.id, today, user=admin)["basic_dashboard"]
    admin_metrics = _metric_map(admin_dashboard)

    assert admin_dashboard["scope_is_personal"] is False
    assert admin_metrics["Tarefas em aberto"]["value"] == 3
    assert admin_metrics["Compromissos (hoje)"]["value"] == 2
    assert admin_metrics["Audiências (semana)"]["value"] == 2
    assert "Novos casos (14d)" in admin_metrics
    # Volume é idêntico (org-wide) entre admin e não-admin.
    assert admin_metrics["Novos casos (14d)"]["value"] == personal_metrics["Novos casos (14d)"]["value"]
    assert [case["title"] for case in admin_dashboard["recent_cases"]] == ["Caso Escritório"]

    dashboard_metrics.clear_dashboard_cache()
    legacy_personal = dashboard_metrics.get_legacy_dashboard_context(
        db, 42, ana.id, today, "lite", user=ana,
    )
    dashboard_metrics.clear_dashboard_cache()
    legacy_admin = dashboard_metrics.get_legacy_dashboard_context(
        db, 42, admin.id, today, "lite", user=admin,
    )

    assert legacy_personal["stats"]["pending_tasks"] == 2
    assert legacy_personal["stats"]["overdue_tasks"] == 1
    assert [task.title for task in legacy_personal["upcoming_tasks"]] == ["Ana direta", "Ana junction"]
    assert legacy_admin["stats"]["pending_tasks"] == 3


def test_basic_dashboard_includes_items_created_by_non_admin(db, monkeypatch):
    """Não-admin vê o que CRIOU, mesmo sem ser o responsável (decisão Equipe CaseHub 2026-06-15):
    posse = assigned_to OR created_by OR junção multi-assignee."""
    from models import Task, User
    from services import dashboard_metrics

    _create_dashboard_appointment_tables(db)
    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(dashboard_metrics, "_redis", lambda: None)
    today = date(2026, 6, 15)
    ana = User(email="ana-created@test.com", name="Ana Created", password_hash="x", org_id=77, user_type="attorney")
    bruno = User(email="bruno-created@test.com", name="Bruno Created", password_hash="x", org_id=77, user_type="attorney")
    db.add_all([ana, bruno])
    db.flush()

    # Tarefa criada por Ana, atribuída a Bruno (não é responsável nem está na junção).
    db.add(Task(org_id=77, title="Criada por Ana", status="pending", assigned_to=bruno.id, created_by=ana.id, due_date=today))
    # Controle: tarefa só de Bruno — Ana não deve ver.
    db.add(Task(org_id=77, title="Só de Bruno", status="pending", assigned_to=bruno.id, created_by=bruno.id, due_date=today))
    db.flush()
    db.execute(
        text("""
            INSERT INTO appointments (id, org_id, title, type, assigned_to, created_by, date, time_start)
            VALUES
              (10, 77, 'Compromisso criado por Ana', 'atendimento', :bruno_id, :ana_id, :today, '09:00'),
              (11, 77, 'Compromisso só de Bruno', 'atendimento', :bruno_id, :bruno_id, :today, '10:00')
        """),
        {"ana_id": ana.id, "bruno_id": bruno.id, "today": today},
    )
    db.commit()

    personal = dashboard_metrics.get_basic_dashboard_context(db, 77, ana.id, today, user=ana)["basic_dashboard"]
    personal_metrics = _metric_map(personal)

    assert personal_metrics["Tarefas em aberto"]["value"] == 1
    assert [task["title"] for task in personal["tasks_today"]] == ["Criada por Ana"]
    assert personal_metrics["Compromissos (hoje)"]["value"] == 1


def test_dashboard_scope_fails_closed_for_identityless_viewer(db):
    """Red line §7 do handoff 03: viewer sem identidade NÃO pode vazar org-wide.
    O primitivo de escopo deve falhar FECHADO (-1 = não casa nada), nunca None
    (None significa org-wide e é reservado a admin/superadmin)."""
    from types import SimpleNamespace
    from services import dashboard_metrics

    # Viewer sem objeto user e sem id de fallback → fail-closed (-1).
    assert dashboard_metrics._dashboard_scoped_user_id(None) == -1
    assert dashboard_metrics._dashboard_scoped_user_id(None, fallback_user_id=None) == -1
    # User sem id resolvível e sem fallback → fail-closed.
    assert dashboard_metrics._dashboard_scoped_user_id(SimpleNamespace(id=None, user_type="attorney")) == -1
    # O filtro de tarefa correspondente NÃO é None (None abriria org-wide).
    assert dashboard_metrics.dashboard_task_scope_filter(db, None) is not None

    # Sanidade: admin continua org-wide (None), não fail-closed.
    admin = SimpleNamespace(id=1, user_type="admin", role=None, name="Adm")
    assert dashboard_metrics._dashboard_scoped_user_id(admin) is None
    assert dashboard_metrics.dashboard_task_scope_filter(db, admin) is None


def test_dashboard_admin_predicate_is_user_type_only(db):
    """Q4 do handoff 03 (resolvida 2026-06-15): admin do dashboard = user_type in
    (admin, superadmin) APENAS. O atributo `role` (que nunca é populado no model)
    não concede mais visão org-wide — evita over-grant latente."""
    from types import SimpleNamespace
    from services import dashboard_metrics

    # user_type admin/superadmin → org-wide (case-insensitive preservado).
    assert dashboard_metrics.dashboard_user_sees_org_scope(SimpleNamespace(user_type="admin")) is True
    assert dashboard_metrics.dashboard_user_sees_org_scope(SimpleNamespace(user_type="superadmin")) is True
    assert dashboard_metrics.dashboard_user_sees_org_scope(SimpleNamespace(user_type="ADMIN")) is True

    # Não-admin por user_type → escopado, MESMO que tenha role='admin'.
    leaky = SimpleNamespace(id=5, user_type="attorney", role="admin")
    assert dashboard_metrics.dashboard_user_sees_org_scope(leaky) is False
    assert dashboard_metrics._dashboard_scoped_user_id(leaky) == 5
    assert dashboard_metrics.dashboard_task_scope_filter(db, leaky) is not None

    # Não-admin comum → escopado.
    assert dashboard_metrics.dashboard_user_sees_org_scope(SimpleNamespace(user_type="paralegal")) is False


def test_basic_dashboard_keeps_process_deadlines_org_wide_for_non_admin(db, monkeypatch):
    from models import User
    from services import dashboard_metrics

    _create_dashboard_appointment_tables(db)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS prazos_processuais (
            id INTEGER PRIMARY KEY,
            org_id INTEGER,
            case_id INTEGER,
            tipo VARCHAR(100),
            data_vencimento DATE,
            status VARCHAR(50),
            descricao TEXT,
            processo_override VARCHAR(80)
        )
    """))
    dashboard_metrics.clear_dashboard_cache()
    monkeypatch.setattr(dashboard_metrics, "_redis", lambda: None)
    today = date(2026, 6, 15)
    ana = User(
        email="ana-prazos@test.com",
        name="Ana Prazos",
        password_hash="x",
        org_id=55,
        user_type="paralegal",
    )
    db.add(ana)
    db.flush()
    db.execute(
        text("""
            INSERT INTO prazos_processuais (id, org_id, tipo, data_vencimento, status, processo_override)
            VALUES
              (1, 55, 'Contestacao', :today, 'pendente', 'PROC-1'),
              (2, 55, 'Recurso', :tomorrow, 'pendente', 'PROC-2')
        """),
        {"today": today, "tomorrow": today + timedelta(days=1)},
    )
    db.commit()

    personal = dashboard_metrics.get_basic_dashboard_context(db, 55, ana.id, today, user=ana)["basic_dashboard"]
    personal_metrics = _metric_map(personal)

    assert personal["scope_is_personal"] is True
    assert personal_metrics["Prazos (7 dias)"]["value"] == 2
    assert [deadline["title"] for deadline in personal["deadlines_week"]] == ["Contestacao", "Recurso"]


def test_widget_tasks_scopes_non_admin_task_list(db):
    from models import Task, User
    from routes.dashboard_api import _widget_tasks

    _create_dashboard_appointment_tables(db)
    today = date(2026, 6, 15)
    ana = User(email="ana-widget@test.com", name="Ana Widget", password_hash="x", org_id=42, user_type="attorney")
    bruno = User(email="bruno-widget@test.com", name="Bruno Widget", password_hash="x", org_id=42, user_type="attorney")
    db.add_all([ana, bruno])
    db.flush()
    db.add_all([
        Task(title="Minha tarefa widget", org_id=42, status="pending", assigned_to=ana.id, due_date=today),
        Task(title="Tarefa de Bruno widget", org_id=42, status="pending", assigned_to=bruno.id, due_date=today),
    ])
    db.commit()

    html = _widget_tasks(db, 42, ana, today)

    assert "Minha tarefa widget" in html
    assert "Tarefa de Bruno widget" not in html


def test_widget_activity_is_admin_only(db):
    from models import Client, User
    from routes.dashboard_api import _widget_activity

    today = date(2026, 6, 15)
    admin = User(email="admin-activity@test.com", name="Admin Activity", password_hash="x", org_id=42, user_type="admin")
    ana = User(email="ana-activity@test.com", name="Ana Activity", password_hash="x", org_id=42, user_type="attorney")
    client = Client(first_name="Cliente", last_name="Sigiloso", org_id=42)
    db.add_all([admin, ana, client])
    db.commit()

    personal_html = _widget_activity(db, 42, ana, today)
    admin_html = _widget_activity(db, 42, admin, today)

    assert "Atividade restrita aos administradores" in personal_html
    assert "Cliente Sigiloso" not in personal_html
    assert "Cliente Sigiloso" in admin_html


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
