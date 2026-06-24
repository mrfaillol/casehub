# CaseHub

**Versao publica:** `0.9.12-alpha`
**Data do snapshot:** 2026-06-23
**Estado:** alpha em desenvolvimento ativo, com acesso manual para escritorios.

CaseHub e um framework juridico para escritorios brasileiros: prazos,
processos, documentos, agenda, comunicacao e IA contextual no mesmo ambiente.
Este repositorio publico e um snapshot sanitizado do produto alpha, sem dados de
clientes, segredos, sessoes WhatsApp, uploads, logs, backups ou topologia de
producao.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white" alt="PostgreSQL 15">
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License">
</p>

---

## Products

### CaseHub

Construido para escritorios brasileiros (inspirado por ADVbox, Astrea, LegalOne).

- Campos juridicos brasileiros -- CPF, RG, CNPJ, numero_processo, vara, comarca, tribunal
- Controladoria juridica: prazos fatais, responsaveis, fontes e status
- Tarefas com kanban dinamico, anexos, multi-responsavel e arquivamento reversivel
- Agenda integrada ao Google Calendar
- Processo tracking, prazos processuais, tribunal integration, OAB validation
- Gmail/SMTP, Notion, Slack e Google Workspace integration
- WhatsApp Chat e WhatsApp Bot (`whatsapp-web.js`, sessoes isoladas por org)
- Maestro: assistente contextual com politica de IA por escritorio
- Dark/light mode, pt-BR interface
- Currency: BRL | Language: pt-BR | Timezone: America/Sao_Paulo

### Shared across both products

Client management, case tracking, document management, task board, calendar, billing & invoicing, email integration, client portal, notifications, audit logging, RBAC (5 roles), 2FA/step-up, reports, team chat, SSO, webhooks, REST API, multi-tenancy with per-org branding.

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
git clone https://github.com/mrfaillol/casehub.git && cd casehub
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

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

```text
casehub/
|-- app.py
|-- core/                 # app factory, assets, runtime Jinja, flags
|-- middleware/           # tenant, permissoes, rate limit
|-- models/               # SQLAlchemy
|-- routes/               # FastAPI routers
|-- services/             # dominio e integracoes
|-- templates/            # Jinja
|-- static/               # CSS, JS, brand kit
|-- migrations/           # SQL idempotente
|-- services/whatsapp-bot # bot Node.js
|-- docs/
`-- tests/
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
| `CASEHUB_PRODUCT` | `immigration` | `lite`, `immigration` ou `whitelabel` |
| `DEFAULT_CURRENCY` | Auto per product | `USD` or `BRL` |
| `DEFAULT_TIMEZONE` | Auto per product | IANA timezone |
| `PREFIX` | `/casehub` | Prefixo HTTP |

### Optional integrations

Stripe, Notion, Google Drive, Google Calendar, Gmail/SMTP, Twilio/WhatsApp, Gemini AI, Perplexity, Resend, OpenRouter, NVIDIA API, PDPJ, Calendly. Integracoes opcionais usam variaveis por provedor, por exemplo `GOOGLE_*`, `GMAIL_*`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `GEMINI_API_KEY`, `SMTP_*`, `PDPJ_*`, `CALENDLY_*`, `NOTION_*` e `CASEHUB_INBOUND_HMAC_SECRET`.

See `.env.example` for all variables.

---

## IA e provedores

CaseHub nao depende de um unico provedor de IA. A camada Maestro pode ser
configurada por escritorio conforme politica de dados, custo e preferencia:

- local/self-hosted, incluindo modelos estilo Hermes via runtime compativel;
- NVIDIA API;
- OpenRouter ou gateway compativel;
- Gemini;
- Claude, Codex, GLM ou outro provedor via adaptador apropriado.

Dados reais de clientes nao devem sair do tenant sem configuracao explicita,
base legal e politica do escritorio. Repos publicos devem usar apenas fixtures
sinteticas.

---

## White-Label Customization

### Organization branding

Each tenant can customize logo, favicon, primary/secondary colors, and display name via the Branding settings page (`/casehub/settings/branding`) or the API.

### Custom domains

Subdomain or custom domain routing per organization. See [docs/WHITE_LABEL_GUIDE.md](docs/WHITE_LABEL_GUIDE.md).

### Plans & feature flags

Three plans (`starter`, `professional`, `enterprise`) with per-org JSON overrides. Features resolve as: plan defaults -> org overrides -> hardcoded fallback.

---

## MCP, SDK e CLI

Projetos relacionados mantidos localmente:

| Projeto | Versao atual | Estado |
| --- | --- | --- |
| `casehub-mcp-server` | `0.2.0` | MCP stdio, read-only, 6 ferramentas allowlisted |
| `casehub-sdk-py` | `0.1.x` | SDK Python em WIP |
| `casehub-cli` | `0.1.x` | CLI em WIP sobre o SDK |

Ferramentas MCP documentadas no v0.2: `search_cases`, `get_case`, `list_clients`,
`validate_documento`, `get_system_status`, `list_templates`.

---

## Tech Stack

Python 3.12, FastAPI 0.109, SQLAlchemy 2.0, PostgreSQL 15, Redis 7, Jinja2, TailwindCSS, JWT + bcrypt, Fernet encryption, Docker, Nginx, PM2, Google Gemini, Perplexity.

---

## Documentacao

| Document | Description |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, app factory, request flow |
| [DEVELOPER_SETUP.md](docs/DEVELOPER_SETUP.md) | Local dev environment setup |
| [WHITE_LABEL_GUIDE.md](docs/WHITE_LABEL_GUIDE.md) | Tenant creation, branding, domains, feature flags |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | REST API endpoints |
| [USER_MANUAL.md](docs/USER_MANUAL.md) | End-user manual |
| [SECURITY.md](SECURITY.md) | Politica de seguranca e divulgacao responsavel |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Como contribuir |

---

## Politica do repositorio publico

Antes de publicar qualquer mudanca:

- rodar scan de segredo e PII;
- remover logs, uploads, backups, caches, sessoes e dados de cliente;
- usar apenas dados demonstrativos;
- nao commitar `.env`, credenciais Google, tokens WhatsApp, `.wwebjs_auth`,
  dumps de banco, screenshots reais com nomes ou artefatos de VPS.

---

## License

Este snapshot publico nao inclui um arquivo `LICENSE`. Ate que uma licenca seja
adicionada, nao assuma permissao de uso comercial, redistribuicao ou hospedagem
de uma instancia derivada fora dos termos combinados com os mantenedores.
