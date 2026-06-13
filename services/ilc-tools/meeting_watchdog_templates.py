"""
Meeting Watchdog - Email Templates
Confirmation templates identical to manually-sent ones.
No AI attribution or automation markers.
"""


def get_confirmation_template_en(
    client_name: str,
    weekday: str,
    date: str,
    time: str,
    timezone: str,
    meet_link: str,
    duration: str = "60",
    meeting_type: str = "attorney",
) -> str:
    """English meeting confirmation email body."""
    who = "Attorney Daniel" if meeting_type == "attorney" else "your paralegal"

    return f"""Dear {client_name},

Your meeting with {who} is confirmed for {weekday}, {date}, at {time} {timezone}.

Here is the link to join:
{meet_link}

The meeting will last approximately {duration} minutes.

If you have any questions, please do not hesitate to reach out.

Respectfully,
CaseHub"""


def get_confirmation_template_pt(
    client_name: str,
    weekday: str,
    date: str,
    time: str,
    timezone: str,
    meet_link: str,
    duration: str = "60",
    meeting_type: str = "attorney",
) -> str:
    """Portuguese meeting confirmation email body."""
    who = "o Advogado Daniel" if meeting_type == "attorney" else "sua paralegal"

    return f"""Ola {client_name},

Sua reuniao com {who} esta confirmada para {weekday}, {date}, as {time} ({timezone}).

Segue o link de acesso:
{meet_link}

A reuniao tera duracao de aproximadamente {duration} minutos.

Caso surja qualquer duvida, nao hesite em nos contatar.

Atenciosamente,
CaseHub"""


def get_confirmation_body(
    client_name: str,
    weekday: str,
    date: str,
    time: str,
    timezone: str,
    meet_link: str,
    duration: str = "60",
    meeting_type: str = "attorney",
    language: str = "en",
) -> str:
    """Get the appropriate confirmation template based on language."""
    # Use first name only for greeting
    first_name = client_name.split()[0] if client_name else client_name

    if language == "pt":
        return get_confirmation_template_pt(
            first_name, weekday, date, time, timezone, meet_link, duration, meeting_type
        )
    else:
        return get_confirmation_template_en(
            first_name, weekday, date, time, timezone, meet_link, duration, meeting_type
        )
