#!/usr/bin/env python3
"""
Import Emil's emails from Gmail All Mail to CaseHub database
Specific search to avoid Gmail quota limits
"""
import imaplib
import email
import base64
from email.header import decode_header
from datetime import datetime
import sys
import os

# Database connection
import psycopg2

# Configuration
GMAIL_EMAIL = os.getenv("ORG_EMAIL", "")
if not GMAIL_EMAIL:
    print("ERROR: ORG_EMAIL not set. Export it or create .env")
    sys.exit(1)
GMAIL_APP_PASSWORD = input("Enter Gmail app password: ")
EMIL_EMAIL = "dr.gaybaliyev@gmail.com"
EMIL_CLIENT_ID = 58

# Database config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "casehub"),
    "user": os.getenv("DB_USER", "casehub"),
    "password": os.getenv("DB_PASSWORD", os.getenv("PGPASSWORD", ""))
}

def decode_email_header(header):
    """Decode email header"""
    if not header:
        return ""
    decoded_parts = []
    for part, charset in decode_header(header):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    return ' '.join(decoded_parts)

def get_email_body(msg):
    """Extract email body"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    break
                except (UnicodeDecodeError, AttributeError):
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
        except (UnicodeDecodeError, AttributeError):
            body = str(msg.get_payload())

    return body[:5000]  # Limit body size

def import_emil_emails():
    """Import all emails from Emil"""

    print(f"Connecting to Gmail...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)

    # Select All Mail folder
    print(f"Selecting [Gmail]/All Mail folder...")
    status, data = mail.select('"[Gmail]/All Mail"')
    if status != "OK":
        print(f"Failed to select All Mail: {data}")
        return

    # Search for emails FROM Emil
    print(f"Searching for emails from {EMIL_EMAIL}...")
    status, messages = mail.search(None, f'FROM "{EMIL_EMAIL}"')

    if status != "OK":
        print(f"Search failed: {messages}")
        return

    email_ids = messages[0].split()
    total_emails = len(email_ids)
    print(f"Found {total_emails} emails from Emil")

    if total_emails == 0:
        print("No emails found!")
        return

    # Connect to database
    print(f"Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    imported = 0
    skipped = 0
    errors = 0

    for i, email_id in enumerate(email_ids, 1):
        try:
            print(f"Processing {i}/{total_emails}...", end='\r')

            # Fetch email
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                errors += 1
                continue

            # Parse email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Extract metadata
            subject = decode_email_header(msg.get("Subject", ""))
            sender = decode_email_header(msg.get("From", ""))
            to = decode_email_header(msg.get("To", ""))
            date_str = msg.get("Date", "")
            message_id = msg.get("Message-ID", "")

            # Parse date
            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except:
                received_at = datetime.now()

            # Get body
            body = get_email_body(msg)

            # Determine direction (simplified)
            direction = "inbound"  # Emil sending TO us

            # Check if already exists
            cursor.execute("""
                SELECT id FROM email_messages
                WHERE message_id = %s
            """, (message_id,))

            if cursor.fetchone():
                skipped += 1
                continue

            # Insert into database
            cursor.execute("""
                INSERT INTO email_messages (
                    account_id, message_id, subject, sender, recipients,
                    body_text, received_at, direction, is_read, client_id,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                1,  # account_id
                message_id,
                subject[:500],
                sender[:500],
                to[:500],
                body,
                received_at,
                direction,
                False,
                EMIL_CLIENT_ID,  # Link to Emil immediately
                datetime.now()
            ))

            imported += 1

        except Exception as e:
            print(f"\nError processing email {email_id}: {e}")
            errors += 1
            continue

    # Commit and close
    conn.commit()
    cursor.close()
    conn.close()
    mail.logout()

    print(f"\n\n✅ Import complete!")
    print(f"   Imported: {imported}")
    print(f"   Skipped (already exists): {skipped}")
    print(f"   Errors: {errors}")
    print(f"   Total: {total_emails}")

if __name__ == "__main__":
    import_emil_emails()
