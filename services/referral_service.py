"""
CaseHub - Referral Management Service
Track referral sources and manage referral commissions.
"""
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum
from decimal import Decimal


class ReferralSource(str, Enum):
    CLIENT = "client"
    ATTORNEY = "attorney"
    WEBSITE = "website"
    GOOGLE = "google"
    SOCIAL_MEDIA = "social_media"
    EVENT = "event"
    ADVERTISING = "advertising"
    OTHER = "other"


class ReferralStatus(str, Enum):
    PENDING = "pending"
    CONVERTED = "converted"
    PAID = "paid"
    CANCELLED = "cancelled"


class ReferralService:
    """Service for managing referrals and referral sources."""

    # Default commission rates
    DEFAULT_COMMISSION_RATES = {
        "flat": 100,  # Flat fee per referral
        "percentage": 5,  # Percentage of case value
    }

    def get_referral_sources(self) -> List[dict]:
        """Get all referral source types."""
        labels = {
            ReferralSource.CLIENT: "Existing Client",
            ReferralSource.ATTORNEY: "Attorney Referral",
            ReferralSource.WEBSITE: "Website",
            ReferralSource.GOOGLE: "Google Search",
            ReferralSource.SOCIAL_MEDIA: "Social Media",
            ReferralSource.EVENT: "Event/Seminar",
            ReferralSource.ADVERTISING: "Advertising",
            ReferralSource.OTHER: "Other"
        }
        return [{"value": s.value, "label": labels.get(s, s.value)} for s in ReferralSource]

    def calculate_commission(
        self,
        case_value: Decimal,
        commission_type: str = "percentage",
        rate: float = None
    ) -> Decimal:
        """Calculate referral commission."""
        if rate is None:
            rate = self.DEFAULT_COMMISSION_RATES.get(commission_type, 0)

        if commission_type == "percentage":
            return Decimal(str(case_value)) * Decimal(str(rate)) / 100
        elif commission_type == "flat":
            return Decimal(str(rate))
        return Decimal("0")

    def get_source_stats(self, referrals: List[dict]) -> dict:
        """Calculate statistics for referral sources."""
        stats = {
            "total_referrals": len(referrals),
            "converted": 0,
            "conversion_rate": 0,
            "total_value": Decimal("0"),
            "total_commission": Decimal("0"),
            "by_source": {}
        }

        for ref in referrals:
            source = ref.get("source", "other")
            if source not in stats["by_source"]:
                stats["by_source"][source] = {"count": 0, "converted": 0, "value": Decimal("0")}

            stats["by_source"][source]["count"] += 1

            if ref.get("status") in ["converted", "paid"]:
                stats["converted"] += 1
                stats["by_source"][source]["converted"] += 1
                stats["by_source"][source]["value"] += Decimal(str(ref.get("case_value", 0)))
                stats["total_value"] += Decimal(str(ref.get("case_value", 0)))
                stats["total_commission"] += Decimal(str(ref.get("commission_amount", 0)))

        if stats["total_referrals"] > 0:
            stats["conversion_rate"] = round(stats["converted"] / stats["total_referrals"] * 100, 1)

        return stats


# SQL for referral tables
CREATE_REFERRAL_TABLE = """
CREATE TABLE IF NOT EXISTS referral_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    company VARCHAR(255),
    commission_type VARCHAR(20) DEFAULT 'percentage',
    commission_rate DECIMAL(10,2) DEFAULT 5.00,
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    total_referrals INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    total_commission_paid DECIMAL(10,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_referral_sources_type ON referral_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_referral_sources_active ON referral_sources(is_active);

CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES referral_sources(id),
    client_id INTEGER REFERENCES clients(id),
    case_id INTEGER REFERENCES cases(id),
    referral_date DATE DEFAULT CURRENT_DATE,
    status VARCHAR(50) DEFAULT 'pending',
    case_value DECIMAL(10,2),
    commission_amount DECIMAL(10,2),
    commission_paid_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_source ON referrals(source_id);
CREATE INDEX IF NOT EXISTS idx_referrals_client ON referrals(client_id);
CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);
"""


# Singleton instance
referral_service = ReferralService()
