"""
Meeting Watchdog - Timezone Engine
Converts between timezones and formats display strings for client communications.
Never exposes BRT to non-Brazil clients.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Map abbreviations used in CLIENT_MAPPING to IANA timezone names
TIMEZONE_MAP = {
    "ET": "America/New_York",
    "CT": "America/Chicago",
    "PT": "America/Los_Angeles",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "GMT": "Europe/London",
    "BRT": "America/Sao_Paulo",
    "IST": "Asia/Kolkata",
    "ICT": "Asia/Bangkok",
    "KST": "Asia/Seoul",
    "JST": "Asia/Tokyo",
    "CST": "America/Chicago",
    "PST": "America/Los_Angeles",
    "EST": "America/New_York",
}

# Display abbreviations (what appears in emails)
DISPLAY_ABBREV = {
    "America/New_York": "ET",
    "America/Chicago": "CT",
    "America/Los_Angeles": "PT",
    "America/Denver": "MT",
    "Europe/London": "GMT",
    "America/Sao_Paulo": "BRT",
    "Asia/Kolkata": "IST",
    "Asia/Bangkok": "ICT",
    "Asia/Seoul": "KST",
    "Asia/Tokyo": "JST",
}

WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_PT = ["segunda-feira", "terca-feira", "quarta-feira", "quinta-feira",
              "sexta-feira", "sabado", "domingo"]

MONTH_EN = ["", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"]
MONTH_PT = ["", "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def get_iana_tz(abbrev: str) -> str:
    """Convert timezone abbreviation to IANA name."""
    return TIMEZONE_MAP.get(abbrev.upper().strip(), abbrev)


def get_display_abbrev(iana_tz: str) -> str:
    """Get display abbreviation from IANA timezone name."""
    return DISPLAY_ABBREV.get(iana_tz, iana_tz.split("/")[-1])


def convert_datetime(dt: datetime, from_tz: str, to_tz: str) -> datetime:
    """
    Convert datetime from one timezone to another.
    Args:
        dt: datetime object (naive or aware)
        from_tz: source timezone abbreviation (e.g., "ET", "CT", "BRT")
        to_tz: target timezone abbreviation
    Returns:
        datetime in target timezone (aware)
    """
    from_zone = ZoneInfo(get_iana_tz(from_tz))
    to_zone = ZoneInfo(get_iana_tz(to_tz))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=from_zone)

    return dt.astimezone(to_zone)


def format_time(dt: datetime, language: str = "en") -> str:
    """Format time in 12h (EN) or 24h (PT) style."""
    if language == "pt":
        return dt.strftime("%H:%M")
    else:
        return dt.strftime("%I:%M %p").lstrip("0")


def format_date(dt: datetime, language: str = "en") -> str:
    """Format date for display."""
    if language == "pt":
        return f"{dt.day} de {MONTH_PT[dt.month]} de {dt.year}"
    else:
        return f"{MONTH_EN[dt.month]} {dt.day}, {dt.year}"


def format_weekday(dt: datetime, language: str = "en") -> str:
    """Get weekday name."""
    if language == "pt":
        return WEEKDAY_PT[dt.weekday()]
    else:
        return WEEKDAY_EN[dt.weekday()]


def format_for_client(dt_est: datetime, client_tz: str, language: str = "en") -> dict:
    """
    Convert an EST datetime to client's timezone and return all formatted strings.
    This is the main function used by the emailer.

    Args:
        dt_est: datetime in EST (America/New_York), naive or aware
        client_tz: client's timezone abbreviation from CLIENT_MAPPING
        language: "en" or "pt"

    Returns:
        dict with: datetime, weekday, date, time, timezone_abbrev, full_display
    """
    client_dt = convert_datetime(dt_est, "ET", client_tz)
    tz_abbrev = client_tz.upper()

    time_str = format_time(client_dt, language)
    date_str = format_date(client_dt, language)
    weekday_str = format_weekday(client_dt, language)

    if language == "pt":
        full_display = f"{weekday_str}, {date_str}, as {time_str} ({tz_abbrev})"
    else:
        full_display = f"{weekday_str}, {date_str}, at {time_str} {tz_abbrev}"

    return {
        "datetime": client_dt,
        "weekday": weekday_str,
        "date": date_str,
        "time": time_str,
        "timezone_abbrev": tz_abbrev,
        "full_display": full_display,
    }


def est_to_client_tz(hour_est: int, minute_est: int, client_tz: str) -> tuple:
    """
    Quick conversion of EST hour:minute to client timezone.
    Returns (hour, minute) in client timezone.
    Useful for comparing times.
    """
    from datetime import date
    today = date.today()
    dt = datetime(today.year, today.month, today.day, hour_est, minute_est)
    converted = convert_datetime(dt, "ET", client_tz)
    return (converted.hour, converted.minute)


def is_valid_daniel_slot(dt_est: datetime) -> bool:
    """Check if a datetime falls within Daniel's availability window."""
    if dt_est.weekday() not in [2, 3]:  # Wed, Thu
        return False
    if dt_est.hour < 11 or dt_est.hour >= 14:
        return False
    return True
