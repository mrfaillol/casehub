#!/usr/bin/env python3
"""
Batch Portal Provision Script
Creates portal_access records for all active clients without access,
then sends each client an email with their unique portal link.

Usage: python3 scripts/batch_portal_provision.py [--dry-run] [--no-email]
  --dry-run: Show what would be done without making changes
  --no-email: Create access records but don't send emails
"""
import os
import sys
import secrets
import smtplib
import time
import argparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Load .env from casehub directory
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip())

# Database config
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "casehub")
DB_USER = os.getenv("DB_USER", "casehub")
DB_PASS = os.getenv("DB_PASSWORD", os.getenv("PGPASSWORD", ""))

# Email config
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ORG_NAME = os.getenv("ORG_NAME", "CaseHub")
ORG_EMAIL = os.getenv("ORG_EMAIL", "")
FROM_EMAIL = f"{ORG_NAME} <{ORG_EMAIL}>"
CC_EMAIL = ORG_EMAIL

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "https://app.casehub.io/intake/portal")


def get_email_html(client_name: str, portal_link: str) -> str:
    """Generate the portal access email HTML."""
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #1a3d6e 0%, #2c5aa0 100%);
                    padding: 25px; border-radius: 10px 10px 0 0; text-align: center;">
            <h2 style="color: white; margin: 0;">Your Client Portal</h2>
            <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0 0;">{ORG_NAME}</p>
        </div>
        <div style="background: #f8f9fa; padding: 25px; border: 1px solid #e9ecef;">
            <p>Dear {client_name},</p>
            <p>Your personal client portal is ready. Use the link below to access your forms and upload documents:</p>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{portal_link}"
                   style="display: inline-block; background: linear-gradient(135deg, #2c5aa0, #1a3d6e);
                          color: white; padding: 14px 35px; text-decoration: none; border-radius: 25px;
                          font-weight: bold; font-size: 16px;">
                    Access My Portal
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">
                <strong>What you can do:</strong>
            </p>
            <ul style="color: #666; font-size: 14px;">
                <li>Fill out immigration forms and questionnaires</li>
                <li>Upload required documents (passport, certificates, etc.)</li>
                <li>Track the status of your submitted documents</li>
            </ul>
            <p style="color: #666; font-size: 14px;">
                This link is unique to you. Please do not share it with others.
                You can use it anytime &mdash; it does not expire.
            </p>
            <p style="color: #666; font-size: 14px;">
                If you have any questions, reply to this email or contact us at
                <a href="mailto:{ORG_EMAIL}">{ORG_EMAIL}</a>.
            </p>
            <p>Respectfully,<br><strong>{ORG_NAME}</strong></p>
        </div>
        <div style="background: #343a40; color: #adb5bd; padding: 15px; text-align: center;
                    border-radius: 0 0 10px 10px; font-size: 12px;">
            <p style="margin: 0;">&copy; 2026 {ORG_NAME}. All rights reserved.</p>
        </div>
    </div>
    """


def send_email(to_email: str, client_name: str, portal_link: str) -> bool:
    """Send portal access email to a client."""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Your Client Portal - {ORG_NAME}"
        msg['Cc'] = CC_EMAIL

        html_body = get_email_html(client_name, portal_link)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, [to_email, CC_EMAIL], msg.as_string())

        return True
    except Exception as e:
        print(f"  ERROR sending to {to_email}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Batch provision portal access")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be done")
    parser.add_argument('--no-email', action='store_true', help="Create access but skip emails")
    args = parser.parse_args()

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    print(f"=== Batch Portal Provision {'(DRY RUN)' if args.dry_run else ''} ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Connect to database
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Get active clients without portal access
    cur.execute("""
        SELECT c.id, c.first_name, c.last_name, c.email
        FROM clients c
        LEFT JOIN portal_access pa ON pa.client_id = c.id
        WHERE pa.id IS NULL
          AND c.email IS NOT NULL AND c.email <> ''
          AND c.status = 'active'
        ORDER BY c.id
    """)
    clients = cur.fetchall()

    print(f"Found {len(clients)} active clients without portal access.")
    print()

    created = 0
    emails_sent = 0
    errors = []

    for client in clients:
        client_name = f"{client['first_name']} {client['last_name']}".strip()
        token = secrets.token_urlsafe(32)
        portal_link = f"{PORTAL_BASE_URL}/{token}"

        print(f"[{client['id']:3d}] {client_name:<35s} {client['email']}")

        if args.dry_run:
            print(f"      -> Would create token and send email")
            created += 1
            emails_sent += 1
            continue

        # Insert portal_access record
        try:
            cur.execute("""
                INSERT INTO portal_access (client_id, access_token, created_by)
                VALUES (%s, %s, %s)
            """, (client['id'], token, 1))  # created_by=1 (admin user)
            created += 1
        except Exception as e:
            errors.append(f"Client {client['id']} DB insert: {e}")
            conn.rollback()
            print(f"      -> ERROR inserting: {e}")
            continue

        # Send email
        if not args.no_email:
            success = send_email(client['email'], client_name, portal_link)
            if success:
                cur.execute("""
                    UPDATE portal_access SET email_sent_at = NOW()
                    WHERE client_id = %s
                """, (client['id'],))
                emails_sent += 1
                print(f"      -> Token created, email sent")
            else:
                errors.append(f"Client {client['id']} email failed")
                print(f"      -> Token created, email FAILED")
            # Small delay between emails to avoid SMTP rate limiting
            time.sleep(1)
        else:
            print(f"      -> Token created (no email)")

    # Commit all changes
    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()

    print()
    print(f"=== Results ===")
    print(f"Created: {created} portal access records")
    print(f"Emails sent: {emails_sent}")
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
    print()


if __name__ == "__main__":
    main()
