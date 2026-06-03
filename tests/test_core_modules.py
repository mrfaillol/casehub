"""
Test CaseHub Core Modules (core/errors.py, core/constants.py, core/resilience.py).

Validates:
  - error_response returns correct JSON structure
  - not_found, forbidden, bad_request return correct status codes
  - plan_limit includes resource details
  - All constants are defined with expected types
  - CircuitBreaker state transitions work
  - retry_external decorator retries on failure
"""
import time
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# core/errors.py
# ---------------------------------------------------------------------------

class TestErrorResponse:
    """Test the error_response factory function."""

    def test_error_response_returns_json_response(self):
        """error_response must return a JSONResponse."""
        from core.errors import error_response
        from fastapi.responses import JSONResponse
        result = error_response("TEST_ERROR", "something went wrong", 400)
        assert isinstance(result, JSONResponse)

    def test_error_response_status_code(self):
        """error_response must set the correct status code."""
        from core.errors import error_response
        result = error_response("ERR", "msg", 422)
        assert result.status_code == 422

    def test_error_response_body_has_error_and_message(self):
        """Response body must contain 'error' and 'message' keys."""
        from core.errors import error_response
        result = error_response("TEST_CODE", "test message", 400)
        # JSONResponse body is bytes
        import json
        body = json.loads(result.body.decode())
        assert body["error"] == "TEST_CODE"
        assert body["message"] == "test message"

    def test_error_response_with_detail(self):
        """error_response with detail dict should include it in body."""
        from core.errors import error_response
        import json
        detail = {"field": "email", "reason": "invalid"}
        result = error_response("VALIDATION", "invalid input", 400, detail=detail)
        body = json.loads(result.body.decode())
        assert body["detail"] == detail

    def test_error_response_without_detail_omits_key(self):
        """error_response without detail should not include 'detail' key."""
        from core.errors import error_response
        import json
        result = error_response("ERR", "msg", 400)
        body = json.loads(result.body.decode())
        assert "detail" not in body


class TestNotFound:
    """Test the not_found helper."""

    def test_not_found_returns_404(self):
        """not_found must return status 404."""
        from core.errors import not_found
        result = not_found()
        assert result.status_code == 404

    def test_not_found_default_message(self):
        """not_found without args should use 'Resource' as default."""
        from core.errors import not_found
        import json
        body = json.loads(result.body.decode()) if (result := not_found()) else {}
        assert "Resource" in body["message"]

    def test_not_found_custom_resource(self):
        """not_found('Client') should include 'Client' in message."""
        from core.errors import not_found
        import json
        result = not_found("Client")
        body = json.loads(result.body.decode())
        assert "Client" in body["message"]


class TestForbidden:
    """Test the forbidden helper."""

    def test_forbidden_returns_403(self):
        """forbidden must return status 403."""
        from core.errors import forbidden
        result = forbidden()
        assert result.status_code == 403

    def test_forbidden_default_message(self):
        """forbidden without args should use 'Access denied'."""
        from core.errors import forbidden
        import json
        result = forbidden()
        body = json.loads(result.body.decode())
        assert "Access denied" in body["message"]


class TestBadRequest:
    """Test the bad_request helper."""

    def test_bad_request_returns_400(self):
        """bad_request must return status 400."""
        from core.errors import bad_request
        result = bad_request()
        assert result.status_code == 400

    def test_bad_request_custom_message(self):
        """bad_request with custom message should use it."""
        from core.errors import bad_request
        import json
        result = bad_request("Missing field: name")
        body = json.loads(result.body.decode())
        assert body["message"] == "Missing field: name"


class TestServerError:
    """Test the server_error helper."""

    def test_server_error_returns_500(self):
        """server_error must return status 500."""
        from core.errors import server_error
        result = server_error()
        assert result.status_code == 500


class TestPlanLimit:
    """Test the plan_limit helper."""

    def test_plan_limit_returns_403(self):
        """plan_limit must return status 403."""
        from core.errors import plan_limit
        result = plan_limit("users", 5, 5)
        assert result.status_code == 403

    def test_plan_limit_includes_resource_detail(self):
        """plan_limit response body must include resource, current, limit."""
        from core.errors import plan_limit
        import json
        result = plan_limit("clients", 100, 100)
        body = json.loads(result.body.decode())
        assert body["detail"]["resource"] == "clients"
        assert body["detail"]["current"] == 100
        assert body["detail"]["limit"] == 100

    def test_plan_limit_message_mentions_upgrade(self):
        """plan_limit message should mention upgrading."""
        from core.errors import plan_limit
        import json
        result = plan_limit("users", 5, 5)
        body = json.loads(result.body.decode())
        assert "upgrade" in body["message"].lower() or "Upgrade" in body["message"]


# ---------------------------------------------------------------------------
# core/constants.py
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify all constants are defined with expected types."""

    def test_http_timeout_short_is_int(self):
        from core.constants import HTTP_TIMEOUT_SHORT
        assert isinstance(HTTP_TIMEOUT_SHORT, int)
        assert HTTP_TIMEOUT_SHORT > 0

    def test_http_timeout_default_is_int(self):
        from core.constants import HTTP_TIMEOUT_DEFAULT, HTTP_TIMEOUT_SHORT
        assert isinstance(HTTP_TIMEOUT_DEFAULT, int)
        assert HTTP_TIMEOUT_DEFAULT > HTTP_TIMEOUT_SHORT

    def test_http_timeout_long_is_int(self):
        from core.constants import HTTP_TIMEOUT_DEFAULT, HTTP_TIMEOUT_LONG
        assert isinstance(HTTP_TIMEOUT_LONG, int)
        assert HTTP_TIMEOUT_LONG > HTTP_TIMEOUT_DEFAULT

    def test_max_upload_size_mb(self):
        from core.constants import MAX_UPLOAD_SIZE_MB
        assert isinstance(MAX_UPLOAD_SIZE_MB, int)
        assert MAX_UPLOAD_SIZE_MB > 0

    def test_allowed_extensions_is_set(self):
        from core.constants import ALLOWED_EXTENSIONS
        assert isinstance(ALLOWED_EXTENSIONS, set)
        assert ".pdf" in ALLOWED_EXTENSIONS
        assert ".docx" in ALLOWED_EXTENSIONS

    def test_default_page_size(self):
        from core.constants import DEFAULT_PAGE_SIZE
        assert isinstance(DEFAULT_PAGE_SIZE, int)
        assert DEFAULT_PAGE_SIZE > 0

    def test_max_page_size_gte_default(self):
        from core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
        assert MAX_PAGE_SIZE >= DEFAULT_PAGE_SIZE

    def test_max_bulk_items(self):
        from core.constants import MAX_BULK_ITEMS
        assert isinstance(MAX_BULK_ITEMS, int)
        assert MAX_BULK_ITEMS > 0

    def test_org_cache_ttl(self):
        from core.constants import ORG_CACHE_TTL
        assert isinstance(ORG_CACHE_TTL, int)
        assert ORG_CACHE_TTL > 0

    def test_max_search_length(self):
        from core.constants import MAX_SEARCH_LENGTH
        assert isinstance(MAX_SEARCH_LENGTH, int)
        assert MAX_SEARCH_LENGTH > 0

    def test_rate_limit_entries(self):
        from core.constants import MAX_RATE_LIMIT_ENTRIES
        assert isinstance(MAX_RATE_LIMIT_ENTRIES, int)
        assert MAX_RATE_LIMIT_ENTRIES >= 1000


# ---------------------------------------------------------------------------
# core/resilience.py - CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    """Test CircuitBreaker state transitions."""

    def test_initial_state_is_closed(self):
        """New circuit breaker starts in CLOSED state."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=3, reset_timeout=60)
        assert cb.state == CircuitBreaker.CLOSED

    def test_allows_request_when_closed(self):
        """CLOSED state should allow requests."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=3)
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self):
        """After failure_threshold failures, state should be OPEN."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=3, reset_timeout=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_blocks_request_when_open(self):
        """OPEN state should block requests."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=2, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

    def test_success_resets_to_closed(self):
        """record_success should reset state to CLOSED."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0

    def test_half_open_after_timeout(self):
        """After reset_timeout, OPEN should transition to HALF_OPEN."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=1, reset_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_reset_clears_everything(self):
        """reset() should return to clean CLOSED state."""
        from core.resilience import CircuitBreaker
        cb = CircuitBreaker("test-svc", failure_threshold=1, reset_timeout=60)
        cb.record_failure()
        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0
        assert cb._last_failure_time is None


class TestPreConfiguredBreakers:
    """Verify pre-configured circuit breakers exist."""

    def test_stripe_breaker_exists(self):
        from core.resilience import stripe_breaker
        assert stripe_breaker.service_name == "stripe"

    def test_notion_breaker_exists(self):
        from core.resilience import notion_breaker
        assert notion_breaker.service_name == "notion"

    def test_google_breaker_exists(self):
        from core.resilience import google_breaker
        assert google_breaker.service_name == "google"

    def test_moskit_breaker_exists(self):
        from core.resilience import moskit_breaker
        assert moskit_breaker.service_name == "moskit"


class TestRetryExternal:
    """Test the retry_external decorator."""

    def test_retry_external_is_callable(self):
        """retry_external must be importable and callable."""
        from core.resilience import retry_external
        assert callable(retry_external)

    def test_sync_function_succeeds_without_retry(self):
        """A function that succeeds on first call should not retry."""
        from core.resilience import retry_external

        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01)
        def always_succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = always_succeeds()
        assert result == "ok"
        assert call_count == 1

    def test_sync_function_retries_on_failure(self):
        """A function that fails then succeeds should retry."""
        from core.resilience import retry_external

        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01, max_delay=0.02)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary failure")
            return "ok"

        result = fails_twice()
        assert result == "ok"
        assert call_count == 3

    def test_sync_function_raises_after_max_retries(self):
        """A function that always fails should raise after max_retries."""
        from core.resilience import retry_external

        @retry_external(max_retries=2, base_delay=0.01, max_delay=0.02, exceptions=(ValueError,))
        def always_fails():
            raise ValueError("permanent failure")

        with pytest.raises(ValueError, match="permanent failure"):
            always_fails()
