#!/usr/bin/env python3
"""
Create Google Calendar meeting for attorney meetings
"""

import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Paths
BASE_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "google_calendar_token.pickle"


def get_calendar_service():
    """Get authenticated Google Calendar service."""
    if not TOKEN_FILE.exists():
        print("❌ Token não encontrado. Execute: python google_calendar.py --setup")
        return None

    with open(TOKEN_FILE, "rb") as token:
        creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)


def create_attorney_meeting(
    client_name: str,
    start_datetime: datetime,
    duration_minutes: int = 60,
    attendees: list = None,
    description: str = None
):
    """
    Create attorney meeting with Google Meet link.

    Args:
        client_name: Client name for the meeting title
        start_datetime: Meeting start time (datetime object)
        duration_minutes: Meeting duration (default 60)
        attendees: List of email addresses
        description: Meeting description/notes
    """
    service = get_calendar_service()
    if not service:
        return None

    # Meeting title format: "Meeting with Attorney- [Client Name]"
    title = f"Meeting with Attorney- {client_name}"

    # Calculate end time
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)

    # Default attendees
    if not attendees:
        attendees = []

    # Always include core participants
    core_attendees = [
        os.getenv("CENTER_EMAIL", "center@casehub.app"),
        os.getenv("ORG_EMAIL", "info@casehub.app")
    ]

    all_attendees = list(set(core_attendees + attendees))

    # Build event
    event = {
        "summary": title,
        "description": description or f"Attorney meeting with {client_name}",
        "start": {
            "dateTime": start_datetime.isoformat(),
            "timeZone": "America/New_York"  # EST
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": "America/New_York"
        },
        "attendees": [{"email": e} for e in all_attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": f"meeting-{client_name.lower().replace(' ', '-')}-{start_datetime.strftime('%Y%m%d')}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 30},
                {"method": "popup", "minutes": 10}
            ]
        }
    }

    try:
        # Create event with Google Meet
        event_result = service.events().insert(
            calendarId="primary",
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all"  # Send invites to all attendees
        ).execute()

        meet_link = event_result.get("hangoutLink", "")

        print(f"\n✅ EVENTO CRIADO COM SUCESSO!")
        print(f"{'='*60}")
        print(f"📅 Título: {event_result.get('summary')}")
        print(f"🕐 Início: {start_datetime.strftime('%d/%m/%Y %H:%M')} EST")
        print(f"🕑 Fim: {end_datetime.strftime('%d/%m/%Y %H:%M')} EST")
        print(f"👥 Participantes: {', '.join(all_attendees)}")
        print(f"🔗 Google Meet: {meet_link}")
        print(f"📎 Link do evento: {event_result.get('htmlLink')}")
        print(f"{'='*60}")

        return {
            "success": True,
            "event_id": event_result.get("id"),
            "meet_link": meet_link,
            "html_link": event_result.get("htmlLink"),
            "attendees": all_attendees
        }

    except Exception as e:
        print(f"❌ Erro ao criar evento: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Criar reunião para Nishant Sagar
    # Data: 05/02/2026 às 3:00 PM EST

    meeting_date = datetime(2026, 2, 5, 15, 0, 0)  # 3:00 PM EST

    # ⚠️ NUNCA incluir cliente nos participantes do Calendar!
    # Cliente recebe link do Meet por email separado
    attendees = [
        os.getenv("CENTER_EMAIL", "center@casehub.app"),
        os.getenv("ORG_EMAIL", "info@casehub.app"),
        "anacleal.2025@gmail.com",  # Paralegal responsável (Ana Clara)
        # ❌ NUNCA: sagarnishant1@gmail.com (cliente)
    ]

    description = """Attorney Meeting - Nishant Sagar

Case #: 63
Paralegal: Ana Clara

Introductory meeting confirmed by client via email."""

    print("\n" + "="*60)
    print("CRIANDO REUNIAO COM ATTORNEY - NISHANT SAGAR")
    print("="*60)

    result = create_attorney_meeting(
        client_name="Nishant Sagar",
        start_datetime=meeting_date,
        duration_minutes=60,
        attendees=attendees,
        description=description
    )

    if result and result.get("success"):
        print("\nConvites enviados automaticamente para todos os participantes!")
