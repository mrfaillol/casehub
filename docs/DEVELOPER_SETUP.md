# CaseHub White-Label -- Developer Setup

> Version 2.0 | Last updated: 2026-03-25

---

## Prerequisites

| Dependency | Minimum Version | Recommended | Notes |
|---|---|---|---|
| Python | 3.12+ | 3.12.x | The Dockerfile uses `python:3.12-slim` |
| PostgreSQL | 15+ | 15.x | Required; SQLite is not supported |
| Redis | 7+ | 7.x (Alpine) | Optional; used for caching. App works without it. |
| Node.js | 18+ | 20.x or later | Only needed for the WhatsApp bot microservice |
| npm | 9+ | Bundled with Node.js | For WhatsApp bot dependencies |
| Git | 2.x | Latest | Source control |

### macOS Quick Install

```bash
brew install python@3.12 postgresql@15 redis node
brew services start postgresql@15
brew services start redis
```

### Ubuntu/Debian Quick Install

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql nginx curl npm
```

---

## 1. Clone the Repository

```bash
git clone git@github.com:mrfaillol/casehub.git casehub-whitelabel
cd casehub-whitelabel
```

---

## 2. Python Virtual Environment

```bash
python3.12 -m venv venv
source venv/bin/activate      # Linux/macOS
# venv\Scripts\activate       # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

The `requirements.txt` includes all necessary packages: FastAPI, SQLAlchemy, uvicorn, bcrypt, PyJWT, httpx, Stripe, Google API client, sentence-transformers, pyotp, cryptography, and more.

---

## 3. Environment Configuration

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum these **required** values:

| Variable | How to Generate / Where to Find |
|---|---|
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ENCRYPTION_KEY` | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `DATABASE_URL` | `postgresql://casehub:YOUR_PASSWORD@localhost/casehub` |
| `ADMIN_EMAIL` | Your email address (first admin account) |

All other variables (SMTP, Google Drive, Stripe, Twilio, etc.) are optional. Features that depend on missing keys will be silently disabled.

---

## 4. Database Setup

### Create the PostgreSQL Database

```bash
# macOS (Homebrew)
createdb casehub
createuser casehub -P    # Enter a password when prompted

# OR via psql
sudo -u postgres psql
CREATE USER casehub WITH PASSWORD 'your_password';
CREATE DATABASE casehub OWNER casehub;
\q
```

### Run Migrations

Apply the SQL migration files in order:

```bash
export PGPASSWORD='your_password'

psql -U casehub -h localhost casehub < migrations/2026-03-20_multi_tenancy.sql
psql -U casehub -h localhost casehub < migrations/2026-03-20_security.sql
psql -U casehub -h localhost casehub < migrations/2026-03-20_billing.sql
psql -U casehub -h localhost casehub < migrations/2026-03-20_document_state.sql
psql -U casehub -h localhost casehub < migrations/2026-03-21_encrypt_pii.sql
```

On first startup, SQLAlchemy will also call `Base.metadata.create_all()` to create any tables not yet present.

---

## 5. Running Locally

### Full Immigration Product (default)

```bash
make dev
# Equivalent to:
# CASEHUB_PRODUCT=immigration uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

### Lite Product (CRM-only, pt-BR locale)

```bash
make dev-lite
# Equivalent to:
# CASEHUB_PRODUCT=lite DEFAULT_LOCALE=pt-BR uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

### Direct uvicorn Command

```bash
source venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

Once running, open `http://localhost:8001/casehub/login` in your browser. On first startup, a temporary admin password is printed to the console:

```
Default admin user created: admin@yourfirm.com / <random-password> (must change on first login)
```

---

## 6. Running with Docker

### Development (full stack)

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 15** on port 5432
- **Redis 7** on port 6379
- **CaseHub app** on port 8001

### Specific Product Variant

```bash
# Immigration product
docker compose -f docker-compose.yml -f docker-compose.immigration.yml up --build

# Lite product
docker compose -f docker-compose.yml -f docker-compose.lite.yml up --build
```

Or use the Makefile shorthand:

```bash
make immigration    # Docker Compose with immigration overlay
make lite           # Docker Compose with lite overlay
```

### Production (with Nginx)

```bash
docker compose --profile production up -d
```

This additionally starts an Nginx container on ports 80/443.

---

## 7. Running Tests

```bash
make test
# Equivalent to: pytest
```

Run specific test files:

```bash
pytest tests/test_auth.py -v
pytest tests/test_tenant.py -v
pytest tests/test_rbac.py -v
pytest tests/test_clients.py -v
```

Run benchmarks:

```bash
make benchmark
```

The test suite uses `conftest.py` fixtures that set up a test database session and mock authentication.

---

## 8. WhatsApp Bot Setup (Optional)

The WhatsApp bot is a separate Node.js application in `services/whatsapp-bot/`.

```bash
cd services/whatsapp-bot
npm install
node server.js
```

The bot runs on port 3001. CaseHub proxies requests to it via `/api/bot-control`, `/api/bot-status`, and `/api/bot-toggle` endpoints (immigration product only).

The bot requires:
- A WhatsApp Business account or personal number for pairing.
- Configuration in `services/whatsapp-bot/config.js`.
- The CaseHub backend running on port 8001 (for data sync).

---

## 9. Useful Make Commands

| Command | Description |
|---|---|
| `make dev` | Start immigration product with hot reload |
| `make dev-lite` | Start lite product with hot reload (pt-BR) |
| `make immigration` | Docker Compose: immigration product |
| `make lite` | Docker Compose: lite product |
| `make test` | Run pytest test suite |
| `make benchmark` | Run performance benchmarks |
| `make clean` | Remove `__pycache__`, `.pyc`, `.pyo` files |

---

## 10. Troubleshooting

### "FATAL: SECRET_KEY must be set in .env"

You forgot to set the `SECRET_KEY` in `.env`. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### "FATAL: DATABASE_URL must be set in .env"

Set `DATABASE_URL` in `.env`. Ensure PostgreSQL is running and the database exists.

### Port 8001 already in use

Another process is occupying the port. Find and kill it:

```bash
lsof -ti:8001 | xargs kill -9
```

### "ModuleNotFoundError: No module named 'xyz'"

Ensure you activated the virtual environment and installed dependencies:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Router "skipped" messages on startup

Messages like `[app_factory] Skipping routes.xyz: No module named 'xyz'` are non-fatal. They mean a router module has an unresolved import. This is expected if you have not installed all optional dependencies.

### Database migration errors

If tables already exist, some migration SQL may fail with `relation already exists`. This is safe to ignore. SQLAlchemy's `create_all()` on startup handles missing tables gracefully.

### WhatsApp bot not connecting

1. Ensure `node server.js` is running in `services/whatsapp-bot/`.
2. Check that port 3001 is not blocked.
3. Review logs with `pm2 logs whatsapp-bot` (production) or check the console output (development).
4. The bot needs an initial QR code scan or pairing code to authenticate.

### PII encryption key mismatch

If `ENCRYPTION_KEY` changes after data has been encrypted, previously encrypted fields (SSN, alien number, passport number) become unrecoverable. Always back up the key separately.

---

## 11. Project Conventions

- **Route modules** live in `routes/` and export a `router` variable (a `fastapi.APIRouter`).
- **Service modules** live in `services/` and contain business logic. Routes should not contain complex logic.
- **Templates** are organized by feature in `templates/<feature>/`.
- **All database queries** must use `tenant_query()` to ensure tenant isolation.
- **Sensitive data** (SSN, passport, alien number) must be encrypted via `services/encryption.py`.
- **Feature-gated endpoints** use `Depends(require_feature("feature_name"))`.
- **Permission-gated endpoints** use `Depends(require_permission("resource.action"))`.
