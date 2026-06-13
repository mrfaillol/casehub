#!/usr/bin/env python3
"""
CaseHub Database Benchmark
Profiles database query performance at various scales.

Usage:
    python benchmark_db.py
    python benchmark_db.py --database-url sqlite:///casehub.db
    python benchmark_db.py --database-url postgresql://user:pass@localhost/casehub
"""
import argparse
import os
import sys
import time
import statistics
from contextlib import contextmanager

# Add parent directory to path so we can import CaseHub modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker, Session
from tabulate import tabulate


def get_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


@contextmanager
def session_scope(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def time_query(session_factory, query_fn, iterations=10):
    """Run a query function multiple times and collect timings."""
    times = []
    errors = 0
    for _ in range(iterations):
        try:
            with session_scope(session_factory) as db:
                start = time.perf_counter()
                query_fn(db)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
        except Exception as e:
            errors += 1
            if not times:
                times.append(0)
    return times, errors


def format_row(label, times, errors):
    if not times or all(t == 0 for t in times):
        return [label, 0, errors, "N/A", "N/A", "N/A", "N/A", "N/A"]
    return [
        label,
        len(times),
        errors,
        f"{statistics.mean(times) * 1000:.2f}",
        f"{statistics.median(times) * 1000:.2f}",
        f"{min(times) * 1000:.2f}",
        f"{max(times) * 1000:.2f}",
        f"{sorted(times)[int(len(times) * 0.95)] * 1000:.2f}" if len(times) >= 2 else "N/A",
    ]


def run_benchmarks(database_url: str, iterations: int):
    from models import Base, User, Client, Case, Document
    from models.tenant import Organization, tenant_query

    engine = get_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    print(f"CaseHub Database Benchmark")
    print(f"  Database: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    print(f"  Iterations per query: {iterations}")
    print()

    # Count existing records
    with session_scope(SessionLocal) as db:
        try:
            client_count = db.query(func.count(Client.id)).scalar()
            case_count = db.query(func.count(Case.id)).scalar()
            user_count = db.query(func.count(User.id)).scalar()
            print(f"  Records: {client_count} clients, {case_count} cases, {user_count} users")
        except Exception as e:
            print(f"  Warning: Could not count records ({e})")
            client_count = 0
    print()

    results = []
    headers = ["Query", "Runs", "Errors", "Avg(ms)", "P50(ms)", "Min(ms)", "Max(ms)", "P95(ms)"]

    # --- 1. List clients with LIMIT ---
    for limit in [10, 100, 1000, 10000]:
        def query_clients(db, lim=limit):
            return db.query(Client).limit(lim).all()
        times, errors = time_query(SessionLocal, query_clients, iterations)
        results.append(format_row(f"SELECT clients LIMIT {limit}", times, errors))

    # --- 2. List cases with joins (client + user) ---
    def query_cases_with_joins(db):
        return (
            db.query(Case)
            .join(Client, Case.client_id == Client.id, isouter=True)
            .limit(100)
            .all()
        )
    times, errors = time_query(SessionLocal, query_cases_with_joins, iterations)
    results.append(format_row("SELECT cases JOIN clients (100)", times, errors))

    # --- 3. Full-text search on client names ---
    def query_fts_client(db):
        return (
            db.query(Client)
            .filter(
                (Client.first_name.ilike("%test%")) | (Client.last_name.ilike("%test%"))
            )
            .limit(50)
            .all()
        )
    times, errors = time_query(SessionLocal, query_fts_client, iterations)
    results.append(format_row("ILIKE search on client name", times, errors))

    # --- 4. Tenant-scoped queries (org_id = 1) ---
    def query_tenant_scoped(db):
        return tenant_query(db, Client, org_id=1).limit(100).all()
    times, errors = time_query(SessionLocal, query_tenant_scoped, iterations)
    results.append(format_row("Tenant-scoped clients (org=1)", times, errors))

    # --- 5. Unscoped query (no tenant filter) ---
    def query_unscoped(db):
        return db.query(Client).limit(100).all()
    times, errors = time_query(SessionLocal, query_unscoped, iterations)
    results.append(format_row("Unscoped clients (no tenant)", times, errors))

    # --- 6. Count aggregation ---
    def query_count(db):
        return db.query(func.count(Client.id)).scalar()
    times, errors = time_query(SessionLocal, query_count, iterations)
    results.append(format_row("COUNT(*) clients", times, errors))

    # --- 7. Count cases grouped by status ---
    def query_grouped_count(db):
        return db.query(Case.status, func.count(Case.id)).group_by(Case.status).all()
    times, errors = time_query(SessionLocal, query_grouped_count, iterations)
    results.append(format_row("COUNT cases GROUP BY status", times, errors))

    # --- 8. Insert + commit single client ---
    def query_insert(db):
        c = Client(
            first_name="BenchInsert",
            last_name="Test",
            email=f"bench-{time.time_ns()}@test.local",
            org_id=1,
        )
        db.add(c)
        db.flush()
        # Rollback to avoid polluting DB
        db.rollback()
    times, errors = time_query(SessionLocal, query_insert, iterations)
    results.append(format_row("INSERT client + flush (rollback)", times, errors))

    # --- 9. Raw SQL ping ---
    def query_ping(db):
        db.execute(text("SELECT 1"))
    times, errors = time_query(SessionLocal, query_ping, iterations)
    results.append(format_row("SELECT 1 (connection test)", times, errors))

    # Print results
    print("=" * 95)
    print("RESULTS")
    print("=" * 95)
    print(tabulate(results, headers=headers, tablefmt="grid"))
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="CaseHub Database Benchmark")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Database URL (default: from DATABASE_URL env or config)",
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=10,
        help="Number of iterations per query (default: 10)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    db_url = args.database_url
    if not db_url:
        try:
            from config import settings
            db_url = settings.DATABASE_URL
        except Exception:
            print("ERROR: No database URL provided. Use --database-url or set DATABASE_URL env.", file=sys.stderr)
            sys.exit(1)
    if not db_url:
        print("ERROR: DATABASE_URL is empty. Provide via --database-url or .env file.", file=sys.stderr)
        sys.exit(1)
    run_benchmarks(db_url, args.iterations)
