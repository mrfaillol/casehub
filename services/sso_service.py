"""
CaseHub - SSO Service
Single Sign-On with Google and Microsoft OAuth2.
"""
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from enum import Enum
from urllib.parse import urlencode


class SSOProvider(str, Enum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class SSOService:
    """Service for managing SSO authentication."""

    # OAuth2 endpoints
    PROVIDERS = {
        SSOProvider.GOOGLE: {
            "name": "Google",
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
            "scopes": ["openid", "email", "profile"],
            "icon": "fab fa-google",
            "color": "#DB4437"
        },
        SSOProvider.MICROSOFT: {
            "name": "Microsoft",
            "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
            "scopes": ["openid", "email", "profile", "User.Read"],
            "icon": "fab fa-microsoft",
            "color": "#00A4EF"
        }
    }

    def __init__(self):
        # These would come from environment variables in production
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.microsoft_client_id = os.environ.get("MICROSOFT_CLIENT_ID", "")
        self.microsoft_client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "")

    def get_provider_config(self, provider: str) -> Optional[dict]:
        """Get configuration for a provider."""
        return self.PROVIDERS.get(provider)

    def get_available_providers(self) -> list:
        """Get list of configured providers."""
        providers = []

        if self.google_client_id:
            providers.append({
                "id": SSOProvider.GOOGLE,
                **self.PROVIDERS[SSOProvider.GOOGLE]
            })

        if self.microsoft_client_id:
            providers.append({
                "id": SSOProvider.MICROSOFT,
                **self.PROVIDERS[SSOProvider.MICROSOFT]
            })

        return providers

    def generate_state(self) -> str:
        """Generate a secure state token for OAuth2."""
        return secrets.token_urlsafe(32)

    def get_authorization_url(
        self,
        provider: str,
        redirect_uri: str,
        state: str
    ) -> Optional[str]:
        """Generate OAuth2 authorization URL."""
        config = self.get_provider_config(provider)
        if not config:
            return None

        client_id = ""
        if provider == SSOProvider.GOOGLE:
            client_id = self.google_client_id
        elif provider == SSOProvider.MICROSOFT:
            client_id = self.microsoft_client_id

        if not client_id:
            return None

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
            "access_type": "offline",
            "prompt": "select_account"
        }

        return f"{config['auth_url']}?{urlencode(params)}"

    def get_client_credentials(self, provider: str) -> tuple:
        """Get client ID and secret for a provider."""
        if provider == SSOProvider.GOOGLE:
            return self.google_client_id, self.google_client_secret
        elif provider == SSOProvider.MICROSOFT:
            return self.microsoft_client_id, self.microsoft_client_secret
        return "", ""

    def verify_state(self, stored_state: str, received_state: str) -> bool:
        """Verify OAuth2 state token."""
        return secrets.compare_digest(stored_state, received_state)

    def map_user_info(self, provider: str, user_data: dict) -> dict:
        """Map provider user info to standard format."""
        if provider == SSOProvider.GOOGLE:
            return {
                "provider": provider,
                "provider_id": user_data.get("sub"),
                "email": user_data.get("email"),
                "email_verified": user_data.get("email_verified", False),
                "name": user_data.get("name"),
                "first_name": user_data.get("given_name"),
                "last_name": user_data.get("family_name"),
                "picture": user_data.get("picture")
            }
        elif provider == SSOProvider.MICROSOFT:
            return {
                "provider": provider,
                "provider_id": user_data.get("id"),
                "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                "email_verified": True,
                "name": user_data.get("displayName"),
                "first_name": user_data.get("givenName"),
                "last_name": user_data.get("surname"),
                "picture": None
            }
        return {}


# SQL for SSO tables
CREATE_SSO_TABLE = """
CREATE TABLE IF NOT EXISTS sso_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    profile_data JSONB,
    is_primary BOOLEAN DEFAULT false,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_sso_user ON sso_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_sso_provider ON sso_connections(provider, provider_user_id);
CREATE INDEX IF NOT EXISTS idx_sso_email ON sso_connections(email);

CREATE TABLE IF NOT EXISTS sso_states (
    id SERIAL PRIMARY KEY,
    state VARCHAR(100) UNIQUE NOT NULL,
    provider VARCHAR(50) NOT NULL,
    redirect_url VARCHAR(500),
    org_id INTEGER NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '10 minutes'
);

-- Backfill column for pre-existing tables (idempotent, NULL allowed for compat).
ALTER TABLE sso_states ADD COLUMN IF NOT EXISTS org_id INTEGER NULL;

CREATE INDEX IF NOT EXISTS idx_sso_state ON sso_states(state);
"""


# Singleton instance
sso_service = SSOService()
