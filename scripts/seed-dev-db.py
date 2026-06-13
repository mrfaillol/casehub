"""
CaseHub Dev Database Seed
Creates org, admin user, sample clients, cases, tasks, and prazos.
Usage: python scripts/seed-dev-db.py
Requires DATABASE_URL env var or defaults to dev postgres.
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta

# Add parent dir to path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
from models.tenant import Organization
from models.user import User
from models.client import Client
from models.case import Case
from models.task import Task

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://casehub:dev123@localhost:5433/casehub_dev"
)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def seed():
    # Create all tables
    Base.metadata.create_all(engine)
    session = Session()

    # Check if already seeded
    existing_org = session.query(Organization).filter_by(slug="dev").first()
    if existing_org:
        print("Database already seeded (org 'dev' exists). Skipping.")
        session.close()
        return

    print("Seeding database...")

    # 1. Organization
    org = Organization(
        uuid=str(uuid.uuid4()),
        name="CaseHub Dev",
        slug="dev",
        domain="localhost",
        email="dev@casehub.local",
        phone="(32) 99999-0000",
        timezone="America/Sao_Paulo",
        locale="pt-BR",
        case_prefix="DEV",
        currency="BRL",
        plan="professional",
        max_users=50,
        max_clients=1000,
        max_storage_gb=50,
        primary_color="#1C2447",
        secondary_color="#C9A208",
        features={
            "hub_tabs": True,
            "whatsapp_bot": False,
            "ai_assistant": True,
            "client_portal": True,
            "billing": True,
            "email_client": True,
            "controladoria": True,
        },
        settings={
            "accent_color": "#1C2447",
            "primary_color": "#1C2447",
            "font_family": "Maven Pro",
            "font_heading": "Maven Pro",
            "theme_bg": "#f5f5f7",
        },
    )
    session.add(org)
    session.flush()

    # 2. Admin user
    admin = User(
        org_id=org.id,
        email="victor@vingren.me",
        name="Victor Vingren",
        password_hash=User.hash_password("dev123"),
        user_type="admin",
        enabled=True,
        must_change_password=False,
    )
    session.add(admin)

    # Demo user
    demo = User(
        org_id=org.id,
        email="demo@casehub.local",
        name="Demo User",
        password_hash=User.hash_password("demo123"),
        user_type="case_worker",
        enabled=True,
        must_change_password=False,
    )
    session.add(demo)
    session.flush()

    # 3. Clients
    clients_data = [
        {"first_name": "Maria", "last_name": "Silva", "email": "maria@example.com",
         "phone": "(32) 99111-0001", "cpf": "123.456.789-00", "client_type": "individual",
         "city": "Juiz de Fora", "state": "MG"},
        {"first_name": "Pedro", "last_name": "Santos", "email": "pedro@example.com",
         "phone": "(32) 99111-0002", "cpf": "987.654.321-00", "client_type": "individual",
         "city": "Juiz de Fora", "state": "MG"},
        {"first_name": "Ana", "last_name": "Oliveira", "email": "ana@example.com",
         "phone": "(32) 99111-0003", "cpf": "456.789.123-00", "client_type": "individual",
         "city": "Belo Horizonte", "state": "MG"},
        {"first_name": "Empresa", "last_name": "Construtora ABC", "email": "contato@abc.com.br",
         "phone": "(32) 99111-0004", "cnpj": "12.345.678/0001-90", "client_type": "corporate",
         "city": "Juiz de Fora", "state": "MG"},
        {"first_name": "Comércio", "last_name": "Loja Central", "email": "loja@central.com.br",
         "phone": "(32) 99111-0005", "cnpj": "98.765.432/0001-10", "client_type": "corporate",
         "city": "São Paulo", "state": "SP"},
    ]

    clients = []
    for i, cd in enumerate(clients_data):
        c = Client(
            org_id=org.id,
            client_number=f"DEV-{i+1:04d}",
            status="active",
            **cd,
        )
        session.add(c)
        clients.append(c)
    session.flush()

    # 4. Cases
    cases_data = [
        {"client_idx": 0, "case_name": "Reclamação Trabalhista - Maria Silva",
         "numero_processo": "0010001-12.2026.5.03.0036", "tipo_acao": "Reclamação Trabalhista",
         "vara": "1ª Vara do Trabalho", "comarca": "Juiz de Fora", "tribunal": "TRT-3",
         "status": "in_progress", "priority": "high", "area_of_practice": "Trabalhista"},
        {"client_idx": 1, "case_name": "Ação de Indenização - Pedro Santos",
         "numero_processo": "0020002-34.2026.8.13.0145", "tipo_acao": "Ação Indenizatória",
         "vara": "3ª Vara Cível", "comarca": "Juiz de Fora", "tribunal": "TJMG",
         "status": "intake", "priority": "medium", "area_of_practice": "Cível"},
        {"client_idx": 3, "case_name": "Execução Fiscal - Construtora ABC",
         "numero_processo": "0030003-56.2026.8.13.0145", "tipo_acao": "Execução Fiscal",
         "vara": "2ª Vara da Fazenda", "comarca": "Juiz de Fora", "tribunal": "TJMG",
         "status": "in_progress", "priority": "urgent", "area_of_practice": "Tributário"},
    ]

    cases = []
    for i, cd in enumerate(cases_data):
        client_idx = cd.pop("client_idx")
        c = Case(
            org_id=org.id,
            client_id=clients[client_idx].id,
            case_number=f"DEV-CASE-{i+1:04d}",
            filing_date=date.today() - timedelta(days=30 * (i + 1)),
            **cd,
        )
        session.add(c)
        cases.append(c)
    session.flush()

    # 5. Tasks
    tasks_data = [
        {"title": "Preparar petição inicial", "status": "completed", "priority": "high",
         "case_idx": 0, "client_idx": 0, "task_type": "form_preparation"},
        {"title": "Juntar documentos trabalhistas", "status": "in_progress", "priority": "high",
         "case_idx": 0, "client_idx": 0, "task_type": "document_collection"},
        {"title": "Audiência de conciliação", "status": "pending", "priority": "urgent",
         "case_idx": 0, "client_idx": 0, "task_type": "reminder"},
        {"title": "Análise de viabilidade", "status": "in_progress", "priority": "medium",
         "case_idx": 1, "client_idx": 1, "task_type": "review"},
        {"title": "Contestação fiscal", "status": "pending", "priority": "urgent",
         "case_idx": 2, "client_idx": 3, "task_type": "form_preparation"},
    ]

    for i, td in enumerate(tasks_data):
        case_idx = td.pop("case_idx")
        client_idx = td.pop("client_idx")
        t = Task(
            org_id=org.id,
            case_id=cases[case_idx].id,
            client_id=clients[client_idx].id,
            assigned_to=admin.id,
            due_date=date.today() + timedelta(days=7 * (i + 1)),
            **td,
        )
        session.add(t)

    session.commit()
    print(f"Seeded: 1 org, 2 users, {len(clients)} clients, {len(cases)} cases, {len(tasks_data)} tasks")
    session.close()


if __name__ == "__main__":
    seed()
