"""Small request helpers shared by route modules."""

from fastapi import Request


def get_request_org_id(request: Request):
    """Return the tenant organization id when middleware populated it."""
    return getattr(request.state, "org_id", None)
