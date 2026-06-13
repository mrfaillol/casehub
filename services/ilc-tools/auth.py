#!/usr/bin/env python3
"""
CaseHub - Authentication Module
Handles user registration, login, 2FA, and session management.
Version: 1.0.0
"""

import os
import secrets
import string
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import json
import logging

# Security libraries
from passlib.context import CryptContext
import pyotp
import qrcode
import io
import base64

# JWT
from jose import JWTError, jwt

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 480
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# Database file (SQLite for now, upgrade to PostgreSQL later)
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
OTP_FILE = DATA_DIR / "email_otps.json"

# =============================================================================
# PASSWORD UTILITIES
# =============================================================================

def generate_strong_password(length: int = 16) -> str:
    """Generate a cryptographically strong password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
    # Ensure at least one of each type
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()_+-=")
    ]
    # Fill the rest randomly
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    # Shuffle to randomize positions
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# =============================================================================
# USER MANAGEMENT (JSON-based for now)
# =============================================================================

def load_users() -> Dict[str, Any]:
    """Load users from JSON file."""
    if USERS_FILE.exists():
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_users(users: Dict[str, Any]):
    """Save users to JSON file."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2, default=str)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email."""
    users = load_users()
    return users.get(email.lower())


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username."""
    users = load_users()
    for user in users.values():
        if user.get("username", "").lower() == username.lower():
            return user
    return None


def create_user(email: str, username: str, full_name: str) -> Dict[str, Any]:
    """Create a new user with pending approval status."""
    users = load_users()
    email = email.lower()

    if email in users:
        raise ValueError("Email already registered")

    if get_user_by_username(username):
        raise ValueError("Username already taken")

    # Generate strong password
    temp_password = generate_strong_password(16)

    user = {
        "id": secrets.token_urlsafe(16),
        "email": email,
        "username": username.lower(),
        "full_name": full_name,
        "password_hash": hash_password(temp_password),
        "totp_secret": None,
        "preferred_2fa": "totp",
        "status": "pending_approval",
        "is_admin": False,
        "is_super_admin": False,
        "must_change_password": True,
        "created_at": datetime.now().isoformat(),
        "approved_at": None,
        "approved_by": None,
        "last_login": None
    }

    users[email] = user
    save_users(users)

    logger.info(f"New user registered: {email} (pending approval)")

    # Return user with temp password (only returned once!)
    return {**user, "temp_password": temp_password}


def approve_user(email: str, approved_by_email: str) -> Dict[str, Any]:
    """Approve a pending user."""
    users = load_users()
    email = email.lower()

    if email not in users:
        raise ValueError("User not found")

    user = users[email]
    if user["status"] != "pending_approval":
        raise ValueError("User is not pending approval")

    # Generate new password for approved user
    new_password = generate_strong_password(16)

    user["status"] = "active"
    user["approved_at"] = datetime.now().isoformat()
    user["approved_by"] = approved_by_email
    user["password_hash"] = hash_password(new_password)
    user["must_change_password"] = True

    users[email] = user
    save_users(users)

    logger.info(f"User approved: {email} by {approved_by_email}")

    return {**user, "temp_password": new_password}


def update_user(email: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update user fields."""
    users = load_users()
    email = email.lower()

    if email not in users:
        raise ValueError("User not found")

    # Protect sensitive fields
    protected = ["id", "email", "password_hash", "is_super_admin"]
    for field in protected:
        updates.pop(field, None)

    users[email].update(updates)
    save_users(users)

    return users[email]


def change_password(email: str, new_password: str):
    """Change user password."""
    users = load_users()
    email = email.lower()

    if email not in users:
        raise ValueError("User not found")

    users[email]["password_hash"] = hash_password(new_password)
    users[email]["must_change_password"] = False
    save_users(users)

    logger.info(f"Password changed for user: {email}")


# =============================================================================
# 2FA - TOTP (Google Authenticator)
# =============================================================================

def setup_totp(email: str) -> Dict[str, str]:
    """Generate TOTP secret and QR code for user."""
    users = load_users()
    email = email.lower()

    if email not in users:
        raise ValueError("User not found")

    # Generate secret
    secret = pyotp.random_base32()
    users[email]["totp_secret"] = secret
    save_users(users)

    # Generate provisioning URI
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=email,
        issuer_name="CaseHub"
    )

    # Generate QR code as base64
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    logger.info(f"TOTP setup initiated for: {email}")

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_base64}",
        "uri": uri
    }


def verify_totp(email: str, code: str) -> bool:
    """Verify TOTP code."""
    user = get_user_by_email(email)
    if not user or not user.get("totp_secret"):
        return False

    totp = pyotp.TOTP(user["totp_secret"])
    return totp.verify(code, valid_window=1)


# =============================================================================
# 2FA - EMAIL OTP
# =============================================================================

def load_otps() -> Dict[str, Any]:
    """Load email OTPs from file."""
    if OTP_FILE.exists():
        with open(OTP_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_otps(otps: Dict[str, Any]):
    """Save email OTPs to file."""
    with open(OTP_FILE, 'w') as f:
        json.dump(otps, f, indent=2)


def generate_email_otp(email: str) -> str:
    """Generate and store email OTP."""
    otps = load_otps()

    # Generate 6-digit code
    code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])

    otps[email.lower()] = {
        "code": code,
        "expires_at": (datetime.now() + timedelta(minutes=5)).isoformat()
    }
    save_otps(otps)

    return code


def verify_email_otp(email: str, code: str) -> bool:
    """Verify email OTP."""
    otps = load_otps()
    email = email.lower()

    if email not in otps:
        return False

    otp_data = otps[email]
    expires_at = datetime.fromisoformat(otp_data["expires_at"])

    if datetime.now() > expires_at:
        # Clean up expired OTP
        del otps[email]
        save_otps(otps)
        return False

    if not secrets.compare_digest(otp_data["code"], code):
        return False

    # OTP used, delete it
    del otps[email]
    save_otps(otps)

    return True


def send_otp_email(email: str, otp: str) -> bool:
    """Send OTP via email."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, cannot send OTP email")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = email
        msg['Subject'] = 'CaseHub - Your Login Code'

        body = f"""
        Your one-time login code is: {otp}

        This code expires in 5 minutes.

        If you did not request this code, please ignore this email.

        - CaseHub Team
        """
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"OTP email sent to: {email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        return False


# =============================================================================
# JWT TOKENS
# =============================================================================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except JWTError:
        return None


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def load_sessions() -> Dict[str, Any]:
    """Load sessions from file."""
    if SESSIONS_FILE.exists():
        with open(SESSIONS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_sessions(sessions: Dict[str, Any]):
    """Save sessions to file."""
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)


def create_session(user_email: str, ip_address: str, user_agent: str) -> Dict[str, str]:
    """Create a new session for user."""
    sessions = load_sessions()

    session_id = secrets.token_urlsafe(32)

    # Create tokens
    token_data = {"sub": user_email, "session_id": session_id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    sessions[session_id] = {
        "user_email": user_email,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
        "is_active": True
    }
    save_sessions(sessions)

    # Update user's last login
    users = load_users()
    if user_email in users:
        users[user_email]["last_login"] = datetime.now().isoformat()
        save_users(users)

    logger.info(f"Session created for: {user_email} from {ip_address}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


def invalidate_session(session_id: str):
    """Invalidate a session."""
    sessions = load_sessions()
    if session_id in sessions:
        sessions[session_id]["is_active"] = False
        save_sessions(sessions)
        logger.info(f"Session invalidated: {session_id}")


def get_active_sessions(user_email: str) -> list:
    """Get all active sessions for a user."""
    sessions = load_sessions()
    return [
        {**s, "session_id": sid}
        for sid, s in sessions.items()
        if s["user_email"] == user_email and s["is_active"]
    ]


# =============================================================================
# LOGIN ATTEMPTS TRACKING
# =============================================================================

LOGIN_ATTEMPTS_FILE = DATA_DIR / "login_attempts.json"

def load_login_attempts() -> Dict[str, Any]:
    """Load login attempts from file."""
    if LOGIN_ATTEMPTS_FILE.exists():
        with open(LOGIN_ATTEMPTS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_login_attempts(attempts: Dict[str, Any]):
    """Save login attempts to file."""
    with open(LOGIN_ATTEMPTS_FILE, 'w') as f:
        json.dump(attempts, f, indent=2)


def record_login_attempt(email: str, ip_address: str, success: bool):
    """Record a login attempt."""
    attempts = load_login_attempts()

    key = f"{email}:{ip_address}"
    if key not in attempts:
        attempts[key] = []

    attempts[key].append({
        "timestamp": datetime.now().isoformat(),
        "success": success
    })

    # Keep only last 100 attempts per key
    attempts[key] = attempts[key][-100:]

    save_login_attempts(attempts)

    if not success:
        logger.warning(f"Failed login attempt for {email} from {ip_address}")


def check_login_allowed(email: str, ip_address: str) -> bool:
    """Check if login is allowed (not rate limited)."""
    attempts = load_login_attempts()
    key = f"{email}:{ip_address}"

    if key not in attempts:
        return True

    # Count failed attempts in last 15 minutes
    cutoff = datetime.now() - timedelta(minutes=15)
    recent_failures = sum(
        1 for a in attempts[key]
        if not a["success"] and datetime.fromisoformat(a["timestamp"]) > cutoff
    )

    return recent_failures < 5


# =============================================================================
# ADMIN FUNCTIONS
# =============================================================================

def get_pending_users() -> list:
    """Get all users pending approval."""
    users = load_users()
    return [
        {k: v for k, v in u.items() if k != "password_hash"}
        for u in users.values()
        if u["status"] == "pending_approval"
    ]


def get_all_users() -> list:
    """Get all users (admin only)."""
    users = load_users()
    return [
        {k: v for k, v in u.items() if k != "password_hash"}
        for u in users.values()
    ]


def suspend_user(email: str, suspended_by: str):
    """Suspend a user account."""
    users = load_users()
    email = email.lower()

    if email not in users:
        raise ValueError("User not found")

    if users[email]["is_super_admin"]:
        raise ValueError("Cannot suspend super admin")

    users[email]["status"] = "suspended"
    save_users(users)

    logger.warning(f"User suspended: {email} by {suspended_by}")


def reset_user_2fa(email: str, reset_by: str):
    """Reset user's 2FA."""
    users = load_users()
    email = email.lower()

    if email not in users:
        raise ValueError("User not found")

    users[email]["totp_secret"] = None
    save_users(users)

    logger.info(f"2FA reset for {email} by {reset_by}")


# =============================================================================
# INITIALIZE SUPER ADMIN
# =============================================================================

def initialize_super_admin():
    """Create super admin if not exists."""
    super_admin_email = os.getenv("ADMIN_EMAIL")
    if not super_admin_email:
        return

    users = load_users()
    if super_admin_email.lower() in users:
        return

    # Create super admin with generated password
    password = generate_strong_password(20)

    users[super_admin_email.lower()] = {
        "id": secrets.token_urlsafe(16),
        "email": super_admin_email.lower(),
        "username": "superadmin",
        "full_name": "Super Administrator",
        "password_hash": hash_password(password),
        "totp_secret": None,
        "preferred_2fa": "totp",
        "status": "active",
        "is_admin": True,
        "is_super_admin": True,
        "must_change_password": True,
        "created_at": datetime.now().isoformat(),
        "approved_at": datetime.now().isoformat(),
        "approved_by": "system",
        "last_login": None
    }

    save_users(users)

    logger.info(f"Super admin created: {super_admin_email}")
    logger.info("IMPORTANT: Super admin temporary password generated (shown on console only, NOT written to logs for security).")
    logger.info("Please change this password immediately after first login!")

    # Also print to console for first setup
    print(f"\n{'='*60}")
    print("SUPER ADMIN CREATED")
    print(f"Email: {super_admin_email}")
    print(f"Password: {password}")
    print("CHANGE THIS PASSWORD IMMEDIATELY!")
    print(f"{'='*60}\n")


# Initialize super admin on module load
initialize_super_admin()
