"""
Demo Guard Middleware — blocks destructive/external actions in DEMO_MODE.

When DEMO_MODE=true:
- Blocks signups, password resets, email sending, external API calls
- Blocks data export/download, admin panel, SSO, webhooks, bulk ops
- Blocks all DELETE requests
- Allows navigation, CRUD on demo data (reset daily via cron), calculators
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse

logger = logging.getLogger(__name__)

# Paths blocked entirely (any method)
BLOCKED_PATH_PREFIXES = [
    "/api/",
    "/superadmin",
    "/sso/",
    "/webhooks/",
    "/bulk/",
]

# Paths blocked with specific substrings
BLOCKED_PATH_CONTAINS = [
    "/export",
    "/download",
    "/settings/google",
    "/settings/stripe",
    "/settings/notion",
    "/settings/whatsapp",
    "/settings/twilio",
    "/settings/callhippo",
    "/settings/moskit",
    "/gdrive-sync",
    "/gdrive",
]

# POST-only blocks (signup, password reset, email sending)
BLOCKED_POST_PATHS = [
    "/signup",
    "/register",
    "/password-reset",
    "/forgot-password",
    "/send-email",
    "/send-whatsapp",
    "/send-sms",
    "/stripe/",
    "/payments/create",
    "/change-password",
]

DEMO_BLOCK_MESSAGE = "Modo demo — esta ação está desabilitada. Entre em contato para conhecer o CaseHub completo."
DEMO_BLOCK_MESSAGE_EN = "Demo mode — this action is disabled. Contact us to learn about the full CaseHub."


class DemoGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Block all DELETE requests
        if method == "DELETE":
            return _demo_response(request, path)

        # Block entire path prefixes
        for prefix in BLOCKED_PATH_PREFIXES:
            if path.startswith(prefix) or (hasattr(request.state, 'org_id') and False):
                # Check with PREFIX stripped too
                pass
            if prefix in path:
                return _demo_response(request, path)

        # Block paths containing specific substrings
        for substr in BLOCKED_PATH_CONTAINS:
            if substr in path:
                return _demo_response(request, path)

        # Block specific POST actions
        if method == "POST":
            for blocked in BLOCKED_POST_PATHS:
                if blocked in path:
                    return _demo_response(request, path)

        return await call_next(request)


def _demo_response(request: Request, path: str):
    """Return a 403 response appropriate for the request type."""
    logger.info("Demo guard blocked: %s %s from %s", request.method, path, request.client.host if request.client else "unknown")

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse(
            status_code=403,
            content={"detail": DEMO_BLOCK_MESSAGE, "demo_mode": True}
        )

    return HTMLResponse(
        status_code=403,
        content=f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Demo Mode</title>
<style>
body {{ font-family: 'Instrument Sans', system-ui, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #fafafa; color: #111; }}
.card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 12px; padding: 48px; text-align: center; max-width: 500px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }}
h1 {{ font-size: 1.5rem; margin: 0 0 12px 0; }}
p {{ color: #555; margin: 0 0 24px 0; line-height: 1.6; }}
a {{ display: inline-block; padding: 10px 24px; background: #111; color: #fff; border-radius: 6px; text-decoration: none; font-weight: 500; transition: opacity 0.2s; }}
a:hover {{ opacity: 0.8; }}
.back {{ background: transparent; color: #555; border: 1px solid #ddd; margin-left: 8px; }}
</style></head>
<body><div class="card">
<h1>Modo Demo</h1>
<p>{DEMO_BLOCK_MESSAGE}</p>
<a href="https://casehub.legal">Conhecer o CaseHub</a>
<a href="javascript:history.back()" class="back">Voltar</a>
</div></body></html>"""
    )
