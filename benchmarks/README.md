# CaseHub Benchmarks

Performance benchmarks for CaseHub API, database, and startup.

## Setup

```bash
pip install -r benchmarks/requirements.txt
```

## API Benchmark

Load-tests key endpoints with configurable concurrency.

```bash
python benchmarks/benchmark_api.py \
    --base-url http://localhost:8001 \
    --email admin@example.com \
    --password yourpassword \
    -n 100 \
    --concurrency 5
```

- Authenticates via form login, then hits each endpoint N times
- POST endpoints (create client, upload) are capped at 20 requests to avoid flooding
- Reports avg, p50, p95, p99, min, max per endpoint

## Database Benchmark

Profiles query performance directly against the database.

```bash
# Uses DATABASE_URL from .env / config automatically
python benchmarks/benchmark_db.py

# Or specify explicitly
python benchmarks/benchmark_db.py --database-url postgresql://user:pass@localhost/casehub -n 20
```

Queries tested:
- Client listing at various LIMIT sizes (10, 100, 1K, 10K)
- Case listing with JOINs
- ILIKE full-text search on client names
- Tenant-scoped vs unscoped queries
- COUNT with GROUP BY
- INSERT + flush (rolled back)
- Raw `SELECT 1` connection test

## Startup Benchmark

Measures import time, app creation, DB init, and memory footprint.

```bash
python benchmarks/benchmark_startup.py
python benchmarks/benchmark_startup.py --product lite --runs 5
```

Reports timing for each startup phase and tracemalloc memory usage.

## Jinja Dashboard Bytecode Cache

Measures `dashboard.html` cold render time versus a render loaded from
Jinja's filesystem bytecode cache.

```bash
DATABASE_URL=sqlite:///tmp.db \
SECRET_KEY=test-secret-key-for-unit-tests-only-32chars \
CASEHUB_ENV=production \
DEBUG=False \
python benchmarks/benchmark_jinja_dashboard.py --runs 5 --cache-dir /tmp/casehub-jinja-benchmark-test
```

The companion smoke renders the same dashboard 100 times with the in-process
Jinja cache cleared between renders and fails if no `__jinja2_*.cache` files
are created.

```bash
DATABASE_URL=sqlite:///tmp.db \
SECRET_KEY=test-secret-key-for-unit-tests-only-32chars \
CASEHUB_ENV=production \
DEBUG=False \
python scripts/smoke_jinja_bytecode_cache.py --requests 100 --cache-dir /tmp/casehub-jinja-smoke-test
```
