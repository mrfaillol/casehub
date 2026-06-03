import asyncio
import inspect
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch


def _client_case(db, org_id, suffix):
    from models import Case, Client

    client = Client(first_name=f"Client{suffix}", last_name="Tenant", org_id=org_id)
    db.add(client)
    db.flush()

    case = Case(
        client_id=client.id,
        org_id=org_id,
        case_number=f"REP-{org_id}-{suffix}",
        case_name=f"Report case {suffix}",
    )
    db.add(case)
    db.flush()
    return case


def test_quick_financeiro_mensal_scopes_billing_items_by_org(db):
    from models import BillingItem
    from routes.reports import quick_report

    visible_case = _client_case(db, 42, "visible")
    hidden_case = _client_case(db, 99, "hidden")

    db.add_all(
        [
            BillingItem(
                org_id=42,
                case_id=visible_case.id,
                description="Visible paid",
                amount=100,
                status="paid",
                created_at=datetime.utcnow(),
            ),
            BillingItem(
                org_id=42,
                case_id=visible_case.id,
                description="Visible pending",
                amount=25,
                status="pending",
                created_at=datetime.utcnow(),
            ),
            BillingItem(
                org_id=99,
                case_id=hidden_case.id,
                description="Hidden paid",
                amount=9000,
                status="paid",
                created_at=datetime.utcnow(),
            ),
            BillingItem(
                org_id=99,
                case_id=hidden_case.id,
                description="Hidden pending",
                amount=8000,
                status="pending",
                created_at=datetime.utcnow(),
            ),
        ]
    )
    db.commit()

    request = SimpleNamespace(state=SimpleNamespace(org_id=42))
    with patch("routes.reports.get_current_user", return_value=SimpleNamespace(id=1)):
        response = asyncio.run(quick_report("financeiro_mensal", request, db))

    payload = json.loads(response.body)
    assert payload["faturado"] == 125.0
    assert payload["pago"] == 100.0
    assert payload["pendente"] == 25.0


def test_financial_report_generators_use_scoped_billing_queries():
    from routes import reports

    revenue_source = inspect.getsource(reports.generate_revenue_summary)
    financeiro_source = inspect.getsource(reports.generate_financeiro_mensal)
    time_entries_source = inspect.getsource(reports.generate_time_entries_report)

    assert "_scoped_query(db, BillingItem, org_id)" in revenue_source
    assert "_scoped_query(db, BillingItem, org_id)" in financeiro_source
    assert "_scoped_query(db, TimeEntry, org_id)" in time_entries_source
