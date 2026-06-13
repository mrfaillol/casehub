from datetime import datetime, timedelta, timezone

from routes.team_messages import _created_at_utc_iso


def test_team_chat_naive_created_at_is_serialized_as_utc_z():
    assert _created_at_utc_iso(datetime(2026, 6, 11, 22, 7, 0)) == "2026-06-11T22:07:00Z"


def test_team_chat_aware_created_at_is_normalized_to_utc_z():
    brt = timezone(timedelta(hours=-3))
    assert _created_at_utc_iso(datetime(2026, 6, 11, 19, 7, 0, tzinfo=brt)) == "2026-06-11T22:07:00Z"


def test_team_chat_string_created_at_is_serialized_as_utc_z():
    assert _created_at_utc_iso("2026-06-11 22:07:00") == "2026-06-11T22:07:00Z"
