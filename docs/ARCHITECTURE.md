# CaseHub White-Label -- Architecture

> Version 2.0 | Last updated: 2026-03-25

---

## 1. System Overview

CaseHub is a multi-tenant, white-label case management platform built for law firms. It ships as a monolithic Python application with optional Node.js microservices.

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.109 (ASGI) |
| Template engine | Jinja2 3.1 (server-side rendering) |
| ORM / database | SQLAlchemy 2.0 + PostgreSQL 15 |
| Cache / sessions | Redis 7 (optional; in-memory fallback) |
| CSS | TailwindCSS (pre-built static assets) |
| Auth | JWT (HS256) via PyJWT, bcrypt passwords |
| PII encryption | Fernet (cryptography library) |
| Process manager | PM2 (production) / uvicorn --reload (dev) |
| Reverse proxy | Nginx with wildcard SSL |
| Containerization | Docker + Docker Compose |

The application follows a **server-side rendered** architecture: Jinja2 templates produce HTML, with minimal client-side JavaScript for interactive components. A REST API layer (`/api/v1/`) supports programmatic access and the client portal.

---

## 2. Directory Structure

```
casehub-whitelabel/
|-- app.py                      # Entry point -- delegates to app factory
|-- config.py                   # Pydantic Settings (reads .env)
|-- auth.py                     # JWT token creation/validation
|-- i18n.py                     # Internationalization loader
|
|-- core/
|   |-- app_factory.py          # create_app() -- the App Factory
|   |-- middleware/              # Core middleware (reserved for future)
|   |-- models/                 # Core model stubs (reserved)
|   |-- routes/                 # Core route stubs (reserved)
|   |-- services/               # Core service stubs (reserved)
|   |-- static/                 # Core static assets (reserved)
|   +-- templates/              # Core templates (reserved)
|
|-- products/
|   |-- immigration/
|   |   +-- app.py              # create_app("immigration")
|   +-- lite/
|       +-- app.py              # create_app("lite")
|
|-- models/
|   |-- __init__.py             # Re-exports all models
|   |-- base.py                 # Engine, SessionLocal, Base, get_db, init_db
|   |-- tenant.py               # Organization model + tenant_query helpers
|   |-- user.py                 # User model (bcrypt auth)
|   |-- client.py               # Client model (encrypted PII)
|   |-- case.py                 # Case model
|   |-- document.py             # Document model
|   |-- task.py                 # Task + Reminder models
|   |-- billing.py              # BillingItem + TimeEntry models
|   |-- notification.py         # Notification model
|   +-- questionnaire.py        # Questionnaire models
|
|-- routes/                     # ~60 FastAPI router modules
|   |-- clients.py, cases.py, documents.py, ...
|   |-- uscis.py, intake.py, efiling.py, ...      (immigration-only)
|   +-- leads.py, whatsapp.py, messaging_hub.py, ...
|
|-- services/                   # ~70 business-logic service modules
|   |-- encryption.py           # Fernet PII encryption
|   |-- audit.py                # Audit logging + SQLAlchemy listeners
|   |-- stripe_service.py       # Billing integration
|   |-- google_drive_handler.py # Drive sync
|   |-- email_service.py        # SMTP outbound
|   |-- ...
|   +-- whatsapp-bot/           # Node.js WhatsApp bot (separate process)
|       |-- server.js
|       |-- package.json
|       +-- ...
|
|-- middleware/
|   |-- tenant.py               # TenantMiddleware (org resolution)
|   |-- features.py             # Feature flag enforcement
|   |-- permissions.py          # RBAC permission checks
|   +-- rate_limit.py           # Per-IP rate limiting
|
|-- templates/                  # Jinja2 HTML templates (~50 subdirectories)
|-- static/                     # CSS, JS, images
|-- migrations/                 # Raw SQL migration files
|-- deploy/                     # Nginx config, PM2 config, setup script
|-- tests/                      # pytest test suite
|-- tools/                      # AI content generators (LOR, PS, packages)
|-- i18n/                       # Translations and document categories
|-- data/                       # USCIS form data, uploads
|-- uploads/                    # User-uploaded files (per-client subdirs)
|-- storage/                    # Emails, signatures, portal files
+-- docker-compose.yml          # Full stack: postgres + redis + app + nginx
```

---

## 3. App Factory Pattern

The core design pattern is the **App Factory** (`core/app_factory.py`). The entry point `app.py` is only three effective lines:

```python
product = os.getenv("CASEHUB_PRODUCT", "immigration")
app = create_app(product)
```

`create_app(product)` performs the following:

1. **Creates a FastAPI instance** with product-specific metadata.
2. **Registers middleware** in order: SecurityHeaders -> RateLimit -> AuditContext.
3. **Mounts static files** and configures Jinja2 templates.
4. **Defines core routes** inline: `/`, `/login`, `/logout`, `/dashboard`, `/api/v1/auth/login`, `/auth/refresh`, `/api/health`, `/api/feedback`.
5. **Selects routers** from the product-specific registry (see below).
6. **Dynamically imports and includes** each router module from `routes/`.
7. **Starts background workers** on the `startup` event (lead surveillance, Notion cache).
8. **Auto-creates the admin user** if none exists.

This pattern means the same codebase can produce different products by changing a single environment variable.

---

## 4. Module Classification

Routers are classified into three tiers:

### Core Routers (shared by ALL products)

Loaded for both `immigration` and `lite`:

```
clients, cases, documents, documents_api, admin, calendar, tasks, billing,
custom_fields, webhooks, emails, portal, api, processes, letters,
questionnaires, reports, notion, import_data, notifications, invoices,
audit, workflow, two_factor, deadlines, versions, notes, doc_templates,
settings, payments, signatures, alerts, triggers, global_alerts, contacts,
sso, referrals, bulk, client_relationships, team_chat, legal_assistant,
communications, google_calendar, email_templates_v2, branding, onboarding,
superadmin, password_reset, subscription
```

### Immigration-Specific Routers

Loaded only when `product == "immigration"`:

```
uscis, uscis_status, uscis_forms, efiling, case_wizard,
packets, shipments, intake, case_archive, ilc_tools
```

### Communication Routers (shared, optional)

Loaded for both products:

```
whatsapp, whatsapp_chat, callhippo, twilio, moskit,
messaging_hub, leads, aila_api, aila_wiki,
lor_maker, ps_maker, package_maker
```

Routers that fail to import (missing dependencies, etc.) are silently skipped with a console warning.

---

## 5. Request Data Flow

```
Client (Browser / API)
  |
  v
Nginx (SSL termination, static files, rate limiting)
  |
  v
Uvicorn ASGI Server (port 8001)
  |
  v
Middleware Stack (executed in reverse registration order):
  1. SecurityHeadersMiddleware  -- adds CSP, X-Frame-Options, etc.
  2. RateLimitMiddleware        -- per-IP request throttling (60/min general, 10/min uploads)
  3. AuditContextMiddleware     -- sets user/IP context for audit logging
  |
  v
FastAPI Router Resolution
  |
  v
Route Handler (in routes/*.py)
  |-- Depends(get_db)           -- yields a SQLAlchemy Session
  |-- Depends(get_current_user) -- extracts user from JWT cookie
  |-- Depends(require_permission("cases.view"))  -- RBAC check
  |-- Depends(require_feature("ai_lor"))         -- feature flag check
  |
  v
Service Layer (services/*.py)
  |-- Business logic, validations, external API calls
  |
  v
Model Layer (models/*.py)
  |-- SQLAlchemy ORM models
  |-- tenant_query(db, Model, org_id) -- all queries scoped to tenant
  |
  v
PostgreSQL Database
```

---

## 6. Multi-Tenancy

### Organization Model

Each tenant is an `Organization` row in the `organizations` table. Key fields:

| Field | Purpose |
|---|---|
| `slug` | URL identifier (e.g., `acme` in `acme.casehub.app`) |
| `domain` | Custom domain (e.g., `cases.acmelegal.com`) |
| `product_type` | `"immigration"` or `"lite"` |
| `plan` | Subscription tier: `starter`, `professional`, `enterprise` |
| `features` | JSON field for per-org feature overrides |
| `primary_color`, `secondary_color`, `logo_url`, `favicon_url` | Branding |
| `smtp_host`, `smtp_user`, `smtp_pass` | Per-tenant email config |
| `google_drive_root_id` | Per-tenant Drive integration |
| `max_users`, `max_clients`, `max_storage_gb` | Plan limits |
| `stripe_customer_id`, `stripe_subscription_id` | Billing |

### Tenant Resolution (middleware/tenant.py)

The `TenantMiddleware` resolves the organization for each request using this priority:

1. **`X-Org-Id` header** -- for API and service-to-service calls.
2. **Exact domain match** -- looks up the `Host` header against `organizations.domain`.
3. **Subdomain extraction** -- parses `acme.casehub.app` -> slug `acme`.
4. **Default organization fallback** -- single-tenant mode uses slug `"default"`.

Resolution results are cached in-memory per host.

### Tenant-Scoped Queries

All database queries MUST use the `tenant_query` helper:

```python
from models.tenant import tenant_query

clients = tenant_query(db, Client, request.state.org_id) \
    .filter(Client.status == "active") \
    .all()
```

This appends `.filter(Model.org_id == org_id)` to every query, ensuring strict data isolation.

### Feature Flags

Features are gated at three levels:

1. **Product type** -- immigration routers are not loaded for `lite`.
2. **Plan-based features** -- resolved from the `plans` table, `org.features` JSON, or a hardcoded fallback map.
3. **Per-org overrides** -- the `features` JSON column on `organizations` can enable/disable individual features.

Use the `require_feature("feature_name")` dependency to enforce:

```python
@router.get("/ai/lor")
async def generate_lor(
    request: Request,
    _feature=Depends(require_feature("ai_lor")),
):
    ...
```

Returns HTTP 402 if the feature is not available, prompting a plan upgrade.

---

## 7. Authentication

### JWT Tokens

- **Access token**: 30-minute expiry, stored in `casehub_token` HttpOnly cookie.
- **Refresh token**: 7-day expiry, stored in `casehub_refresh` HttpOnly cookie.
- **Algorithm**: HS256 with `SECRET_KEY` from `.env`.
- **Payload**: `{"sub": "<email>", "exp": <timestamp>, "type": "access"|"refresh"}`.

### Cookie-Based Sessions (Browser)

Browser clients authenticate via cookies. The login flow:

1. POST `/login` with email + password.
2. Server verifies credentials against bcrypt hash.
3. On success, sets `casehub_token` and `casehub_refresh` cookies.
4. Redirects to `/dashboard`.

### Bearer Token (API)

API clients authenticate via `Authorization: Bearer <token>` header. The login flow:

1. POST `/api/v1/auth/login` with email + password.
2. Returns JSON with `access_token`, `refresh_token`, `expires_in`.

Both browser and API auth share the same `get_current_user` / `get_current_user_api` functions.

### Login Rate Limiting

An in-memory `LoginRateLimiter` tracks failed attempts per IP:

- **5 failed attempts** within a 5-minute window triggers a **15-minute lockout**.
- Successful login resets the counter for that IP.

### Two-Factor Authentication (2FA)

Optional TOTP-based 2FA using the `pyotp` library. Managed via the `two_factor` route module and `services/two_factor.py`.

### Role-Based Access Control (RBAC)

Five predefined roles with wildcard permission matching:

| Role | Permissions |
|---|---|
| `superadmin` | `*` (everything) |
| `admin` | `org.*`, `admin.*`, `billing.*`, `reports.*`, `settings.*`, `cases.*`, `clients.*`, `documents.*`, `tasks.*`, `emails.*`, `intake.*`, `calendar.*` |
| `attorney` | `cases.*`, `clients.*`, `documents.*`, `billing.*`, `reports.view`, `tasks.*`, `emails.*` |
| `paralegal` | `cases.view`, `cases.edit`, `clients.view`, `clients.edit`, `documents.*`, `tasks.*`, `intake.*`, `emails.view` |
| `assistant` | `cases.view`, `clients.view`, `tasks.view`, `tasks.edit`, `calendar.*`, `documents.view` |

Usage in routes:

```python
@router.delete("/cases/{id}")
async def delete_case(user: User = Depends(require_permission("cases.delete"))):
    ...
```

---

## 8. Key Design Decisions and Trade-offs

| Decision | Rationale | Trade-off |
|---|---|---|
| **Server-side rendering** (Jinja2) over SPA | Faster initial load, better SEO for portal pages, simpler deployment | Less interactive UI; requires page reloads for some actions |
| **Monolith with App Factory** over microservices | Single deployment unit, shared DB, simpler ops | All features share one process; a crash affects everything |
| **In-memory rate limiting** over Redis-backed | No Redis hard dependency; sufficient for single-instance deployments | Does not share state across multiple uvicorn workers |
| **Raw SQL migrations** over Alembic auto-generate | Explicit control over schema changes; no migration state drift | Must write SQL manually; no automatic rollback |
| **Fernet encryption for PII** | Transparent encrypt/decrypt at the application layer | Key loss = data loss; adds latency to PII reads |
| **Single database, `org_id` column** over schema-per-tenant | Simpler queries, easier migrations, lower resource usage | Requires disciplined use of `tenant_query` everywhere |
| **WhatsApp bot as a separate Node.js process** | Uses Baileys library (Node.js only) for WhatsApp Web protocol | Two runtimes to manage; communication via HTTP proxy |

---

## 9. Integration Architecture

### External Service Integrations

| Service | Purpose | Module(s) |
|---|---|---|
| **Google Drive** | Document storage and sync per client | `services/google_drive_handler.py`, `services/document_sync.py` |
| **Google Calendar** | Appointment scheduling | `services/google_calendar.py`, `routes/google_calendar.py` |
| **Stripe** | Payment processing, subscription billing | `services/stripe_service.py`, `routes/payments.py`, `routes/subscription.py` |
| **Twilio** | SMS and WhatsApp messaging | `services/twilio.py`, `routes/twilio.py` |
| **CallHippo** | VoIP calls and SMS | `services/callhippo.py`, `routes/callhippo.py` |
| **Notion** | Knowledge base (AILA Wiki), task sync, ticketing | `services/notion_tasks.py`, `services/notion_sync.py`, `services/notion_tickets.py` |
| **Moskit CRM** | Bidirectional lead/deal sync | `services/moskit.py`, `routes/moskit.py` |
| **Perplexity AI** | Legal research assistant | `services/aila_search.py`, `routes/aila_api.py` |
| **Google Gemini** | Document and letter generation | `services/llm_content_generator.py`, `tools/llm_content_generator.py` |
| **Resend** | Transactional email (alternative to SMTP) | Config only (`RESEND_API_KEY`) |
| **USCIS** | Case status tracking, form data | `services/uscis_status.py`, `services/uscis_forms_service.py` |

### WhatsApp Bot (Node.js Microservice)

The WhatsApp bot runs as a separate Node.js process (`services/whatsapp-bot/server.js`) on port 3001. CaseHub proxies control commands to it:

- `POST /api/bot-control` -- send commands to the bot.
- `GET /api/bot-status` -- check bot connection status.
- `POST /api/bot-toggle` -- enable/disable the bot.

The bot handles:
- Automated client intake via WhatsApp.
- Lead capture and CRM sync (Moskit).
- AI-powered conversation (Maestro/Claude integration).
- Follow-up scheduling and reminders.

### Internal Communication

All integrations follow a consistent pattern:

1. **Configuration** via `.env` variables or per-org database fields.
2. **Service module** in `services/` handles API calls and business logic.
3. **Route module** in `routes/` exposes endpoints to the UI/API.
4. **Graceful degradation** -- missing API keys cause features to be silently disabled, not crashes.
