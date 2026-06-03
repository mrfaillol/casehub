"""
CaseHub - Centralized Configuration
All settings loaded from environment variables (.env file).
No hardcoded values. No defaults for sensitive fields.
"""
import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # === Organization ===
    ORG_NAME: str = "CaseHub"
    ORG_EMAIL: str = ""
    ORG_DOMAIN: str = ""
    ORG_CENTER_EMAIL: str = ""
    CASE_PREFIX: str = "CH"
    TEAM_MEMBERS: str = ""  # Comma-separated list of team member names

    # === Admin ===
    ADMIN_EMAIL: str = ""
    # No default password — generated at first run

    # === Database ===
    DATABASE_URL: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_be_set(cls, v):
        if not v:
            print("FATAL: DATABASE_URL must be set in .env", file=sys.stderr)
            sys.exit(1)
        return v

    # === Authentication ===
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    COOKIE_NAME: str = "casehub_token"

    # === Server ===
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    BASE_URL: str = ""  # Set in .env (e.g., http://REDACTED-HOST:8002)
    PREFIX: str = "/casehub"
    BASE_DIR: str = str(Path(__file__).parent)
    UPLOAD_DIR: str = ""
    CASEHUB_ENV: str = "development"
    DEBUG: bool = True
    JINJA_BYTECODE_CACHE_DIR: str = "/tmp/casehub-jinja-cache"

    # === Internal Services ===
    WHATSAPP_BOT_URL: str = "http://localhost:3001"
    LM_STUDIO_URL: str = "http://localhost:1234"
    ILC_TOOLS_URL: str = "http://localhost:8000"

    # === Cache ===
    REDIS_URL: str = ""
    DASHBOARD_CACHE_TTL_SECONDS: int = 60

    # === Partner Domains (for email tagging) ===
    PARTNER_DOMAINS: str = ""  # Comma-separated, e.g. "iasuk.org,iasuk.co.uk,ashoorilaw.com"

    # === Team Emails (staff/paralegal contacts) ===
    TEAM_EMAILS: str = ""  # JSON dict, e.g. '{"juliana": {"name": "Juliana", "email": "j@x.com"}, ...}'

    # === Email SMTP ===
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM_NAME: str = ""

    # === Gmail IMAP ===
    GMAIL_CENTER_EMAIL: str = ""
    GMAIL_CENTER_APP_PASSWORD: str = ""

    # === Gmail OAuth (multi-tenant, alpha 2026-05-27) ===
    # Feature flag — set False to hide the Gmail OAuth card and skip route
    # registration. Default True now that Calendar/Drive per-org pattern is
    # battle-tested.
    GMAIL_OAUTH_ENABLED: bool = True
    GMAIL_DEFAULT_ACCOUNTS: str = "info"

    # === Google Drive ===
    GOOGLE_DRIVE_CREDENTIALS_PATH: str = ""
    GOOGLE_DRIVE_TOKEN_PATH: str = ""
    GOOGLE_DRIVE_ROOT_ID: str = ""
    GOOGLE_DRIVE_TASKS_ID: str = ""
    GOOGLE_CALENDAR_CREDENTIALS_PATH: str = ""
    GOOGLE_CALENDAR_TOKEN_DIR: str = ""
    GOOGLE_CALENDAR_LEGACY_TOKEN_PATH: str = ""
    GOOGLE_CALENDAR_DEFAULT_ACCOUNTS: str = "center,info"
    GOOGLE_CALENDAR_SEND_UPDATES: str = "none"
    GOOGLE_CALENDAR_CREATE_MEET: bool = False
    GOOGLE_CALENDAR_EVENT_DETAIL_MODE: str = "details"
    GOOGLE_CALENDAR_EVENT_LANG: str = "pt-BR"

    # === Integrations ===
    MOSKIT_API_KEY: str = ""
    MOSKIT_RESPONSIBLE_ID: str = ""
    MOSKIT_PIPELINE_ID: str = ""

    CALLHIPPO_API_KEY: str = ""
    CALLHIPPO_FROM: str = ""
    CALLHIPPO_EMAIL: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_WHATSAPP_FROM: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # === Self-service signup (Fatia B — gated by Council ruling) ===
    # Master kill switch. While FALSE, /signup serves the legacy
    # access_request form and no Organization is auto-created.
    SELF_SERVICE_SIGNUP_ENABLED: bool = False
    # Cloudflare Turnstile (https://www.cloudflare.com/products/turnstile/).
    # When both keys are empty, captcha is bypassed in dev mode.
    CF_TURNSTILE_SITE_KEY: str = ""
    CF_TURNSTILE_SECRET_KEY: str = ""
    # Email-verification token lifetime (hours)
    EMAIL_VERIFY_TOKEN_TTL_HOURS: int = 24
    # Rate-limit caps on signup attempts
    SIGNUP_RATE_LIMIT_PER_IP_PER_HOUR: int = 5
    SIGNUP_RATE_LIMIT_PER_DOMAIN_PER_DAY: int = 3

    NOTION_TOKEN: str = ""
    NOTION_AILA_WIKI_DB: str = ""
    NOTION_TICKET_DATABASE_ID: str = ""

    PERPLEXITY_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    RESEND_API_KEY: str = ""

    # === DataJud (CNJ) ===
    DATAJUD_API_KEY: str = ""

    # === Brazilian Legal APIs ===
    ESCAVADOR_API_KEY: str = ""
    JUSBRASIL_API_KEY: str = ""

    # === Product ===
    CASEHUB_PRODUCT: str = "lite"  # "lite" is the 2026-05 Basic default; use "immigration" for ILC legacy.
    DEMO_MODE: bool = False  # When True, blocks external integrations, exports, destructive actions
    DEFAULT_CURRENCY: str = ""  # Auto-set per product if empty: USD (immigration), BRL (lite)
    DEFAULT_TIMEZONE: str = ""  # Auto-set per product if empty
    CASEHUB_RELEASE_NOTICE_ENABLED: bool = False
    CASEHUB_RELEASE_NOTICE_ID: str = "casehub-release-notice"
    CASEHUB_MAESTRO_FAB_ENABLED: bool = False
    CASEHUB_MCP_CLIENT_ENABLED: bool = False
    CASEHUB_INTEGRATIONS_GATEWAY_ENABLED: bool = False
    CASEHUB_IMPROVEMENT_TASKS_ENABLED: str = ""
    CASEHUB_IMPROVEMENT_HMAC_KEY: str = ""
    CASEHUB_OPS_HMAC_KEY: str = ""

    # === WhatsApp inbound bridge ===
    # HMAC secret shared with services/whatsapp-bot/casehub-bridge.js.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    CASEHUB_INBOUND_HMAC_SECRET: str = ""
    # Public URL the Node bridge will POST to. Default to local dev.
    CASEHUB_API_URL: str = "http://localhost:8001"

    # === Maestro pipeline (gated; default OFF until Council ruling) ===
    # When True, inbound flow records labelled samples into maestro_training_samples.
    # Per-org consent (org_settings.maestro_training_consent) is still required.
    MAESTRO_TRAINING_COLLECTION_ENABLED: bool = False

    # === Maestro repo-aware grounding (gated; default OFF) ===
    # When True AND a repo index exists (build via scripts/maestro_index_repo.py),
    # product/"how does CaseHub work" questions are answered with RAG grounding +
    # source-file citation, refusing to invent. The index holds only CaseHub
    # product code/docs (no tenant data, no secrets) so it is shared across tenants.
    # Safe to flip on once the index is built; OFF keeps current behaviour.
    CASEHUB_MAESTRO_REPO_AWARE_ENABLED: bool = False

    # === Alerts ===
    ALERT_PHONE: str = ""
    ALERT_WHATSAPP: str = ""

    # === CRM Webhook ===
    CRM_WEBHOOK_API_KEY: str = ""

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_set(cls, v):
        if not v:
            print("FATAL: SECRET_KEY must be set in .env", file=sys.stderr)
            sys.exit(1)
        return v

    @property
    def upload_path(self) -> str:
        return self.UPLOAD_DIR or os.path.join(self.BASE_DIR, "uploads")

    @property
    def from_email(self) -> str:
        name = self.SMTP_FROM_NAME or self.ORG_NAME
        email = self.SMTP_USER or self.ORG_EMAIL
        return f"{name} <{email}>"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
