#!/usr/bin/env python3
"""
CaseHub - Demo Seed Script
Creates a demo organization with sample data for testing/demos.

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --product lite
    python scripts/seed_demo.py --product immigration
"""
import argparse
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import get_db, init_db, User, Client, Case, Task, Document, BillingItem, TimeEntry
from models.tenant import Organization, get_org_by_slug


# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

IMMIGRATION_CLIENTS = [
    {"first_name": "Maria", "last_name": "Santos", "email": "maria.santos@example.com",
     "phone": "+1-305-555-0101", "country_of_origin": "Brazil", "status": "active"},
    {"first_name": "James", "last_name": "Chen", "email": "james.chen@example.com",
     "phone": "+1-415-555-0202", "country_of_origin": "China", "status": "active"},
    {"first_name": "Priya", "last_name": "Sharma", "email": "priya.sharma@example.com",
     "phone": "+1-212-555-0303", "country_of_origin": "India", "status": "active"},
    {"first_name": "Ahmed", "last_name": "Hassan", "email": "ahmed.hassan@example.com",
     "phone": "+1-713-555-0404", "country_of_origin": "Egypt", "status": "active"},
    {"first_name": "Elena", "last_name": "Petrova", "email": "elena.petrova@example.com",
     "phone": "+1-312-555-0505", "country_of_origin": "Russia", "status": "active"},
]

LITE_CLIENTS = [
    {"first_name": "Carlos", "last_name": "Oliveira", "email": "carlos.oliveira@exemplo.com",
     "phone": "(32) 99100-1001", "cpf": "123.456.789-00", "city": "Juiz de Fora",
     "state": "MG", "status": "active"},
    {"first_name": "Ana", "last_name": "Souza", "email": "ana.souza@exemplo.com",
     "phone": "(32) 99100-2002", "cpf": "987.654.321-00", "city": "Juiz de Fora",
     "state": "MG", "status": "active"},
    {"first_name": "Pedro", "last_name": "Mendes", "email": "pedro.mendes@exemplo.com",
     "phone": "(21) 99100-3003", "cpf": "456.789.123-00", "city": "Rio de Janeiro",
     "state": "RJ", "status": "active"},
    {"first_name": "Mariana", "last_name": "Costa", "email": "mariana.costa@exemplo.com",
     "phone": "(11) 99100-4004", "cpf": "321.654.987-00", "city": "Sao Paulo",
     "state": "SP", "status": "active"},
    {"first_name": "Rafael", "last_name": "Ferreira", "email": "rafael.ferreira@exemplo.com",
     "phone": "(31) 99100-5005", "cpf": "654.321.987-00", "city": "Belo Horizonte",
     "state": "MG", "status": "active"},
]

IMMIGRATION_CASES = [
    {"case_name": "Santos - H-1B Petition", "visa_type": "H-1B",
     "status": "intake", "priority": "high",
     "receipt_number": "EAC-26-001-12345", "jurisdiction": "Vermont Service Center",
     "notes": "Software engineer, employer: TechCorp Inc."},
    {"case_name": "Chen - EB-1A Extraordinary Ability", "visa_type": "EB-1A",
     "status": "in_progress", "priority": "medium",
     "receipt_number": "SRC-26-002-67890", "jurisdiction": "Texas Service Center",
     "filing_date": date.today() - timedelta(days=45),
     "notes": "AI researcher with 50+ publications."},
    {"case_name": "Sharma - L-1A Intracompany Transfer", "visa_type": "L-1A",
     "status": "approved", "priority": "low",
     "receipt_number": "WAC-25-003-11111", "jurisdiction": "California Service Center",
     "filing_date": date.today() - timedelta(days=180),
     "notes": "VP of Engineering, multinational company."},
]

LITE_CASES = [
    {"case_name": "Oliveira vs. Banco Nacional S.A.", "status": "intake",
     "priority": "high", "area_of_practice": "Consumidor",
     "numero_processo": "5001234-56.2026.8.13.0145",
     "tipo_acao": "Acao de Indenizacao", "vara": "1a Vara Civel",
     "comarca": "Juiz de Fora", "tribunal": "TJMG",
     "fase_processual": "Conhecimento",
     "polo_ativo": "Carlos Oliveira", "polo_passivo": "Banco Nacional S.A.",
     "notes": "Cobranca indevida em cartao de credito."},
    {"case_name": "Souza - Divorcio Consensual", "status": "in_progress",
     "priority": "medium", "area_of_practice": "Familia",
     "numero_processo": "5005678-90.2026.8.13.0145",
     "tipo_acao": "Divorcio Consensual", "vara": "2a Vara de Familia",
     "comarca": "Juiz de Fora", "tribunal": "TJMG",
     "fase_processual": "Instrucao",
     "polo_ativo": "Ana Souza", "polo_passivo": "Marcos Souza",
     "notes": "Partilha de bens e guarda compartilhada."},
    {"case_name": "Mendes - Reclamacao Trabalhista", "status": "completed",
     "priority": "low", "area_of_practice": "Trabalhista",
     "numero_processo": "0001234-56.2025.5.01.0001",
     "tipo_acao": "Reclamacao Trabalhista", "vara": "1a Vara do Trabalho",
     "comarca": "Rio de Janeiro", "tribunal": "TRT-1",
     "fase_processual": "Transitado em Julgado",
     "polo_ativo": "Pedro Mendes", "polo_passivo": "Empresa XYZ Ltda.",
     "filing_date": date.today() - timedelta(days=300),
     "notes": "Verbas rescisorias e FGTS."},
]

IMMIGRATION_TASKS = [
    {"title": "Collect Santos passport copy", "task_type": "document_collection",
     "status": "pending", "priority": "high",
     "due_date": date.today() + timedelta(days=3)},
    {"title": "Draft H-1B support letter", "task_type": "form_preparation",
     "status": "in_progress", "priority": "high",
     "due_date": date.today() + timedelta(days=7)},
    {"title": "Review Chen publication list", "task_type": "review",
     "status": "pending", "priority": "medium",
     "due_date": date.today() + timedelta(days=5)},
    {"title": "File EB-1A I-140 petition", "task_type": "filing",
     "status": "in_progress", "priority": "high",
     "due_date": date.today() + timedelta(days=14)},
    {"title": "Follow up with USCIS on Sharma case", "task_type": "follow_up",
     "status": "completed", "priority": "low",
     "due_date": date.today() - timedelta(days=10),
     "completed_at": datetime.now() - timedelta(days=12)},
    {"title": "Prepare RFE response for Chen", "task_type": "form_preparation",
     "status": "pending", "priority": "urgent",
     "due_date": date.today() - timedelta(days=2)},  # overdue
    {"title": "Schedule Santos interview prep", "task_type": "follow_up",
     "status": "pending", "priority": "medium",
     "due_date": date.today() + timedelta(days=21)},
    {"title": "Update Sharma approval notice in system", "task_type": "review",
     "status": "completed", "priority": "low",
     "due_date": date.today() - timedelta(days=30),
     "completed_at": datetime.now() - timedelta(days=32)},
]

LITE_TASKS = [
    {"title": "Elaborar peticao inicial - Oliveira", "task_type": "form_preparation",
     "status": "pending", "priority": "high",
     "due_date": date.today() + timedelta(days=5)},
    {"title": "Juntar documentos comprobatorios", "task_type": "document_collection",
     "status": "in_progress", "priority": "high",
     "due_date": date.today() + timedelta(days=3)},
    {"title": "Audiencia de conciliacao - Souza", "task_type": "follow_up",
     "status": "pending", "priority": "medium",
     "due_date": date.today() + timedelta(days=15)},
    {"title": "Protocolar recurso trabalhista", "task_type": "filing",
     "status": "in_progress", "priority": "high",
     "due_date": date.today() + timedelta(days=2)},
    {"title": "Consultar andamento processual - Mendes", "task_type": "follow_up",
     "status": "completed", "priority": "low",
     "due_date": date.today() - timedelta(days=7),
     "completed_at": datetime.now() - timedelta(days=8)},
    {"title": "Revisar calculo de verbas rescisorias", "task_type": "review",
     "status": "pending", "priority": "urgent",
     "due_date": date.today() - timedelta(days=1)},  # overdue
    {"title": "Agendar depoimento testemunhas", "task_type": "follow_up",
     "status": "pending", "priority": "medium",
     "due_date": date.today() + timedelta(days=20)},
    {"title": "Encerrar processo - Mendes (arquivar)", "task_type": "review",
     "status": "completed", "priority": "low",
     "due_date": date.today() - timedelta(days=14),
     "completed_at": datetime.now() - timedelta(days=15)},
]

IMMIGRATION_BILLING = [
    {"description": "H-1B Filing Fee (I-129)", "amount": Decimal("460.00"),
     "item_type": "filing_fee", "status": "paid",
     "paid_date": date.today() - timedelta(days=5), "currency": "USD"},
    {"description": "Legal fees - EB-1A petition preparation", "amount": Decimal("7500.00"),
     "item_type": "fee", "status": "invoiced",
     "due_date": date.today() + timedelta(days=30), "currency": "USD"},
    {"description": "Premium processing fee", "amount": Decimal("2805.00"),
     "item_type": "filing_fee", "status": "pending",
     "due_date": date.today() + timedelta(days=14), "currency": "USD"},
]

LITE_BILLING = [
    {"description": "Honorarios advocaticios - Oliveira", "amount": Decimal("3500.00"),
     "item_type": "fee", "status": "pending",
     "due_date": date.today() + timedelta(days=30), "currency": "BRL"},
    {"description": "Custas judiciais - Souza", "amount": Decimal("450.00"),
     "item_type": "filing_fee", "status": "paid",
     "paid_date": date.today() - timedelta(days=10), "currency": "BRL"},
    {"description": "Honorarios periciais - Mendes", "amount": Decimal("2000.00"),
     "item_type": "expense", "status": "paid",
     "paid_date": date.today() - timedelta(days=60), "currency": "BRL"},
]


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

def seed_demo(product: str = "immigration"):
    """Seed the database with demo data. Idempotent -- skips if demo org exists."""
    init_db()
    db = next(get_db())

    try:
        # Check idempotency
        existing = get_org_by_slug(db, "demo")
        if existing:
            print(f"[seed_demo] Demo organization already exists (id={existing.id}). Skipping.")
            return

        # 1. Create demo organization
        org = Organization(
            uuid=str(uuid.uuid4()),
            name="Demo Law Firm",
            slug="demo",
            domain=None,
            email="demo@casehub.io",
            phone="+1-555-000-0000" if product == "immigration" else "(32) 3000-0000",
            website="https://demo.casehub.io",
            timezone="America/New_York" if product == "immigration" else "America/Sao_Paulo",
            locale="en" if product == "immigration" else "pt",
            case_prefix="DEMO",
            currency="USD" if product == "immigration" else "BRL",
            plan="professional",
            max_users=25,
            max_clients=500,
            max_storage_gb=50,
            is_active=True,
        )
        db.add(org)
        db.flush()  # get org.id
        print(f"[seed_demo] Created organization: {org.name} (id={org.id})")

        # 2. Create admin user
        admin = User(
            email="demo@casehub.io",
            name="Demo Admin",
            password_hash=User.hash_password("demo123"),
            user_type="admin",
            must_change_password=False,
        )
        # Set org_id if the column exists on User
        if hasattr(User, "org_id"):
            admin.org_id = org.id
        db.add(admin)
        db.flush()
        print(f"[seed_demo] Created admin user: demo@casehub.io / demo123")

        # 3. Create clients
        client_data = LITE_CLIENTS if product == "lite" else IMMIGRATION_CLIENTS
        clients = []
        for cdata in client_data:
            c = Client(**cdata)
            if hasattr(Client, "org_id"):
                c.org_id = org.id
            db.add(c)
            db.flush()
            clients.append(c)
        print(f"[seed_demo] Created {len(clients)} clients")

        # 4. Create cases (assign to first 3 clients)
        case_data = LITE_CASES if product == "lite" else IMMIGRATION_CASES
        cases = []
        for i, csdata in enumerate(case_data):
            case_num = f"DEMO-2026-{i+1:04d}"
            c = Case(
                client_id=clients[i].id,
                case_number=case_num,
                **csdata,
            )
            if hasattr(Case, "org_id"):
                c.org_id = org.id
            db.add(c)
            db.flush()
            cases.append(c)
        print(f"[seed_demo] Created {len(cases)} cases")

        # 5. Create tasks (distribute across cases)
        task_data = LITE_TASKS if product == "lite" else IMMIGRATION_TASKS
        task_count = 0
        for i, tdata in enumerate(task_data):
            case_idx = i % len(cases)
            client_idx = i % len(clients)
            t = Task(
                client_id=clients[client_idx].id,
                case_id=cases[case_idx].id,
                assigned_to=admin.id,
                **tdata,
            )
            if hasattr(Task, "org_id"):
                t.org_id = org.id
            db.add(t)
            task_count += 1
        db.flush()
        print(f"[seed_demo] Created {task_count} tasks")

        # 6. Create billing items (one per case)
        billing_data = LITE_BILLING if product == "lite" else IMMIGRATION_BILLING
        for i, bdata in enumerate(billing_data):
            bi = BillingItem(
                case_id=cases[i].id,
                **bdata,
            )
            if hasattr(BillingItem, "org_id"):
                bi.org_id = org.id
            db.add(bi)
        db.flush()
        print(f"[seed_demo] Created {len(billing_data)} billing items")

        # 7. Create 1 time entry
        te = TimeEntry(
            case_id=cases[1].id,
            user_id=admin.id,
            description="Research and case strategy meeting" if product == "immigration" else "Pesquisa jurisprudencial e estrategia",
            hours=Decimal("2.50"),
            rate=Decimal("250.00") if product == "immigration" else Decimal("150.00"),
            date=date.today() - timedelta(days=3),
            billable=True,
            currency="USD" if product == "immigration" else "BRL",
        )
        if hasattr(TimeEntry, "org_id"):
            te.org_id = org.id
        db.add(te)
        db.flush()
        print(f"[seed_demo] Created 1 time entry")

        db.commit()
        print(f"\n[seed_demo] Done! Demo data seeded for product '{product}'.")
        print(f"  Organization: {org.name} (slug: demo)")
        print(f"  Login: demo@casehub.io / demo123")
        print(f"  Clients: {len(clients)}, Cases: {len(cases)}, Tasks: {task_count}")

    except Exception as e:
        db.rollback()
        print(f"[seed_demo] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed CaseHub with demo data")
    parser.add_argument(
        "--product",
        choices=["immigration", "lite"],
        default="immigration",
        help="Product variant to seed (default: immigration)",
    )
    args = parser.parse_args()
    seed_demo(args.product)
