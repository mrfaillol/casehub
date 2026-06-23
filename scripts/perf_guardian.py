#!/usr/bin/env python3
"""
CaseHub Performance Guardian.

Safe lanes:
  - benchmark: authenticated route timing with stable JSON output
  - seed: create/reset the synthetic perf-bench-dev tenant in non-production envs
  - cleanup: inventory or remove only trusted synthetic benchmark data
  - markdown: render a report summary from JSON
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx


SCHEMA_VERSION = "casehub-performance-guardian.v1"
DEFAULT_TENANT = "perf-bench-dev"
DEFAULT_EMAIL = "perf-bench@casehub.local"
DEFAULT_PASSWORD = "perf-bench-dev-only"
MANAGED_BY = "casehub-performance-guardian"
ISSUE_URL = "https://github.com/mrfaillol/casehub/issues"


ROUTES = [
    {"name": "dashboard", "path": "/casehub/dashboard", "size_budget_bytes": 350_000},
    {"name": "clients", "path": "/casehub/clients", "size_budget_bytes": 350_000},
    {"name": "cases", "path": "/casehub/cases", "size_budget_bytes": 350_000},
    {"name": "tasks", "path": "/casehub/tasks", "size_budget_bytes": 350_000},
    {"name": "tasks-kanban", "path": "/casehub/tasks/kanban", "size_budget_bytes": 900_000},
    {"name": "calendar", "path": "/casehub/calendar", "size_budget_bytes": 350_000},
    {"name": "controladoria", "path": "/casehub/controladoria", "size_budget_bytes": 900_000},
    {"name": "leads-dashboard", "path": "/casehub/leads/dashboard", "size_budget_bytes": 650_000},
]


PROFILES = {
    "readme-min-current": {
        "cpu_cores": 2,
        "ram_gb": 4,
        "disk_gb": 20,
        "concurrent_users": 5,
        "clients": 500,
        "cases": 1000,
        "tasks": 2500,
        "appointments": 300,
        "prazos": 1000,
        "leads": 500,
    },
    "growth": {
        "cpu_cores": 4,
        "ram_gb": 8,
        "disk_gb": 50,
        "concurrent_users": 10,
        "clients": 2000,
        "cases": 5000,
        "tasks": 12000,
        "appointments": 1200,
        "prazos": 5000,
        "leads": 2500,
    },
    "basic-floor-candidate": {
        "cpu_cores": 1,
        "ram_gb": 2,
        "disk_gb": 20,
        "concurrent_users": 3,
        "clients": 250,
        "cases": 500,
        "tasks": 1250,
        "appointments": 150,
        "prazos": 500,
        "leads": 250,
    },
}


BUDGETS = {
    "ttfb_p95_ms": 800,
    "total_p95_ms": 2500,
    "timeout_ms": 8000,
}


@dataclass(frozen=True)
class RouteSample:
    status_code: int
    total_ms: float
    ttfb_ms: float
    bytes: int
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "total_ms": round(self.total_ms, 2),
            "ttfb_ms": round(self.ttfb_ms, 2),
            "bytes": self.bytes,
            "error": self.error,
        }


def percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = math.ceil((p / 100) * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def summarize_samples(samples: list[RouteSample], size_budget_bytes: int) -> dict[str, Any]:
    successful = [sample for sample in samples if not sample.error]
    totals = [sample.total_ms for sample in successful]
    ttfbs = [sample.ttfb_ms for sample in successful]
    sizes = [sample.bytes for sample in successful]
    statuses: dict[str, int] = {}
    for sample in samples:
        statuses[str(sample.status_code)] = statuses.get(str(sample.status_code), 0) + 1

    errors = [sample.error for sample in samples if sample.error]
    summary = {
        "count": len(samples),
        "errors": len(errors),
        "status_codes": statuses,
        "total_ms": {
            "avg": round(statistics.mean(totals), 2) if totals else None,
            "p50": round(percentile(totals, 50), 2) if totals else None,
            "p95": round(percentile(totals, 95), 2) if totals else None,
            "p99": round(percentile(totals, 99), 2) if totals else None,
            "max": round(max(totals), 2) if totals else None,
        },
        "ttfb_ms": {
            "avg": round(statistics.mean(ttfbs), 2) if ttfbs else None,
            "p50": round(percentile(ttfbs, 50), 2) if ttfbs else None,
            "p95": round(percentile(ttfbs, 95), 2) if ttfbs else None,
            "p99": round(percentile(ttfbs, 99), 2) if ttfbs else None,
            "max": round(max(ttfbs), 2) if ttfbs else None,
        },
        "bytes": {
            "avg": round(statistics.mean(sizes), 2) if sizes else None,
            "max": max(sizes) if sizes else None,
            "budget": size_budget_bytes,
        },
        "error_messages": sorted({error for error in errors if error}),
    }
    summary["verdict"] = route_verdict(summary)
    return summary


def route_verdict(summary: dict[str, Any]) -> dict[str, Any]:
    failures = []
    if summary["errors"]:
        failures.append(f"{summary['errors']} request(s) errored")

    ttfb_p95 = summary["ttfb_ms"]["p95"]
    total_p95 = summary["total_ms"]["p95"]
    max_bytes = summary["bytes"]["max"]
    size_budget = summary["bytes"]["budget"]

    if ttfb_p95 is not None and ttfb_p95 > BUDGETS["ttfb_p95_ms"]:
        failures.append(f"ttfb_p95_ms {ttfb_p95} > {BUDGETS['ttfb_p95_ms']}")
    if total_p95 is not None and total_p95 > BUDGETS["total_p95_ms"]:
        failures.append(f"total_p95_ms {total_p95} > {BUDGETS['total_p95_ms']}")
    if max_bytes is not None and max_bytes > size_budget:
        failures.append(f"bytes {max_bytes} > {size_budget}")

    return {"status": "fail" if failures else "pass", "failures": failures}


def overall_verdict(route_reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures = []
    for route in route_reports:
        for failure in route["summary"]["verdict"]["failures"]:
            failures.append(f"{route['name']}: {failure}")
    return {"status": "fail" if failures else "pass", "failures": failures}


def suggestions_for(route_reports: list[dict[str, Any]]) -> list[str]:
    suggestions = []
    for route in route_reports:
        summary = route["summary"]
        name = route["name"]
        if summary["errors"]:
            suggestions.append(f"{name}: inspect route errors/timeouts before tuning")
        if (summary["ttfb_ms"]["p95"] or 0) > BUDGETS["ttfb_p95_ms"]:
            suggestions.append(f"{name}: profile server-side DB/Jinja/auth path")
        if (summary["total_ms"]["p95"] or 0) > BUDGETS["total_p95_ms"]:
            suggestions.append(f"{name}: inspect end-to-end transfer and blocking dependencies")
        if summary["bytes"]["max"] and summary["bytes"]["max"] > summary["bytes"]["budget"]:
            suggestions.append(f"{name}: reduce initial HTML/asset payload or move heavy data to async API")
    return sorted(set(suggestions))


def fetch_health_sha(client: httpx.Client, base_url: str, fallback: str) -> str:
    for path in ("/casehub/healthz", "/api/health"):
        try:
            response = client.get(f"{base_url}{path}", timeout=5)
            if response.status_code == 200:
                payload = response.json()
                commit = payload.get("commit")
                if commit:
                    return commit
        except Exception:
            continue
    return fallback


def authenticate(client: httpx.Client, base_url: str, email: str, password: str) -> str:
    response = client.post(
        f"{base_url}/casehub/login",
        data={"email": email, "password": password},
        follow_redirects=False,
        timeout=10,
    )
    if response.status_code in (302, 303):
        return "form"

    response = client.post(
        f"{base_url}/casehub/api/v1/auth/login",
        data={"email": email, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if token:
        client.cookies.set("casehub_token", token)
    return "api"


def measure_route(client: httpx.Client, url: str, timeout_seconds: float) -> RouteSample:
    start = time.perf_counter()
    try:
        with client.stream("GET", url, follow_redirects=True, timeout=timeout_seconds) as response:
            first_byte = None
            size = 0
            for chunk in response.iter_bytes():
                if first_byte is None:
                    first_byte = time.perf_counter()
                size += len(chunk)
            end = time.perf_counter()
            if first_byte is None:
                first_byte = end
            return RouteSample(
                status_code=response.status_code,
                total_ms=(end - start) * 1000,
                ttfb_ms=(first_byte - start) * 1000,
                bytes=size,
            )
    except Exception as exc:
        end = time.perf_counter()
        return RouteSample(
            status_code=0,
            total_ms=(end - start) * 1000,
            ttfb_ms=(end - start) * 1000,
            bytes=0,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    profile = PROFILES[args.profile]
    timeout_seconds = args.timeout_ms / 1000
    route_reports = []

    with httpx.Client(verify=not args.insecure, headers={"User-Agent": "casehub-performance-guardian/1.0"}) as client:
        auth_method = None
        if args.email and args.password:
            auth_method = authenticate(client, base_url, args.email, args.password)
        sha = args.sha or fetch_health_sha(client, base_url, "unknown")

        for route in ROUTES:
            if args.route and route["name"] not in args.route:
                continue
            samples = [
                measure_route(client, f"{base_url}{route['path']}", timeout_seconds)
                for _ in range(args.repeat)
            ]
            route_reports.append({
                "name": route["name"],
                "path": route["path"],
                "samples": [sample.as_dict() for sample in samples],
                "summary": summarize_samples(samples, route["size_budget_bytes"]),
            })

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "issue": ISSUE_URL,
        "sha": sha,
        "environment": {
            "name": args.environment,
            "base_url": base_url,
            "auth_method": auth_method,
        },
        "tenant": {
            "slug": args.tenant,
            "synthetic": args.tenant == DEFAULT_TENANT,
        },
        "profile": {
            "name": args.profile,
            **profile,
        },
        "budgets": BUDGETS,
        "routes": route_reports,
        "database": {
            "enabled": False,
            "reason": "query/EXPLAIN capture is performed on the Oracle dev runner with DB access",
        },
        "assets": {
            "enabled": False,
            "reason": "static budget checks run in scripts/perf_guardian_static_check.py",
        },
        "browser": {
            "enabled": False,
            "reason": "browser screenshots/Lighthouse run in the Oracle dev nightly lane",
        },
        "verdict": overall_verdict(route_reports),
        "suggestions": suggestions_for(route_reports),
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def require_non_production(target: str) -> None:
    if target == "production":
        raise SystemExit("Refusing production target. Performance Guardian never mutates production target.")


def ensure_project_root_on_path() -> None:
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def lazy_db_imports():
    ensure_project_root_on_path()
    from sqlalchemy import inspect, text
    from models import Case, Client, Organization, Reminder, Task, User
    from models.base import SessionLocal

    return {
        "Case": Case,
        "Client": Client,
        "Organization": Organization,
        "Reminder": Reminder,
        "Task": Task,
        "User": User,
        "SessionLocal": SessionLocal,
        "inspect": inspect,
        "text": text,
    }


def lazy_leads_imports():
    ensure_project_root_on_path()
    from services import leads_manager

    return {
        "load_leads": leads_manager.load_leads,
        "save_leads": leads_manager.save_leads,
        "rebuild_indexes": leads_manager.rebuild_indexes,
        "STAGES_BR": leads_manager.STAGES_BR,
        "LEADS_FILE": leads_manager.LEADS_FILE,
    }


def table_exists(db, name: str, inspect_fn) -> bool:
    return inspect_fn(db.bind).has_table(name)


def table_columns(db, name: str, inspect_fn) -> set[str]:
    return {column["name"] for column in inspect_fn(db.bind).get_columns(name)}


def is_guardian_owned_mapping(value: Any) -> bool:
    return isinstance(value, dict) and value.get("managed_by") == MANAGED_BY


def is_perf_lead_marker(lead_id: str, lead: dict[str, Any]) -> bool:
    email = str(lead.get("email") or "")
    guardian_owned = (
        lead.get("managed_by") == MANAGED_BY
        or lead.get("source_detail") == MANAGED_BY
        or lead.get("indicado_por") == MANAGED_BY
    )
    return (
        guardian_owned
        and (
            lead.get("perf_bench") is True
            or lead.get("benchmark_tenant") == DEFAULT_TENANT
            or lead_id.startswith("perf-bench-")
            or email.endswith("@perf-bench.local")
        )
    )


def lead_status_from_score(score: int) -> str:
    if score >= 80:
        return "hot"
    if score >= 55:
        return "qualified"
    if score >= 30:
        return "warm"
    return "cold"


def load_perf_leads_inventory() -> dict[str, Any]:
    imports = lazy_leads_imports()
    data = imports["load_leads"]()
    perf_ids = [
        lead_id
        for lead_id, lead in (data.get("leads") or {}).items()
        if is_perf_lead_marker(lead_id, lead)
    ]
    return {
        "count": len(perf_ids),
        "ids": perf_ids,
        "file": str(imports["LEADS_FILE"]),
    }


def remove_perf_leads() -> dict[str, Any]:
    imports = lazy_leads_imports()
    data = imports["load_leads"]()
    leads = data.setdefault("leads", {})
    deleted_ids = [
        lead_id
        for lead_id, lead in list(leads.items())
        if is_perf_lead_marker(lead_id, lead)
    ]
    for lead_id in deleted_ids:
        del leads[lead_id]
    imports["rebuild_indexes"](data)
    if deleted_ids:
        imports["save_leads"](data)
    return {
        "leads_crm": len(deleted_ids),
        "leads_file": str(imports["LEADS_FILE"]),
    }


def seed_perf_leads(count: int) -> dict[str, Any]:
    removed = remove_perf_leads()
    imports = lazy_leads_imports()
    data = imports["load_leads"]()
    leads = data.setdefault("leads", {})
    stages = list(imports["STAGES_BR"].keys()) or ["PROSPECCAO", "CONSULTA", "PROPOSTA"]
    statuses = ["new", "contacted", "qualified", "converted", "lost"]
    now = datetime.now().isoformat()
    for i in range(count):
        lead_id = f"perf-bench-{i:05d}"
        score = (i * 17) % 100
        stage = stages[i % len(stages)]
        phone = f"+5532988{i % 100000:05d}"
        email = f"lead-{i:05d}@perf-bench.local"
        name = f"Perf Lead {i:05d}"
        leads[lead_id] = {
            "id": lead_id,
            "created_at": now,
            "updated_at": now,
            "name": name,
            "display_name": name,
            "phone": phone,
            "email": email,
            "whatsapp_name": name,
            "language": "pt-BR",
            "source": "MANUAL",
            "source_detail": MANAGED_BY,
            "utm_source": "perf-bench",
            "utm_medium": "synthetic",
            "utm_campaign": DEFAULT_TENANT,
            "pipeline_stage": stage,
            "status": statuses[i % len(statuses)],
            "lead_status": lead_status_from_score(score),
            "conversation_state": "benchmark",
            "lead_score": score,
            "score_factors": ["synthetic", "perf-bench"],
            "visa_interest": "",
            "profession": ["advogado", "empresario", "autonomo"][i % 3],
            "is_urgent": i % 13 == 0,
            "message_count": (i % 8) + 1,
            "last_message_at": now,
            "first_contact_at": now,
            "notes": "perf-bench synthetic CRM lead; safe to delete",
            "communication_log": [
                {
                    "type": "system",
                    "message": "Synthetic benchmark lead generated by CaseHub Performance Guardian.",
                    "timestamp": now,
                }
            ],
            "moskit_contact_id": None,
            "moskit_deal_id": None,
            "moskit_sent": False,
            "moskit_stage_id": None,
            "notion_page_id": None,
            "notion_synced": False,
            "assigned_to": None,
            "auto_registered": False,
            "tags": ["perf-bench", "synthetic"],
            "is_deleted": False,
            "area_atuacao": ["civel", "trabalhista", "previdenciario"][i % 3],
            "valor_causa": str(5000 + (i % 250) * 100),
            "comarca": "Juiz de Fora",
            "indicado_por": MANAGED_BY,
            "perf_bench": True,
            "benchmark_tenant": DEFAULT_TENANT,
            "managed_by": MANAGED_BY,
        }
    imports["rebuild_indexes"](data)
    imports["save_leads"](data)
    return {
        "leads_crm": count,
        "deleted_before_seed": removed["leads_crm"],
        "leads_file": str(imports["LEADS_FILE"]),
    }


def ensure_perf_org(db, imports: dict[str, Any]):
    Organization = imports["Organization"]
    org = db.query(Organization).filter(Organization.slug == DEFAULT_TENANT).first()
    if org:
        settings = org.settings or {}
        if not (is_guardian_owned_mapping(settings) and settings.get("perf_bench") is True):
            raise RuntimeError(
                f"Refusing to use existing organization slug={DEFAULT_TENANT!r} "
                f"without perf_bench/managed_by markers"
            )
        return org
    org = Organization(
        uuid=str(uuid.uuid5(uuid.NAMESPACE_DNS, DEFAULT_TENANT)),
        name="CaseHub Performance Benchmark",
        slug=DEFAULT_TENANT,
        email=DEFAULT_EMAIL,
        timezone="America/Sao_Paulo",
        locale="pt-BR",
        currency="BRL",
        case_prefix="PERF",
        plan="enterprise",
        max_users=20,
        max_clients=999999,
        features={
            "crm": True,
            "tasks": True,
            "calendar": True,
            "controladoria": True,
            "performance_benchmark": True,
        },
        settings={"perf_bench": True, "managed_by": MANAGED_BY},
        is_active=True,
    )
    db.add(org)
    db.flush()
    return org


def reset_perf_tenant(db, org_id: int, imports: dict[str, Any]) -> dict[str, int]:
    text = imports["text"]
    inspect_fn = imports["inspect"]
    deleted: dict[str, int] = {}
    raw_tables = ["prazos_processuais", "appointments"]
    for table in raw_tables:
        if table_exists(db, table, inspect_fn):
            result = db.execute(text(f"DELETE FROM {table} WHERE org_id = :org_id"), {"org_id": org_id})
            deleted[table] = result.rowcount or 0

    # ORM tables in dependency order.
    for model_name in ["Reminder", "Task", "Case", "Client", "User"]:
        model = imports[model_name]
        query = db.query(model).filter(model.org_id == org_id)
        deleted[model.__tablename__] = query.delete(synchronize_session=False)
    db.flush()
    return deleted


def seed_perf_tenant(args: argparse.Namespace) -> dict[str, Any]:
    require_non_production(args.target)
    imports = lazy_db_imports()
    SessionLocal = imports["SessionLocal"]
    Client = imports["Client"]
    Case = imports["Case"]
    Task = imports["Task"]
    Reminder = imports["Reminder"]
    User = imports["User"]
    text = imports["text"]
    inspect_fn = imports["inspect"]
    profile = PROFILES[args.profile]

    db = SessionLocal()
    try:
        org = ensure_perf_org(db, imports)
        deleted = reset_perf_tenant(db, org.id, imports) if args.reset else {}

        user = db.query(User).filter(User.email == DEFAULT_EMAIL).first()
        if user:
            if user.org_id != org.id:
                raise RuntimeError(
                    f"Refusing to modify existing benchmark email outside org_id={org.id}"
                )
            user.org_id = org.id
            user.password_hash = User.hash_password(DEFAULT_PASSWORD)
            user.enabled = True
            user.must_change_password = False
        else:
            user = User(
                org_id=org.id,
                email=DEFAULT_EMAIL,
                name="Performance Benchmark",
                password_hash=User.hash_password(DEFAULT_PASSWORD),
                user_type="admin",
                enabled=True,
                must_change_password=False,
                ui_theme="neuromorphic",
                oab_number="MG PERF",
            )
            db.add(user)
        db.flush()

        clients = []
        for i in range(profile["clients"]):
            clients.append(Client(
                org_id=org.id,
                first_name="Perf",
                last_name=f"Cliente {i:04d}",
                email=f"cliente-{i:04d}@perf-bench.local",
                phone=f"+5532999{i % 10000:04d}",
                whatsapp=f"+5532999{i % 10000:04d}",
                client_number=f"PERF-CLIENT-{i:04d}",
                cpf=f"000000{i % 100000:05d}",
                city="Juiz de Fora",
                state="MG",
                nationality="Brasileira",
                client_type="individual",
                status="active",
                notes="perf-bench synthetic client; safe to delete",
            ))
        db.bulk_save_objects(clients)
        db.flush()
        client_rows = db.query(Client).filter(Client.org_id == org.id).order_by(Client.id).all()

        cases = []
        for i in range(profile["cases"]):
            client = client_rows[i % len(client_rows)]
            cases.append(Case(
                org_id=org.id,
                client_id=client.id,
                case_number=f"PERF-BENCH-{i:06d}",
                case_name=f"Perf Bench Processo {i:06d}",
                status=["intake", "active", "pending", "closed"][i % 4],
                priority=["low", "medium", "high", "urgent"][i % 4],
                area_of_practice=["civel", "trabalhista", "previdenciario"][i % 3],
                numero_processo=f"500{i:07d}-00.2026.8.13.0000",
                tipo_acao=["Cobranca", "Reclamacao trabalhista", "Beneficio previdenciario"][i % 3],
                vara=f"{(i % 5) + 1}a Vara",
                comarca="Juiz de Fora",
                tribunal=["TJMG", "TRT3", "TRF6"][i % 3],
                fase_processual=["conhecimento", "instrucao", "recurso", "cumprimento"][i % 4],
                notes="perf-bench synthetic case; safe to delete",
            ))
        db.bulk_save_objects(cases)
        db.flush()
        case_rows = db.query(Case).filter(Case.org_id == org.id).order_by(Case.id).all()

        today = date.today()
        tasks = []
        for i in range(profile["tasks"]):
            case = case_rows[i % len(case_rows)]
            client = client_rows[i % len(client_rows)]
            tasks.append(Task(
                org_id=org.id,
                title=f"perf-bench tarefa {i:05d}",
                description="Synthetic cumulative benchmark task; safe to delete.",
                task_type=["prazo", "follow_up", "review", "filing"][i % 4],
                status=["pending", "in_progress", "blocked", "completed"][i % 4],
                priority=["low", "medium", "high", "urgent"][i % 4],
                position=i,
                column_id=(i % 5) + 1,
                client_id=client.id,
                case_id=case.id,
                assigned_to=user.id,
                tags="perf-bench,synthetic",
                estimated_hours=float((i % 6) + 1),
                due_date=today + timedelta(days=(i % 45) - 10),
            ))
        db.bulk_save_objects(tasks)

        reminders = []
        for i in range(min(profile["appointments"], 500)):
            case = case_rows[i % len(case_rows)]
            client = client_rows[i % len(client_rows)]
            reminders.append(Reminder(
                org_id=org.id,
                title=f"perf-bench compromisso {i:04d}",
                description="Synthetic reminder for benchmark.",
                reminder_type="meeting",
                client_id=client.id,
                case_id=case.id,
                due_date=datetime.combine(today + timedelta(days=i % 30), datetime.min.time()),
                is_completed=False,
            ))
        db.bulk_save_objects(reminders)
        db.flush()

        raw_inserted = {}
        if table_exists(db, "appointments", inspect_fn):
            appointment_columns = table_columns(db, "appointments", inspect_fn)
            insert_columns = [
                "org_id",
                "title",
                "type",
                "assigned_to",
                "client_name",
                "case_id",
                "date",
                "time_start",
                "time_end",
                "is_virtual",
                "notes",
                "created_by",
            ]
            insert_columns = [column for column in insert_columns if column in appointment_columns]
            rows = []
            for i in range(profile["appointments"]):
                case = case_rows[i % len(case_rows)]
                client = client_rows[i % len(client_rows)]
                row = {
                    "org_id": org.id,
                    "title": f"perf-bench agenda {i:04d}",
                    "type": ["atendimento", "audiencia", "reuniao"][i % 3],
                    "assigned_to": user.id,
                    "client_name": client.full_name,
                    "case_id": case.id,
                    "date": today + timedelta(days=i % 30),
                    "time_start": "09:00",
                    "time_end": "10:00",
                    "is_virtual": i % 2 == 0,
                    "notes": "perf-bench synthetic appointment; safe to delete",
                    "created_by": user.id,
                }
                rows.append({column: row[column] for column in insert_columns})
            placeholders = ", ".join(f":{column}" for column in insert_columns)
            db.execute(
                text(f"INSERT INTO appointments ({', '.join(insert_columns)}) VALUES ({placeholders})"),
                rows,
            )
            raw_inserted["appointments"] = len(rows)

        if table_exists(db, "prazos_processuais", inspect_fn):
            rows = []
            for i in range(profile["prazos"]):
                case = case_rows[i % len(case_rows)]
                start = today - timedelta(days=i % 20)
                rows.append({
                    "case_id": case.id,
                    "org_id": org.id,
                    "tipo": ["contestacao", "recurso", "embargos", "manifestacao"][i % 4],
                    "data_intimacao": start,
                    "data_inicio": start + timedelta(days=1),
                    "data_vencimento": today + timedelta(days=(i % 45) - 8),
                    "dias_prazo": [5, 10, 15, 30][i % 4],
                    "responsavel": user.name,
                    "status": ["pendente", "em_andamento", "concluido"][i % 3],
                    "descricao": f"perf-bench prazo processual {i:05d}",
                    "uf": "MG",
                    "dobro": i % 7 == 0,
                })
            db.execute(text("""
                INSERT INTO prazos_processuais
                    (case_id, org_id, tipo, data_intimacao, data_inicio, data_vencimento,
                     dias_prazo, responsavel, status, descricao, uf, dobro)
                VALUES
                    (:case_id, :org_id, :tipo, :data_intimacao, :data_inicio, :data_vencimento,
                     :dias_prazo, :responsavel, :status, :descricao, :uf, :dobro)
            """), rows)
            raw_inserted["prazos_processuais"] = len(rows)

        db.commit()
        leads_inserted = seed_perf_leads(profile["leads"])
        result = {
            "schema_version": SCHEMA_VERSION,
            "action": "seed",
            "target": args.target,
            "tenant": DEFAULT_TENANT,
            "org_id": org.id,
            "profile": args.profile,
            "deleted_before_seed": deleted,
            "inserted": {
                "users": 1,
                "clients": len(client_rows),
                "cases": len(case_rows),
                "tasks": profile["tasks"],
                "reminders": len(reminders),
                "leads_crm": leads_inserted["leads_crm"],
                **raw_inserted,
            },
            "leads_crm": leads_inserted,
            "login": {"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD},
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return result
    finally:
        db.close()


def cleanup_inventory(args: argparse.Namespace) -> dict[str, Any]:
    imports = lazy_db_imports()
    SessionLocal = imports["SessionLocal"]
    Organization = imports["Organization"]
    text = imports["text"]
    inspect_fn = imports["inspect"]
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == DEFAULT_TENANT).first()
        org_id = org.id if org else None
        counts = {}
        if org_id:
            for model_name in ["User", "Client", "Case", "Task", "Reminder"]:
                model = imports[model_name]
                counts[model.__tablename__] = db.query(model).filter(model.org_id == org_id).count()
            for table in ["appointments", "prazos_processuais"]:
                if table_exists(db, table, inspect_fn):
                    counts[table] = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE org_id = :org_id"), {"org_id": org_id}).scalar() or 0

        marker_counts = {
            "clients_benchmark_user": db.execute(text(
                "SELECT COUNT(*) FROM clients WHERE first_name = 'BenchmarkUser' OR email LIKE '%@test.local'"
            )).scalar() if table_exists(db, "clients", inspect_fn) else 0,
            "clients_perf_bench": db.execute(text(
                "SELECT COUNT(*) FROM clients WHERE email LIKE '%@perf-bench.local' OR notes LIKE '%perf-bench%'"
            )).scalar() if table_exists(db, "clients", inspect_fn) else 0,
        }
        leads_inventory = load_perf_leads_inventory()
        result = {
            "schema_version": SCHEMA_VERSION,
            "action": "cleanup-inventory",
            "tenant": DEFAULT_TENANT,
            "org_id": org_id,
            "counts": counts,
            "marker_counts": marker_counts,
            "leads_crm": leads_inventory,
            "dry_run": True,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return result
    finally:
        db.close()


def cleanup_apply(args: argparse.Namespace) -> dict[str, Any]:
    require_non_production(args.target)
    if args.confirm != DEFAULT_TENANT:
        raise SystemExit(f"Refusing cleanup without --confirm {DEFAULT_TENANT}")
    imports = lazy_db_imports()
    SessionLocal = imports["SessionLocal"]
    Organization = imports["Organization"]
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == DEFAULT_TENANT).first()
        if not org:
            result = {
                "schema_version": SCHEMA_VERSION,
                "action": "cleanup-apply",
                "tenant": DEFAULT_TENANT,
                "deleted": {"leads_crm": remove_perf_leads()["leads_crm"]},
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return result
        deleted = reset_perf_tenant(db, org.id, imports)
        db.delete(org)
        deleted["organizations"] = 1
        db.commit()
        deleted["leads_crm"] = remove_perf_leads()["leads_crm"]
        result = {"schema_version": SCHEMA_VERSION, "action": "cleanup-apply", "tenant": DEFAULT_TENANT, "org_id": org.id, "deleted": deleted}
        print(json.dumps(result, indent=2, sort_keys=True))
        return result
    finally:
        db.close()


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## CaseHub Performance Guardian",
        "",
        f"- Target: `{report['environment']['base_url']}`",
        f"- SHA: `{report['sha']}`",
        f"- Tenant: `{report['tenant']['slug']}`",
        f"- Profile: `{report['profile']['name']}`",
        f"- Verdict: **{report['verdict']['status'].upper()}**",
        "",
        "### Routes",
        "",
        "| Route | Status | TTFB p95 | Total p95 | Max bytes |",
        "|---|---:|---:|---:|---:|",
    ]
    for route in report["routes"]:
        summary = route["summary"]
        lines.append(
            f"| `{route['path']}` | {summary['verdict']['status']} | "
            f"{summary['ttfb_ms']['p95']} | {summary['total_ms']['p95']} | {summary['bytes']['max']} |"
        )
    if report["suggestions"]:
        lines.extend(["", "### Suggested next actions", ""])
        lines.extend(f"- {item}" for item in report["suggestions"])
    return "\n".join(lines) + "\n"


def command_markdown(args: argparse.Namespace) -> str:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    markdown = render_markdown(report)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    print(markdown)
    return markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CaseHub Performance Guardian")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("benchmark", help="Run authenticated route benchmark")
    bench.add_argument("--base-url", required=True)
    bench.add_argument("--environment", default="dev")
    bench.add_argument("--tenant", default=DEFAULT_TENANT)
    bench.add_argument("--profile", choices=sorted(PROFILES), default="readme-min-current")
    bench.add_argument("--email", default=os.getenv("CASEHUB_PERF_EMAIL", DEFAULT_EMAIL))
    bench.add_argument("--password", default=os.getenv("CASEHUB_PERF_PASSWORD", DEFAULT_PASSWORD))
    bench.add_argument("--repeat", type=int, default=3)
    bench.add_argument("--timeout-ms", type=int, default=BUDGETS["timeout_ms"])
    bench.add_argument("--route", action="append", help="Route name to include; may repeat")
    bench.add_argument("--sha", default="")
    bench.add_argument("--output")
    bench.add_argument("--insecure", action="store_true")
    bench.set_defaults(func=run_benchmark)

    seed = sub.add_parser("seed", help="Create/reset synthetic performance tenant")
    seed.add_argument("--target", choices=["local", "dev", "snapshot", "production"], default="local")
    seed.add_argument("--profile", choices=sorted(PROFILES), default="readme-min-current")
    seed.add_argument("--reset", action="store_true", help="Delete existing perf-bench-dev tenant data first")
    seed.set_defaults(func=seed_perf_tenant)

    cleanup = sub.add_parser("cleanup", help="Inventory or remove synthetic benchmark tenant")
    cleanup.add_argument("--target", choices=["local", "dev", "snapshot", "production"], default="local")
    cleanup.add_argument("--apply", action="store_true")
    cleanup.add_argument("--confirm", default="")
    cleanup.set_defaults(func=lambda args: cleanup_apply(args) if args.apply else cleanup_inventory(args))

    md = sub.add_parser("markdown", help="Render markdown summary from benchmark JSON")
    md.add_argument("report")
    md.add_argument("--output")
    md.set_defaults(func=command_markdown)
    return parser


def main(argv: list[str] | None = None) -> Any:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    main()
