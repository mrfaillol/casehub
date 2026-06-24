"""
CaseHub - Tenant Model & Query Helpers
Provides the Organization SQLAlchemy model and helper functions
for tenant-scoped database queries.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import Session, Query

from .base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    domain = Column(String(255), unique=True, nullable=True)
    logo_url = Column(String(500))
    favicon_url = Column(String(500))
    primary_color = Column(String(7), default="#1a56db")
    secondary_color = Column(String(7), default="#7c3aed")

    # Contact
    email = Column(String(255))
    phone = Column(String(50))
    website = Column(String(255))
    address = Column(Text)

    # Operational
    timezone = Column(String(50), default="America/New_York")
    locale = Column(String(10), default="en")
    case_prefix = Column(String(10), default="CH")
    currency = Column(String(3), default="USD")

    # Integrations (encrypted at app level)
    google_drive_root_id = Column(String(255))
    google_credentials_path = Column(String(500))
    smtp_host = Column(String(255))
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(255))
    smtp_pass = Column(String(255))
    smtp_from_name = Column(String(255))

    # Subscription
    # Spec (Equipe CaseHub, 28/05/2026): usuários ILIMITADOS por enquanto em todos os
    # planos. max_users = -1 => unlimited (ver middleware/plan_enforcement.py).
    plan = Column(String(50), default="office")
    max_users = Column(Integer, default=-1)
    max_clients = Column(Integer, default=100)
    max_storage_gb = Column(Integer, default=10)
    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255))
    subscription_status = Column(String(50), default="active")

    # Feature flags
    features = Column(JSON, default={})

    # Extended settings (per-org theming, font, accent, etc.)
    settings = Column(JSON, default={})

    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Provisioning provenance + slug lockdown (Fatia A — self-service signup)
    created_via = Column(String(20), default="manual")  # 'manual' | 'self_service' | 'manual_migration'
    subdomain_locked = Column(Boolean, default=False)

    def has_feature(self, feature_name: str) -> bool:
        """Check if this organization has a specific feature enabled."""
        if not self.features:
            return False
        return self.features.get(feature_name, False)

    @property
    def from_email(self) -> str:
        """Formatted sender email."""
        name = self.smtp_from_name or self.name
        email = self.smtp_user or self.email
        if email:
            return f"{name} <{email}>"
        return ""

    def __repr__(self):
        return f"<Organization {self.slug} ({self.name})>"


# =============================================================================
# Tenant-scoped query helpers
# =============================================================================

def tenant_query(db: Session, model, org_id: int) -> Query:
    """
    Return a query pre-filtered by org_id.

    Usage:
        clients = tenant_query(db, Client, org_id).filter(Client.status == 'active').all()
    """
    return db.query(model).filter(model.org_id == org_id)


def tenant_count(db: Session, model, org_id: int) -> int:
    """Count records for a specific tenant."""
    return db.query(model).filter(model.org_id == org_id).count()


def get_org_by_id(db: Session, org_id: int) -> Organization:
    """Fetch organization by primary key."""
    return db.query(Organization).filter(Organization.id == org_id).first()


def get_org_by_slug(db: Session, slug: str) -> Organization:
    """Fetch organization by slug."""
    return (
        db.query(Organization)
        .filter(Organization.slug == slug, Organization.is_active == True)
        .first()
    )


def get_org_by_domain(db: Session, domain: str) -> Organization:
    """Fetch organization by custom domain."""
    return (
        db.query(Organization)
        .filter(Organization.domain == domain, Organization.is_active == True)
        .first()
    )


def get_all_active_orgs(db: Session) -> list:
    """Fetch all active organizations."""
    return db.query(Organization).filter(Organization.is_active == True).all()


def create_org(db: Session, **kwargs) -> Organization:
    """Create a new organization."""
    org = Organization(**kwargs)
    db.add(org)
    db.flush()
    return org


def check_org_limits(db: Session, org: Organization, model) -> bool:
    """
    Check if an org has reached its limit for a given model.

    Usage:
        from models.client import Client
        if not check_org_limits(db, org, Client):
            raise HTTPException(403, "Client limit reached")
    """
    count = tenant_count(db, model, org.id)

    # Map model tablename to org limit field
    limits = {
        "users": org.max_users,
        "clients": org.max_clients,
    }

    limit = limits.get(model.__tablename__)
    if limit is None:
        return True  # No limit defined for this model

    return count < limit
