"""
CaseHub - Auto-Numbering Service
Generates customizable case and client numbers.
Formats: {YYYY}, {YY}, {MM}, {DD}, {####}, {#####}, {DEPT}, {TYPE}
"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import json


class NumberingService:
    """Service for generating auto-numbers for cases and clients."""

    # Default formats
    DEFAULT_CASE_FORMAT = "CASE-{YYYY}-{####}"
    DEFAULT_CLIENT_FORMAT = "CLT-{YYYY}-{####}"

    def __init__(self, db: Session):
        self.db = db

    def get_settings(self) -> dict:
        """Get numbering settings from database."""
        try:
            result = self.db.execute(text("""
                SELECT config_value FROM app_settings WHERE config_key = 'numbering'
            """))
            row = result.fetchone()
            if row:
                return json.loads(row[0])
        except Exception:
            pass

        # Return defaults
        return {
            "case_format": self.DEFAULT_CASE_FORMAT,
            "client_format": self.DEFAULT_CLIENT_FORMAT,
            "case_counter": 1,
            "client_counter": 1,
            "reset_annually": True,
            "last_reset_year": datetime.now().year
        }

    def save_settings(self, settings: dict):
        """Save numbering settings to database."""
        try:
            self.db.execute(text("""
                INSERT INTO app_settings (config_key, config_value, updated_at)
                VALUES ('numbering', :value, NOW())
                ON CONFLICT (config_key) DO UPDATE SET config_value = :value, updated_at = NOW()
            """), {"value": json.dumps(settings)})
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    def _get_next_counter(self, counter_type: str) -> int:
        """Get and increment the counter for cases or clients."""
        settings = self.get_settings()
        now = datetime.now()

        # Check if we need to reset counters annually
        if settings.get("reset_annually", True):
            if settings.get("last_reset_year", now.year) != now.year:
                settings["case_counter"] = 1
                settings["client_counter"] = 1
                settings["last_reset_year"] = now.year

        # Get current counter and increment
        counter_key = f"{counter_type}_counter"
        counter = settings.get(counter_key, 1)
        settings[counter_key] = counter + 1

        # Save updated settings
        self.save_settings(settings)

        return counter

    def _format_number(self, format_str: str, counter: int, **kwargs) -> str:
        """Format the number string with placeholders."""
        now = datetime.now()

        # Replace date placeholders
        result = format_str
        result = result.replace("{YYYY}", str(now.year))
        result = result.replace("{YY}", str(now.year)[-2:])
        result = result.replace("{MM}", f"{now.month:02d}")
        result = result.replace("{DD}", f"{now.day:02d}")

        # Replace counter placeholders (varying lengths)
        for i in range(6, 1, -1):  # Try {######} down to {##}
            placeholder = "{" + "#" * i + "}"
            if placeholder in result:
                result = result.replace(placeholder, f"{counter:0{i}d}")
                break

        # Replace custom placeholders from kwargs
        for key, value in kwargs.items():
            result = result.replace("{" + key.upper() + "}", str(value))

        return result

    def generate_case_number(self, visa_type: str = None, department: str = None) -> str:
        """Generate the next case number."""
        settings = self.get_settings()
        format_str = settings.get("case_format", self.DEFAULT_CASE_FORMAT)
        counter = self._get_next_counter("case")

        kwargs = {}
        if visa_type:
            # Create short code from visa type (e.g., "EB-1A" -> "EB1A")
            kwargs["type"] = visa_type.replace("-", "").replace(" ", "")[:5]
        if department:
            kwargs["dept"] = department[:3].upper()

        return self._format_number(format_str, counter, **kwargs)

    def generate_client_number(self) -> str:
        """Generate the next client number."""
        settings = self.get_settings()
        format_str = settings.get("client_format", self.DEFAULT_CLIENT_FORMAT)
        counter = self._get_next_counter("client")

        return self._format_number(format_str, counter)

    def preview_format(self, format_str: str, entity_type: str = "case") -> str:
        """Preview what a format would look like without incrementing counters."""
        settings = self.get_settings()
        counter = settings.get(f"{entity_type}_counter", 1)

        kwargs = {}
        if entity_type == "case":
            kwargs["type"] = "EB1A"
            kwargs["dept"] = "IMM"

        return self._format_number(format_str, counter, **kwargs)


# SQL to create the app_settings table
CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_settings_key ON app_settings(config_key);
"""
