"""
Meeting Watchdog - Email Scanner
Connects to IMAP, fetches new emails, pre-filters for meeting confirmations.
"""

import imaplib
import email as email_lib
from email.header import decode_header
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GMAIL_EMAIL = os.getenv("GMAIL_CENTER_EMAIL", "info@casehub.app")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_CENTER_APP_PASSWORD", "")

# Meeting-related keywords for pre-filtering
MEETING_KEYWORDS_EN = [
    "confirm", "confirmed", "works for me", "that works", "sounds good",
    "i can make it", "i'll be there", "let's go with", "let's do",
    "yes", "perfect", "great", "available", "agree",
    "meeting", "schedule", "appointment",
    "wednesday", "thursday", "11 am", "12 pm", "1 pm", "2 pm",
    "11:00", "12:00", "1:00", "2:00",
]

MEETING_KEYWORDS_PT = [
    "confirma", "confirmado", "confirmamos", "funciona", "pode ser",
    "tudo certo", "combinado", "perfeito", "ok", "sim",
    "reuniao", "reunião", "agendar", "horario", "horário",
    "quarta", "quinta", "disponibilidade",
]

# Keywords that indicate a meeting was PROPOSED in an outbound email
PROPOSAL_KEYWORDS = [
    "disponibilidade", "availability", "meeting with attorney",
    "meeting with the attorney", "reuniao com o advogado",
    "reunião com o advogado", "temos disponibilidade",
    "we have availability", "schedule a meeting",
    "horario", "horário", "time slot",
    "11 am", "12 pm", "1 pm", "2 pm",
    "google meet", "link de acesso",
]


def decode_mime_header(header: str) -> str:
    """Decode MIME-encoded email header."""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def extract_email_address(from_header: str) -> str:
    """Extract email address from From header."""
    if not from_header:
        return ""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].strip().lower()
    return from_header.strip().lower()


def get_email_body(msg) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        break
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
        except Exception:
            pass
    return body[:3000]  # Limit to 3000 chars


def has_meeting_keywords(text: str) -> bool:
    """Check if text contains any meeting-related keywords."""
    text_lower = text.lower()
    all_keywords = MEETING_KEYWORDS_EN + MEETING_KEYWORDS_PT
    return any(kw in text_lower for kw in all_keywords)


def has_proposal_keywords(text: str) -> bool:
    """Check if text contains meeting proposal keywords (outbound email)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in PROPOSAL_KEYWORDS)


def fetch_parent_message(mail: imaplib.IMAP4_SSL, msg) -> Optional[Dict]:
    """
    Fetch the parent message in a thread using In-Reply-To/References.
    Returns dict with body, subject, from, is_outbound.
    """
    in_reply_to = msg.get("In-Reply-To", "").strip()
    references = msg.get("References", "").strip()

    if not in_reply_to and not references:
        return None

    # Get the parent message ID
    parent_id = in_reply_to if in_reply_to else references.split()[-1]
    parent_id = parent_id.strip("<>")

    try:
        # Search in all mail for the parent message
        mail.select('"[Gmail]/All Mail"', readonly=True)
        _, data = mail.search(None, f'HEADER Message-ID "<{parent_id}>"')

        if not data[0]:
            # Try with original format
            _, data = mail.search(None, f'HEADER Message-ID "{parent_id}"')

        if data[0]:
            msg_ids = data[0].split()
            _, msg_data = mail.fetch(msg_ids[0], "(RFC822)")
            parent_msg = email_lib.message_from_bytes(msg_data[0][1])

            parent_from = extract_email_address(parent_msg.get("From", ""))
            parent_body = get_email_body(parent_msg)
            parent_subject = decode_mime_header(parent_msg.get("Subject", ""))

            is_outbound = parent_from in [
                os.getenv("ORG_EMAIL", "info@casehub.app"), os.getenv("CENTER_EMAIL", "center@casehub.app")
            ]

            return {
                "body": parent_body,
                "subject": parent_subject,
                "from": parent_from,
                "is_outbound": is_outbound,
                "message_id": parent_msg.get("Message-ID", ""),
            }

        # Switch back to inbox
        mail.select("INBOX", readonly=True)

    except Exception as e:
        logger.warning(f"Error fetching parent message: {e}")

    return None


def scan_inbox(client_mapping: dict, processed_ids: list, hours_back: int = 48) -> List[Dict]:
    """
    Scan Gmail inbox for potential meeting confirmation emails.

    Args:
        client_mapping: CLIENT_MAPPING dict from email_processor
        processed_ids: list of already-processed Message-IDs
        hours_back: how far back to search

    Returns:
        List of candidate emails with context, ready for LLM analysis.
    """
    candidates = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        mail.select("INBOX", readonly=True)

        # Search for recent emails
        date_str = (datetime.now() - timedelta(hours=hours_back)).strftime("%d-%b-%Y")
        _, messages = mail.search(None, f'SINCE "{date_str}"')

        if not messages[0]:
            mail.logout()
            return []

        msg_ids = messages[0].split()
        logger.info(f"Scanning {len(msg_ids)} emails from last {hours_back}h")

        for msg_id in msg_ids:
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                msg = email_lib.message_from_bytes(msg_data[0][1])

                message_id = msg.get("Message-ID", "")

                # Skip if already processed
                if message_id in processed_ids:
                    continue

                # Get sender
                from_header = msg.get("From", "")
                sender_email = extract_email_address(from_header)

                # Skip outbound emails
                if sender_email in [os.getenv("ORG_EMAIL", "info@casehub.app"), os.getenv("CENTER_EMAIL", "center@casehub.app")]:
                    continue

                # Skip if sender not in client mapping
                client_info = client_mapping.get(sender_email)
                if not client_info:
                    continue

                # Get email content
                subject = decode_mime_header(msg.get("Subject", ""))
                body = get_email_body(msg)
                date_header = msg.get("Date", "")
                full_text = f"{subject} {body}"

                # Pre-filter: check for meeting keywords
                if not has_meeting_keywords(full_text):
                    continue

                # Get thread context (parent message)
                thread_context = fetch_parent_message(mail, msg)

                # If we have an outbound parent with proposal keywords, this is high-signal
                is_reply_to_proposal = False
                if thread_context and thread_context.get("is_outbound"):
                    parent_text = f"{thread_context.get('subject', '')} {thread_context.get('body', '')}"
                    is_reply_to_proposal = has_proposal_keywords(parent_text)

                # Must be either reply-to-proposal OR have strong meeting keywords
                strong_keywords = ["confirm", "confirmed", "confirmado", "works for me",
                                   "that works", "combinado", "tudo certo"]
                has_strong = any(kw in full_text.lower() for kw in strong_keywords)

                if not is_reply_to_proposal and not has_strong:
                    continue

                # Select back to inbox for next iteration
                mail.select("INBOX", readonly=True)

                candidates.append({
                    "message_id": message_id,
                    "sender_email": sender_email,
                    "sender_name": client_info.get("name", sender_email),
                    "subject": subject,
                    "body": body,
                    "date": date_header,
                    "client_info": client_info,
                    "thread_context": thread_context,
                    "is_reply_to_proposal": is_reply_to_proposal,
                    "in_reply_to": msg.get("In-Reply-To", ""),
                    "references": msg.get("References", ""),
                })

                logger.info(f"Candidate found: {client_info.get('name')} - {subject[:50]}")

            except Exception as e:
                logger.warning(f"Error processing email {msg_id}: {e}")
                # Ensure we're back in inbox
                try:
                    mail.select("INBOX", readonly=True)
                except Exception:
                    pass
                continue

        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error: {e}")
    except Exception as e:
        logger.error(f"Scanner error: {e}")

    logger.info(f"Found {len(candidates)} meeting confirmation candidates")
    return candidates
