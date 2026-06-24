import asyncio
from datetime import date, timedelta
from types import SimpleNamespace


def _request(org_id=1):
    return SimpleNamespace(state=SimpleNamespace(org_id=org_id))


def test_dashboard_stats_current_contract(db):
    from models import Case, Client, Document, Task, User
    from routes.api import get_dashboard_stats

    user = User(email="admin-dashboard@test.com", name="Admin Dashboard", password_hash="x", org_id=1, user_type="admin")
    client = Client(first_name="Ana", last_name="Silva", org_id=1)
    db.add_all([user, client])
    db.commit()

    case = Case(client_id=client.id, org_id=1, case_name="Caso Trabalhista", status="intake", visa_type="labor")
    task = Task(title="Prazo", org_id=1, status="pending", due_date=date.today() - timedelta(days=1))
    db.add_all([case, task])
    db.commit()

    document = Document(name="Contrato", org_id=1, client_id=client.id, case_id=case.id)
    db.add(document)
    db.commit()

    response = asyncio.run(get_dashboard_stats(_request(1), db, user=user))

    assert set(response) == {"stats", "charts"}
    assert response["stats"]["total_clients"] == 1
    assert response["stats"]["total_cases"] == 1
    assert response["stats"]["active_cases"] == 1
    assert response["stats"]["total_documents"] == 1
    assert response["stats"]["pending_tasks"] == 1
    assert response["stats"]["overdue_tasks"] == 1
    assert response["charts"]["cases_by_status"] == {"intake": 1}
    assert response["charts"]["cases_by_visa_type"] == {"labor": 1}


def test_dashboard_stats_scopes_task_counts_for_non_admin(db):
    from models import Task, User
    import routes.api as api_route

    ana = User(
        email="ana-api-scope@test.com",
        name="Ana API",
        password_hash="x",
        org_id=1,
        user_type="attorney",
    )
    bruno = User(
        email="bruno-api-scope@test.com",
        name="Bruno API",
        password_hash="x",
        org_id=1,
        user_type="attorney",
    )
    db.add_all([ana, bruno])
    db.flush()
    db.add_all([
        Task(
            title="Minha tarefa",
            org_id=1,
            status="pending",
            assigned_to=ana.id,
            due_date=date.today() - timedelta(days=1),
        ),
        Task(
            title="Tarefa de outra pessoa",
            org_id=1,
            status="pending",
            assigned_to=bruno.id,
            due_date=date.today() - timedelta(days=1),
        ),
    ])
    db.commit()
    response = asyncio.run(api_route.get_dashboard_stats(_request(1), db, ana))

    assert response["stats"]["pending_tasks"] == 1
    assert response["stats"]["overdue_tasks"] == 1


def test_cases_list_current_contract_is_tenant_scoped(db):
    from models import Case, Client
    from routes.api import list_cases

    client = Client(first_name="Ana", last_name="Silva", org_id=1)
    other_client = Client(first_name="Other", last_name="Tenant", org_id=2)
    db.add_all([client, other_client])
    db.commit()

    visible = Case(client_id=client.id, org_id=1, case_name="Visible", status="intake", visa_type="labor")
    hidden = Case(client_id=other_client.id, org_id=2, case_name="Hidden", status="intake", visa_type="civil")
    db.add_all([visible, hidden])
    db.commit()

    response = asyncio.run(
        list_cases(
            _request(1),
            skip=0,
            limit=50,
            search=None,
            status=None,
            client_id=None,
            visa_type=None,
            db=db,
        )
    )

    assert response["total"] == 1
    assert response["skip"] == 0
    assert response["limit"] == 50
    assert len(response["data"]) == 1
    assert response["data"][0]["case_name"] == "Visible"
    assert response["data"][0]["status"] == "intake"
    assert response["data"][0]["visa_type"] == "labor"


def test_dashboard_asset_manifest_versions_minified_files():
    from core.static_assets import asset_url

    css_url = asset_url("css/templates/dashboard_modular.css")
    js_url = asset_url("js/dashboard-widgets.js")

    assert css_url.startswith("/static/css/templates/dashboard_modular.min.css?v=")
    assert js_url.startswith("/static/js/dashboard-widgets.min.js?v=")
    assert asset_url("css/not-in-manifest.css") == "/static/css/not-in-manifest.css"


def test_asset_manifest_covers_high_impact_assets():
    from core.static_assets import asset_url

    # Basic mode primary CSS/JS (highest-impact assets)
    browser_basic_css = asset_url("css/casehub-browser-basic.css")
    browser_basic_js = asset_url("js/casehub-browser-basic.js")
    tab_manager_js = asset_url("js/tab-manager.js")
    login_css = asset_url("css/casehub-login-basic.css")

    # Shared CSS used by all themes
    design_system_css = asset_url("css/design-system.css")
    liquid_glass_css = asset_url("css/liquid-glass.css")
    casehub_theme_css = asset_url("css/casehub-theme.css")
    dashboard_css = asset_url("css/templates/dashboard.css")
    tab_bar_css = asset_url("css/tab-bar.css")
    release_notice_css = asset_url("css/casehub-release-notice.css")

    assert browser_basic_css.startswith("/static/css/casehub-browser-basic.min.css?v=")
    assert browser_basic_js.startswith("/static/js/casehub-browser-basic.min.js?v=")
    assert tab_manager_js.startswith("/static/js/tab-manager.min.js?v=")
    assert login_css.startswith("/static/css/casehub-login-basic.min.css?v=")
    assert design_system_css.startswith("/static/css/design-system.min.css?v=")
    assert liquid_glass_css.startswith("/static/css/liquid-glass.min.css?v=")
    assert casehub_theme_css.startswith("/static/css/casehub-theme.min.css?v=")
    assert dashboard_css.startswith("/static/css/templates/dashboard.min.css?v=")
    assert tab_bar_css.startswith("/static/css/tab-bar.min.css?v=")
    assert release_notice_css.startswith("/static/css/casehub-release-notice.min.css?v=")


def test_brand_kit_fallback_favicon_uses_manifest():
    import json

    from core.static_assets import BRAND_KIT_MANIFEST_PATH, brand_kit_fallback_favicon_url

    with open(BRAND_KIT_MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    assert brand_kit_fallback_favicon_url() == (
        f"/static/brand-kit/{manifest['fallback_favicon']}"
        f"?v={manifest['favicons'][manifest['fallback_favicon']]}"
    )
