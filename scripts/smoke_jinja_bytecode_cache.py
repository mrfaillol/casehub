#!/usr/bin/env python3
"""Local Jinja bytecode-cache smoke for dashboard.html."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def build_dashboard_context(product: str = "lite") -> dict:
    from i18n import get_translations

    today = date.today()
    request = _ns(path="/casehub/dashboard", query_params={}, app=_ns(state=_ns(product=product)))
    user = _ns(
        id=1,
        name="Benchmark User",
        full_name="Benchmark User",
        email="benchmark@example.invalid",
        ui_theme="glass",
        must_change_password=False,
        user_type="admin",
        photo_url="",
    )

    return {
        "request": request,
        "PREFIX": "/casehub",
        "product": product,
        "lang": "pt-BR" if product == "lite" else "en",
        "theme": "light",
        "ui_theme": "glass",
        "org_name": "CaseHub Benchmark",
        "org_slug": "benchmark",
        "org_logo": "",
        "org_theme_primary": "#111111",
        "org_theme_secondary": "#f8f9fa",
        "org_theme_bg": "#f5f5f7",
        "org_features": {},
        "org_currency": "BRL" if product == "lite" else "USD",
        "base_url": "",
        "version": "2.0.0-local",
        "demo_mode": False,
        "casehub_release_notice": None,
        "casehub_maestro_fab_enabled": False,
        "enable_basic_onboarding_tour": False,
        "t": get_translations("pt-BR" if product == "lite" else "en"),
        "today": today,
        "user": user,
        "stats": _ns(
            total_clients=128,
            new_clients_month=8,
            total_cases=214,
            new_cases_month=13,
            active_cases=89,
            rfe_cases=4,
            pending_tasks=17,
            overdue_tasks=3,
        ),
        "revenue": _ns(total_paid=32000, pending=7500, hours_logged=68),
        "case_stats": _ns(filed=18, approved=22, pending=31, rfe=4, denied=2),
        "trend_months": ["Dec", "Jan", "Feb", "Mar", "Apr", "May"],
        "trend_counts": [5, 8, 7, 11, 9, 13],
        "visa_types": ["EB-2", "O-1", "F-1", "I-130"],
        "visa_counts": [7, 3, 5, 2],
        "cases_attention": [],
        "expiring_soon": [],
        "recent_clients": [],
        "recent_cases": [],
        "upcoming_tasks": [],
    }


def build_templates(cache_dir: Path, *, product: str = "lite") -> Jinja2Templates:
    from core.jinja_runtime import configure_jinja_templates

    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
    configure_jinja_templates(templates, production=True, cache_dir=str(cache_dir))
    templates.env.globals.update(
        {
            "PREFIX": "/casehub",
            "product": product,
            "version": "2.0.0-local",
            "asset_url": lambda path: f"/static/{str(path).lstrip('/')}",
            "casehub_release_notice": None,
            "casehub_maestro_fab_enabled": False,
            "demo_mode": False,
        }
    )
    templates.env.filters["format_currency"] = _format_currency
    return templates


def _format_currency(value, currency="BRL") -> str:
    symbols = {"BRL": "R$", "USD": "$", "EUR": "EUR", "GBP": "GBP"}
    symbol = symbols.get(currency or "BRL", currency or "BRL")
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if currency == "BRL":
        return f"{symbol} {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{symbol}{amount:,.2f}"


def reset_cache_dir(cache_dir: Path) -> None:
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)


def cache_files(cache_dir: Path) -> list[Path]:
    return sorted(cache_dir.glob("__jinja2_*.cache"))


def render_dashboard(templates: Jinja2Templates, template_name: str, context: dict) -> str:
    return templates.env.get_template(template_name).render(context)


def run_smoke(requests: int, cache_dir: Path, template_name: str, product: str) -> int:
    reset_cache_dir(cache_dir)
    templates = build_templates(cache_dir, product=product)
    context = build_dashboard_context(product=product)

    started = time.perf_counter()
    bytes_rendered = 0
    for _ in range(requests):
        templates.env.cache.clear()
        bytes_rendered += len(render_dashboard(templates, template_name, context).encode("utf-8"))
    elapsed_ms = (time.perf_counter() - started) * 1000
    files = cache_files(cache_dir)

    print(f"template={template_name}")
    print(f"product={product}")
    print(f"renders={requests}")
    print(f"elapsed_ms={elapsed_ms:.2f}")
    print(f"bytes_rendered={bytes_rendered}")
    print(f"cache_dir={cache_dir}")
    print(f"cache_files={len(files)}")
    for path in files[:10]:
        print(f"cache_file={path.name}")

    if not files:
        print("ERROR: no __jinja2_*.cache files were created", file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/casehub-jinja-smoke"))
    parser.add_argument("--template", default="dashboard.html")
    parser.add_argument("--product", choices=("lite", "immigration"), default="lite")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_smoke(args.requests, args.cache_dir, args.template, args.product)


if __name__ == "__main__":
    raise SystemExit(main())
