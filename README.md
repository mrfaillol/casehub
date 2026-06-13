# CaseHub

> Case management platform for law firms. Two products, one codebase.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white" alt="PostgreSQL 15">
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License">
</p>

---

## Products

### CaseHub

Built for Brazilian law firms (inspired by ADVbox, Astrea, LegalOne).

- Brazilian legal fields -- CPF, RG, CNPJ, numero_processo, vara, comarca, tribunal
- Controladoria jurídica
- Tarefas com kanban dinâmico
- Agenda integrada ao Google Drive
- Processo tracking, prazos processuais, tribunal integration, OAB validation
- Notion, Slack, and Google Workspace integration
- Dark/light mode, pt-BR interface
- Currency: BRL | Language: pt-BR | Timezone: America/Sao_Paulo

### Shared across both products

Client management, case tracking, document management, task board, calendar, billing & invoicing, email integration, client portal, notifications, audit logging, RBAC (5 roles), 2FA, reports, team chat, SSO, webhooks, REST API, multi-tenancy with per-org branding.

---

## Quick Start

### Docker (recommended)

```bash
# Immigration product
docker compose -f docker-compose.yml -f docker-compose.immigration.yml up --build

# Lite product
docker compose -f docker-compose.yml -f docker-compose.lite.yml up --build
```

### Local Development

```bash
# Clone and install
git clone git@github.com:mrfaillol/casehub-prod.git && cd casehub
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Database
createdb casehub
psql casehub < migrations/2026-03-20_multi_tenancy.sql

# Configure
cp .env.example .env   # Set SECRET_KEY, DATABASE_URL, ADMIN_EMAIL at minimum

# Run
make dev          # Immigration product
make dev-lite     # Lite product
```

Both expand to `CASEHUB_PRODUCT=<product> uvicorn app:app --host 0.0.0.0 --port 8001 --reload`.

Open [http://localhost:8001/casehub](http://localhost:8001/casehub). On first run, an admin account is created from `ADMIN_EMAIL` (password printed to stdout).

### Prerequisites

- Python 3.12+, PostgreSQL 15+, Redis 7+ (optional; in-memory fallback)
- Node.js 20+ (only for WhatsApp bot)

---

## Architecture

CaseHub uses an **app factory pattern** (`core/app_factory.py`). The `CASEHUB_PRODUCT` env var selects which product to boot:

```
CASEHUB_PRODUCT=immigration  ->  core routers + immigration routers + communication routers
CASEHUB_PRODUCT=lite         ->  core routers + communication routers
```

Product-specific defaults (currency, locale, timezone, feature flags) are resolved automatically. Per-org overrides and plan-based feature flags layer on top.

```
casehub-whitelabel/
|-- app.py                          # Entry point
|-- config.py                       # Pydantic Settings (.env)
|-- core/app_factory.py             # create_app(product) factory
|-- products/immigration/           # Immigration-specific modules
|-- products/lite/                  # Lite-specific modules
|-- models/                         # SQLAlchemy models (tenant-scoped)
|-- routes/                         # FastAPI routers (~60 modules)
|-- services/                       # Business logic (~70 modules)
|-- middleware/                     # Tenant, features, permissions, rate limiting
|-- templates/                      # Jinja2 templates
|-- static/                         # CSS (Tailwind), JS, images
|-- migrations/                     # SQL migration files
|-- i18n/                           # Translations (en, pt-BR)
+-- docs/                           # Full documentation
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the complete system design.

---

## Configuration

### Required

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing key (app exits if unset) |
| `DATABASE_URL` | PostgreSQL connection string |
| `ADMIN_EMAIL` | Auto-created admin account |

### Product selection

| Variable | Default | Description |
|---|---|---|
| `CASEHUB_PRODUCT` | `immigration` | `immigration` or `lite` |
| `DEFAULT_CURRENCY` | Auto per product | `USD` or `BRL` |
| `DEFAULT_TIMEZONE` | Auto per product | IANA timezone |

### Optional integrations

Stripe (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`), Notion (`NOTION_TOKEN`), Google Drive (`GOOGLE_DRIVE_*`), Twilio/WhatsApp (`TWILIO_*`), Gemini AI (`GEMINI_API_KEY`), Perplexity (`PERPLEXITY_API_KEY`), SMTP (`SMTP_*`), Resend (`RESEND_API_KEY`).

See `.env.example` for all variables.

---

## White-Label Customization

### Organization branding

Each tenant can customize logo, favicon, primary/secondary colors, and display name via the Branding settings page (`/casehub/settings/branding`) or the API.

### Custom domains

Subdomain or custom domain routing per organization. See [docs/WHITE_LABEL_GUIDE.md](docs/WHITE_LABEL_GUIDE.md).

### Plans & feature flags

Three plans (`starter`, `professional`, `enterprise`) with per-org JSON overrides. Features resolve as: plan defaults -> org overrides -> hardcoded fallback.

---

## Hardware Requirements

| Tier | CPU | RAM | Disk |
|---|---|---|---|
| Minimum | 2 cores | 4 GB | 20 GB |
| Recommended | 4 cores | 8 GB | 50 GB |
| Production (multi-tenant) | 8 cores | 16 GB | 100 GB SSD |

See [docs/HARDWARE_REQUIREMENTS.md](docs/HARDWARE_REQUIREMENTS.md) for benchmarks.

---

## Tech Stack

Python 3.12, FastAPI 0.109, SQLAlchemy 2.0, PostgreSQL 15, Redis 7, Jinja2, TailwindCSS, JWT + bcrypt, Fernet encryption, Docker, Nginx, PM2, Google Gemini, Perplexity.

---

## Documentation

| Document | Description |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, app factory, request flow |
| [DEVELOPER_SETUP.md](docs/DEVELOPER_SETUP.md) | Local dev environment setup |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, PM2, bare metal deployment |
| [WHITE_LABEL_GUIDE.md](docs/WHITE_LABEL_GUIDE.md) | Tenant creation, branding, domains, feature flags |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | REST API endpoints |
| [FORM_ENRICHMENT_GUIDE.md](docs/FORM_ENRICHMENT_GUIDE.md) | USCIS form expander development |
| [HARDWARE_REQUIREMENTS.md](docs/HARDWARE_REQUIREMENTS.md) | Server sizing and benchmarks |
| [USER_MANUAL.md](docs/USER_MANUAL.md) | End-user manual |

---

## License

Proprietary. All rights reserved. Victor Vingren / [vingren.me](https://vingren.me)
