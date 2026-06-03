"""
CaseHub - API Rate Limiting Middleware
In-memory rate limiter with per-IP tracking and automatic cleanup.
No Redis dependency.

Usage:
    from middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
"""
import time
import threading
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Thread-safe in-memory rate limiter.
    Tracks requests per IP within a rolling window.
    """

    MAX_ENTRIES = 10_000  # Hard cap to prevent memory exhaustion under attack

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def _cleanup(self):
        """Remove expired entries. Called every 30s to prevent memory growth."""
        now = time.time()
        if now - self._last_cleanup < 30:
            return
        self._last_cleanup = now
        cutoff = now - self.window_seconds
        expired_keys = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if not self._requests[key]:
                expired_keys.append(key)
        removed = len(expired_keys)
        for key in expired_keys:
            del self._requests[key]
        # Hard cap: if still too many entries, drop oldest
        if len(self._requests) > self.MAX_ENTRIES:
            excess = len(self._requests) - self.MAX_ENTRIES
            oldest_keys = sorted(self._requests, key=lambda k: min(self._requests[k]))[:excess]
            for key in oldest_keys:
                del self._requests[key]
            removed += excess
        if removed > 0:
            logger.debug("Rate limiter cleanup: removed %d entries, %d active", removed, len(self._requests))

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Check if a request is allowed.
        Returns (allowed: bool, remaining: int).
        """
        with self._lock:
            self._cleanup()
            now = time.time()
            cutoff = now - self.window_seconds

            if key not in self._requests:
                self._requests[key] = []

            # Remove expired timestamps for this key
            self._requests[key] = [t for t in self._requests[key] if t > cutoff]

            current_count = len(self._requests[key])
            remaining = max(0, self.max_requests - current_count)

            if current_count >= self.max_requests:
                return False, 0

            self._requests[key].append(now)
            return True, remaining - 1


# Pre-configured limiters for different endpoint categories
_page_limiter = RateLimiter(max_requests=300, window_seconds=60)
_api_limiter = RateLimiter(max_requests=60, window_seconds=60)
_upload_limiter = RateLimiter(max_requests=10, window_seconds=60)


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting proxy headers."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _classify_path(path: str, method: str = "GET") -> Optional[str]:
    """
    Classify a request path into a rate-limit category.
    Returns None for paths that should not be rate-limited.
    """
    # Static files and health checks are exempt
    if path.startswith("/static") or path in ("/health", "/api/health", "/favicon.ico"):
        return None

    # Login endpoints are handled by the existing LoginRateLimiter
    if path.endswith("/login"):
        return None

    # ALL page navigation is exempt from strict API limits
    # Only POST/API endpoints get rate-limited
    if method == "GET" and path.startswith("/casehub/"):
        return "page"

    # File upload endpoints
    if "/upload" in path and method == "POST":
        return "upload"

    # API/POST endpoints get stricter limits
    if path.startswith("/api/") or method == "POST":
        return "api"

    # Regular GET requests (page views)
    return "page"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that applies rate limits based on client IP and endpoint category.

    Limits:
      - Page views:  120 requests/minute per IP (navigation, GET)
      - API/POST:     60 requests/minute per IP
      - File upload:  10 requests/minute per IP
      - Login:        handled by existing LoginRateLimiter (5 attempts/5min)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        category = _classify_path(path, method)

        # No rate limiting for exempt paths
        if category is None:
            return await call_next(request)

        client_ip = _get_client_ip(request)

        # Choose the right limiter
        if category == "upload":
            limiter = _upload_limiter
        elif category == "api":
            limiter = _api_limiter
        else:
            limiter = _page_limiter

        allowed, remaining = limiter.is_allowed(f"{client_ip}:{category}")

        if not allowed:
            logger.warning(f"Rate limit exceeded: {client_ip} on {path} ({category})")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={
                    "Retry-After": str(limiter.window_seconds),
                    "X-RateLimit-Limit": str(limiter.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
