"""
CaseHub - Standardized Error Responses
Provides consistent error formatting across all API endpoints.
"""
from fastapi.responses import JSONResponse
from fastapi import HTTPException

def error_response(code: str, message: str, status_code: int = 400, detail: dict = None) -> JSONResponse:
    """Return a standardized JSON error response."""
    body = {"error": code, "message": message}
    if detail:
        body["detail"] = detail
    return JSONResponse(content=body, status_code=status_code)

# Common error responses
def not_found(resource: str = "Resource") -> JSONResponse:
    return error_response("NOT_FOUND", f"{resource} not found", 404)

def forbidden(message: str = "Access denied") -> JSONResponse:
    return error_response("FORBIDDEN", message, 403)

def bad_request(message: str = "Invalid request") -> JSONResponse:
    return error_response("BAD_REQUEST", message, 400)

def server_error(message: str = "Internal server error") -> JSONResponse:
    return error_response("INTERNAL_ERROR", message, 500)

def plan_limit(resource: str, current: int, limit: int) -> JSONResponse:
    return error_response(
        "PLAN_LIMIT_REACHED",
        f"{resource} limit reached ({current}/{limit}). Upgrade your plan.",
        403,
        {"resource": resource, "current": current, "limit": limit}
    )
