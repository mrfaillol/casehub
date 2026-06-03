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

    def __init__(self, db: Session):
        self.db = db
        self.issuer = "CaseHub"

    def generate_secret(self, user_id: int) -> Dict[str, Any]:
        """Generate a new TOTP secret for a user."""
        from models import User
        
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
        result = self.db.execute(text("""
            SELECT totp_enabled FROM users WHERE id = :user_id
        """), {"user_id": user_id}).fetchone()

        return result and result.totp_enabled

    def disable_2fa(self, user_id: int, code: str) -> Dict[str, Any]:
        """Disable 2FA for a user (requires valid code)."""
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
