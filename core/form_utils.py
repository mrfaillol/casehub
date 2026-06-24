from __future__ import annotations

"""Form utilities for handling empty string → None conversion from HTML forms."""

def form_int(value: str) -> int | None:
    """Convert form string to int, treating empty strings as None."""
    if not value or value.strip() == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def form_float(value: str) -> float | None:
    """Convert form string to float, treating empty strings as None."""
    if not value or value.strip() == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
