from datetime import datetime, timezone

from core.jinja_runtime import format_datetime_brt


def test_format_datetime_brt_converts_utc_to_brasilia_time():
    value = datetime(2026, 6, 19, 18, 32, tzinfo=timezone.utc)

    assert format_datetime_brt(value, "%d/%m/%Y · %H:%M") == "19/06/2026 · 15:32"


def test_format_datetime_brt_treats_naive_values_as_utc():
    value = datetime(2026, 6, 19, 18, 32)

    assert format_datetime_brt(value) == "19/06/2026 às 15:32"


def test_format_datetime_brt_fallback_for_missing_values():
    assert format_datetime_brt(None) == "-"
