#!/usr/bin/env python3
"""
Send Cerenade transition email to all active clients via BCC.
Maintains HTML formatting (bold, bullets, underline).

Usage: python3 scripts/send_cerenade_email.py [--dry-run]
"""
import os
import sys
import smtplib
import argparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip())

# Email config
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ORG_NAME = os.getenv("ORG_NAME", "CaseHub")
ORG_EMAIL = os.getenv("ORG_EMAIL", "")
FROM_EMAIL = f"{ORG_NAME} <{ORG_EMAIL}>"

# DB config
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "casehub")
DB_USER = os.getenv("DB_USER", "casehub")
DB_PASS = os.getenv("DB_PASSWORD", os.getenv("PGPASSWORD", ""))

SUBJECT = "Important Administrative Update \u2013 New Secure Client Platform"

HTML_BODY = """\
<html>
<head>
<style>
  body { font-family: Arial, sans-serif; font-size: 14px; color: #222; line-height: 1.6; }
  p { margin: 0 0 12px 0; }
  ul { margin: 8px 0 12px 20px; }
  li { margin-bottom: 6px; }
</style>
</head>
<body>
<p>Hello,</p>

<p>We are writing to formally inform you of an important administrative update regarding our document management system.</p>

<p>Our firm previously utilized the platform <em>Eimmigration</em> by Cerenade for case management and document intake. Due to significant operational and technical disruptions that materially affected our internal workflow and case preparation processes, the contractual relationship was unilaterally terminated. The matter is currently being addressed through appropriate legal channels.</p>

<p>Although the platform is widely known within the immigration field, recurring technical deficiencies were impacting our team&rsquo;s ability to efficiently prepare and manage filings. As a result of the contractual termination, we no longer maintain access to that specific platform environment.</p>

<p>We would like to clarify that, as a result of the termination of access to the former platform, certain client documents and data stored exclusively within that system are no longer accessible to our office.</p>

<p>Importantly, this situation does <strong>not</strong> involve a data breach, cyber intrusion, or unauthorized disclosure of information. There is no indication of any data leakage or external compromise. The issue relates solely to loss of platform access, not to a security failure.</p>

<p>All client confidentiality remains protected under the attorney&ndash;client privilege, a fundamental safeguard grounded in United States constitutional principles and governed by the ethical and professional standards of the State Bar of California. The integrity and security of your information continue to be our highest priority.</p>

<p><strong>Introduction of Our New Platform &ndash; CaseHub</strong></p>

<p>To ensure enhanced stability, security, and operational efficiency, our firm has developed and implemented an internal proprietary system called <strong>CaseHub</strong>, designed exclusively for our practice. CaseHub allows us to maintain direct administrative oversight of document management while providing a secure and centralized environment for case materials.</p>

<p>As the platform is in its final stages of optimization, we kindly request your understanding should any minor technical issues arise. If you experience any difficulties, please notify our team promptly so that our support staff may address them without delay.</p>

<p><u><strong>Please note that the temporary Google Drive submission process previously implemented is no longer necessary.</strong></u></p>

<p><strong>Important &ndash; Document Visibility in the New Portal</strong></p>

<p>Because the prior platform access was discontinued, documents were not automatically transferred into CaseHub. If you do not see a specific document in your new portal, this means it was not migrated automatically. In such cases, we kindly request that you either:</p>

<ul>
<li>Re-send the document to our official email address, or</li>
<li>Upload the document directly into your CaseHub portal.<br>This will ensure that your case file remains complete and properly organized.</li>
</ul>

<p><strong>Updated Methods for Document Submission</strong></p>

<p>To reiterate, we now provide two official methods for document submission:</p>

<p><strong>1. Submission via Email</strong></p>

<p>Documents sent to our official email address are automatically directed to your client profile within our secure internal system.</p>

<p><strong>2. Secure Client Portal &ndash; CaseHub</strong></p>

<p>You will receive a separate email containing your unique login credentials and secure access link to your personalized CaseHub portal.<br>
Through this portal, you will be able to:</p>

<ul>
<li>Upload required documents securely</li>
<li>Review pending items</li>
<li>Maintain centralized organization of your case materials</li>
</ul>

<p>This administrative transition does <strong>not</strong> affect your case status, legal strategy, deadlines, or representation in any manner. All legal services and case management remain fully active and uninterrupted.</p>

<p>You will receive your portal login information shortly.</p>

<p>Should you require any assistance, please do not hesitate to contact our team:</p>

<p>&#x1F4F1; WhatsApp: +1 (940) 618-3140 - <a href="https://wa.me/19406183140">wa.me/19406183140</a></p>

<p>&#x1F310; <a href="https://immigrant.law">https://immigrant.law</a></p>

<p>We sincerely appreciate your continued trust in our firm and remain fully committed to delivering legal services at the highest professional standard.</p>

<p>Yours faithfully,</p>

<p><strong>Immigrant Law Center</strong></p>
</body>
</html>
"""


def get_active_client_emails():
    """Get all active client emails from database."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("ERROR: psycopg2 not installed")
        sys.exit(1)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, first_name, last_name, email
        FROM clients
        WHERE status = 'active'
          AND email IS NOT NULL AND email <> ''
        ORDER BY id
    """)
    clients = cur.fetchall()
    cur.close()
    conn.close()
    return clients


def send_bcc_email(bcc_emails, dry_run=False):
    """Send email with all clients in BCC."""
    msg = MIMEMultipart('alternative')
    msg['From'] = FROM_EMAIL
    msg['To'] = "info@immigrant.law"
    msg['Subject'] = SUBJECT
    # BCC is NOT added to headers (that's what makes it blind)
    # but we include all emails in the sendmail recipients

    msg.attach(MIMEText(HTML_BODY, 'html', 'utf-8'))

    all_recipients = ["info@immigrant.law"] + bcc_emails

    if dry_run:
        print(f"[DRY RUN] Would send to {len(bcc_emails)} BCC recipients")
        print(f"[DRY RUN] Subject: {SUBJECT}")
        print(f"[DRY RUN] From: {FROM_EMAIL}")
        print(f"[DRY RUN] To: info@immigrant.law")
        print(f"[DRY RUN] BCC count: {len(bcc_emails)}")
        return True

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, all_recipients, msg.as_string())
        print(f"Email sent successfully to {len(bcc_emails)} BCC recipients")
        return True
    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send Cerenade transition email to all clients")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be done")
    args = parser.parse_args()

    print(f"=== Cerenade Transition Email {'(DRY RUN)' if args.dry_run else ''} ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    clients = get_active_client_emails()
    print(f"Found {len(clients)} active clients with email.")
    print()

    emails = []
    for c in clients:
        name = f"{c['first_name']} {c['last_name']}".strip()
        print(f"  [{c['id']:3d}] {name:<35s} {c['email']}")
        emails.append(c['email'])

    print()
    print(f"Total BCC recipients: {len(emails)}")
    print(f"Subject: {SUBJECT}")
    print()

    success = send_bcc_email(emails, dry_run=args.dry_run)

    if success:
        print("DONE.")
    else:
        print("FAILED.")


if __name__ == "__main__":
    main()
