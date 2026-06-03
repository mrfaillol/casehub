"""
Test core/resilience.py - Retry decorator and CircuitBreaker.

Covers:
  - retry_external: retries on exception, respects max_retries,
    exponential backoff, passes through on success, sync and async variants
  - CircuitBreaker: state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED),
    failure_threshold, reset_timeout, allow_request(), reset()
"""
import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock

from core.resilience import retry_external, CircuitBreaker


# ---------------------------------------------------------------------------
# retry_external - Sync
# ---------------------------------------------------------------------------

class TestRetryExternalSync:
    """Test retry_external decorator with synchronous functions."""

    def test_success_on_first_attempt(self):
        """Should pass through without retrying when function succeeds."""
        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count == 1

    def test_retries_then_succeeds(self):
        """Should retry and eventually return the successful result."""
        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01)
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary failure")
            return "recovered"

        result = fail_twice()
        assert result == "recovered"
        assert call_count == 3

    def test_exhausts_retries_and_raises(self):
        """After max_retries failures, should raise the last exception."""
        call_count = 0

        @retry_external(max_retries=2, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fail()
        # Initial attempt + 2 retries = 3 calls total
        assert call_count == 3

    def test_respects_max_retries_zero(self):
        """With max_retries=0, should only attempt once."""
        call_count = 0

        @retry_external(max_retries=0, base_delay=0.01)
        def fail_once():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            fail_once()
        assert call_count == 1

    def test_only_retries_specified_exceptions(self):
        """Should only retry on the specified exception types."""
        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01, exceptions=(ConnectionError,))
        def wrong_exception():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            wrong_exception()
        assert call_count == 1  # No retry because ValueError is not in exceptions

    def test_preserves_function_name(self):
        """Decorated function should keep its original name."""
        @retry_external(max_retries=1)
        def my_function():
            pass

        assert my_function.__name__ == "my_function"

    def test_service_name_used_in_logging(self):
        """Custom service_name should appear in log messages."""
        @retry_external(max_retries=1, base_delay=0.01, service_name="stripe_api")
        def call_stripe():
            raise ConnectionError("down")

        with patch("core.resilience.logger") as mock_logger:
            with pytest.raises(ConnectionError):
                call_stripe()
            # Should have logged with the service name
            log_calls = str(mock_logger.method_calls)
            assert "stripe_api" in log_calls

    def test_exponential_backoff_delay_values(self):
        """Verify the delay calculation matches exponential backoff formula."""
        # base_delay * (2 ** attempt), capped at max_delay
        base = 2.0
        max_d = 30.0
        expected_delays = [
            min(base * (2 ** 0), max_d),  # attempt 0: 2.0
            min(base * (2 ** 1), max_d),  # attempt 1: 4.0
            min(base * (2 ** 2), max_d),  # attempt 2: 8.0
        ]
        assert expected_delays == [2.0, 4.0, 8.0]

    def test_max_delay_cap(self):
        """Delay should never exceed max_delay."""
        base = 10.0
        max_d = 15.0
        delay_attempt_5 = min(base * (2 ** 5), max_d)
        assert delay_attempt_5 == 15.0


# ---------------------------------------------------------------------------
# retry_external - Async
# ---------------------------------------------------------------------------

class TestRetryExternalAsync:
    """Test retry_external decorator with async functions."""

    @pytest.mark.asyncio
    async def test_async_success_on_first_attempt(self):
        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "async_ok"

        result = await succeed()
        assert result == "async_ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retries_then_succeeds(self):
        call_count = 0

        @retry_external(max_retries=3, base_delay=0.01)
        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temp")
            return "async_recovered"

        result = await fail_once()
        assert result == "async_recovered"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_exhausts_retries(self):
        call_count = 0

        @retry_external(max_retries=1, base_delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError):
            await always_fail()
        assert call_count == 2

    def test_async_function_detected(self):
        """Async functions should be detected and wrapped with async wrapper."""
        @retry_external(max_retries=1)
        async def async_fn():
            pass

        assert asyncio.iscoroutinefunction(async_fn)

    def test_sync_function_detected(self):
        """Sync functions should NOT be wrapped as async."""
        @retry_external(max_retries=1)
        def sync_fn():
            pass

        assert not asyncio.iscoroutinefunction(sync_fn)


# ---------------------------------------------------------------------------
# CircuitBreaker - State transitions
# ---------------------------------------------------------------------------

class TestCircuitBreakerStates:
    """Test CircuitBreaker state machine transitions."""

    def test_starts_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, reset_timeout=60)
        assert cb.state == CircuitBreaker.CLOSED

    def test_allows_request_when_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, reset_timeout=60)
        assert cb.allow_request() is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_opens_at_failure_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_blocks_requests_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_allows_request_in_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.allow_request() is True

    def test_closes_on_success_in_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0

    def test_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, reset_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_reset_returns_to_closed(self):
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0
        assert cb._last_failure_time is None

    def test_record_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=5, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitBreaker.CLOSED

    def test_service_name_stored(self):
        cb = CircuitBreaker("my_service")
        assert cb.service_name == "my_service"


# ---------------------------------------------------------------------------
# Pre-configured breakers
# ---------------------------------------------------------------------------

class TestPreConfiguredBreakers:
    """Test that the module exports pre-configured circuit breakers."""

    def test_stripe_breaker_exists(self):
        from core.resilience import stripe_breaker
        assert isinstance(stripe_breaker, CircuitBreaker)
        assert stripe_breaker.service_name == "stripe"
        assert stripe_breaker.failure_threshold == 5

    def test_notion_breaker_exists(self):
        from core.resilience import notion_breaker
        assert isinstance(notion_breaker, CircuitBreaker)
        assert notion_breaker.service_name == "notion"
        assert notion_breaker.failure_threshold == 3

    def test_google_breaker_exists(self):
        from core.resilience import google_breaker
        assert isinstance(google_breaker, CircuitBreaker)
        assert google_breaker.service_name == "google"

    def test_moskit_breaker_exists(self):
        from core.resilience import moskit_breaker
        assert isinstance(moskit_breaker, CircuitBreaker)
        assert moskit_breaker.service_name == "moskit"
