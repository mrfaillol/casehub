"""
Test middleware/rate_limit.py - RateLimiter and path classification.

Covers:
  - RateLimiter.is_allowed(): allows under limit, blocks over limit
  - Window expiration: old timestamps are pruned
  - MAX_ENTRIES cap: prevents memory exhaustion
  - Cleanup timing: only runs every 30s
  - _classify_path(): correct categorization of request paths
  - _get_client_ip(): proxy header parsing
"""
import time
import pytest
from unittest.mock import MagicMock, patch

from middleware.rate_limit import RateLimiter, _classify_path, _get_client_ip


# ---------------------------------------------------------------------------
# RateLimiter - Basic allow/deny
# ---------------------------------------------------------------------------

class TestRateLimiterAllowDeny:
    """Test that requests are allowed or denied based on the limit."""

    def test_allows_first_request(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        allowed, remaining = rl.is_allowed("10.0.0.1")
        assert allowed is True
        assert remaining == 4

    def test_allows_requests_under_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = rl.is_allowed("10.0.0.1")
        # All 3 should have been allowed
        assert allowed is True

    def test_blocks_request_over_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            rl.is_allowed("10.0.0.1")
        allowed, remaining = rl.is_allowed("10.0.0.1")
        assert allowed is False
        assert remaining == 0

    def test_different_keys_are_independent(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        rl.is_allowed("ip_a")
        rl.is_allowed("ip_a")
        # ip_a is now at limit
        allowed_a, _ = rl.is_allowed("ip_a")
        assert allowed_a is False

        # ip_b should still be allowed
        allowed_b, _ = rl.is_allowed("ip_b")
        assert allowed_b is True

    def test_remaining_decreases(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        _, r1 = rl.is_allowed("10.0.0.1")
        _, r2 = rl.is_allowed("10.0.0.1")
        assert r2 < r1


# ---------------------------------------------------------------------------
# RateLimiter - Window expiration
# ---------------------------------------------------------------------------

class TestRateLimiterWindowExpiration:
    """Test that timestamps expire after the window and capacity is restored."""

    def test_expired_timestamps_are_pruned(self):
        rl = RateLimiter(max_requests=2, window_seconds=0.1)
        rl.is_allowed("10.0.0.1")
        rl.is_allowed("10.0.0.1")

        # Should be blocked now
        allowed, _ = rl.is_allowed("10.0.0.1")
        assert allowed is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be allowed again
        allowed, _ = rl.is_allowed("10.0.0.1")
        assert allowed is True

    def test_partial_expiration(self):
        """Some timestamps expire while newer ones remain."""
        rl = RateLimiter(max_requests=3, window_seconds=0.2)
        rl.is_allowed("10.0.0.1")  # t=0
        time.sleep(0.12)
        rl.is_allowed("10.0.0.1")  # t=0.12
        rl.is_allowed("10.0.0.1")  # t=0.12

        # Wait so first request expires but second/third don't
        time.sleep(0.12)

        # First request expired, so we have room for 1 more
        allowed, _ = rl.is_allowed("10.0.0.1")
        assert allowed is True


# ---------------------------------------------------------------------------
# RateLimiter - MAX_ENTRIES cap
# ---------------------------------------------------------------------------

class TestRateLimiterMaxEntries:
    """Test the hard cap on number of tracked IPs."""

    def test_max_entries_constant(self):
        assert RateLimiter.MAX_ENTRIES == 10_000

    def test_cleanup_enforces_max_entries(self):
        """After cleanup, excess entries beyond MAX_ENTRIES should be dropped."""
        rl = RateLimiter(max_requests=100, window_seconds=60)
        # Temporarily lower MAX_ENTRIES for testing
        original_max = RateLimiter.MAX_ENTRIES
        RateLimiter.MAX_ENTRIES = 5
        try:
            # Add more entries than MAX_ENTRIES
            for i in range(10):
                rl.is_allowed(f"ip_{i}")

            # Force cleanup by setting last_cleanup far in the past
            rl._last_cleanup = 0

            # Next call triggers cleanup
            rl.is_allowed("trigger_cleanup")
            assert len(rl._requests) <= 6  # MAX_ENTRIES (5) + 1 (trigger_cleanup)
        finally:
            RateLimiter.MAX_ENTRIES = original_max

    def test_cleanup_skipped_if_recent(self):
        """Cleanup should not run if called within 30 seconds."""
        rl = RateLimiter(max_requests=100, window_seconds=60)
        rl._last_cleanup = time.time()  # Just cleaned
        rl._requests = {"stale_ip": [time.time() - 1000]}  # Expired entry

        rl.is_allowed("new_ip")
        # stale_ip should still be present because cleanup was skipped
        assert "stale_ip" in rl._requests


# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------

class TestClassifyPath:
    """Test _classify_path categorizes URLs correctly."""

    def test_static_files_exempt(self):
        assert _classify_path("/static/css/main.css") is None

    def test_health_check_exempt(self):
        assert _classify_path("/health") is None
        assert _classify_path("/api/health") is None

    def test_favicon_exempt(self):
        assert _classify_path("/favicon.ico") is None

    def test_login_exempt(self):
        assert _classify_path("/login") is None
        assert _classify_path("/casehub/login") is None

    def test_upload_path_classified(self):
        assert _classify_path("/api/upload", method="POST") == "upload"
        assert _classify_path("/documents/upload", method="POST") == "upload"

    def test_documents_path_classified_as_api(self):
        assert _classify_path("/api/v1/documents", method="POST") == "api"

    def test_general_api_classified(self):
        assert _classify_path("/api/v1/clients") == "api"
        assert _classify_path("/dashboard") == "page"

    def test_general_page_classified(self):
        assert _classify_path("/cases/123") == "page"


# ---------------------------------------------------------------------------
# Client IP extraction
# ---------------------------------------------------------------------------

class TestGetClientIP:
    """Test _get_client_ip extracts IP correctly from request."""

    def test_direct_client_ip(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.1"
        assert _get_client_ip(request) == "192.168.1.1"

    def test_forwarded_for_header(self):
        request = MagicMock()
        request.headers = {"x-forwarded-for": "203.0.113.50, 70.41.3.18"}
        assert _get_client_ip(request) == "203.0.113.50"

    def test_single_forwarded_ip(self):
        request = MagicMock()
        request.headers = {"x-forwarded-for": "10.0.0.1"}
        assert _get_client_ip(request) == "10.0.0.1"

    def test_no_client_returns_unknown(self):
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert _get_client_ip(request) == "unknown"
