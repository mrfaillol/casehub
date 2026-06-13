"""
Meeting Watchdog - Calendar Orchestration
Checks availability, creates events, handles conflicts.
"""
import os

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Import existing calendar modules
try:
    from google_calendar import get_events, get_daniel_availability, DANIEL_CONFIG
    from create_meeting import create_attorney_meeting, get_calendar_service
except ImportError as e:
    logger.error(f"Cannot import calendar modules: {e}")

# Paralegal email mapping
PARALEGAL_EMAILS = {
    "Ana Clara": "anacleal.2025@gmail.com",
    "Juliana": "juliana.moreschi.2025@gmail.com",
    "Daniele": "danielle.fujii.2023@gmail.com",
}


def check_slot_available(target_dt: datetime, duration_minutes: int = 60) -> Dict:
    """
    Check if a specific time slot is available on the Google Calendar.

    Returns:
        {available: bool, conflict: str or None}
    """
    try:
        events = get_events(days_ahead=14)
        target_end = target_dt + timedelta(minutes=duration_minutes)

        for event in events:
            start = event.get("start", {}).get("dateTime")
            end = event.get("end", {}).get("dateTime")
            if start and end:
                event_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                event_end = datetime.fromisoformat(end.replace("Z", "+00:00"))

                # Make target timezone-aware if needed
                if target_dt.tzinfo is None:
                    from zoneinfo import ZoneInfo
                    target_aware = target_dt.replace(tzinfo=ZoneInfo("America/New_York"))
                    target_end_aware = target_end.replace(tzinfo=ZoneInfo("America/New_York"))
                else:
                    target_aware = target_dt
                    target_end_aware = target_end

                # Check overlap
                if target_aware < event_end and target_end_aware > event_start:
                    return {
                        "available": False,
                        "conflict": event.get("summary", "Busy"),
                    }

        return {"available": True, "conflict": None}

    except Exception as e:
        logger.error(f"Error checking slot availability: {e}")
        return {"available": False, "conflict": f"Error: {e}"}


def is_valid_daniel_meeting(dt_est: datetime) -> bool:
    """Check if datetime falls within Daniel's availability."""
    if dt_est.weekday() not in DANIEL_CONFIG["available_days"]:
        return False
    if dt_est.hour < DANIEL_CONFIG["available_hours"]["start"]:
        return False
    if dt_est.hour >= DANIEL_CONFIG["available_hours"]["end"]:
        return False
    return True


def create_meeting_event(
    client_name: str,
    client_info: dict,
    confirmed_dt_est: datetime,
    meeting_type: str = "attorney",
    duration_minutes: int = 60,
) -> Optional[Dict]:
    """
    Create a Google Calendar event for a confirmed meeting.

    Args:
        client_name: Client's full name
        client_info: CLIENT_MAPPING entry for this client
        confirmed_dt_est: Confirmed meeting time in EST
        meeting_type: "attorney" or "paralegal"
        duration_minutes: Meeting duration

    Returns:
        dict with success, event_id, meet_link, or None on failure
    """
    # Get paralegal email
    paralegal_name = client_info.get("paralegal", "")
    paralegal_email = PARALEGAL_EMAILS.get(paralegal_name, "")

    # Build attendee list (NEVER include client)
    attendees = [os.getenv("CENTER_EMAIL", "center@casehub.app"), os.getenv("ORG_EMAIL", "info@casehub.app")]
    if paralegal_email:
        attendees.append(paralegal_email)

    # Build description
    case_num = client_info.get("case", "")
    case_type = client_info.get("case_type", "")
    description = f"{'Attorney' if meeting_type == 'attorney' else 'Paralegal'} Meeting - {client_name}"
    if case_num:
        description += f"\nCase #: {case_num}"
    if case_type:
        description += f"\nCase Type: {case_type}"
    if paralegal_name:
        description += f"\nParalegal: {paralegal_name}"

    if meeting_type == "attorney":
        # Use existing function which sets the correct title format
        result = create_attorney_meeting(
            client_name=client_name,
            start_datetime=confirmed_dt_est,
            duration_minutes=duration_minutes,
            attendees=attendees,
            description=description,
        )
    else:
        # Paralegal meeting - create manually with different title
        result = _create_paralegal_meeting(
            client_name=client_name,
            start_datetime=confirmed_dt_est,
            duration_minutes=duration_minutes,
            attendees=attendees,
            description=description,
        )

    if result and result.get("success"):
        logger.info(
            f"Meeting created: {client_name} at {confirmed_dt_est.strftime('%Y-%m-%d %H:%M')} EST, "
            f"Meet: {result.get('meet_link')}"
        )
    else:
        logger.error(f"Failed to create meeting for {client_name}: {result}")

    return result


def _create_paralegal_meeting(
    client_name: str,
    start_datetime: datetime,
    duration_minutes: int,
    attendees: list,
    description: str,
) -> Dict:
    """Create a paralegal meeting (different title format)."""
    service = get_calendar_service()
    if not service:
        return {"success": False, "error": "Calendar service unavailable"}

    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    title = f"Paralegal Meeting- {client_name}"

    event = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": start_datetime.isoformat(),
            "timeZone": "America/New_York",
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": "America/New_York",
        },
        "attendees": [{"email": e} for e in attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": f"paralegal-{client_name.lower().replace(' ', '-')}-{start_datetime.strftime('%Y%m%d')}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 30},
                {"method": "popup", "minutes": 10},
            ],
        },
    }

    try:
        event_result = service.events().insert(
            calendarId="primary",
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all",
        ).execute()

        return {
            "success": True,
            "event_id": event_result.get("id"),
            "meet_link": event_result.get("hangoutLink", ""),
            "html_link": event_result.get("htmlLink"),
            "attendees": attendees,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
