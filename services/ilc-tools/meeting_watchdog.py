#!/usr/bin/env python3
"""
Meeting Confirmation Watchdog - CaseHub
Monitors Gmail for client meeting confirmations and auto-schedules events.

Usage:
    python meeting_watchdog.py              # Run daemon (90s loop)
    python meeting_watchdog.py --dry-run    # Scan only, no actions
    python meeting_watchdog.py --once       # Run one scan cycle and exit
    python meeting_watchdog.py --status     # Show current state
"""

import sys
import os
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Ensure we can import local modules
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from email_processor import CLIENT_MAPPING
from meeting_watchdog_scanner import scan_inbox
from meeting_watchdog_llm import analyze_candidate
from meeting_watchdog_calendar import (
    check_slot_available, is_valid_daniel_meeting, create_meeting_event,
)
from meeting_watchdog_emailer import send_confirmation_email
from meeting_watchdog_maestro import (
    notify_meeting_confirmed, notify_review_needed,
    notify_conflict, notify_error,
)
from meeting_watchdog_timezone import format_for_client
from meeting_watchdog_state import (
    load_state, save_state, is_message_processed,
    mark_message_processed, is_duplicate_meeting,
    add_confirmed_meeting, add_pending_review,
    update_last_scan, log_action,
)

# Configuration
SCAN_INTERVAL = int(os.getenv("WATCHDOG_SCAN_INTERVAL", "90"))

# Logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "meeting_watchdog.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("watchdog")

# Graceful shutdown
_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info(f"Received signal {signum}, shutting down...")
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def process_candidate(candidate: dict, state: dict, dry_run: bool = False) -> str:
    """
    Process a single candidate email through the full pipeline.
    Returns: "confirmed", "review", "ignored", or "error"
    """
    client_name = candidate.get("sender_name", "Unknown")
    client_email = candidate.get("sender_email", "")
    client_info = candidate.get("client_info", {})
    message_id = candidate.get("message_id", "")

    logger.info(f"Processing: {client_name} - {candidate.get('subject', '')[:60]}")

    # Step 1: LLM Analysis
    analysis = analyze_candidate(candidate)
    if not analysis:
        logger.warning(f"LLM analysis failed for {client_name}")
        mark_message_processed(state, message_id)
        return "error"

    is_confirmation = analysis.get("is_meeting_confirmation", False)
    confidence = analysis.get("confidence", 0)
    action = analysis.get("action", "ignore")
    confirmed_dt_str = analysis.get("confirmed_datetime_est")
    meeting_type = analysis.get("meeting_type", "unknown")
    language = analysis.get("language_detected", client_info.get("language", "en"))

    logger.info(
        f"LLM result: confirmation={is_confirmation}, confidence={confidence:.2f}, "
        f"action={action}, type={meeting_type}"
    )

    # Mark as processed regardless of outcome
    mark_message_processed(state, message_id)

    if not is_confirmation or action == "ignore":
        return "ignored"

    # Handle alternative proposals
    if analysis.get("client_proposed_alternative"):
        alt_desc = analysis.get("alternative_description", "")
        logger.info(f"Client proposed alternative: {alt_desc}")
        if not dry_run:
            notify_review_needed(
                client_name=client_name,
                possible_time=alt_desc or "Alternative proposed",
                confidence=confidence,
                email_preview=candidate.get("body", "")[:300],
                meeting_type=meeting_type,
            )
            add_pending_review(state, {
                "client_email": client_email,
                "client_name": client_name,
                "possible_time": alt_desc,
                "confidence": confidence,
                "message_id": message_id,
                "email_preview": candidate.get("body", "")[:300],
                "meeting_type": meeting_type,
            })
        return "review"

    # MEDIUM confidence: notify for review
    if action == "review":
        time_display = confirmed_dt_str or "Unknown time"
        logger.info(f"Medium confidence ({confidence:.2f}) - flagging for review")
        if not dry_run:
            notify_review_needed(
                client_name=client_name,
                possible_time=time_display,
                confidence=confidence,
                email_preview=candidate.get("body", "")[:300],
                meeting_type=meeting_type,
            )
            add_pending_review(state, {
                "client_email": client_email,
                "client_name": client_name,
                "possible_time": time_display,
                "confidence": confidence,
                "message_id": message_id,
                "meeting_type": meeting_type,
            })
        return "review"

    # HIGH confidence: auto-confirm
    if not confirmed_dt_str:
        logger.warning(f"High confidence but no datetime extracted for {client_name}")
        if not dry_run:
            notify_review_needed(
                client_name=client_name,
                possible_time="Time not extracted",
                confidence=confidence,
                email_preview=candidate.get("body", "")[:300],
                meeting_type=meeting_type,
            )
        return "review"

    # Parse confirmed datetime
    try:
        confirmed_dt = datetime.fromisoformat(confirmed_dt_str)
    except ValueError:
        logger.warning(f"Invalid datetime format: {confirmed_dt_str}")
        return "error"

    # Deduplication check
    if is_duplicate_meeting(state, client_email, confirmed_dt.isoformat()):
        logger.info(f"Duplicate meeting detected for {client_name} at {confirmed_dt}")
        return "ignored"

    if dry_run:
        logger.info(
            f"[DRY RUN] Would auto-confirm: {client_name} at "
            f"{confirmed_dt.strftime('%Y-%m-%d %H:%M')} EST ({meeting_type})"
        )
        return "confirmed"

    # Step 2: Check availability (attorney meetings only)
    if meeting_type == "attorney":
        if not is_valid_daniel_meeting(confirmed_dt):
            logger.warning(f"Time outside Daniel's window: {confirmed_dt}")
            notify_review_needed(
                client_name=client_name,
                possible_time=confirmed_dt.strftime("%Y-%m-%d %H:%M EST"),
                confidence=confidence,
                email_preview=f"Time outside Daniel's availability (Wed/Thu 11AM-2PM EST). Client said: {candidate.get('body', '')[:200]}",
                meeting_type=meeting_type,
            )
            return "review"

    slot_check = check_slot_available(confirmed_dt)
    if not slot_check.get("available"):
        conflict = slot_check.get("conflict", "Unknown event")
        logger.warning(f"Calendar conflict: {conflict}")
        notify_conflict(
            client_name=client_name,
            requested_time=confirmed_dt.strftime("%Y-%m-%d %H:%M EST"),
            conflict_event=conflict,
        )
        return "review"

    # Step 3: Create calendar event
    event_result = create_meeting_event(
        client_name=client_info.get("name", client_name),
        client_info=client_info,
        confirmed_dt_est=confirmed_dt,
        meeting_type=meeting_type,
    )

    event_created = event_result and event_result.get("success")
    meet_link = event_result.get("meet_link", "") if event_created else ""

    if not event_created:
        logger.error(f"Calendar event creation failed: {event_result}")
        notify_error(f"Failed to create calendar event for {client_name}: {event_result}")
        add_confirmed_meeting(state, {
            "client_email": client_email,
            "client_name": client_name,
            "confirmed_datetime": confirmed_dt.isoformat(),
            "event_created": False,
            "confirmation_email_sent": False,
            "confidence": confidence,
            "meeting_type": meeting_type,
            "error": str(event_result),
        })
        return "error"

    # Step 4: Send confirmation email to client
    email_result = send_confirmation_email(
        client_email=client_email,
        client_info=client_info,
        confirmed_dt_est=confirmed_dt,
        meet_link=meet_link,
        meeting_type=meeting_type,
        original_subject=candidate.get("subject", ""),
        in_reply_to=candidate.get("message_id", ""),
        references=candidate.get("references", ""),
    )

    email_sent = email_result.get("success", False)

    # Step 5: Notify admin
    client_tz = client_info.get("timezone", "ET")
    display = format_for_client(confirmed_dt, client_tz, client_info.get("language", "en"))

    notify_meeting_confirmed(
        client_name=client_info.get("name", client_name),
        meeting_time_display=display["full_display"],
        meeting_type=meeting_type,
        meet_link=meet_link,
        paralegal=client_info.get("paralegal", "Unknown"),
        case_number=client_info.get("case", ""),
    )

    # Step 6: Record in state
    add_confirmed_meeting(state, {
        "client_email": client_email,
        "client_name": client_name,
        "confirmed_datetime": confirmed_dt.isoformat(),
        "event_created": True,
        "event_id": event_result.get("event_id"),
        "meet_link": meet_link,
        "confirmation_email_sent": email_sent,
        "admin_notified": True,
        "confidence": confidence,
        "meeting_type": meeting_type,
        "message_id": message_id,
    })

    log_action("meeting_auto_confirmed", {
        "client": client_name,
        "datetime_est": confirmed_dt.isoformat(),
        "meet_link": meet_link,
        "type": meeting_type,
        "confidence": confidence,
    })

    logger.info(
        f"AUTO-CONFIRMED: {client_name} at {confirmed_dt.strftime('%Y-%m-%d %H:%M')} EST | "
        f"Meet: {meet_link} | Email: {'sent' if email_sent else 'FAILED'}"
    )

    return "confirmed"


def run_scan_cycle(dry_run: bool = False):
    """Run one complete scan cycle."""
    state = load_state()

    # Scan inbox for candidates
    candidates = scan_inbox(
        client_mapping=CLIENT_MAPPING,
        processed_ids=state.get("processed_message_ids", []),
    )

    if not candidates:
        logger.debug("No meeting confirmation candidates found")
        update_last_scan(state)
        save_state(state)
        return

    logger.info(f"Processing {len(candidates)} candidate(s)")

    stats = {"confirmed": 0, "review": 0, "ignored": 0, "error": 0}

    for candidate in candidates:
        result = process_candidate(candidate, state, dry_run=dry_run)
        stats[result] = stats.get(result, 0) + 1

    update_last_scan(state)
    save_state(state)

    logger.info(
        f"Scan complete: {stats['confirmed']} confirmed, {stats['review']} review, "
        f"{stats['ignored']} ignored, {stats['error']} errors"
    )


def show_status():
    """Display current watchdog state."""
    state = load_state()

    print("\n" + "=" * 60)
    print("MEETING WATCHDOG - STATUS")
    print("=" * 60)

    print(f"\nLast scan: {state.get('last_scan', 'Never')}")
    print(f"Processed message IDs: {len(state.get('processed_message_ids', []))}")

    confirmed = state.get("confirmed_meetings", [])
    print(f"\nConfirmed meetings: {len(confirmed)}")
    for m in confirmed[-5:]:
        print(f"  - {m.get('client_name')}: {m.get('confirmed_datetime')} "
              f"({m.get('meeting_type')}) [confidence: {m.get('confidence', 0):.2f}]")

    pending = state.get("pending_review", [])
    print(f"\nPending review: {len(pending)}")
    for p in pending[-5:]:
        print(f"  - {p.get('client_name')}: {p.get('possible_time')} "
              f"[confidence: {p.get('confidence', 0):.2f}]")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Meeting Confirmation Watchdog")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan only, do not create events or send emails")
    parser.add_argument("--once", action="store_true",
                        help="Run one scan cycle and exit")
    parser.add_argument("--status", action="store_true",
                        help="Show current watchdog state")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info(f"Meeting Watchdog starting ({mode})")
    logger.info(f"Scan interval: {SCAN_INTERVAL}s | Clients tracked: {len(CLIENT_MAPPING)}")

    if args.once:
        run_scan_cycle(dry_run=args.dry_run)
        return

    # Daemon loop
    logger.info("Entering daemon loop...")
    while _running:
        try:
            run_scan_cycle(dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"Scan cycle error: {e}", exc_info=True)
            try:
                notify_error(f"Scan cycle error: {e}")
            except Exception:
                pass

        # Sleep in small increments for responsive shutdown
        for _ in range(SCAN_INTERVAL):
            if not _running:
                break
            time.sleep(1)

    logger.info("Meeting Watchdog stopped")


if __name__ == "__main__":
    main()
