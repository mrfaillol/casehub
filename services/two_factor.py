"""
CaseHub - Two-Factor Authentication Service
TOTP-based 2FA for admin users
"""
import pyotp
import qrcode
import io
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text


class TwoFactorService:
    """Service for managing two-factor authentication."""

    # Per-process guard so the additive DDL runs at most once per engine
    # (keyed by the engine the session is bound to). Avoids per-call overhead
    # while staying safe if called many times. Mirrors the lazy-ensure pattern
    # of services.google_calendar._ensure_sync_schema (CaseHub has no Alembic).
    _schema_ensured: set = set()

    def __init__(self, db: Session):
        self.db = db
        self.issuer = "CaseHub"

    def _ensure_2fa_schema(self) -> None:
        """Additive, idempotent self-healing schema for 2FA.

        The 2FA feature shipped without a migration, so environments that were
        not manually patched lack the totp_* columns on `users` and the
        `backup_codes` table — get_2fa_status then raised SQLAlchemyError and
        the UI showed "2FA temporariamente indisponivel". This guarantees the
        schema before any 2FA query so DEV/rebuilds/other orgs self-heal.

        ADDITIVE ONLY (no DROP, no ALTER ... DROP COLUMN) — no data loss. Safe
        to call on every public method; guarded to run the DDL once per engine.
        Mirrors services.google_calendar.GoogleCalendarService._ensure_sync_schema.
        """
        bind = self.db.get_bind()
        if bind is not None:
            key = id(bind.engine) if hasattr(bind, "engine") else id(bind)
            if key in TwoFactorService._schema_ensured:
                return
        else:
            key = None

        dialect = bind.dialect.name if bind is not None else "sqlite"
        ts_type = "TIMESTAMPTZ" if dialect == "postgresql" else "TIMESTAMP"

        def _has_column(table: str, column: str) -> bool:
            if dialect == "postgresql":
                return bool(self.db.execute(
                    text("""
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = :table AND column_name = :column
                    """),
                    {"table": table, "column": column},
                ).first())
            return any(
                row[1] == column
                for row in self.db.execute(text(f"PRAGMA table_info({table})")).fetchall()
            )

        # Additive columns on users (totp_*). NOT NULL DEFAULT is applied via the
        # DEFAULT so existing rows backfill atomically; no data loss.
        additions = [
            ("users", "totp_secret", "TEXT"),
            ("users", "totp_enabled", "BOOLEAN NOT NULL DEFAULT false"),
            ("users", "totp_setup_at", ts_type),
            ("users", "totp_verified_at", ts_type),
        ]
        for table, column, definition in additions:
            try:
                if not _has_column(table, column):
                    self.db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                    self.db.commit()
            except Exception:
                self.db.rollback()

        # backup_codes table + supporting index. SERIAL is Postgres; SQLite uses
        # INTEGER PRIMARY KEY AUTOINCREMENT. Both IF NOT EXISTS (idempotent).
        try:
            id_type = "SERIAL PRIMARY KEY" if dialect == "postgresql" \
                else "INTEGER PRIMARY KEY AUTOINCREMENT"
            self.db.execute(text(f"""
                CREATE TABLE IF NOT EXISTS backup_codes (
                    id {id_type},
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code TEXT NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT false,
                    created_at {ts_type} NOT NULL DEFAULT NOW(),
                    used_at {ts_type}
                )
            """) if dialect == "postgresql" else text(f"""
                CREATE TABLE IF NOT EXISTS backup_codes (
                    id {id_type},
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code TEXT NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT 0,
                    created_at {ts_type} NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    used_at {ts_type}
                )
            """))
            self.db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_backup_codes_user_id "
                "ON backup_codes (user_id)"
            ))
            self.db.commit()
        except Exception:
            self.db.rollback()

        if key is not None:
            TwoFactorService._schema_ensured.add(key)

    def generate_secret(self, user_id: int) -> Dict[str, Any]:
        """Generate a new TOTP secret for a user."""
        from models import User

        self._ensure_2fa_schema()
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "User not found"}

        # Generate new secret
        secret = pyotp.random_base32()
        
        # Store secret (not enabled yet until verified)
        self.db.execute(text("""
            UPDATE users SET
                totp_secret = :secret,
                totp_enabled = false,
                totp_setup_at = NOW()
            WHERE id = :user_id
        """), {"secret": secret, "user_id": user_id})
        self.db.commit()

        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=self.issuer
        )

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            "success": True,
            "secret": secret,
            "qr_code": f"data:image/png;base64,{qr_base64}",
            "uri": uri
        }

    def verify_and_enable(self, user_id: int, code: str) -> Dict[str, Any]:
        """Verify TOTP code and enable 2FA for user."""
        self._ensure_2fa_schema()
        # Get user's secret
        result = self.db.execute(text("""
            SELECT totp_secret FROM users WHERE id = :user_id
        """), {"user_id": user_id}).fetchone()

        if not result or not result.totp_secret:
            return {"success": False, "error": "No 2FA setup in progress"}

        secret = result.totp_secret
        totp = pyotp.TOTP(secret)

        # Verify code
        if not totp.verify(code):
            return {"success": False, "error": "Invalid code. Please try again."}

        # Enable 2FA
        self.db.execute(text("""
            UPDATE users SET 
                totp_enabled = true,
                totp_verified_at = NOW()
            WHERE id = :user_id
        """), {"user_id": user_id})

        # Generate backup codes
        backup_codes = self._generate_backup_codes(user_id)

        return {
            "success": True,
            "message": "2FA enabled successfully",
            "backup_codes": backup_codes
        }

    def verify_code(self, user_id: int, code: str) -> bool:
        """Verify a TOTP code for login."""
        self._ensure_2fa_schema()
        # Get user's secret
        result = self.db.execute(text("""
            SELECT totp_secret, totp_enabled FROM users WHERE id = :user_id
        """), {"user_id": user_id}).fetchone()

        if not result or not result.totp_enabled:
            return True  # 2FA not enabled, pass through

        if not result.totp_secret:
            return True

        totp = pyotp.TOTP(result.totp_secret)
        
        # Check TOTP code
        if totp.verify(code, valid_window=1):  # Allow 1 window tolerance (30 sec)
            return True
        
        # Check backup codes
        if self._check_backup_code(user_id, code):
            return True
        
        return False

    def is_2fa_required(self, user_id: int) -> bool:
        """Check if user has 2FA enabled."""
        self._ensure_2fa_schema()
        result = self.db.execute(text("""
            SELECT totp_enabled FROM users WHERE id = :user_id
        """), {"user_id": user_id}).fetchone()

        return result and result.totp_enabled

    def disable_2fa(self, user_id: int, code: str) -> Dict[str, Any]:
        """Disable 2FA for a user (requires valid code)."""
        self._ensure_2fa_schema()
        if not self.verify_code(user_id, code):
            return {"success": False, "error": "Invalid verification code"}

        self.db.execute(text("""
            UPDATE users SET 
                totp_secret = NULL,
                totp_enabled = false
            WHERE id = :user_id
        """), {"user_id": user_id})
        
        # Remove backup codes
        self.db.execute(text("""
            DELETE FROM backup_codes WHERE user_id = :user_id
        """), {"user_id": user_id})
        
        self.db.commit()

        return {"success": True, "message": "2FA disabled successfully"}

    def _generate_backup_codes(self, user_id: int, count: int = 10) -> list:
        """Generate backup codes for a user."""
        import secrets
        
        self.db.execute(text("DELETE FROM backup_codes WHERE user_id = :user_id"),
                        {"user_id": user_id})
        
        codes = []
        for _ in range(count):
            code = secrets.token_hex(4).upper()  # 8 character hex code
            codes.append(code)
            
            self.db.execute(text("""
                INSERT INTO backup_codes (user_id, code, used, created_at)
                VALUES (:user_id, :code, false, NOW())
            """), {"user_id": user_id, "code": code})
        
        self.db.commit()
        return codes

    def _check_backup_code(self, user_id: int, code: str) -> bool:
        """Check and consume a backup code."""
        code = code.upper().replace("-", "").replace(" ", "")
        
        result = self.db.execute(text("""
            SELECT id FROM backup_codes 
            WHERE user_id = :user_id AND code = :code AND used = false
        """), {"user_id": user_id, "code": code}).fetchone()

        if result:
            self.db.execute(text("""
                UPDATE backup_codes SET used = true, used_at = NOW()
                WHERE id = :id
            """), {"id": result.id})
            self.db.commit()
            return True
        
        return False

    def get_2fa_status(self, user_id: int) -> Dict[str, Any]:
        """Get 2FA status for a user."""
        self._ensure_2fa_schema()
        result = self.db.execute(text("""
            SELECT totp_enabled, totp_setup_at, totp_verified_at 
            FROM users WHERE id = :user_id
        """), {"user_id": user_id}).fetchone()

        if not result:
            return {"enabled": False, "setup_at": None}

        # Count remaining backup codes
        backup_count = self.db.execute(text("""
            SELECT COUNT(*) FROM backup_codes WHERE user_id = :user_id AND used = false
        """), {"user_id": user_id}).scalar() or 0

        return {
            "enabled": result.totp_enabled or False,
            "setup_at": result.totp_setup_at.isoformat() if result.totp_setup_at else None,
            "verified_at": result.totp_verified_at.isoformat() if result.totp_verified_at else None,
            "backup_codes_remaining": backup_count
        }
